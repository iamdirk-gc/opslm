"""Claude-backed system: the model judges meaning, code compares numbers.

The model answers two questions (same concept? same scope?). The numeric comparison and the
final label come from ``opslm.labels``, exactly as for every other system, so a model can
never call two facts equivalent when their normalized values disagree.

Notes for evaluation integrity:
- The model is never silently swapped. Server-side refusal fallbacks are deliberately NOT
  enabled: a fallback would change which model produced a prediction mid-benchmark. A refusal
  is recorded as an error for that case instead.
- Numeric values are hidden from the model by default (``show_values=False``): concept and
  scope judgments must not depend on the numbers (labeling guidelines, "Same concept").
- No sampling parameters are sent (current Claude models reject them) and thinking is left
  at the model default. ``effort`` is set explicitly because defaults differ by model.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel

from opslm.baselines.prompts import (
    JUDGMENT_SCHEMA,
    PROMPT_SHA256,
    PROMPT_VERSION,
    SYSTEM_PROMPT,
)
from opslm.labels import derive_label, values_agree
from opslm.schema import BusinessFact, Evidence, FactPair, Prediction

# USD per million tokens (input, output). Snapshot of Anthropic list prices; verify before
# quoting costs externally. Output tokens include thinking tokens.
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
    _extra: dict[str, Any] = field(default_factory=dict)


class ClaudePredictor:
    """Frontier-LLM system. Requires ``pip install 'opslm[llm]'`` unless a client is injected."""

    def __init__(
        self,
        model: str = "claude-opus-5-5",
        *,
        effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium",
        show_values: bool = False,
        max_tokens: int = 8000,
        client: Any = None,
    ) -> None:
        if client is None:
            import anthropic  # deferred so the rest of opslm works without the SDK

            client = anthropic.Anthropic()
        self._client = client
        self.model = model
        self.effort = effort
        self.show_values = show_values
        self.max_tokens = max_tokens
        self.name = f"claude:{model}:{effort}"
        self.usage = Usage()

    def describe(self) -> dict[str, Any]:
        """Everything needed to reproduce the run, for the result artifact's ``config``."""
        return {
            "provider": "anthropic",
            "model": self.model,
            "effort": self.effort,
            "show_values": self.show_values,
            "max_tokens": self.max_tokens,
            "prompt_version": PROMPT_VERSION,
            "prompt_sha256": PROMPT_SHA256,
            "pricing_snapshot": PRICING_SNAPSHOT,
            "server_side_fallbacks": False,
            "calls": self.usage.calls,
            "failed_calls": self.usage.failed_calls,
            "input_tokens": self.usage.input_tokens,
            "output_tokens": self.usage.output_tokens,
            "total_cost_usd": self.usage.cost_usd,
        }

    def _cost(self, input_tokens: int, output_tokens: int) -> float | None:
        price = MODEL_PRICES.get(self.model)
        if price is None:
            return None
        return (input_tokens * price[0] + output_tokens * price[1]) / 1_000_000

    def _call(self, pair: FactPair) -> tuple[Judgment, float | None]:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": build_user_message(pair, show_values=self.show_values)}
            ],
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": JUDGMENT_SCHEMA},
            },
        )
        usage = response.usage
        cost = self._cost(usage.input_tokens, usage.output_tokens)
        self.usage.calls += 1
        self.usage.input_tokens += usage.input_tokens
        self.usage.output_tokens += usage.output_tokens
        self.usage.cost_usd = (
            None if cost is None or self.usage.cost_usd is None else self.usage.cost_usd + cost
        )

        if response.stop_reason == "refusal":
            category = getattr(getattr(response, "stop_details", None), "category", None)
            raise LLMError(f"model refused (category: {category})")
        if response.stop_reason == "max_tokens":
            raise LLMError("response hit max_tokens before finishing")
        text = next((b.text for b in response.content if b.type == "text"), None)
        if text is None:
            raise LLMError("response contained no text block")
        try:
            return Judgment.model_validate_json(text), cost
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


def estimate_cost(pairs: list[FactPair], model: str, *, show_values: bool = False) -> dict[str, Any]:
    """Rough spend estimate before any API call. Token counts are approximations.

    Input is estimated at ~3.5 characters per token. Output (thinking plus the answer) is not
    knowable in advance, so a low and high assumption bracket it.
    """
    price = MODEL_PRICES.get(model)
    if price is None:
        raise ValueError(f"no price on file for {model}; known: {sorted(MODEL_PRICES)}")
    in_tokens = sum(
        (len(SYSTEM_PROMPT) + len(build_user_message(p, show_values=show_values))) / 3.5
        for p in pairs
    )
    out_low, out_high = 400 * len(pairs), 2500 * len(pairs)
    cost = lambda out: (in_tokens * price[0] + out * price[1]) / 1_000_000
    return {
        "model": model,
        "pairs": len(pairs),
        "input_tokens_approx": round(in_tokens),
        "output_tokens_assumed": (out_low, out_high),
        "cost_usd_range": (round(cost(out_low), 4), round(cost(out_high), 4)),
        "pricing_snapshot": PRICING_SNAPSHOT,
    }
