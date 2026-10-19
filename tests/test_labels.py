import pytest

from opslm.labels import derive_label, infer_reasons, values_agree
from opslm.schema import Period, Relationship
from tests.factories import fact, quantity

M, K, U = "1000000", "1000", "1"


def test_agree_across_scales():
    assert values_agree(quantity("42.5", M), quantity("42500", K))
    assert values_agree(quantity("42.5", M), quantity("42500000", U))


def test_agree_within_rounding_of_coarser_precision():
    assert values_agree(quantity("42.5", M), quantity("42540000", U))
    assert values_agree(quantity("42.5", M), quantity("42460000", U))


def test_disagree_outside_rounding():
    assert values_agree(quantity("42.5", M), quantity("42700000", U)) is False
    assert values_agree(quantity("42.5", M), quantity("44.1", M)) is False


def test_precise_values_must_match_exactly():
    assert values_agree(quantity("42500000", U), quantity("42500001", U)) is False


def test_scale_mistake_is_disagreement():
    assert values_agree(quantity("42.5", M), quantity("42.5", U)) is False


def test_different_currencies_or_units_not_comparable():
    assert values_agree(quantity("1", U, "USD"), quantity("1", U, "EUR")) is None
    assert values_agree(quantity("1", U, "usd"), quantity("1", U, "USD")) is True
    assert values_agree(quantity("72", U, unit="percent"), quantity("72", U)) is None


def test_percent_values_compare():
    assert values_agree(quantity("72", U, unit="percent"), quantity("72.0", U, unit="percent"))
    assert values_agree(quantity("72", U, unit="percent"), quantity("76", U, unit="percent")) is False


@pytest.mark.parametrize(
    "concept,scope,values,expected",
    [
        (True, True, True, Relationship.EQUIVALENT),
        (True, True, False, Relationship.CONFLICTING),
        (False, True, True, Relationship.RELATED_BUT_DIFFERENT),
        (True, False, False, Relationship.RELATED_BUT_DIFFERENT),
        (False, False, None, Relationship.RELATED_BUT_DIFFERENT),
        (False, None, None, Relationship.RELATED_BUT_DIFFERENT),
        (None, False, None, Relationship.INSUFFICIENT_EVIDENCE),
        (None, True, True, Relationship.INSUFFICIENT_EVIDENCE),
        (True, None, True, Relationship.INSUFFICIENT_EVIDENCE),
        (True, True, None, Relationship.INSUFFICIENT_EVIDENCE),
    ],
)
def test_decision_table(concept, scope, values, expected):
    assert derive_label(concept, scope, values) is expected


ASOF = Period(type="instant", label="as of Dec 31, 2025", as_of="2025-12-31")


@pytest.mark.parametrize(
    "a,b,judgments,culprits,expected",
    [
        (fact("a"), fact("b"), (True, True, True), (), ["exact_match"]),
        (fact("a"), fact("b", "Sales", "42500", scale="1000"), (True, True, True), (),
         ["synonym", "unit_scale"]),
        (fact("a"), fact("b", "Sales", "42540000", scale="1"), (True, True, True), (),
         ["synonym", "rounding", "unit_scale"]),
        (fact("a"), fact("b", value="44.1"), (True, True, False), (), ["value_mismatch"]),
        (fact("a"), fact("b", scale="1"), (True, True, False), (), ["value_mismatch", "unit_scale"]),
        (fact("a"), fact("b", currency="EUR"), (True, True, None), (), ["currency_mismatch"]),
        (fact("a"), fact("b", "ARR"), (False, True, None), ["metric"], ["definition_mismatch"]),
        (fact("a"), fact("b", basis="non_gaap"), (False, True, True), ["basis"], ["basis_mismatch"]),
        (fact("a", "Gross margin", "72", unit="percent", scale="1"), fact("b", "Gross profit"),
         (False, True, None), ["metric"], ["percent_vs_amount", "definition_mismatch"]),
        (fact("a"), fact("b", "Net revenue"), (None, True, True), ["metric"], ["missing_definition"]),
        (fact("a"), fact("b", period=Period(type="duration", label="Q3", fiscal_year=2025,
                                            fiscal_quarter=3)),
         (True, False, False), ["period"], ["period_mismatch"]),
        (fact("a", "ARR", period=ASOF), fact("b", "ARR", period=ASOF.model_copy(
            update={"as_of": "2024-12-31"})), (True, False, False), ["period"], ["as_of_mismatch"]),
        (fact("a"), fact("b", entity="Acme Europe Ltd"), (True, False, True), ["entity"],
         ["entity_mismatch"]),
        (fact("a", entity=None), fact("b"), (True, None, True), ["entity"], ["missing_entity"]),
        (fact("a", period=None), fact("b"), (True, None, True), [], ["missing_period"]),
    ],
)
def test_infer_reasons(a, b, judgments, culprits, expected):
    assert infer_reasons(a, b, *judgments, culprits) == expected


# --- sign conventions ----------------------------------------------------------------------------


def _loss(fid, metric, raw, value="-5.2"):
    f = fact(fid, metric, value)
    return f.model_copy(update={"quantity": f.quantity.model_copy(update={"raw_text": raw})})


def test_a_loss_written_two_ways_is_a_sign_convention_equivalent():
    a, b = _loss("a", "Net income (loss)", "(5.2)"), _loss("b", "Net loss", "5.2")
    assert infer_reasons(a, b, True, True, True) == ["sign_convention", "synonym"]
    c = _loss("c", "Net income", "-5.2")
    assert infer_reasons(a, c, True, True, True)[0] == "sign_convention"


def test_the_same_style_on_both_sides_is_not_a_sign_convention_issue():
    a, b = _loss("a", "Net income", "(5.2)"), _loss("b", "Net earnings", "(5.2)")
    assert infer_reasons(a, b, True, True, True) == ["synonym"]


def test_opposite_signs_add_sign_convention_to_a_value_conflict():
    a, b = _loss("a", "Net income", "(5.2)"), fact("b", "Net income", "5.2")
    assert infer_reasons(a, b, True, True, False) == ["value_mismatch", "sign_convention"]
