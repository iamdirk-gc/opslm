import json
from collections import Counter
from datetime import date
from decimal import Decimal

import pytest

from opslm.baselines.rules import RulesBaseline
from opslm.data import load_dataset, read_cases
from opslm.datagen import scenarios as S
from opslm.datagen import vocab as V
from opslm.datagen.audit import compare_to_construction
from opslm.datagen.generate import GeneratorError, generate, write_outputs
from opslm.eval.harness import evaluate
from opslm.labeling import Review, export_review_sheet, read_candidates
from opslm.labels import GUIDELINE_VERSION
from opslm.schema import Relation, Split

HELDOUT = {n for c in V.CONCEPTS.values() for n in c.heldout}


@pytest.fixture(scope="module")
def big():
    return generate(500, seed=3)


def test_deterministic_for_a_seed_and_different_across_seeds():
    a, b, c = generate(60, seed=1), generate(60, seed=1), generate(60, seed=2)
    assert a.manifest["splits"] == b.manifest["splits"]
    assert a.manifest["splits"] != c.manifest["splits"]


def test_split_sizes_and_scenarios_never_span_splits(big):
    m = big.manifest["splits"]
    assert m["train"]["scenarios"] == 350 and m["validation"]["scenarios"] == 50
    assert m["test"]["scenarios"] == 100
    seen = {}
    for name, cases in (("train", big.train), ("val", big.validation), ("test", big.test_construction)):
        for c in cases:
            assert seen.setdefault(c.scenario_id, name) == name


def test_every_label_is_well_represented(big):
    counts = Counter(c.label for c in big.train)
    total = sum(counts.values())
    for label in Relation:
        assert counts[label] / total > 0.12, (label, counts)


def test_every_template_appears(big):
    kinds = set(big.manifest["pairs_by_kind"])
    assert kinds == set(S.TEMPLATES)


def test_heldout_names_only_outside_train(big):
    train_names = {f.metric for c in big.train for f in (c.pair.fact_a, c.pair.fact_b)}
    assert not train_names & HELDOUT
    later = {f.metric for c in big.validation + big.test_construction
             for f in (c.pair.fact_a, c.pair.fact_b)}
    assert later & HELDOUT


def test_cases_are_unreviewed_and_use_current_guidelines(big):
    for c in big.train + big.validation + big.test_construction:
        assert not c.reviewed and c.guideline_version == GUIDELINE_VERSION
        assert c.source_kind.value == "synthetic"


def test_test_candidates_match_construction_cases(big):
    assert {c.case_id for c in big.test_candidates} == {c.case_id for c in big.test_construction}
    assert all(c.split is Split.TEST for c in big.test_candidates)


def test_rules_baseline_is_not_at_ceiling(big):
    # a generator built from the baseline's own vocabulary would score near 100% here
    run = evaluate(RulesBaseline(), big.train, bootstrap_n=0)
    assert run.metrics["accuracy"].value < 0.8


def test_missing_entity_excerpts_do_not_leak_the_entity(big):
    for c in big.train + big.validation + big.test_construction:
        for me, other in ((c.pair.fact_a, c.pair.fact_b), (c.pair.fact_b, c.pair.fact_a)):
            if me.entity is None and me.source.excerpt and other.entity:
                assert other.entity.split()[0].lower() not in me.source.excerpt.lower()


def test_missing_period_excerpts_do_not_leak_the_period(big):
    for c in big.train:
        for me, other in ((c.pair.fact_a, c.pair.fact_b), (c.pair.fact_b, c.pair.fact_a)):
            if me.period is None and me.source.excerpt and other.period:
                assert other.period.label not in me.source.excerpt


def test_point_in_time_concepts_use_as_of_dates(big):
    seen = 0
    for c in big.train:
        for f in (c.pair.fact_a, c.pair.fact_b):
            if f.metric in ("ARR", "Annual recurring revenue") and f.period:
                assert f.period.type.value == "point_in_time" and f.period.start == f.period.end
                seen += 1
    assert seen


def test_negative_net_income_is_signed_and_uses_parentheses_in_excerpts(big):
    found = [f for c in big.train for f in (c.pair.fact_a, c.pair.fact_b)
             if f.value is not None and f.value < 0]
    assert found and all(f.metric.startswith(("Net income", "Net earnings", "Net loss",
                                              "Profit")) for f in found)
    assert any(f.source.excerpt and "(" in f.source.excerpt for f in found)


def test_wrong_template_expectation_fails_loudly(monkeypatch):
    original, weight = S.TEMPLATES["synonym_equivalent"]

    def broken(ctx):
        kind, pairs = original(ctx)
        from dataclasses import replace

        return kind, [replace(p, expect=Relation.CONFLICTING) for p in pairs]

    monkeypatch.setitem(S.TEMPLATES, "synonym_equivalent", (broken, weight))
    with pytest.raises(GeneratorError, match="template expected conflicting"):
        generate(30, seed=0, weights={k: (0 if k != "synonym_equivalent" else 1) for k in S.TEMPLATES})


def test_write_outputs_and_downstream_loading(tmp_path):
    r = generate(80, seed=5)
    paths = write_outputs(r, tmp_path)
    assert len(load_dataset(paths["train"])) == len(r.train)
    assert len(load_dataset(paths["validation"])) == len(r.validation)
    cands = read_candidates(paths["test_candidates"])
    assert len(cands) == len(r.test_candidates)
    manifest = json.loads(paths["manifest"].read_text())
    assert manifest["generator_version"] and "must not be used as gold" in manifest["notes"]
    assert not any(c.reviewed for c in read_cases(paths["test_construction_labels"]))
    export_review_sheet(tmp_path / "sheet.xlsx", cands[:5])  # feeds the labeling workflow


def test_audit_against_construction_labels():
    r = generate(60, seed=7)
    perfect = [Review(case_id=c.case_id, reviewer="h", concept_same=c.concept_same,
                      scope_same=c.scope_same, discrepancy_reason=c.discrepancy_reason,
                      discriminating_fields=c.discriminating_fields, rationale="r")
               for c in r.test_construction]
    ok = compare_to_construction(perfect, r.test_construction, r.test_candidates)
    assert ok["agreement"] == 1.0 and ok["n"] == len(perfect) and not ok["disagreements"]
    flipped = [p.model_copy(update={"concept_same": not p.concept_same}) if p.concept_same is not None
               else p for p in perfect]
    bad = compare_to_construction(flipped, r.test_construction, r.test_candidates)
    assert bad["agreement"] < 1.0 and bad["disagreements"]


def test_fiscal_calendar_dates_are_consistent():
    cal = V.FiscalCalendar(2025, 6)
    assert cal.end == date(2025, 6, 30) and cal.start == date(2024, 7, 1)
    assert cal.quarter(4, dated=True).end == cal.end
    assert cal.quarter(1, dated=True).start == cal.start
    assert cal.ltm().end == cal.quarter(3, dated=True).end
    import random

    assert cal.asof(random.Random(0)).end == cal.end
    assert cal.asof(random.Random(0), quarter=2).end == date(2024, 12, 31)


def test_amount_text_formats_negatives_with_parentheses():
    import random

    ctx = S.Ctx(random.Random(0), "s", V.Company("Acme", "Inc"), V.FiscalCalendar(2025, 12),
                heldout=False)
    from opslm.schema import Scale

    assert ctx.amount_text(Decimal("-5.2"), Scale.MILLIONS, "USD") == "($5.2 million)"
    assert ctx.amount_text(Decimal("12.5"), Scale.UNITS, "percent") == "12.5%"


def test_cli_smoke(tmp_path, capsys):
    from opslm.datagen.__main__ import main

    main(["--scenarios", "40", "--seed", "1", "--out-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "train" in out and "wrote manifest" in out
