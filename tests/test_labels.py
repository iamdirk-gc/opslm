from decimal import Decimal

import pytest

from opslm.labels import derive_label, values_agree
from opslm.schema import BusinessFact, Relation, Scale, SourceRef


def fact(value, scale=Scale.UNITS, unit="USD"):
    return BusinessFact(
        fact_id="f",
        metric="Revenue",
        value=None if value is None else Decimal(value),
        unit=unit,
        scale=scale,
        source=SourceRef(document_id="d"),
    )


def test_agree_across_scales():
    assert values_agree(fact("42.5", Scale.MILLIONS), fact("42500", Scale.THOUSANDS))
    assert values_agree(fact("42.5", Scale.MILLIONS), fact("42500000"))


def test_agree_within_rounding_of_coarser_precision():
    assert values_agree(fact("42.5", Scale.MILLIONS), fact("42540000"))
    assert values_agree(fact("42.5", Scale.MILLIONS), fact("42460000"))


def test_disagree_outside_rounding():
    assert values_agree(fact("42.5", Scale.MILLIONS), fact("42700000")) is False
    assert values_agree(fact("42.5", Scale.MILLIONS), fact("44.1", Scale.MILLIONS)) is False


def test_precise_values_must_match_exactly():
    assert values_agree(fact("42500000"), fact("42500001")) is False


def test_scale_mistake_is_disagreement():
    assert values_agree(fact("42.5", Scale.MILLIONS), fact("42.5")) is False


@pytest.mark.parametrize(
    "a,b",
    [(None, "1"), ("1", None)],
)
def test_missing_value_not_comparable(a, b):
    assert values_agree(fact(a), fact(b)) is None


def test_different_or_missing_units_not_comparable():
    assert values_agree(fact("1", unit="USD"), fact("1", unit="EUR")) is None
    assert values_agree(fact("1", unit=None), fact("1", unit="USD")) is None
    assert values_agree(fact("1", unit="usd"), fact("1", unit="USD")) is True


@pytest.mark.parametrize(
    "concept,scope,values,expected",
    [
        (True, True, True, Relation.EQUIVALENT),
        (True, True, False, Relation.CONFLICTING),
        (False, True, True, Relation.RELATED_BUT_DIFFERENT),
        (True, False, False, Relation.RELATED_BUT_DIFFERENT),
        (False, False, None, Relation.RELATED_BUT_DIFFERENT),
        (None, True, True, Relation.INSUFFICIENT_EVIDENCE),
        (True, None, True, Relation.INSUFFICIENT_EVIDENCE),
        (True, True, None, Relation.INSUFFICIENT_EVIDENCE),
    ],
)
def test_decision_table(concept, scope, values, expected):
    assert derive_label(concept, scope, values) is expected
