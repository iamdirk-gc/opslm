import json

import pytest

from opslm.baselines.backends import Completion
from opslm.baselines.llm import LLMError, LLMPredictor, build_user_message, estimate_cost
from opslm.baselines.prompts import PROMPT_SHA256
from opslm.eval.harness import evaluate
from opslm.schema import Relationship
from tests.factories import case_input
from tests.factories import fact as make_fact


def fact(fid, metric="Revenue", value="42.5", currency="USD"):
    # evidence text without the number, so tests can check values stay hidden
    return make_fact(fid, metric, value, currency=currency, doc="secret-doc-id",
                     text=f"{metric} for FY2025")


def pair(**kw):
    return case_input(fact("a"), fact("b", **kw))


def answer(concept="yes", scope="yes", fields=(), finish="stop", text=None, usage=(1000, 500),
           refs=("s-a", "s-b")):
    body = text if text is not None else json.dumps(
        {"rationale": "r", "concept_same": concept, "scope_same": scope,
         "deciding_fields": list(fields), "evidence_refs": list(refs)}
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
    assert "secret-doc-id" not in msg and "fact_id" not in msg  # document and fact ids omitted
    assert json.loads(msg)["fact_a"]["evidence"] == [
        {"span_id": "s-a", "document_type": "10-K", "text": "Revenue for FY2025"}]
    shown = build_user_message(pair(value="44.1"), show_values=True)
    assert "42.5" in shown and "44.1" in shown


def test_backend_receives_prompt_schema_and_limit():
    p, backend = predictor(answer(), max_tokens=1234)
    p.predict(pair())
    system, user, schema, limit = backend.calls[0]
    assert "concept_same" in system and "fact_a" in user
    assert schema["required"] and limit == 1234
    assert p.name == "fake:model"


def test_equivalent_when_model_says_yes_and_values_agree():
    p, _ = predictor(answer())
    pred = p.predict(pair())
    assert pred.relationship == Relationship.EQUIVALENT and pred.reasons == ["exact_match"]
    assert pred.evidence_refs == ["s-a", "s-b"] and pred.check_references(pair()) == []


def test_code_not_model_decides_value_conflicts():
    p, _ = predictor(answer())
    pred = p.predict(pair(value="44.1"))
    assert pred.relationship == Relationship.CONFLICTING and pred.values_agree is False
    assert pred.reasons == ["value_mismatch"]


def test_concept_no_is_related_and_cites_model_fields():
    p, _ = predictor(answer(concept="no", fields=["metric"]))
    pred = p.predict(pair(value="39.2"))
    assert pred.relationship == Relationship.RELATED_BUT_DIFFERENT
    assert pred.reasons == ["definition_mismatch"]


def test_cannot_tell_gives_insufficient_evidence():
    p, _ = predictor(answer(scope="cannot_tell", fields=["entity"]))
    pred = p.predict(pair())
    assert pred.relationship == Relationship.INSUFFICIENT_EVIDENCE and pred.scope_same is None
    assert pred.reasons == ["missing_entity"]


def test_currency_mismatch_is_insufficient():
    p, _ = predictor(answer())
    assert p.predict(pair(currency="EUR")).relationship == Relationship.INSUFFICIENT_EVIDENCE


def test_cost_and_usage_accounting():
    p, _ = predictor(answer(usage=(10_000, 2_000)))
    pred = p.predict(pair())
    assert pred.run.cost_usd == pytest.approx((10_000 * 4 + 2_000 * 20) / 1e6)
    assert pred.run.input_tokens == 10_000 and pred.run.model_name == "claude-opus-5-5"
    cfg = p.describe()
    assert cfg["input_tokens"] == 10_000 and cfg["prompt_sha256"] == PROMPT_SHA256
    assert cfg["provider"] == "fake"


def test_explicit_prices_override_table():
    p, _ = predictor(answer(usage=(1_000_000, 1_000_000)), prices=(1.0, 2.0))
    assert p.predict(pair()).run.cost_usd == pytest.approx(3.0)


def test_unpriced_model_has_no_cost():
    backend = FakeBackend(answer())
    backend.model = "my-finetune"
    p = LLMPredictor(backend)
    assert p.predict(pair()).run.cost_usd is None
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
        p.predict(pair())
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


def test_long_rationale_is_clipped_to_the_output_limit():
    p, _ = predictor(answer(text=json.dumps({"rationale": "x" * 5000, "concept_same": "yes",
                                             "scope_same": "yes", "deciding_fields": [],
                                             "evidence_refs": ["s-a"]})))
    assert len(p.predict(pair()).explanation) == 1000


def test_model_sees_structured_fields():
    msg = json.loads(build_user_message(pair(), show_values=True))
    a = msg["fact_a"]
    assert "metric_id" not in a and a["entity"]["scope"] == "consolidated"
    assert a["period"] == {"type": "duration", "fiscal_year": 2025, "label": "FY2025"}
    assert a["value"]["as_printed"] == "42.5" and a["basis"]["accounting"] == "unknown"


# --- evidence chosen by the model, and the metric_id hint ---------------------------------------


def test_schema_limits_evidence_refs_to_the_cases_own_spans():
    p, backend = predictor(answer())
    p.predict(pair())
    schema = backend.calls[0][2]
    assert schema["properties"]["evidence_refs"]["items"]["enum"] == ["s-a", "s-b"]
    assert "evidence_refs" in schema["required"]


def test_model_cited_spans_become_the_output_evidence():
    p, _ = predictor(answer(refs=("s-b",)))
    out = p.predict(pair())
    assert out.evidence_refs == ["s-b"]  # not every span: the model chose one


def test_duplicate_citations_are_collapsed():
    p, _ = predictor(answer(refs=("s-a", "s-a", "s-b")))
    assert p.predict(pair()).evidence_refs == ["s-a", "s-b"]


def test_no_evidence_for_a_decision_that_needs_it_is_an_error():
    p, _ = predictor(answer(refs=()))
    with pytest.raises(LLMError, match="cited no evidence spans"):
        p.predict(pair())
    assert p.describe()["failed_calls"] == 1


def test_abstention_may_cite_no_evidence():
    p, _ = predictor(answer(concept="cannot_tell", fields=["definition"], refs=()))
    out = p.predict(pair())
    assert out.relationship == Relationship.INSUFFICIENT_EVIDENCE and out.evidence_refs == []


def test_unknown_span_ids_are_kept_so_the_harness_can_count_them():
    p, _ = predictor(answer(refs=("s-a", "s-nonexistent")))
    case = pair()
    out = p.predict(case)
    assert out.evidence_refs == ["s-a", "s-nonexistent"]
    assert any("not in input" in x for x in out.check_references(case))


def test_context_spans_are_shown_with_ids_and_can_be_cited():
    from opslm.schema import EvidenceSpan

    case = pair()
    ctx = EvidenceSpan(span_id="ctx-1", doc_id=case.documents[0].doc_id, page=2,
                       text="Net revenue means revenue after platform fees.")
    case = case.model_copy(update={"context": [ctx]})
    p, backend = predictor(answer(refs=("ctx-1",)))
    out = p.predict(case)
    assert json.loads(backend.calls[0][1])["context"][0]["span_id"] == "ctx-1"
    assert "ctx-1" in backend.calls[0][2]["properties"]["evidence_refs"]["items"]["enum"]
    assert out.evidence_refs == ["ctx-1"] and out.check_references(case) == []


def test_metric_id_is_hidden_unless_asked():
    msg = json.loads(build_user_message(pair(), show_values=False))
    assert "metric_id" not in msg["fact_a"] and "metric_id" not in msg["fact_b"]
    shown = json.loads(build_user_message(pair(), show_values=False, show_metric_id=True))
    assert shown["fact_a"]["metric_id"] == "revenue"


def test_show_metric_id_flag_reaches_the_prompt_and_the_run_config():
    p, backend = predictor(answer(), show_metric_id=True)
    p.predict(pair())
    assert "metric_id" in backend.calls[0][1] and p.describe()["show_metric_id"] is True
    q, backend2 = predictor(answer())
    q.predict(pair())
    assert "metric_id" not in backend2.calls[0][1] and q.describe()["show_metric_id"] is False


def test_estimate_is_larger_when_more_is_shown():
    cases = [pair()] * 5
    base = estimate_cost(cases, None)["input_tokens_approx"]
    more = estimate_cost(cases, None, show_values=True, show_metric_id=True)["input_tokens_approx"]
    assert more > base
