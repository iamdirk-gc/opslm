import json

import pytest

from opslm.baselines.rules import RulesBaseline
from opslm.eval import metrics as m
from opslm.eval.__main__ import main
from opslm.eval.harness import compare_runs, evaluate, read_run, write_run
from opslm.eval.stats import bootstrap_ci, mcnemar_exact
from opslm.schema import Period, ReconciliationOutput, Relationship
from tests.factories import case, fact

E, C, R, I = (
    Relationship.EQUIVALENT,
    Relationship.CONFLICTING,
    Relationship.RELATED_BUT_DIFFERENT,
    Relationship.INSUFFICIENT_EVIDENCE,
)


# --- metrics -------------------------------------------------------------------


def test_perfect_predictions():
    gold = [E, C, R, I]
    assert m.accuracy(gold, gold) == 1.0
    assert m.macro_f1(gold, gold) == 1.0
    assert m.false_match_rate(gold, gold) == 0.0
    assert m.missed_match_rate(gold, gold) == 0.0


def test_per_class_precision_recall():
    gold = [E, E, C, C]
    pred = [E, C, E, C]
    pc = m.per_class(gold, pred)
    assert pc["equivalent"].precision == 0.5 and pc["equivalent"].recall == 0.5
    assert pc["equivalent"].support == 2


def test_false_and_missed_match_rates():
    gold = [E, E, C, R, I]
    pred = [E, C, E, E, I]
    assert m.false_match_rate(gold, pred) == pytest.approx(2 / 3)
    assert m.missed_match_rate(gold, pred) == 0.5


def test_rates_undefined_without_denominator():
    assert m.false_match_rate([E], [E]) is None
    assert m.missed_match_rate([C], [C]) is None


def test_none_prediction_is_a_miss():
    gold = [E, C]
    assert m.accuracy(gold, [None, C]) == 0.5
    assert m.per_class(gold, [None, C])["equivalent"].recall == 0.0
    assert m.confusion_matrix(gold, [None, C])["equivalent"]["none"] == 1


def test_macro_f1_ignores_classes_absent_from_gold():
    assert m.macro_f1([E, E], [E, E]) == 1.0


def test_confusion_matrix_shape():
    cm = m.confusion_matrix([E, C], [C, C])
    assert cm["equivalent"]["conflicting"] == 1 and cm["conflicting"]["conflicting"] == 1


# --- stats ---------------------------------------------------------------------


def test_mcnemar_known_values():
    assert mcnemar_exact(0, 0) == 1.0
    assert mcnemar_exact(5, 5) == 1.0
    assert mcnemar_exact(0, 10) == pytest.approx(2 / 1024)
    assert mcnemar_exact(2, 8) == pytest.approx(2 * (1 + 10 + 45) / 1024)


def test_bootstrap_ci_brackets_point_estimate_and_is_seeded():
    gold = [E, C] * 20
    pred = [E, C, C, C] * 10
    ci = bootstrap_ci(m.accuracy, gold, pred, n=500, seed=1)
    assert ci is not None and ci[0] <= m.accuracy(gold, pred) <= ci[1]
    assert ci == bootstrap_ci(m.accuracy, gold, pred, n=500, seed=1)


def test_bootstrap_ci_none_for_empty():
    assert bootstrap_ci(m.accuracy, [], [], n=10) is None


def test_metrics_accept_plain_strings():
    assert m.accuracy(["equivalent", "conflicting"], [E, "conflicting"]) == 1.0
    assert m.confusion_matrix(["equivalent"], ["equivalent"])["equivalent"]["equivalent"] == 1


# --- harness -------------------------------------------------------------------

Q3 = Period(type="duration", label="Q3 2025", fiscal_year=2025, fiscal_quarter=3)


def sample_cases():
    return [
        case("c1", fact("a1"), fact("b1", "Total Revenue"), E, family="s1", split="test",
             tags=["synonym"]),
        case("c2", fact("a2"), fact("b2", "Sales", "44.1"), C, family="s2", split="test",
             reasons=("value_mismatch",)),
        case("c3", fact("a3"), fact("b3", "ARR", "39.2"), R, False, True, family="s3",
             split="test", reasons=("definition_mismatch",)),
        case("c4", fact("a4"), fact("b4", period=Q3), R, True, False, family="s4", split="test",
             reasons=("period_mismatch",)),
    ]


def test_rules_baseline_on_sample_cases():
    run = evaluate(RulesBaseline(), sample_cases(), bootstrap_n=50)
    assert run.n_cases == 4 and run.n_errors == 0 and run.n_invalid_references == 0
    assert run.metrics["accuracy"].value == 1.0
    assert run.metrics["concept_accuracy"].value == 1.0
    assert run.metrics["false_match_rate"].value == 0.0
    assert run.evidence is not None and run.evidence.recall == 1.0
    assert run.cost.total_usd == 0.0
    assert run.slices["tag"]["synonym"].n == 1
    assert run.slices["primary_reason"]["period_mismatch"].accuracy == 1.0
    assert run.slices["source"]["synthetic"].n == 4


class Broken:
    """Errors on c2, otherwise calls everything equivalent and cites one span."""

    name = "broken"

    def predict(self, case):
        if case.case_id == "c2":
            raise RuntimeError("boom")
        return ReconciliationOutput(case_id=case.case_id, relationship=E, reasons=["synonym"],
                                    explanation="x", evidence_refs=[case.fact_a.evidence[0].span_id])


def test_predictor_errors_are_recorded_not_raised():
    run = evaluate(Broken(), sample_cases(), bootstrap_n=10)
    assert run.n_errors == 1
    bad = next(r for r in run.records if r.case_id == "c2")
    assert bad.prediction is None and "boom" in bad.error and not bad.correct
    assert run.confusion["conflicting"]["none"] == 1
    assert run.metrics["false_match_rate"].value == pytest.approx(2 / 3)
    assert run.evidence.recall == 0.5 and run.evidence.precision == 1.0


class Fabricating(Broken):
    name = "fabricating"

    def predict(self, case):
        out = super().predict(case)
        return out.model_copy(update={"evidence_refs": ["made-up"]})


def test_references_to_spans_not_in_the_input_are_counted():
    run = evaluate(Fabricating(), sample_cases(), bootstrap_n=0)
    assert run.n_invalid_references == 3
    assert run.records[0].reference_problems == ["evidence_refs not in input: ['made-up']"]


def test_run_roundtrips_through_json(tmp_path):
    run = evaluate(RulesBaseline(), sample_cases(), bootstrap_n=10, config={"note": "x"})
    write_run(tmp_path / "r.json", run)
    assert read_run(tmp_path / "r.json") == run
    assert run.config == {"note": "x"}


def test_compare_runs_requires_same_dataset():
    a = evaluate(RulesBaseline(), sample_cases(), bootstrap_n=0)
    b = evaluate(RulesBaseline(), sample_cases()[:3], bootstrap_n=0)
    with pytest.raises(ValueError, match="different datasets"):
        compare_runs(a, b)


def test_compare_runs_counts_discordant_cases():
    cases = sample_cases()
    a = evaluate(RulesBaseline(), cases, bootstrap_n=0)
    b = evaluate(Broken(), cases, bootstrap_n=0)
    cmp = compare_runs(a, b)
    assert cmp.only_a_correct == 3 and cmp.only_b_correct == 0 and cmp.n == 4
    assert cmp.p_value == pytest.approx(0.25)


def test_cli_run_and_compare(tmp_path, capsys):
    from opslm.data import write_cases

    data = tmp_path / "d.jsonl"
    write_cases(data, sample_cases())
    out = tmp_path / "rules.json"
    main(["run", "--dataset", str(data), "--system", "rules", "--split", "test",
          "--out", str(out), "--bootstrap", "20"])
    assert "macro_f1" in capsys.readouterr().out
    assert json.loads(out.read_text())["system"] == "rules"
    main(["compare", str(out), str(out)])
    assert "McNemar" in capsys.readouterr().out


def test_example_dataset_loads_and_is_valid():
    from opslm.data import load_dataset

    cases = load_dataset("data/examples/guideline_examples.jsonl")
    assert len(cases) == 9 and all(c.gold.labeled_by == "guideline-examples" for c in cases)
    run = evaluate(RulesBaseline(), cases, bootstrap_n=0)
    assert run.metrics["accuracy"].value == 1.0  # written alongside the rules; see the README
