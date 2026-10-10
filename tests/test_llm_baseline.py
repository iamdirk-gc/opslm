import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

from opslm.baselines.llm import (
    ClaudePredictor,
    LLMError,
    build_user_message,
    estimate_cost,
)
from opslm.baselines.prompts import PROMPT_SHA256
from opslm.eval.harness import evaluate
from opslm.schema import (
    BusinessFact,
    FactPair,
    Period,
    PeriodType,
    Relation,
    Scale,
    SourceRef,
)


def fact(fid, metric="Revenue", value="42.5", unit="USD"):
    return BusinessFact(
        fact_id=fid,
        metric=metric,
        value=Decimal(value),
        unit=unit,
        scale=Scale.MILLIONS,
        entity="Acme Corp",
        period=Period(label="FY2025", type=PeriodType.FISCAL_YEAR),
        source=SourceRef(document_id="secret-doc-id", location="p.14"),
    )


def reply(concept="yes", scope="yes", fields=(), stop="end_turn", text=None, usage=(1000, 500)):
    body = text if text is not None else json.dumps(
        {"rationale": "r", "concept_same": concept, "scope_same": scope,
         "deciding_fields": list(fields)}
    )
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="text", text=body)],
        stop_reason=stop,
        stop_details=SimpleNamespace(category="cyber") if stop == "refusal" else None,
        usage=SimpleNamespace(input_tokens=usage[0], output_tokens=usage[1]),
    )


class FakeClient:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        return self.replies.pop(0)


def predictor(*replies, **kw):
    client = FakeClient(*replies)
    return ClaudePredictor(client=client, **kw), client


def pair(**kw):
    return FactPair(fact_a=fact("a"), fact_b=fact("b", **kw))


def test_request_shape_avoids_rejected_parameters():
    p, client = predictor(reply())
    p.predict("c1", pair())
    call = client.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["output_config"]["effort"] == "medium"
    assert call["output_config"]["format"]["type"] == "json_schema"
    for forbidden in ("temperature", "top_p", "top_k", "tool_choice", "betas", "fallbacks"):
        assert forbidden not in call
    assert "thinking" not in call  # left at the model default


def test_values_hidden_from_model_by_default():
    msg = build_user_message(pair(value="44.1"), show_values=False)
    assert "42.5" not in msg and "44.1" not in msg
    assert "secret-doc-id" not in msg and "p.14" not in msg  # ids and locations omitted
    shown = build_user_message(pair(value="44.1"), show_values=True)
    assert "42.5" in shown and "44.1" in shown


def test_equivalent_when_model_says_yes_and_values_agree():
    p, _ = predictor(reply())
    pred = p.predict("c1", pair())
    assert pred.label is Relation.EQUIVALENT and not pred.evidence


def test_code_not_model_decides_value_conflicts():
    p, _ = predictor(reply())
    pred = p.predict("c1", pair(value="44.1"))
    assert pred.label is Relation.CONFLICTING and pred.values_agree is False
    assert {e.field for e in pred.evidence} == {"value", "scale"}


def test_concept_no_is_related_and_cites_model_fields():
    p, _ = predictor(reply(concept="no", fields=["metric"]))
    pred = p.predict("c1", pair(value="39.2"))
    assert pred.label is Relation.RELATED_BUT_DIFFERENT
    assert {e.field for e in pred.evidence} == {"metric"}


def test_cannot_tell_gives_insufficient_evidence():
    p, _ = predictor(reply(scope="cannot_tell", fields=["entity"]))
    pred = p.predict("c1", pair())
    assert pred.label is Relation.INSUFFICIENT_EVIDENCE and pred.scope_same is None


def test_currency_mismatch_is_insufficient():
    p, _ = predictor(reply())
    assert p.predict("c1", pair(unit="EUR")).label is Relation.INSUFFICIENT_EVIDENCE


def test_cost_and_usage_accounting():
    p, _ = predictor(reply(usage=(10_000, 2_000)))
    pred = p.predict("c1", pair())
    assert pred.cost_usd == pytest.approx((10_000 * 4 + 2_000 * 20) / 1e6)
    cfg = p.describe()
    assert cfg["input_tokens"] == 10_000 and cfg["prompt_sha256"] == PROMPT_SHA256
    assert cfg["server_side_fallbacks"] is False


def test_unknown_model_has_no_cost():
    p, _ = predictor(reply(), model="some-future-model")
    assert p.predict("c1", pair()).cost_usd is None
    assert p.describe()["total_cost_usd"] is None


@pytest.mark.parametrize(
    "bad,match",
    [
        (reply(stop="refusal"), "refused"),
        (reply(stop="max_tokens"), "max_tokens"),
        (reply(text="not json"), "unparseable"),
        (reply(concept="maybe"), "unparseable"),
    ],
)
def test_failures_raise_llm_error_and_count(bad, match):
    p, _ = predictor(bad)
    with pytest.raises(LLMError, match=match):
        p.predict("c1", pair())
    assert p.describe()["failed_calls"] == 1


def test_harness_records_llm_errors_without_crashing():
    from tests.test_eval import sample_cases

    cases = sample_cases()
    replies = [reply(stop="refusal")] + [reply() for _ in range(3)]
    run = evaluate(predictor(*replies)[0], cases, bootstrap_n=0)
    assert run.n_errors == 1 and run.records[0].prediction is None


def test_estimate_cost_brackets_spend():
    est = estimate_cost([pair()] * 200, "claude-opus-5-5")
    lo, hi = est["cost_usd_range"]
    assert 0 < lo < hi and est["pairs"] == 200
    with pytest.raises(ValueError, match="no price"):
        estimate_cost([pair()], "mystery-model")


def test_cli_requires_confirmation_before_paid_calls(tmp_path, capsys):
    from opslm.eval.__main__ import main

    with pytest.raises(SystemExit):
        main(["run", "--dataset", "data/examples/guideline_examples.jsonl", "--system", "claude"])
    out = capsys.readouterr()
    assert "estimate" in out.out and "--confirm-spend" in out.err


def test_cli_estimate_only_makes_no_calls(capsys):
    from opslm.eval.__main__ import main

    main(["run", "--dataset", "data/examples/guideline_examples.jsonl", "--system", "claude",
          "--estimate-only"])
    assert "estimate (9 pairs" in capsys.readouterr().out
