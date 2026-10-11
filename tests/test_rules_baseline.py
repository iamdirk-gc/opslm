from datetime import date

import pytest

from opslm.baselines.rules import RulesBaseline, normalize_entity, normalize_period_label
from opslm.schema import Entity, Period, Relationship
from tests.factories import case_input, fact


def predict(a, b):
    return RulesBaseline().predict(case_input(a, b))


def test_plan_example_equivalent():
    p = predict(fact("f", "Revenue"), fact("g", "Total Revenue"))
    assert p.relationship == Relationship.EQUIVALENT and p.reasons == ["synonym"]


def test_plan_example_conflicting():
    p = predict(fact("f", "Revenue"), fact("g", "Sales", "44.1"))
    assert p.relationship == Relationship.CONFLICTING and p.values_agree is False
    assert p.reasons == ["value_mismatch"]


def test_plan_example_arr_is_different_concept():
    p = predict(fact("f", "Revenue"), fact("g", "ARR", "39.2"))
    assert p.relationship == Relationship.RELATED_BUT_DIFFERENT and p.concept_same is False
    assert p.reasons == ["definition_mismatch"]


@pytest.mark.parametrize(
    "a,b,same",
    [
        ("EBITDA", "Adjusted EBITDA", False),
        ("Revenue", "Gross Revenue", False),
        ("Net Income", "Non-GAAP Net Income", False),
        ("Revenue", "Revenue (GAAP)", True),
        ("Gross Profit", "Gross Income", True),
        ("Gross Profit", "Revenue", False),
        ("R&D", "Research and Development", True),
        ("Operating Profit", "EBIT", True),
        ("Core Revenue", "Revenue", None),
        ("Customer Lifetime Value", "Churn Rate", None),
    ],
)
def test_concept_judgments(a, b, same):
    assert predict(fact("f", a), fact("g", b)).concept_same is same


def test_non_gaap_basis_changes_concept():
    p = predict(fact("f", "EBITDA", basis="non_gaap"), fact("g", "EBITDA"))
    assert p.concept_same is False and p.reasons == ["basis_mismatch"]


def test_gaap_basis_is_neutral():
    assert predict(fact("f", basis="gaap"), fact("g")).concept_same is True


def test_period_mismatch_is_related_but_different():
    q3 = Period(type="duration", label="Q3 2025", fiscal_year=2025, fiscal_quarter=3)
    p = predict(fact("f"), fact("g", value="11.0", period=q3))
    assert p.relationship == Relationship.RELATED_BUT_DIFFERENT and p.scope_same is False
    assert p.reasons == ["period_mismatch"]


def test_entity_mismatch_is_related_but_different():
    p = predict(fact("f"), fact("g", entity=Entity(name="Acme Europe Ltd", scope="subsidiary")))
    assert p.relationship == Relationship.RELATED_BUT_DIFFERENT
    assert p.reasons == ["entity_mismatch"]


def test_segment_differs_from_consolidated():
    seg = Entity(name="Acme Corp", scope="segment", segment="Cloud")
    assert predict(fact("f"), fact("g", entity=seg)).scope_same is False


def test_entity_suffix_and_case_ignored():
    assert predict(fact("f", entity="ACME, Inc."), fact("g", entity="Acme Corporation")).scope_same


def test_missing_entity_is_insufficient():
    p = predict(fact("f", entity=None), fact("g"))
    assert p.relationship == Relationship.INSUFFICIENT_EVIDENCE
    assert p.reasons == ["missing_entity"]


def test_missing_period_is_insufficient():
    p = predict(fact("f", period=None), fact("g"))
    assert p.relationship == Relationship.INSUFFICIENT_EVIDENCE and p.reasons == ["missing_period"]


def test_currency_mismatch_is_insufficient():
    p = predict(fact("f"), fact("g", currency="EUR", value="39.0"))
    assert p.relationship == Relationship.INSUFFICIENT_EVIDENCE
    assert p.reasons == ["currency_mismatch"]


def test_scale_error_is_conflicting():
    p = predict(fact("f"), fact("g", scale="1"))
    assert p.relationship == Relationship.CONFLICTING and "unit_scale" in p.reasons


def test_dates_override_labels():
    a = Period(type="duration", label="FY2025", start=date(2024, 7, 1), end=date(2025, 6, 30))
    b = Period(type="duration", label="Fiscal 2025", start=date(2024, 7, 1), end=date(2025, 6, 30))
    c = Period(type="duration", label="FY2025", start=date(2025, 1, 1), end=date(2025, 12, 31))
    assert predict(fact("f", period=a), fact("g", period=b)).scope_same is True
    assert predict(fact("f", period=a), fact("g", period=c)).scope_same is False


def test_fiscal_year_matches_a_differently_worded_label():
    long_form = Period(type="duration", label="Year ended December 31, 2025", fiscal_year=2025,
                       start=date(2025, 1, 1), end=date(2025, 12, 31))
    assert predict(fact("f", period=long_form), fact("g")).scope_same is True


def test_as_of_dates_compare_for_point_in_time_metrics():
    ye = Period(type="instant", label="as of Dec 31, 2025", as_of=date(2025, 12, 31))
    q3 = Period(type="instant", label="Sep 30, 2025", as_of=date(2025, 9, 30))
    p = predict(fact("f", "ARR", period=ye), fact("g", "ARR", period=q3))
    assert p.scope_same is False and p.reasons == ["as_of_mismatch"]
    assert predict(fact("f", "ARR", period=ye), fact("g", "ARR", period=ye)).scope_same is True


def test_flow_and_point_in_time_periods_differ():
    ye = Period(type="instant", label="as of Dec 31, 2025", as_of=date(2025, 12, 31))
    assert predict(fact("f"), fact("g", period=ye)).scope_same is False


def test_output_cites_both_facts_and_records_run():
    p = predict(fact("f"), fact("g"))
    assert p.evidence_refs == ["s-f", "s-g"] and p.explanation.startswith("Same concept: yes")
    assert p.run.system == "rules" and p.run.latency_ms >= 0 and p.run.cost_usd == 0.0
    assert p.check_references(case_input(fact("f"), fact("g"))) == []


def test_normalizers():
    assert normalize_entity("Acme, Inc.") == "acme"
    assert normalize_period_label("FY 2025") == normalize_period_label("Fiscal Year 2025")
