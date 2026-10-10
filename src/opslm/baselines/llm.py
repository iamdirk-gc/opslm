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
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel

from opslm.baselines.backends import ChatBackend
from opslm.baselines.prompts import (
    JUDGMENT_SCHEMA,
    PROMPT_SHA256,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
)
from opslm.labels import derive_label, values_agree
from opslm.schema import BusinessFact, Evidence, FactPair, Prediction

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
    deciding_fields: list[Literal["metric", "qualifiers", "definition", "entity", "period"]]


def _tri(v: Verdict) -> bool | None:
    return {"yes": True, "no": False}.get(v)


def fact_view(fact: BusinessFact, *, show_values: bool) -> dict[str, Any]:
    """What the model sees of a fact. Identifiers and locations are omitted."""
    view: dict[str, Any] = {"metric": fact.metric}
    if show_values:
        view.update(value=str(fact.value) if fact.value is not None else None,
                    unit=fact.unit, scale=fact.scale.name.lower())
    view["entity"] = fact.entity
    if fact.period:
        view["period"] = {
            "label": fact.period.label,
            "type": fact.period.type.value,
            "start": fact.period.start.isoformat() if fact.period.start else None,
            "end": fact.period.end.isoformat() if fact.period.end else None,
        }
    else:
        view["period"] = None
    view["definition"] = fact.definition
    view["qualifiers"] = list(fact.qualifiers)
    view["source"] = {"document_type": fact.source.document_type, "excerpt": fact.source.excerpt}
    return view


def build_user_message(pair: FactPair, *, show_values: bool) -> str:
    return json.dumps(
        {
            "fact_a": fact_view(pair.fact_a, show_values=show_values),
            "fact_b": fact_view(pair.fact_b, show_values=show_values),
        },
        indent=2,
    )


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
        max_tokens: int = 8000,
        prices: tuple[float, float] | None = None,
    ) -> None:
        self.backend = backend
        self.show_values = show_values
        self.max_tokens = max_tokens
        self.prices = prices if prices is not None else MODEL_PRICES.get(backend.model)
        self.name = backend.label
        self.usage = Usage()

    def describe(self) -> dict[str, Any]:
        """Everything needed to reproduce the run, for the result artifact's ``config``."""
        return {
            **self.backend.describe(),
            "show_values": self.show_values,
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

    def _call(self, pair: FactPair) -> tuple[Judgment, float | None]:
        c = self.backend.complete(
            SYSTEM_PROMPT,
            build_user_message(pair, show_values=self.show_values),
            JUDGMENT_SCHEMA,
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
            return Judgment.model_validate_json(c.text), cost
        except ValueError as e:
            raise LLMError(f"unparseable model output: {e}") from e

    def predict(self, case_id: str, pair: FactPair) -> Prediction:
        start = time.perf_counter()
        try:
            judgment, cost = self._call(pair)
        except LLMError:
            self.usage.failed_calls += 1
            raise
        latency = time.perf_counter() - start

        a, b = pair.fact_a, pair.fact_b
        concept, scope = _tri(judgment.concept_same), _tri(judgment.scope_same)
        agree = values_agree(a, b)
        label = derive_label(concept, scope, agree)

        if concept is not True or scope is not True:
            fields = list(dict.fromkeys(judgment.deciding_fields))
        elif agree is False:
            fields = ["value", "scale"]
        elif agree is None:
            fields = ["value", "unit"]
        else:
            fields = []
        evidence = tuple(Evidence(fact_id=f.fact_id, field=n) for n in fields for f in (a, b))
        return Prediction(
            case_id=case_id,
            label=label,
            concept_same=concept,
            scope_same=scope,
            values_agree=agree,
            evidence=evidence,
            rationale=judgment.rationale,
            latency_s=latency,
            cost_usd=cost,
        )


def estimate_cost(
    pairs: list[FactPair], prices: tuple[float, float] | None, *, show_values: bool = False
) -> dict[str, Any]:
    """Rough spend estimate before any call. Token counts are approximations.

    Input is estimated at ~3.5 characters per token. Output (including any reasoning tokens)
    is not knowable in advance, so a low and high per-pair assumption bracket it. With no
    price (self-hosted or unknown model) only token counts are returned.
    """
    in_tokens = sum(
        (len(SYSTEM_PROMPT) + len(build_user_message(p, show_values=show_values))) / 3.5
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
