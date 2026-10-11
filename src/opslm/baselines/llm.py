"""Model-agnostic LLM system: the model judges meaning, code compares numbers.

The model answers two questions (same concept? same scope?). The numeric comparison and the
final label come from ``opslm.labels``, exactly as for every other system, so a model can
never call two facts equivalent when their normalized values disagree. Provider details live
in ``opslm.baselines.backends``; this class works with any ``ChatBackend``.

Notes for evaluation integrity:
- The model is never silently swapped: no provider-side fallbacks are enabled. A refusal is
  recorded as an error for that case.
- Numeric values are hidden from the model by default (``show_values=False``): concept and
  scope judgments must not depend on the numbers (labeling guidelines, "Same concept").
- ``metric_id`` is hidden by default (``show_metric_id=False``). It is an upstream mapping that
  predicts the label (facts with different ids are mostly related-but-different), the rules
  baseline does not use it, and a model that leans on it would not transfer to real extractor
  output. Show it only to measure that effect.
- The model chooses the evidence spans it cites. Citing none is an error unless the answer is
  insufficient evidence.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from opslm.baselines.backends import ChatBackend
from opslm.baselines.prompts import (
    PROMPT_SHA256,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
    judgment_schema,
)
from opslm.labels import derive_label, infer_reasons, values_agree
from opslm.schema import (
    BusinessFact,
    ModelRunInfo,
    ReconciliationInput,
    ReconciliationOutput,
    Relationship,
)

# Optional USD per million tokens (input, output) for hosted models. Prices change and differ
# by platform, so these are a dated snapshot of Anthropic first-party list prices only; pass
# ``prices=`` for anything else. Self-hosted models have no per-token price (None), and their
# cost is compute time, which this harness does not attribute.
PRICING_SNAPSHOT = "2026-10-06"
MODEL_PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}

Verdict = Literal["yes", "no", "cannot_tell"]


class LLMError(RuntimeError):
    """The model call failed or returned something unusable for this case."""


class Judgment(BaseModel):
    rationale: str
    concept_same: Verdict
    scope_same: Verdict
    deciding_fields: list[Literal["metric", "basis", "definition", "entity", "period"]]
    evidence_refs: list[str] = []


def _tri(v: Verdict) -> bool | None:
    return {"yes": True, "no": False}.get(v)


def fact_view(fact: BusinessFact, doc_types: dict[str, str], *, show_values: bool,
              show_metric_id: bool = False) -> dict[str, Any]:
    """What the model sees of a fact. Fact ids, locations and extraction details are omitted;
    each evidence span keeps its id so the model can cite it."""
    view: dict[str, Any] = {"metric": fact.metric_label}
    if show_metric_id:
        view["metric_id"] = fact.metric_id
    if show_values:
        q = fact.quantity
        view["value"] = {"value": str(q.value), "unit": q.unit, "currency": q.currency,
                         "reported_scale": str(q.reported_scale), "as_printed": q.raw_text}
    view["entity"] = fact.entity.model_dump(mode="json") if fact.entity else None
    view["period"] = (fact.period.model_dump(mode="json", exclude_defaults=True)
                      if fact.period else None)
    view["definition"] = fact.stated_definition
    view["basis"] = {"accounting": fact.accounting_basis, "reporting": fact.reporting_status}
    view["evidence"] = [{"span_id": s.span_id, "document_type": doc_types.get(s.doc_id),
                         "text": s.text} for s in fact.evidence]
    return view


def build_user_message(case: ReconciliationInput, *, show_values: bool,
                       show_metric_id: bool = False) -> str:
    doc_types = {d.doc_id: d.doc_type for d in case.documents}
    view = {
        "fact_a": fact_view(case.fact_a, doc_types, show_values=show_values,
                            show_metric_id=show_metric_id),
        "fact_b": fact_view(case.fact_b, doc_types, show_values=show_values,
                            show_metric_id=show_metric_id),
    }
    if case.context:
        view["context"] = [{"span_id": s.span_id, "document_type": doc_types.get(s.doc_id),
                            "text": s.text} for s in case.context]
    return json.dumps(view, indent=2)


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = 0.0
    failed_calls: int = 0


class LLMPredictor:
    """LLM-backed system over any ``ChatBackend``."""

    def __init__(
        self,
        backend: ChatBackend,
        *,
        show_values: bool = False,
        show_metric_id: bool = False,
        max_tokens: int = 8000,
        prices: tuple[float, float] | None = None,
    ) -> None:
        self.backend = backend
        self.show_values = show_values
        self.show_metric_id = show_metric_id
        self.max_tokens = max_tokens
        self.prices = prices if prices is not None else MODEL_PRICES.get(backend.model)
        self.name = backend.label
        self.usage = Usage()

    def describe(self) -> dict[str, Any]:
        """Everything needed to reproduce the run, for the result artifact's ``config``."""
        return {
            **self.backend.describe(),
            "show_values": self.show_values,
            "show_metric_id": self.show_metric_id,
            "max_tokens": self.max_tokens,
            "prices_usd_per_mtok": list(self.prices) if self.prices else None,
            "pricing_snapshot": PRICING_SNAPSHOT,
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": PROMPT_SHA256,
            "calls": self.usage.calls,
            "failed_calls": self.usage.failed_calls,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "total_cost_usd": self.usage.cost_usd,
        }

    def _cost(self, input_tokens: int, output_tokens: int) -> float | None:
        if self.prices is None:
            return None
        return (input_tokens * self.prices[0] + output_tokens * self.prices[1]) / 1_000_000

    def _call(self, case: ReconciliationInput) -> tuple[Judgment, float | None, int, int]:
        c = self.backend.complete(
            SYSTEM_PROMPT,
            build_user_message(case, show_values=self.show_values,
                               show_metric_id=self.show_metric_id),
            judgment_schema(case.span_ids()),
            max_tokens=self.max_tokens,
        )
        cost = self._cost(c.input_tokens, c.output_tokens)
        self.usage.calls += 1
        self.usage.input_tokens += c.input_tokens
        self.usage.output_tokens += c.output_tokens
        self.usage.cost_usd = (
            None if cost is None or self.usage.cost_usd is None else self.usage.cost_usd + cost
        )

        if c.finish == "refused":
            raise LLMError(f"model refused ({c.detail})")
        if c.finish == "length":
            raise LLMError("response hit the token limit before finishing")
        if c.finish == "other":
            raise LLMError(f"unexpected stop: {c.detail}")
        if not c.text:
            raise LLMError("response contained no text")
        try:
            return Judgment.model_validate_json(c.text), cost, c.input_tokens, c.output_tokens
        except ValueError as e:
            raise LLMError(f"unparseable model output: {e}") from e

    def predict(self, case: ReconciliationInput) -> ReconciliationOutput:
        start = time.perf_counter()
        try:
            judgment, cost, in_tokens, out_tokens = self._call(case)
        except LLMError:
            self.usage.failed_calls += 1
            raise
        latency = time.perf_counter() - start

        a, b = case.fact_a, case.fact_b
        concept, scope = _tri(judgment.concept_same), _tri(judgment.scope_same)
        agree = values_agree(a.quantity, b.quantity)
        culprits = list(dict.fromkeys(judgment.deciding_fields))
        relationship = derive_label(concept, scope, agree)
        refs = list(dict.fromkeys(judgment.evidence_refs))
        if not refs and relationship != Relationship.INSUFFICIENT_EVIDENCE:
            self.usage.failed_calls += 1
            raise LLMError("the model cited no evidence spans for a decision that needs them")
        return ReconciliationOutput(
            case_id=case.case_id,
            relationship=relationship,
            reasons=infer_reasons(a, b, concept, scope, agree, culprits),
            explanation=_clip(judgment.rationale or "No rationale given."),
            evidence_refs=refs,  # chosen by the model; unknown ids are flagged by the harness
            concept_same=concept,
            scope_same=scope,
            values_agree=agree,
            run=ModelRunInfo(system="llm", model_name=self.backend.model,
                             latency_ms=latency * 1000, input_tokens=in_tokens,
                             output_tokens=out_tokens, cost_usd=cost),
        )


def _clip(text: str, limit: int = 1000) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def estimate_cost(
    pairs: list[ReconciliationInput], prices: tuple[float, float] | None, *,
    show_values: bool = False, show_metric_id: bool = False,
) -> dict[str, Any]:
    """Rough spend estimate before any call. Token counts are approximations.

    Input is estimated at ~3.5 characters per token. Output (including any reasoning tokens)
    is not knowable in advance, so a low and high per-pair assumption bracket it. With no
    price (self-hosted or unknown model) only token counts are returned.
    """
    in_tokens = sum(
        (len(SYSTEM_PROMPT) + len(build_user_message(p, show_values=show_values,
                                                     show_metric_id=show_metric_id))) / 3.5
        for p in pairs
    )
    out_per_pair = (400, 2500)
    cost_range = None
    if prices is not None:
        cost_range = tuple(
            round((in_tokens * prices[0] + out * len(pairs) * prices[1]) / 1_000_000, 4)
            for out in out_per_pair
        )
    return {
        "pairs": len(pairs),
        "input_tokens_approx": round(in_tokens),
        "output_tokens_assumed_per_pair": out_per_pair,
        "cost_usd_range": cost_range,
        "pricing_snapshot": PRICING_SNAPSHOT,
    }
