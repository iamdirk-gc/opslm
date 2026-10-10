import json
from decimal import Decimal

import pytest

from opslm.baselines.backends import Completion
from opslm.baselines.llm import LLMError, LLMPredictor, build_user_message, estimate_cost
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


def pair(**kw):
    return FactPair(fact_a=fact("a"), fact_b=fact("b", **kw))


def answer(concept="yes", scope="yes", fields=(), finish="stop", text=None, usage=(1000, 500)):
    body = text if text is not None else json.dumps(
        {"rationale": "r", "concept_same": concept, "scope_same": scope,
         "deciding_fields": list(fields)}
    )
    return Completion(body, usage[0], usage[1], finish, "cyber" if finish == "refused" else None)


class FakeBackend:
    model = "claude-opus-5-5"
    label = "fake:model"

    def __init__(self, *answers):
        self.answers = list(answers)
        self.calls = []

    def complete(self, system, user, schema, *, max_tokens):
        self.calls.append((system, user, schema, max_tokens))
        return self.answers.pop(0)

    def describe(self):
        return {"provider": "fake", "model": self.model}


def predictor(*answers, **kw):
    backend = FakeBackend(*answers)
    return LLMPredictor(backend, **kw), backend


def test_values_hidden_from_model_by_default():
    msg = build_user_message(pair(value="44.1"), show_values=False)
    assert "42.5" not in msg and "44.1" not in msg
    assert "secret-doc-id" not in msg and "p.14" not in msg  # ids and locations omitted
    shown = build_user_message(pair(value="44.1"), show_values=True)
    assert "42.5" in shown and "44.1" in shown


def test_backend_receives_prompt_schema_and_limit():
    p, backend = predictor(answer(), max_tokens=1234)
    p.predict("c1", pair())
    system, user, schema, limit = backend.calls[0]
    assert "concept_same" in system and "fact_a" in user
    assert schema["required"] and limit == 1234
    assert p.name == "fake:model"


def test_equivalent_when_model_says_yes_and_values_agree():
    p, _ = predictor(answer())
    pred = p.predict("c1", pair())
    assert pred.label is Relation.EQUIVALENT and not pred.evidence


def test_code_not_model_decides_value_conflicts():
    p, _ = predictor(answer())
    pred = p.predict("c1", pair(value="44.1"))
    assert pred.label is Relation.CONFLICTING and pred.values_agree is False
    assert {e.field for e in pred.evidence} == {"value", "scale"}


def test_concept_no_is_related_and_cites_model_fields():
    p, _ = predictor(answer(concept="no", fields=["metric"]))
    pred = p.predict("c1", pair(value="39.2"))
    assert pred.label is Relation.RELATED_BUT_DIFFERENT
    assert {e.field for e in pred.evidence} == {"metric"}


def test_cannot_tell_gives_insufficient_evidence():
    p, _ = predictor(answer(scope="cannot_tell", fields=["entity"]))
    pred = p.predict("c1", pair())
    assert pred.label is Relation.INSUFFICIENT_EVIDENCE and pred.scope_same is None


def test_currency_mismatch_is_insufficient():
    p, _ = predictor(answer())
    assert p.predict("c1", pair(unit="EUR")).label is Relation.INSUFFICIENT_EVIDENCE


def test_cost_and_usage_accounting():
    p, _ = predictor(answer(usage=(10_000, 2_000)))
    pred = p.predict("c1", pair())
    assert pred.cost_usd == pytest.approx((10_000 * 4 + 2_000 * 20) / 1e6)
    cfg = p.describe()
    assert cfg["input_tokens"] == 10_000 and cfg["prompt_sha256"] == PROMPT_SHA256
    assert cfg["provider"] == "fake"


def test_explicit_prices_override_table():
    p, _ = predictor(answer(usage=(1_000_000, 1_000_000)), prices=(1.0, 2.0))
    assert p.predict("c1", pair()).cost_usd == pytest.approx(3.0)


def test_unpriced_model_has_no_cost():
    backend = FakeBackend(answer())
    backend.model = "my-finetune"
    p = LLMPredictor(backend)
    assert p.predict("c1", pair()).cost_usd is None
    assert p.describe()["total_cost_usd"] is None


@pytest.mark.parametrize(
    "bad,match",
    [
        (answer(finish="refused"), "refused"),
        (answer(finish="length"), "token limit"),
        (answer(finish="other"), "unexpected stop"),
        (answer(text=""), "no text"),
        (answer(text="not json"), "unparseable"),
        (answer(concept="maybe"), "unparseable"),
    ],
)
def test_failures_raise_llm_error_and_count(bad, match):
    p, _ = predictor(bad)
    with pytest.raises(LLMError, match=match):
        p.predict("c1", pair())
    assert p.describe()["failed_calls"] == 1


def test_harness_records_llm_errors_without_crashing():
    from tests.test_eval import sample_cases

    answers = [answer(finish="refused")] + [answer() for _ in range(3)]
    run = evaluate(predictor(*answers)[0], sample_cases(), bootstrap_n=0)
    assert run.n_errors == 1 and run.records[0].prediction is None


def test_estimate_cost_brackets_spend():
    est = estimate_cost([pair()] * 200, (4.0, 20.0))
    lo, hi = est["cost_usd_range"]
    assert 0 < lo < hi and est["pairs"] == 200
    assert estimate_cost([pair()], None)["cost_usd_range"] is None


def test_cli_requires_provider_and_model():
    from opslm.eval.__main__ import main

    with pytest.raises(SystemExit):
        main(["run", "--dataset", "data/examples/guideline_examples.jsonl", "--system", "llm"])


def test_cli_requires_confirmation_before_model_calls(capsys):
    from opslm.eval.__main__ import main

    argv = ["run", "--dataset", "data/examples/guideline_examples.jsonl", "--system", "llm",
            "--provider", "openai-compatible", "--model", "my-model"]
    with pytest.raises(SystemExit):
        main(argv)
    out = capsys.readouterr()
    assert "estimate" in out.out and "--confirm-spend" in out.err


def test_cli_estimate_only_makes_no_calls(capsys):
    from opslm.eval.__main__ import main

    main(["run", "--dataset", "data/examples/guideline_examples.jsonl", "--system", "llm",
          "--provider", "vertex-gemini", "--model", "gemini-x", "--estimate-only"])
    out = capsys.readouterr().out
    assert "estimate: 9 pairs" in out and "cost unknown" in out
