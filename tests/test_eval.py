import json
from decimal import Decimal

import pytest

from opslm.baselines.rules import RulesBaseline
from opslm.eval import metrics as m
from opslm.eval.__main__ import main
from opslm.eval.harness import compare_runs, evaluate, read_run, write_run
from opslm.eval.stats import bootstrap_ci, mcnemar_exact
from opslm.labels import GUIDELINE_VERSION
from opslm.schema import (
    BusinessFact,
    DiscrepancyReason,
    EvalCase,
    Evidence,
    FactPair,
    Period,
    PeriodType,
    Prediction,
    Relation,
    SourceKind,
    SourceRef,
    Split,
)

E, C, R, I = (
    Relation.EQUIVALENT,
    Relation.CONFLICTING,
    Relation.RELATED_BUT_DIFFERENT,
    Relation.INSUFFICIENT_EVIDENCE,
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


# --- harness -------------------------------------------------------------------


def fact(fid, metric="Revenue", value="42.5", period="FY2025", entity="Acme Corp"):
    return BusinessFact(
        fact_id=fid,
        metric=metric,
        value=Decimal(value),
        unit="USD",
        entity=entity,
        period=Period(label=period, type=PeriodType.FISCAL_YEAR),
        source=SourceRef(document_id="d"),
    )


def make_case(n, a, b, label, concept, scope, reason=None, fields=(), split=Split.TEST, tags=()):
    return EvalCase(
        case_id=f"c{n}",
        scenario_id=f"s{n}",
        pair=FactPair(fact_a=a, fact_b=b),
        label=label,
        concept_same=concept,
        scope_same=scope,
        rationale="r",
        source_kind=SourceKind.SYNTHETIC,
        split=split,
        reviewed=True,
        guideline_version=GUIDELINE_VERSION,
        discrepancy_reason=reason,
        discriminating_fields=fields,
        tags=tags,
    )


def sample_cases():
    return [
        make_case(1, fact("a1"), fact("b1", "Net Revenue"), E, True, True, tags=("synonym",)),
        make_case(2, fact("a2"), fact("b2", "Sales", "44.1"), C, True, True,
                  DiscrepancyReason.UNEXPLAINED, ("value",)),
        make_case(3, fact("a3"), fact("b3", "ARR", "39.2"), R, False, True,
                  DiscrepancyReason.DEFINITION, ("metric",)),
        make_case(4, fact("a4"), fact("b4", period="Q3 2025"), R, True, False,
                  DiscrepancyReason.PERIOD, ("period",)),
    ]


def test_rules_baseline_on_sample_cases():
    run = evaluate(RulesBaseline(), sample_cases(), bootstrap_n=50)
    assert run.n_cases == 4 and run.n_errors == 0
    assert run.metrics["accuracy"].value == 1.0
    assert run.metrics["concept_accuracy"].value == 1.0
    assert run.metrics["false_match_rate"].value == 0.0
    assert run.evidence is not None and run.evidence.recall == 1.0
    assert run.cost.total_usd == 0.0
    assert run.slices["tag"]["synonym"].n == 1
    assert run.slices["discrepancy_reason"]["period"].accuracy == 1.0


class Broken:
    name = "broken"

    def predict(self, case_id, pair):
        if case_id == "c2":
            raise RuntimeError("boom")
        return Prediction(case_id=case_id, label=E, evidence=(Evidence(fact_id="x", field="metric"),))


def test_predictor_errors_are_recorded_not_raised():
    run = evaluate(Broken(), sample_cases(), bootstrap_n=10)
    assert run.n_errors == 1
    bad = next(r for r in run.records if r.case_id == "c2")
    assert bad.prediction is None and "boom" in bad.error and not bad.correct
    assert run.confusion["conflicting"]["none"] == 1
    assert run.metrics["false_match_rate"].value == pytest.approx(2 / 3)


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
    assert len(cases) == 9 and not any(c.reviewed for c in cases)
