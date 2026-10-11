"""Deterministic parts of reconciliation: value comparison and the label decision table.

A model judges meaning (same concept? same scope?). Code compares numbers and combines
the judgments into a final label, so a system can never call two facts ``equivalent``
when their normalized values disagree. See docs/labeling-guidelines.md.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from opslm.schema import BusinessFact, PeriodType, Quantity, ReasonCode, Relationship

GUIDELINE_VERSION = "1.1"


def _half_unit(q: Quantity) -> Decimal:
    """Absolute rounding tolerance implied by the precision the value was reported at."""
    exponent = q.reported_value.as_tuple().exponent
    assert isinstance(exponent, int)
    return Decimal(10) ** exponent / 2 * q.reported_scale


def values_agree(a: Quantity, b: Quantity) -> bool | None:
    """Whether two quantities report the same number.

    Values agree when they differ by no more than the rounding implied by the coarser
    reported precision (so 42.5 in millions agrees with 42,540,000 but not 42,700,000).
    Returns None when the values are not comparable: the units differ, or the currencies
    differ (no currency conversion is attempted).
    """
    if a.unit != b.unit:
        return None
    if (a.currency or "").upper() != (b.currency or "").upper():
        return None
    return abs(a.value - b.value) <= max(_half_unit(a), _half_unit(b))


def derive_label(
    concept_same: bool | None, scope_same: bool | None, values_agree: bool | None
) -> Relationship:
    """Combine the three judgments into the final label. None means undeterminable.

    A different concept settles the label whatever the scope. Otherwise the concept must be
    known; then a different scope settles it; then scope and value comparison must be known.
    """
    if concept_same is False:
        return Relationship.RELATED_BUT_DIFFERENT
    if concept_same is None:
        return Relationship.INSUFFICIENT_EVIDENCE
    if scope_same is False:
        return Relationship.RELATED_BUT_DIFFERENT
    if scope_same is None or values_agree is None:
        return Relationship.INSUFFICIENT_EVIDENCE
    return Relationship.EQUIVALENT if values_agree else Relationship.CONFLICTING


def _sign_style(q: Quantity) -> str:
    """How a number's sign was presented: '(5.2)', '-5.2', or no mark at all (the label, such as
    'Net loss', carries the sign)."""
    if q.value >= 0:
        return "positive"
    raw = q.raw_text.strip()
    return "paren" if raw.startswith("(") else "minus" if raw[:1] in "-\u2212" else "label"


def infer_reasons(
    a: BusinessFact,
    b: BusinessFact,
    concept_same: bool | None,
    scope_same: bool | None,
    agree: bool | None,
    culprits: Iterable[str] = (),
) -> list[ReasonCode]:
    """Reason codes for a system's judgments, primary reason first.

    ``culprits`` names the fact fields behind any judgment that is not a clean yes
    ("metric", "definition", "basis", "entity", "period"). Systems that only produce the
    judgments use this so their reasons are comparable with the gold labels.
    """
    fields = set(culprits)
    qa, qb = a.quantity, b.quantity
    reasons: list[ReasonCode] = []
    if concept_same is False:
        if qa.unit != qb.unit and {qa.unit, qb.unit} <= {"percent", "currency"}:
            reasons.append(ReasonCode.PERCENT_VS_AMOUNT)
        reasons.append(ReasonCode.BASIS_MISMATCH if fields == {"basis"}
                       else ReasonCode.DEFINITION_MISMATCH)
    elif concept_same is None:
        reasons.append(ReasonCode.MISSING_DEFINITION)
    elif scope_same is False:
        if "period" in fields or not fields:
            instant = PeriodType.INSTANT.value in {p.type for p in (a.period, b.period) if p}
            reasons.append(ReasonCode.AS_OF_MISMATCH if instant else ReasonCode.PERIOD_MISMATCH)
        if "entity" in fields:
            reasons.append(ReasonCode.ENTITY_MISMATCH)
    elif scope_same is None:
        if "period" in fields or a.period is None or b.period is None:
            reasons.append(ReasonCode.MISSING_PERIOD)
        if "entity" in fields or a.entity is None or b.entity is None:
            reasons.append(ReasonCode.MISSING_ENTITY)
    elif agree is None:
        reasons.append(ReasonCode.CURRENCY_MISMATCH if qa.unit == qb.unit
                       else ReasonCode.PERCENT_VS_AMOUNT)
    elif agree is False:
        reasons.append(ReasonCode.VALUE_MISMATCH)
        if qa.reported_value == qb.reported_value and qa.reported_scale != qb.reported_scale:
            reasons.append(ReasonCode.UNIT_SCALE)
        if qa.value == -qb.value:  # same magnitude, opposite sign: a sign was lost or flipped
            reasons.append(ReasonCode.SIGN_CONVENTION)
    else:
        same_label = a.metric_label.casefold() == b.metric_label.casefold()
        reasons.append(ReasonCode.EXACT_MATCH if same_label else ReasonCode.SYNONYM)
        if qa.value != qb.value:
            reasons.append(ReasonCode.ROUNDING)
        if qa.reported_scale != qb.reported_scale:
            reasons.append(ReasonCode.UNIT_SCALE)
        if qa.value < 0 and qb.value < 0 and _sign_style(qa) != _sign_style(qb):
            reasons.insert(0, ReasonCode.SIGN_CONVENTION)  # a loss shown two different ways
    return reasons or [ReasonCode.UNSUPPORTED_CLAIM]
