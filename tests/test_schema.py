"""Worked examples and checks for the v0.2.0 schema."""

import json
import re
from pathlib import Path

import pydantic
import pytest
from pydantic import ValidationError

from opslm.export_schemas import MODELS, json_schemas, render
from opslm.schema import (
    ALLOWED_STATUSES,
    BusinessFact,
    EvalCase,
    GoldLabel,
    Period,
    Quantity,
    ReconciliationInput,
    ReconciliationOutput,
    Relationship,
    ResolutionStatus,
    evidence_recall,
)
from tests.factories import case, fact

DOCS = [
    {"doc_id": "acme-10k-fy2025", "company": "Acme Software", "document_family": "acme-fy2025",
     "doc_type": "10-K", "source_url": "https://example.com/acme-10k", "license_note": "SEC filing, public"},
    {"doc_id": "acme-deck-q4fy25", "company": "Acme Software", "document_family": "acme-fy2025",
     "doc_type": "investor_presentation"},
]

REVENUE_10K = {
    "fact_id": "f1", "metric_label": "Total revenue", "metric_id": "revenue",
    "entity": {"name": "Acme Software Inc.", "scope": "consolidated"},
    "period": {"type": "duration", "start": "2025-01-01", "end": "2025-12-31",
               "fiscal_year": 2025, "label": "FY2025"},
    "quantity": {"value": "42481000", "unit": "currency", "currency": "USD",
                 "reported_scale": "1000", "raw_text": "42,481"},
    "accounting_basis": "gaap", "reporting_status": "audited",
    "evidence": [{"span_id": "s1", "doc_id": "acme-10k-fy2025", "page": 54, "table_id": "t3",
                  "text": "Total revenue  42,481"}],
    "extraction": {"extractor": "docling", "confidence": 0.97},
}

SALES_DECK = {
    "fact_id": "f2", "metric_label": "Sales", "metric_id": "revenue",
    "entity": {"name": "Acme Software", "scope": "consolidated"},
    "period": {"type": "duration", "fiscal_year": 2025, "label": "FY2025"},  # no dates in the deck
    "quantity": {"value": "44100000", "unit": "currency", "currency": "USD",
                 "reported_scale": "1000000", "raw_text": "$44.1M"},
    "reporting_status": "unaudited",
    "evidence": [{"span_id": "s2", "doc_id": "acme-deck-q4fy25", "page": 7,
                  "text": "FY2025 Sales: $44.1M"}],
    "extraction": {"extractor": "docling", "confidence": 0.91},
}

ARR_DECK = {
    "fact_id": "f3", "metric_label": "ARR", "metric_id": "arr",
    "entity": {"name": "Acme Software", "scope": "consolidated"},
    "period": {"type": "instant", "as_of": "2025-12-31", "label": "as of Dec 31, 2025"},
    "quantity": {"value": "39200000", "unit": "currency", "currency": "USD",
                 "reported_scale": "1000000", "raw_text": "$39.2M"},
    "accounting_basis": "non_gaap", "reporting_status": "unaudited",
    "evidence": [{"span_id": "s3", "doc_id": "acme-deck-q4fy25", "page": 4,
                  "text": "ARR of $39.2M"}],
    "extraction": {"extractor": "docling"},
}


@pytest.fixture
def case1():
    return ReconciliationInput(case_id="c1", fact_a=REVENUE_10K, fact_b=SALES_DECK, documents=DOCS)


@pytest.fixture
def case2():
    return ReconciliationInput(case_id="c2", fact_a=REVENUE_10K, fact_b=ARR_DECK, documents=DOCS)


RESOLVED_CONFLICT = {
    "case_id": "c1", "relationship": "conflicting", "resolution_status": "resolved_with_conflict",
    "canonical_value": REVENUE_10K["quantity"], "selected_fact_id": "f1",
    "conflicting_fact_ids": ["f2"], "reasons": ["value_mismatch", "synonym"],
    "explanation": "Same metric, entity and period. The audited 10-K figure ($42.5M) is "
                   "preferred; the deck reports $44.1M, unaudited.",
    "evidence_refs": ["s1", "s2"],
    "run": {"system": "frontier_llm", "latency_ms": 1840, "cost_usd": 0.004},
}


def resolved_conflict(**kw):
    return ReconciliationOutput(**{**RESOLVED_CONFLICT, **kw})


# --- worked examples -----------------------------------------------------------------


def test_defaults_are_plain_strings_and_dates_may_be_unknown():
    f2 = BusinessFact(**SALES_DECK)
    assert f2.accounting_basis == "unknown" and type(f2.accounting_basis) is str
    assert not f2.period.dates_known and BusinessFact(**REVENUE_10K).period.dates_known


def test_classification_only_output_needs_no_resolution(case1):
    out = ReconciliationOutput(
        case_id="c1", relationship="conflicting", reasons=["value_mismatch", "synonym"],
        explanation="Same metric, entity and fiscal year; values differ by $1.6M.",
        evidence_refs=["s1", "s2"])
    assert out.resolution_status is None and out.check_references(case1) == []


def test_classification_with_resolution(case1):
    assert resolved_conflict().check_references(case1) == []


def test_different_concepts_and_evidence_recall(case2):
    out = ReconciliationOutput(
        case_id="c2", relationship="related_but_different", resolution_status="not_applicable",
        reasons=["definition_mismatch", "period_mismatch"],
        explanation="ARR is a point-in-time run-rate; revenue is recognized over the fiscal year.",
        evidence_refs=["s3"])
    gold = GoldLabel(case_id="c2", relationship="related_but_different", concept_same=False,
                     scope_same=None, reasons=["definition_mismatch"],
                     required_evidence_refs=["s1", "s3"], rationale="ARR is not revenue.",
                     split="test", source="real", labeled_by="nicole", guideline_version="1.1")
    assert out.check_references(case2) == []
    assert evidence_recall(out, gold) == 0.5  # cited a real span, but missed one the labeler required


def test_abstention_needs_no_evidence_or_value():
    out = ReconciliationOutput(case_id="c2", relationship="insufficient_evidence",
                               resolution_status="abstained", reasons=["missing_definition"],
                               explanation="ARR definition not stated.")
    assert out.abstained


# --- invalid records -----------------------------------------------------------------

INVALID_COMBINATIONS = [
    (rel.value, st.value) for rel in Relationship for st in ResolutionStatus
    if st.value not in ALLOWED_STATUSES[rel.value]
]


def test_twelve_invalid_combinations():
    assert len(INVALID_COMBINATIONS) == 12


@pytest.mark.parametrize("rel,status", INVALID_COMBINATIONS)
def test_relationship_status_outside_allowed_table_is_rejected(rel, status):
    kw = {}
    if status in ("resolved", "resolved_with_conflict"):
        kw = {"canonical_value": REVENUE_10K["quantity"], "selected_fact_id": "f1"}
    if status == "resolved_with_conflict":
        kw["conflicting_fact_ids"] = ["f2"]
    with pytest.raises(ValidationError):
        ReconciliationOutput(case_id="c1", relationship=rel, resolution_status=status,
                             reasons=["synonym"], explanation="x", evidence_refs=["s1"], **kw)


@pytest.mark.parametrize("build", [
    pytest.param(lambda: resolved_conflict(conflicting_fact_ids=[]),
                 id="conflict without naming the conflicting fact"),
    pytest.param(lambda: ReconciliationOutput(
        case_id="c1", relationship="equivalent", reasons=["synonym"], explanation="x"),
        id="decision with no evidence_refs"),
    pytest.param(lambda: ReconciliationOutput(
        case_id="c1", relationship="equivalent", reasons=["synonym"], explanation="x",
        evidence_refs=["s1"], conflicting_fact_ids=["f2"]),
        id="equivalent pair listing a conflict"),
    pytest.param(lambda: ReconciliationOutput(
        case_id="c1", relationship="equivalent", reasons=[], explanation="x", evidence_refs=["s1"]),
        id="no reasons"),
    pytest.param(lambda: Period(type="instant", start="2025-01-01", label="x"),
                 id="instant period with a start date"),
    pytest.param(lambda: Period(type="duration", as_of="2025-01-01", label="x"),
                 id="duration period with an as_of date"),
    pytest.param(lambda: Period(type="duration", start="2025-12-31", end="2025-01-01", label="x"),
                 id="period that ends before it starts"),
    pytest.param(lambda: BusinessFact(**{**REVENUE_10K, "evidence": []}), id="fact with no evidence"),
    pytest.param(lambda: BusinessFact(**{**REVENUE_10K, "basis": "gaap"}), id="old single 'basis' field"),
    pytest.param(lambda: BusinessFact(**{**REVENUE_10K, "quantity": {**REVENUE_10K["quantity"],
                                                                   "currency": None}}),
                 id="currency amount without a currency code"),
    pytest.param(lambda: BusinessFact(**{**REVENUE_10K, "evidence": [
        {"span_id": "s1", "doc_id": "d", "text": "x"}]}), id="evidence span with no location"),
    pytest.param(lambda: ReconciliationInput(case_id="c", fact_a=REVENUE_10K, fact_b=REVENUE_10K,
                                             documents=DOCS), id="pair of the same fact"),
    pytest.param(lambda: ReconciliationInput(case_id="c", fact_a=REVENUE_10K, fact_b=SALES_DECK,
                                             documents=DOCS[:1]), id="span from an unlisted document"),
])
def test_invalid_records_are_rejected(build):
    with pytest.raises(ValidationError):
        build()


def test_reference_check_on_a_fabricated_output(case1):
    bad = ReconciliationOutput(
        case_id="c1", relationship="equivalent", resolution_status="resolved",
        canonical_value={"value": "42500000", "unit": "currency", "currency": "EUR", "raw_text": "42.5"},
        selected_fact_id="f2", reasons=["rounding"], explanation="x", evidence_refs=["s1", "s9"])
    problems = bad.check_references(case1)
    assert problems == [
        "evidence_refs not in input: ['s9']",
        "canonical_value differs from the selected fact's value",
        "canonical_value currency differs from the selected fact's currency",
    ]


def test_reference_check_unknown_fact_and_case(case1):
    out = resolved_conflict(case_id="other", selected_fact_id="f9", conflicting_fact_ids=["f8"])
    problems = out.check_references(case1)
    assert "case_id does not match input" in problems
    assert "selected_fact_id f9 not in input" in problems and "conflicting fact f8 not in input" in problems


# --- eval cases ----------------------------------------------------------------------


def test_eval_case_json_roundtrip():
    c = case("c1", fact("a"), fact("b", "Total revenue"), "equivalent", tags=["synonym"])
    assert EvalCase.model_validate_json(c.model_dump_json()) == c


def test_label_must_follow_judgments():
    a, b = fact("a"), fact("b", value="50")
    # values differ, same concept and scope -> must be conflicting, not equivalent
    with pytest.raises(ValidationError, match="contradicts the judgments"):
        case("c1", a, b, "equivalent")
    with pytest.raises(ValidationError, match="contradicts the judgments"):
        case("c1", a, b, "conflicting", concept=False, reasons=("value_mismatch",))
    assert case("c1", a, b, "conflicting", reasons=("value_mismatch",)).gold.relationship == "conflicting"
    assert case("c1", a, fact("b"), "equivalent").gold.relationship == "equivalent"


def test_gold_label_must_record_both_judgments():
    with pytest.raises(ValidationError):
        GoldLabel(case_id="c", relationship="equivalent", reasons=["synonym"], rationale="r",
                  split="train", source="real", labeled_by="x", guideline_version="1.1")


def test_gold_references_must_exist_in_the_input():
    good = case("c1", fact("a"), fact("b"), "equivalent")
    with pytest.raises(ValidationError, match="required_evidence_refs not in input"):
        good.model_validate({**good.model_dump(), "gold": {**good.gold.model_dump(),
                                                           "required_evidence_refs": ["s9"]}})
    with pytest.raises(ValidationError, match="canonical_fact_id"):
        case("c1", fact("a"), fact("b"), "equivalent", canonical_fact_id="zzz")
    with pytest.raises(ValidationError, match="acceptable_statuses"):
        case("c1", fact("a"), fact("b"), "equivalent", acceptable_statuses=["abstained"])
    with pytest.raises(ValidationError, match="does not match input"):
        EvalCase(input=good.input, gold=good.gold.model_copy(update={"case_id": "c2"}))


# --- checked-in examples and JSON Schemas ----------------------------------------------


def test_example_case_file_is_valid():
    data = json.loads(Path("data/examples/example_case.json").read_text())
    inp = ReconciliationInput.model_validate(data["input"])
    out = ReconciliationOutput.model_validate(data["output"])
    assert out.check_references(inp) == []
    assert out.relationship == "conflicting" and out.selected_fact_id == "f1"


def _recorded_pydantic_version() -> str:
    return Path("schemas/pydantic_version.txt").read_text().strip()


@pytest.mark.parametrize("name", list(MODELS))
def test_checked_in_json_schemas_are_current(name):
    if pydantic.VERSION != _recorded_pydantic_version():
        pytest.skip(f"schemas were generated with pydantic {_recorded_pydantic_version()}; "
                    f"installed {pydantic.VERSION}. CI's 'schemas' job checks them at the recorded version.")
    path = Path("schemas") / f"{name}.schema.json"
    assert path.read_text() == render(json_schemas()[name]), (
        f"{path} is stale; run: python -m opslm.export_schemas")


def test_pydantic_version_file_is_a_real_version():
    assert re.fullmatch(r"\d+\.\d+\.\d+", _recorded_pydantic_version())


# --- Quantity validation ---------------------------------------------------------------------


def _q(**kw):
    base = {"value": "42500000", "unit": "currency", "currency": "USD",
            "reported_scale": "1000000", "raw_text": "$42.5M"}
    return Quantity(**{**base, **kw})


@pytest.mark.parametrize("scale", ["0", "-1000000"])
def test_reported_scale_must_be_positive(scale):
    with pytest.raises(ValidationError):
        _q(reported_scale=scale)


def test_currency_is_normalized_and_must_be_iso_shaped():
    assert _q(currency=" usd ").currency == "USD"
    for bad in ("DOLLARS", "US", "U$D", "1AB"):
        with pytest.raises(ValidationError):
            _q(currency=bad)


def test_currency_only_on_currency_quantities():
    with pytest.raises(ValidationError, match="Only currency quantities"):
        _q(unit="percent", currency="USD")
    assert _q(unit="percent", currency=None, reported_scale="1").currency is None


def test_values_agree_works_for_every_valid_scale():
    from opslm.labels import values_agree

    assert values_agree(_q(), _q(reported_scale="1000", raw_text="42,500")) is True


# --- reasons must fit the relationship ----------------------------------------------------------

from tests.factories import gold


@pytest.mark.parametrize(
    "relationship,reasons",
    [
        ("conflicting", ("exact_match", "synonym")),
        ("equivalent", ("value_mismatch",)),
        ("related_but_different", ("synonym",)),
        ("insufficient_evidence", ("value_mismatch",)),
        ("conflicting", ("value_mismatch", "period_mismatch")),
    ],
)
def test_reasons_that_contradict_the_relationship_are_rejected(relationship, reasons):
    concept, scope = {"equivalent": (True, True), "conflicting": (True, True),
                      "related_but_different": (False, True),
                      "insufficient_evidence": (None, True)}[relationship]
    with pytest.raises(ValidationError, match="reason"):
        gold("c1", relationship, concept, scope, reasons=reasons)


@pytest.mark.parametrize(
    "relationship,reasons",
    [
        ("equivalent", ("synonym", "rounding", "unit_scale")),
        ("conflicting", ("value_mismatch", "unit_scale")),
        ("conflicting", ("restatement", "value_mismatch")),
        ("conflicting", ("value_mismatch", "synonym")),
        ("related_but_different", ("definition_mismatch", "percent_vs_amount")),
        ("insufficient_evidence", ("missing_definition",)),
    ],
)
def test_sensible_reason_lists_are_accepted(relationship, reasons):
    concept, scope = {"equivalent": (True, True), "conflicting": (True, True),
                      "related_but_different": (False, True),
                      "insufficient_evidence": (None, True)}[relationship]
    assert gold("c1", relationship, concept, scope, reasons=reasons).reasons == list(reasons)


def test_reasons_problem_message_names_the_valid_choices():
    from opslm.schema import reasons_problem

    msg = reasons_problem("conflicting", ["synonym"])
    assert "value_mismatch" in msg and "restatement" in msg
    assert reasons_problem("equivalent", []) == "at least one reason is required"
