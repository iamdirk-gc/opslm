from datetime import date
from decimal import Decimal

import pytest

from opslm.baselines.rules import RulesBaseline, normalize_entity, normalize_period_label
from opslm.schema import (
    BusinessFact,
    FactPair,
    Period,
    PeriodType,
    Relation,
    Scale,
    SourceRef,
)

FY25 = Period(label="FY2025", type=PeriodType.FISCAL_YEAR)


def fact(metric="Revenue", value="42.5", fid="f", entity="Acme Corp", period=FY25,
         unit="USD", scale=Scale.MILLIONS, qualifiers=()):
    return BusinessFact(
        fact_id=fid, metric=metric, value=None if value is None else Decimal(value), unit=unit,
        scale=scale, entity=entity, period=period, qualifiers=qualifiers,
        source=SourceRef(document_id="d"),
    )


def predict(a, b):
    return RulesBaseline().predict("c", FactPair(fact_a=a, fact_b=b))


def test_plan_example_equivalent():
    assert predict(fact("Revenue"), fact("Total Revenue", fid="g")).label is Relation.EQUIVALENT


def test_plan_example_conflicting():
    p = predict(fact("Revenue"), fact("Sales", "44.1", fid="g"))
    assert p.label is Relation.CONFLICTING
    assert {e.field for e in p.evidence} == {"value", "scale"}


def test_plan_example_arr_is_different_concept():
    p = predict(fact("Revenue"), fact("ARR", "39.2", fid="g"))
    assert p.label is Relation.RELATED_BUT_DIFFERENT and p.concept_same is False


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
    assert predict(fact(a), fact(b, fid="g")).concept_same is same


def test_qualifier_marker_changes_concept():
    p = predict(fact("EBITDA", qualifiers=("adjusted",)), fact("EBITDA", fid="g"))
    assert p.concept_same is False


def test_neutral_qualifier_ignored():
    p = predict(fact("Revenue", qualifiers=("GAAP",)), fact("Revenue", fid="g"))
    assert p.concept_same is True


def test_period_mismatch_is_related_but_different():
    q3 = Period(label="Q3 2025", type=PeriodType.QUARTER)
    p = predict(fact(), fact(value="11.0", fid="g", period=q3))
    assert p.label is Relation.RELATED_BUT_DIFFERENT and p.scope_same is False
    assert {e.field for e in p.evidence} == {"period"}


def test_entity_mismatch_is_related_but_different():
    p = predict(fact(), fact(fid="g", entity="Acme Europe Ltd"))
    assert p.label is Relation.RELATED_BUT_DIFFERENT
    assert {e.field for e in p.evidence} == {"entity"}


def test_entity_suffix_and_case_ignored():
    assert predict(fact(entity="ACME, Inc."), fact(fid="g", entity="Acme Corporation")).scope_same


def test_missing_entity_is_insufficient():
    p = predict(fact(entity=None), fact(fid="g"))
    assert p.label is Relation.INSUFFICIENT_EVIDENCE
    assert {e.field for e in p.evidence} == {"entity"}


def test_missing_period_is_insufficient():
    assert predict(fact(period=None), fact(fid="g")).label is Relation.INSUFFICIENT_EVIDENCE


def test_currency_mismatch_is_insufficient():
    p = predict(fact(), fact(fid="g", unit="EUR", value="39.0"))
    assert p.label is Relation.INSUFFICIENT_EVIDENCE
    assert {e.field for e in p.evidence} == {"value", "unit"}


def test_scale_error_is_conflicting():
    p = predict(fact(), fact(fid="g", scale=Scale.UNITS))
    assert p.label is Relation.CONFLICTING


def test_dates_override_labels():
    a = Period(label="FY2025", type=PeriodType.FISCAL_YEAR, start=date(2024, 7, 1), end=date(2025, 6, 30))
    b = Period(label="Fiscal 2025", type=PeriodType.FISCAL_YEAR, start=date(2024, 7, 1), end=date(2025, 6, 30))
    c = Period(label="FY2025", type=PeriodType.FISCAL_YEAR, start=date(2025, 1, 1), end=date(2025, 12, 31))
    assert predict(fact(period=a), fact(fid="g", period=b)).scope_same is True
    assert predict(fact(period=a), fact(fid="g", period=c)).scope_same is False


def test_prediction_records_latency_and_zero_cost():
    p = predict(fact(), fact(fid="g"))
    assert p.latency_s is not None and p.latency_s >= 0 and p.cost_usd == 0.0


def test_normalizers():
    assert normalize_entity("Acme, Inc.") == "acme"
    assert normalize_period_label("FY 2025") == normalize_period_label("Fiscal Year 2025")
