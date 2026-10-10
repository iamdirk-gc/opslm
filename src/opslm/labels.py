"""Deterministic parts of reconciliation: value comparison and the label decision table.

A model judges meaning (same concept? same scope?). Code compares numbers and combines
the judgments into a final label, so a system can never call two facts ``equivalent``
when their normalized values disagree. See docs/labeling-guidelines.md.
"""

from __future__ import annotations

from decimal import Decimal

from opslm.schema import BusinessFact, Relation

GUIDELINE_VERSION = "1.1"


def _half_unit(fact: BusinessFact) -> Decimal:
    """Absolute rounding tolerance implied by the precision the value was reported at."""
    assert fact.value is not None
    exponent = fact.value.as_tuple().exponent
    assert isinstance(exponent, int)
    return Decimal(10) ** exponent / 2 * int(fact.scale)


def values_agree(a: BusinessFact, b: BusinessFact) -> bool | None:
    """Whether two facts report the same number once scale is applied.

    Values agree when they differ by no more than the rounding implied by the coarser
    reported precision (so 42.5 in millions agrees with 42,540,000 but not 42,700,000).
    Returns None when the values are not comparable: a value is missing, a unit is
    missing, or the units differ (no currency conversion is attempted).
    """
    if a.value is None or b.value is None:
        return None
    if a.unit is None or b.unit is None or a.unit.casefold() != b.unit.casefold():
        return None
    assert a.absolute_value is not None and b.absolute_value is not None
    return abs(a.absolute_value - b.absolute_value) <= max(_half_unit(a), _half_unit(b))


def derive_label(
    concept_same: bool | None, scope_same: bool | None, values_agree: bool | None
) -> Relation:
    """Combine the three judgments into the final label. None means undeterminable.

    A different concept settles the label whatever the scope. Otherwise the concept must be
    known; then a different scope settles it; then scope and value comparison must be known.
    """
    if concept_same is False:
        return Relation.RELATED_BUT_DIFFERENT
    if concept_same is None:
        return Relation.INSUFFICIENT_EVIDENCE
    if scope_same is False:
        return Relation.RELATED_BUT_DIFFERENT
    if scope_same is None or values_agree is None:
        return Relation.INSUFFICIENT_EVIDENCE
    return Relation.EQUIVALENT if values_agree else Relation.CONFLICTING
