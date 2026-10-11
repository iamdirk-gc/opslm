"""OpsLM v1 schema: canonical business facts and pairwise reconciliation.

Four layers, each a separate model so extraction and reconciliation can be
evaluated independently:

1. Provenance   SourceDocument, EvidenceSpan   where a fact came from
2. Facts        BusinessFact                   what a document claims
3. Task input   ReconciliationInput            two facts to compare
4. Task output  ReconciliationOutput           what a model decides
                GoldLabel                      what a labeler decided (eval only)

An ``EvalCase`` (one line of a dataset file) is an input with its gold label.

v1 scope: pairwise comparison of two facts for the metrics in
docs/metric-set-v1.md (mirrored on the project wiki). Clustering of 3+ facts is built on top of pairs later.

Primary benchmark task: classify the relationship between two facts.
Canonical resolution (picking a value) is optional and scored separately; a
system that returns only a relationship, reasons and evidence is valid.

The relationship follows from two judgments (same concept? same scope?) and a
value comparison done in code, as set out in docs/labeling-guidelines.md. Gold
labels record both judgments, and an EvalCase is rejected if its relationship
does not follow from them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCHEMA_VERSION = "0.2.0"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_enum_values=True,
                              validate_default=True)


# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------

class MetricId(str, Enum):
    """Canonical metric IDs, matching the v1 metric set on the wiki.

    Core: revenue, gross_margin, adjusted_ebitda, net_income.
    Optional: arr (subscription businesses only; not expected for every company).
    Free cash flow and cash are out of scope for v1. Facts for them, or for any
    other metric, map to OTHER.
    """
    REVENUE = "revenue"
    GROSS_MARGIN = "gross_margin"
    ADJUSTED_EBITDA = "adjusted_ebitda"
    NET_INCOME = "net_income"
    ARR = "arr"
    OTHER = "other"  # extracted fact that maps to none of the above


CORE_METRICS = frozenset({MetricId.REVENUE.value, MetricId.GROSS_MARGIN.value,
                          MetricId.ADJUSTED_EBITDA.value, MetricId.NET_INCOME.value})
OPTIONAL_METRICS = frozenset({MetricId.ARR.value})


class EntityScope(str, Enum):
    CONSOLIDATED = "consolidated"
    ATTRIBUTABLE_TO_PARENT = "attributable_to_parent"
    SEGMENT = "segment"
    SUBSIDIARY = "subsidiary"
    PRO_FORMA = "pro_forma"  # e.g. including an acquisition
    UNKNOWN = "unknown"


class PeriodType(str, Enum):
    DURATION = "duration"  # flow metrics: revenue, gross margin, adjusted EBITDA, net income
    INSTANT = "instant"    # point-in-time metrics: ARR


class AccountingBasis(str, Enum):
    """Which accounting rules produced the number."""
    GAAP = "gaap"
    IFRS = "ifrs"
    NON_GAAP = "non_gaap"
    UNKNOWN = "unknown"


class ReportingStatus(str, Enum):
    """Assurance level of the source, independent of accounting basis.
    Management can report unaudited GAAP revenue: gaap + unaudited."""
    AUDITED = "audited"
    UNAUDITED = "unaudited"
    UNKNOWN = "unknown"


class UnitType(str, Enum):
    CURRENCY = "currency"
    PERCENT = "percent"
    RATIO = "ratio"
    COUNT = "count"


class Relationship(str, Enum):
    """The core classification label."""
    EQUIVALENT = "equivalent"
    RELATED_BUT_DIFFERENT = "related_but_different"
    CONFLICTING = "conflicting"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ResolutionStatus(str, Enum):
    """What the system does with the pair."""
    RESOLVED = "resolved"                     # one canonical value, no open issue
    RESOLVED_WITH_CONFLICT = "resolved_with_conflict"  # canonical value picked, conflicting source flagged
    NOT_APPLICABLE = "not_applicable"         # different concepts; nothing to resolve
    NEEDS_REVIEW = "needs_review"             # route to an analyst
    ABSTAINED = "abstained"                   # not enough evidence to decide


class ReasonCode(str, Enum):
    """Why the facts match or differ. Also used as difficulty slices in eval."""
    EXACT_MATCH = "exact_match"
    SYNONYM = "synonym"
    ROUNDING = "rounding"
    UNIT_SCALE = "unit_scale"              # $42.5M vs $42,481K
    SIGN_CONVENTION = "sign_convention"    # -5.2 vs (5.2) vs "net loss of 5.2"
    PERCENT_VS_AMOUNT = "percent_vs_amount"
    CURRENCY_MISMATCH = "currency_mismatch"  # USD vs EUR, no conversion available
    PERIOD_MISMATCH = "period_mismatch"    # FY vs LTM, fiscal vs calendar
    AS_OF_MISMATCH = "as_of_mismatch"      # instant metrics at different dates
    ENTITY_MISMATCH = "entity_mismatch"
    DEFINITION_MISMATCH = "definition_mismatch"
    BASIS_MISMATCH = "basis_mismatch"      # GAAP vs non-GAAP
    RESTATEMENT = "restatement"
    VALUE_MISMATCH = "value_mismatch"      # same concept, different number
    MISSING_DEFINITION = "missing_definition"
    MISSING_PERIOD = "missing_period"
    MISSING_ENTITY = "missing_entity"
    UNSUPPORTED_CLAIM = "unsupported_claim"


# Which reasons can be the primary reason for each relationship. Secondary reasons may also come
# from DESCRIPTIVE_REASONS, which describe how the facts were named or how their numbers were
# shown, whatever the relationship (for example a conflict between two synonymous labels).
PRIMARY_REASONS: dict[str, frozenset[str]] = {
    "equivalent": frozenset({"exact_match", "synonym", "rounding", "unit_scale", "sign_convention"}),
    "conflicting": frozenset({"value_mismatch", "restatement"}),
    "related_but_different": frozenset({
        "definition_mismatch", "basis_mismatch", "percent_vs_amount", "period_mismatch",
        "as_of_mismatch", "entity_mismatch"}),
    "insufficient_evidence": frozenset({
        "missing_definition", "missing_period", "missing_entity", "currency_mismatch",
        "percent_vs_amount", "unsupported_claim"}),
}
DESCRIPTIVE_REASONS = frozenset({"synonym", "unit_scale", "rounding", "sign_convention"})


def _value(x: object) -> str:
    return str(getattr(x, "value", x))


def reasons_problem(relationship: object, reasons: Iterable[object]) -> str | None:
    """Why a reason list does not fit a relationship, or None if it does. Primary reason first."""
    rel, codes = _value(relationship), [_value(r) for r in reasons]
    if not codes:
        return "at least one reason is required"
    primary_ok = PRIMARY_REASONS[rel]
    if codes[0] not in primary_ok:
        return (f"primary reason '{codes[0]}' does not fit relationship '{rel}'; "
                f"use one of: {', '.join(sorted(primary_ok))}")
    extra = [c for c in codes[1:] if c not in primary_ok | DESCRIPTIVE_REASONS]
    if extra:
        return f"reasons {extra} do not fit relationship '{rel}'"
    return None


class Split(str, Enum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class Source(str, Enum):
    """Where a case came from."""
    REAL = "real"
    SYNTHETIC = "synthetic"


# ---------------------------------------------------------------------------
# 1. Provenance
# ---------------------------------------------------------------------------

class SourceDocument(_Model):
    doc_id: str = Field(description="Stable ID, e.g. 'acme-10k-fy2025'.")
    company: str
    document_family: str = Field(
        description="Groups related docs for the train/eval split, e.g. 'acme-fy2025'.")
    doc_type: str = Field(description="10-K, 10-Q, earnings_deck, investor_presentation, workbook, ...")
    title: str | None = None
    source_url: str | None = None
    retrieved_at: datetime | None = None
    content_sha256: str | None = Field(default=None, description="Hash of the exact file parsed.")
    license_note: str | None = Field(
        default=None, description="Redistribution terms or restriction (task 2.4).")


class EvidenceSpan(_Model):
    """An exact location in a source document. Every fact and every
    reconciliation decision must point at one or more of these."""
    span_id: str
    doc_id: str
    page: int | None = None
    table_id: str | None = None
    cell_ref: str | None = Field(default=None, description="e.g. 'R12C4' or 'B17' for workbooks.")
    char_start: int | None = None
    char_end: int | None = None
    text: str = Field(description="Verbatim text of the span as extracted.")

    @model_validator(mode="after")
    def _has_location(self):
        if self.page is None and self.cell_ref is None and self.char_start is None:
            raise ValueError("EvidenceSpan needs a page, cell_ref or char offset.")
        if (self.char_start is None) != (self.char_end is None):
            raise ValueError("char_start and char_end must be set together.")
        return self


# ---------------------------------------------------------------------------
# 2. Facts
# ---------------------------------------------------------------------------

class Entity(_Model):
    name: str
    scope: EntityScope = EntityScope.CONSOLIDATED
    segment: str | None = None


class Period(_Model):
    """A reporting period.

    Expected behavior when dates are missing (common in decks):
    - Unknown dates are allowed. A DURATION may omit start/end and an INSTANT
      may omit as_of; None means "not stated in the source", not invalid.
    - The minimum valid period is the source label. fiscal_year plus label
      ("FY2025") is enough to compare against another period that states the
      same fiscal year. It is NOT enough to match a calendar-dated period
      ("year ended Dec 31, 2025") unless the fiscal year end is known.
    - Invalid records are ones that contradict themselves: an INSTANT with
      start/end, a DURATION with as_of, or start after end.
    """
    type: PeriodType
    start: date | None = None   # DURATION
    end: date | None = None     # DURATION
    as_of: date | None = None   # INSTANT
    fiscal_year: int | None = None
    fiscal_quarter: int | None = Field(default=None, ge=1, le=4)
    is_ltm: bool = False
    label: str = Field(description="As written in the source, e.g. 'FY2025', 'Q3 FY25'.")

    @model_validator(mode="after")
    def _consistent(self):
        if self.type == PeriodType.INSTANT.value and (self.start or self.end):
            raise ValueError("INSTANT periods use as_of, not start/end.")
        if self.type == PeriodType.DURATION.value and self.as_of:
            raise ValueError("DURATION periods use start/end, not as_of.")
        if self.start and self.end and self.start > self.end:
            raise ValueError("Period start is after end.")
        return self

    @property
    def dates_known(self) -> bool:
        if self.type == PeriodType.INSTANT.value:
            return self.as_of is not None
        return self.start is not None and self.end is not None


class Quantity(_Model):
    value: Decimal = Field(description="Normalized to base units: 42500000, not 42.5.")
    unit: UnitType
    currency: str | None = Field(default=None, description="ISO 4217, required for CURRENCY.")
    reported_scale: Decimal = Field(
        default=Decimal(1), gt=0,
        description="Scale as shown in the source: 1e6 for '$ in millions'. Must be positive.")
    raw_text: str = Field(description="Value exactly as printed, e.g. '(5.2)' or '$42.5M'.")

    @field_validator("currency", mode="before")
    @classmethod
    def _normalize_currency(cls, v):
        return v.strip().upper() if isinstance(v, str) else v

    @model_validator(mode="after")
    def _currency(self):
        is_currency = self.unit == UnitType.CURRENCY.value
        if is_currency and not self.currency:
            raise ValueError("Currency quantities need an ISO currency code.")
        if self.currency is not None:
            if not re.fullmatch(r"[A-Z]{3}", self.currency):
                raise ValueError(f"currency must be a three-letter ISO 4217 code, got {self.currency!r}")
            if not is_currency:
                raise ValueError("Only currency quantities may have a currency code.")
        return self

    @property
    def reported_value(self) -> Decimal:
        """The number in the scale it was reported at: 42.5 for $42.5M. Its precision sets
        the rounding tolerance when two values are compared."""
        return self.value / self.reported_scale


class ExtractionInfo(_Model):
    extractor: str = Field(description="'docling', 'azure_di', 'manual', 'synthetic', ...")
    extractor_version: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class BusinessFact(_Model):
    """One value a document claims.

    ``entity`` and ``period`` may be None when the source does not state them; such facts
    can still be compared, but scope cannot be established (insufficient evidence)."""
    fact_id: str
    metric_label: str = Field(description="Label as written: 'Net sales', 'Adj. EBITDA'.")
    metric_id: MetricId = Field(description="Canonical mapping; OTHER if none applies.")
    entity: Entity | None = Field(default=None, description="None means not stated in the source.")
    period: Period | None = Field(default=None, description="None means not stated in the source.")
    quantity: Quantity
    accounting_basis: AccountingBasis = AccountingBasis.UNKNOWN
    reporting_status: ReportingStatus = ReportingStatus.UNKNOWN
    stated_definition: str | None = Field(
        default=None, description="Definition text if the document gives one. None means not stated.")
    evidence: list[EvidenceSpan] = Field(min_length=1)
    extraction: ExtractionInfo


# ---------------------------------------------------------------------------
# 3. Task input
# ---------------------------------------------------------------------------

class ReconciliationInput(_Model):
    """One eval/training case. The model sees only this."""
    schema_version: str = SCHEMA_VERSION
    case_id: str
    fact_a: BusinessFact
    fact_b: BusinessFact
    documents: list[SourceDocument] = Field(
        description="Metadata for every doc_id referenced by the facts.")
    context: list[EvidenceSpan] = Field(
        default_factory=list,
        description="Optional extra spans, e.g. a definition footnote or reconciliation table.")

    def span_ids(self) -> set[str]:
        spans = [*self.fact_a.evidence, *self.fact_b.evidence, *self.context]
        return {s.span_id for s in spans}

    def fact_ids(self) -> set[str]:
        return {self.fact_a.fact_id, self.fact_b.fact_id}

    def document_families(self) -> set[str]:
        return {d.document_family for d in self.documents}

    @model_validator(mode="after")
    def _docs_present(self):
        known = {d.doc_id for d in self.documents}
        for s in [*self.fact_a.evidence, *self.fact_b.evidence, *self.context]:
            if s.doc_id not in known:
                raise ValueError(f"span {s.span_id} references unknown doc {s.doc_id}")
        if self.fact_a.fact_id == self.fact_b.fact_id:
            raise ValueError("fact_a and fact_b must be different facts.")
        return self


# ---------------------------------------------------------------------------
# 4. Task output
# ---------------------------------------------------------------------------

class ModelRunInfo(_Model):
    system: str = Field(description="'rules', 'frontier_llm', 'open_weight_base', 'open_weight_ft'.")
    model_name: str | None = None
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None


# Which resolution statuses make sense for each relationship.
ALLOWED_STATUSES: dict[str, set[str]] = {
    Relationship.EQUIVALENT.value: {ResolutionStatus.RESOLVED.value,
                                    ResolutionStatus.NEEDS_REVIEW.value},
    Relationship.CONFLICTING.value: {ResolutionStatus.RESOLVED_WITH_CONFLICT.value,
                                     ResolutionStatus.NEEDS_REVIEW.value},
    Relationship.RELATED_BUT_DIFFERENT.value: {ResolutionStatus.NOT_APPLICABLE.value,
                                               ResolutionStatus.NEEDS_REVIEW.value},
    Relationship.INSUFFICIENT_EVIDENCE.value: {ResolutionStatus.ABSTAINED.value,
                                               ResolutionStatus.NEEDS_REVIEW.value},
}


class ReconciliationOutput(_Model):
    """What every system (rules, LLM, open-weight) must return.

    Required: relationship, reasons, explanation, and evidence_refs (unless the
    relationship is insufficient_evidence). Resolution fields are optional;
    leave resolution_status as None for a classification-only system.

    Systems that follow the guidelines' decision table also report the judgments
    behind the relationship (concept_same, scope_same, values_agree), which the
    harness scores separately. None means "cannot tell" or "not reported".
    """
    schema_version: str = SCHEMA_VERSION
    case_id: str
    relationship: Relationship
    resolution_status: ResolutionStatus | None = None
    canonical_value: Quantity | None = Field(
        default=None, description="The value the system settles on, if any.")
    selected_fact_id: str | None = Field(
        default=None, description="Which input fact the canonical value comes from.")
    conflicting_fact_ids: list[str] = Field(default_factory=list)
    reasons: list[ReasonCode] = Field(min_length=1)
    explanation: str = Field(max_length=1000, description="One or two sentences, human readable.")
    evidence_refs: list[str] = Field(
        default_factory=list, description="span_ids from the input that support the decision.")
    concept_same: bool | None = Field(default=None, description="Judgment 1: same business concept?")
    scope_same: bool | None = Field(default=None, description="Judgment 2: same entity and period?")
    values_agree: bool | None = Field(
        default=None, description="Normalized values agree? None = not comparable.")
    run: ModelRunInfo | None = None

    @property
    def abstained(self) -> bool:
        return (self.resolution_status == ResolutionStatus.ABSTAINED.value
                or self.relationship == Relationship.INSUFFICIENT_EVIDENCE.value)

    @model_validator(mode="after")
    def _internally_consistent(self):
        rel, status = self.relationship, self.resolution_status
        resolving = {ResolutionStatus.RESOLVED.value, ResolutionStatus.RESOLVED_WITH_CONFLICT.value}

        if status is not None and status not in ALLOWED_STATUSES[rel]:
            raise ValueError(f"resolution_status '{status}' is not valid for relationship '{rel}'.")
        if status in resolving and (self.canonical_value is None or self.selected_fact_id is None):
            raise ValueError("A resolved status needs canonical_value and selected_fact_id.")
        if status not in resolving and (self.canonical_value is not None or self.selected_fact_id):
            raise ValueError("Only resolved statuses may set canonical_value or selected_fact_id.")
        if status == ResolutionStatus.RESOLVED_WITH_CONFLICT.value and not self.conflicting_fact_ids:
            raise ValueError("resolved_with_conflict must name the conflicting fact.")
        if rel != Relationship.CONFLICTING.value and self.conflicting_fact_ids:
            raise ValueError("Only conflicting relationships may list conflicting facts.")
        if rel != Relationship.INSUFFICIENT_EVIDENCE.value and not self.evidence_refs:
            raise ValueError("Every decision except insufficient_evidence must cite evidence_refs.")
        return self

    def check_references(self, case: ReconciliationInput) -> list[str]:
        """Reference validity: do the cited facts and spans exist in the input,
        and does any canonical value match the fact it was taken from?

        This is structural only. It does NOT test evidence correctness (whether
        the spans actually support the conclusion); that needs gold labels or
        human review, see evidence_recall()."""
        problems = []
        if self.case_id != case.case_id:
            problems.append("case_id does not match input")
        fact_ids = case.fact_ids()
        if self.selected_fact_id and self.selected_fact_id not in fact_ids:
            problems.append(f"selected_fact_id {self.selected_fact_id} not in input")
        for fid in self.conflicting_fact_ids:
            if fid not in fact_ids:
                problems.append(f"conflicting fact {fid} not in input")
        unknown = set(self.evidence_refs) - case.span_ids()
        if unknown:
            problems.append(f"evidence_refs not in input: {sorted(unknown)}")
        if self.selected_fact_id in fact_ids and self.canonical_value is not None:
            src = case.fact_a if self.selected_fact_id == case.fact_a.fact_id else case.fact_b
            cv, q = self.canonical_value, src.quantity
            if cv.value != q.value:
                problems.append("canonical_value differs from the selected fact's value")
            if cv.unit != q.unit:
                problems.append("canonical_value unit differs from the selected fact's unit")
            if (cv.currency or "").upper() != (q.currency or "").upper():
                problems.append("canonical_value currency differs from the selected fact's currency")
        return problems


# ---------------------------------------------------------------------------
# Gold labels (eval and training only, never shown to the model)
# ---------------------------------------------------------------------------

class GoldLabel(_Model):
    case_id: str
    relationship: Relationship
    concept_same: bool | None = Field(
        description="Guideline judgment 1: same business concept? None = cannot tell.")
    scope_same: bool | None = Field(
        description="Guideline judgment 2: same entity and period? None = cannot tell.")
    acceptable_statuses: list[ResolutionStatus] = Field(
        default_factory=list,
        description="Optional, for the secondary resolution metric. "
                    "e.g. both needs_review and resolved_with_conflict may be fine.")
    canonical_fact_id: str | None = None
    reasons: list[ReasonCode] = Field(min_length=1, description="Primary reason first; drives the difficulty slice.")
    required_evidence_refs: list[str] = Field(default_factory=list)
    rationale: str = Field(description="Why this label is correct.")
    tags: list[str] = Field(
        default_factory=list, description="Finer slices, e.g. 'same_value_trap', 'heldout_name'.")
    split: Split
    source: Source
    labeled_by: str = Field(description="Person who labeled the case, or 'generator' for synthetic labels.")
    reviewed_by: str | None = None
    adjudication_note: str | None = Field(
        default=None, description="Set when labelers disagreed; records the decision and why.")
    guideline_version: str

    @model_validator(mode="after")
    def _reasons_fit_relationship(self):
        problem = reasons_problem(self.relationship, self.reasons)
        if problem:
            raise ValueError(problem)
        return self


CONSTRUCTION_LABELER = "generator"


class EvalCase(_Model):
    """One line of a dataset file: an input and its gold label.

    Rejected when the label contradicts its own judgments (per the guidelines' decision table
    and the computed value comparison) or cites spans and facts the input does not contain.
    """
    input: ReconciliationInput
    gold: GoldLabel

    @property
    def case_id(self) -> str:
        return self.input.case_id

    @property
    def human_labeled(self) -> bool:
        return self.gold.labeled_by != CONSTRUCTION_LABELER

    @model_validator(mode="after")
    def _consistent(self):
        from opslm.labels import derive_label, values_agree  # deferred: labels imports schema

        g, inp = self.gold, self.input
        if g.case_id != inp.case_id:
            raise ValueError(f"gold case_id {g.case_id} does not match input {inp.case_id}")
        agree = values_agree(inp.fact_a.quantity, inp.fact_b.quantity)
        expected = derive_label(g.concept_same, g.scope_same, agree).value
        if g.relationship != expected:
            raise ValueError(
                f"label {g.relationship} contradicts the judgments (concept_same="
                f"{g.concept_same}, scope_same={g.scope_same}, values_agree={agree}), "
                f"which give {expected}")
        unknown = set(g.required_evidence_refs) - inp.span_ids()
        if unknown:
            raise ValueError(f"required_evidence_refs not in input: {sorted(unknown)}")
        if g.canonical_fact_id is not None and g.canonical_fact_id not in inp.fact_ids():
            raise ValueError(f"canonical_fact_id {g.canonical_fact_id} not in input")
        bad = set(g.acceptable_statuses) - ALLOWED_STATUSES[g.relationship]
        if bad:
            raise ValueError(f"acceptable_statuses {sorted(bad)} are not valid for {g.relationship}")
        return self


def evidence_recall(output: ReconciliationOutput, gold: GoldLabel) -> float | None:
    """Evidence correctness against gold: share of the spans a labeler marked
    as required that the system cited. None when the gold label requires none."""
    required = set(gold.required_evidence_refs)
    if not required:
        return None
    return len(required & set(output.evidence_refs)) / len(required)
