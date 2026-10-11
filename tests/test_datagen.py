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
from opslm.labels import GUIDELINE_VERSION, values_agree
from opslm.schema import CONSTRUCTION_LABELER, Relationship, Split

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
            (family,) = c.input.document_families()  # one family (= scenario) per case
            assert seen.setdefault(family, name) == name


def test_every_label_is_well_represented(big):
    counts = Counter(c.gold.relationship for c in big.train)
    total = sum(counts.values())
    for label in Relationship:
        assert counts[label] / total > 0.12, (label, counts)


def test_every_template_appears(big):
    kinds = set(big.manifest["pairs_by_kind"])
    assert kinds == set(S.TEMPLATES)


def test_heldout_names_only_outside_train(big):
    train_names = {f.metric_label for c in big.train for f in (c.input.fact_a, c.input.fact_b)}
    assert not train_names & HELDOUT
    later = {f.metric_label for c in big.validation + big.test_construction
             for f in (c.input.fact_a, c.input.fact_b)}
    assert later & HELDOUT


def test_cases_are_generator_labeled_and_use_current_guidelines(big):
    for c in big.train + big.validation + big.test_construction:
        assert c.gold.labeled_by == CONSTRUCTION_LABELER and not c.human_labeled
        assert c.gold.guideline_version == GUIDELINE_VERSION and c.gold.source == "synthetic"


def test_gold_labels_have_reasons_and_cite_both_facts(big):
    for c in big.train + big.validation + big.test_construction:
        assert c.gold.reasons and c.gold.tags[0] in S.TEMPLATES
        assert set(c.gold.required_evidence_refs) == c.input.span_ids()
    by_kind = {c.gold.tags[0]: c.gold.reasons[0] for c in big.train}
    assert by_kind["missing_entity"] == "missing_entity"
    assert by_kind["missing_period"] == "missing_period"
    assert by_kind["currency_mismatch"] == "currency_mismatch"
    assert by_kind["restatement"] == "restatement"
    assert by_kind["entity_mismatch"] == "entity_mismatch"


def test_metric_ids_come_from_names_not_ground_truth(big):
    for c in big.train:
        for f in (c.input.fact_a, c.input.fact_b):
            assert f.metric_id == V.metric_id_for(f.metric_label)
    ebitda = [c for c in big.train if c.gold.tags[0] == "company_defined"
              and c.gold.relationship == "related_but_different"
              and c.input.fact_a.metric_id == "adjusted_ebitda"]
    # different stated adjustments: same id, different concept
    assert all(c.input.fact_b.metric_id == "adjusted_ebitda" for c in ebitda)


def test_test_candidates_match_construction_cases(big):
    assert {c.case_id for c in big.test_candidates} == {c.case_id for c in big.test_construction}
    assert all(c.split == Split.TEST for c in big.test_candidates)


def test_rules_baseline_is_strong_on_names_but_cannot_read_definitions(big):
    # The baseline knows every naming variant on the metric page (a test requires it), so it does
    # well on synthetic names. A generator whose hard cases were solvable by lookup would score
    # near 100% here; the cases that need a definition read must stay out of its reach.
    run = evaluate(RulesBaseline(), big.train, bootstrap_n=0)
    assert run.metrics["accuracy"].value < 0.95
    assert run.slices["tag"]["definition_resolves"].accuracy < 0.5


def _pairs(cases):
    for c in cases:
        yield c.input.fact_a, c.input.fact_b
        yield c.input.fact_b, c.input.fact_a


def test_missing_entity_evidence_does_not_leak_the_entity(big):
    checked = 0
    for me, other in _pairs(big.train + big.validation + big.test_construction):
        if me.entity is None and other.entity:
            assert other.entity.name.split()[0].lower() not in me.evidence[0].text.lower()
            checked += 1
    assert checked


def test_missing_period_evidence_does_not_leak_the_period(big):
    checked = 0
    for me, other in _pairs(big.train):
        if me.period is None and other.period:
            assert other.period.label not in me.evidence[0].text
            checked += 1
    assert checked


def test_point_in_time_concepts_use_as_of_dates(big):
    seen = 0
    for c in big.train:
        for f in (c.input.fact_a, c.input.fact_b):
            if f.metric_label in ("ARR", "Annual recurring revenue") and f.period:
                assert f.period.type == "instant" and f.period.as_of is not None
                seen += 1
    assert seen


def test_quantities_are_normalized_to_base_units(big):
    for c in big.train:
        for f in (c.input.fact_a, c.input.fact_b):
            q = f.quantity
            assert q.value == q.reported_value * q.reported_scale
            assert (q.unit == "currency") == (q.currency is not None)


def _facts(cases):
    for c in cases:
        yield from (c.input.fact_a, c.input.fact_b)


def test_negative_net_income_is_signed_and_printed_in_a_recognisable_style(big):
    found = [(c, f) for c in big.train for f in (c.input.fact_a, c.input.fact_b)
             if f.quantity.value < 0]
    assert found and all(f.metric_label.startswith(("Net income", "Net earnings", "Net loss",
                                                    "Profit")) for _, f in found)
    # outside the sign-convention scenarios a loss is always printed in parentheses
    plain = [f for c, f in found if "sign_convention" not in c.gold.tags]
    assert plain and all(f.quantity.raw_text.startswith("(") for f in plain)
    assert any("(" in f.evidence[0].text for f in plain)


def test_sign_convention_equivalents_show_the_same_loss_in_different_styles(big):
    cases = [c for c in big.train + big.validation if "sign_convention" in c.gold.tags
             and c.gold.relationship == "equivalent"]
    assert cases
    for c in cases:
        a, b = c.input.fact_a.quantity, c.input.fact_b.quantity
        assert a.value < 0 and b.value < 0 and values_agree(a, b) and a.raw_text != b.raw_text
        assert c.gold.reasons[0] == "sign_convention"
    labelled = [f for f in _facts(cases) if f.metric_label == "Net loss"]
    assert labelled and all(not f.quantity.raw_text.startswith(("(", "-")) for f in labelled)


def test_a_lost_sign_is_a_conflict(big):
    cases = [c for c in big.train + big.validation if "sign_error" in c.gold.tags]
    assert cases
    for c in cases:
        a, b = c.input.fact_a.quantity, c.input.fact_b.quantity
        assert a.value == -b.value != 0
        assert c.gold.relationship == "conflicting"
        assert c.gold.reasons[:2] == ["value_mismatch", "sign_convention"]


def test_as_of_mismatch_uses_arr_with_matching_definitions(big):
    cases = [c for c in big.train if "as_of_mismatch" in c.gold.tags]
    assert cases
    for c in cases:
        a, b = c.input.fact_a, c.input.fact_b
        assert a.metric_id == b.metric_id == "arr"
        assert a.period.type == b.period.type == "instant" and a.period.as_of != b.period.as_of
        assert a.stated_definition and b.stated_definition  # concept is settled, only the date differs
        assert c.gold.relationship == "related_but_different"
        assert c.gold.reasons == ["as_of_mismatch"]
        assert c.gold.concept_same is True and c.gold.scope_same is False


def test_new_reason_codes_appear_as_primary_reasons(big):
    primary = {c.gold.reasons[0] for c in big.train + big.validation + big.test_construction}
    assert {"as_of_mismatch", "sign_convention"} <= primary


def test_wrong_template_expectation_fails_loudly(monkeypatch):
    original, weight = S.TEMPLATES["synonym_equivalent"]

    def broken(ctx):
        kind, pairs = original(ctx)
        from dataclasses import replace

        return kind, [replace(p, expect=Relationship.CONFLICTING) for p in pairs]

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
    assert not any(c.human_labeled for c in read_cases(paths["test_construction_labels"]))
    export_review_sheet(tmp_path / "sheet.xlsx", cands[:5])  # feeds the labeling workflow


def test_audit_against_construction_labels():
    r = generate(60, seed=7)
    perfect = [Review(case_id=c.case_id, reviewer="h", concept_same=c.gold.concept_same,
                      scope_same=c.gold.scope_same, reasons=tuple(c.gold.reasons),
                      evidence_refs=tuple(c.gold.required_evidence_refs), rationale="r")
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

    assert cal.asof(random.Random(0)).as_of == cal.end
    assert cal.asof(random.Random(0), quarter=2).as_of == date(2024, 12, 31)
    assert cal.quarter(2, dated=False).fiscal_quarter == 2 and cal.ltm().is_ltm


def test_amount_text_formats_negatives_with_parentheses():
    import random

    ctx = S.Ctx(random.Random(0), "s", V.Company("Acme", "Inc"), V.FiscalCalendar(2025, 12),
                heldout=False)
    Scale = S.Scale

    assert ctx.amount_text(Decimal("-5.2"), Scale.MILLIONS, "USD") == "($5.2 million)"
    assert ctx.amount_text(Decimal("12.5"), Scale.UNITS, "percent") == "12.5%"


def test_cli_smoke(tmp_path, capsys):
    from opslm.datagen.__main__ import main

    main(["--scenarios", "40", "--seed", "1", "--out-dir", str(tmp_path)])
    out = capsys.readouterr().out
    assert "train" in out and "wrote manifest" in out


def test_basis_diff_changes_only_the_accounting_basis(big):
    cases = [c for c in big.train if "basis_diff" in c.gold.tags]
    assert cases
    for c in cases:
        a, b = c.input.fact_a, c.input.fact_b
        assert a.metric_label == b.metric_label
        assert (a.accounting_basis, b.accounting_basis) == ("gaap", "non_gaap")
        assert c.gold.reasons == ["basis_mismatch"] and c.gold.concept_same is False
