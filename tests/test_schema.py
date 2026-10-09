from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from opslm.schema import (
    BusinessFact,
    EvalCase,
    FactPair,
    Period,
    PeriodType,
    Relation,
    Scale,
    SourceKind,
    SourceRef,
    Split,
)


def make_fact(fact_id="f1", metric="Revenue", value="42.5", **kw):
    return BusinessFact(
        fact_id=fact_id,
        metric=metric,
        value=Decimal(value),
        unit="USD",
        scale=Scale.MILLIONS,
        entity="Acme Corp",
        period=Period(label="FY2025", type=PeriodType.FISCAL_YEAR),
        source=SourceRef(document_id="doc1", location="p.14"),
        **kw,
    )


def test_absolute_value_applies_scale():
    assert make_fact().absolute_value == Decimal(42500000)


def test_absolute_value_none_when_missing():
    fact = BusinessFact(fact_id="x", metric="ARR", source=SourceRef(document_id="d"))
    assert fact.absolute_value is None


def test_pair_requires_distinct_facts():
    with pytest.raises(ValidationError):
        FactPair(fact_a=make_fact("f1"), fact_b=make_fact("f1"))


def test_period_rejects_reversed_dates():
    with pytest.raises(ValidationError):
        Period(label="bad", start=date(2025, 12, 31), end=date(2025, 1, 1))


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        SourceRef(document_id="d", bogus=1)


def test_eval_case_json_roundtrip():
    case = EvalCase(
        case_id="c1",
        scenario_id="s1",
        pair=FactPair(fact_a=make_fact("f1", "Revenue"), fact_b=make_fact("f2", "Net Revenue")),
        label=Relation.EQUIVALENT,
        rationale="Same entity, period and value; net revenue is the reported revenue line.",
        source_kind=SourceKind.SYNTHETIC,
        split=Split.TEST,
        tags=("synonym",),
    )
    assert EvalCase.model_validate_json(case.model_dump_json()) == case
