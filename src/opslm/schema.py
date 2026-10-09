"""Canonical schema for business facts and reconciliation cases.

A ``BusinessFact`` is one value extracted from a document, together with the context
needed to judge whether it means the same thing as a fact from another source.
A ``FactPair`` is the unit the models are asked to judge, an ``EvalCase`` adds the
reviewed gold label, and a ``Prediction`` is what a system returns.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Relation(str, Enum):
    """Relationship between two business facts."""

    EQUIVALENT = "equivalent"
    RELATED_BUT_DIFFERENT = "related_but_different"
    CONFLICTING = "conflicting"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class PeriodType(str, Enum):
    FISCAL_YEAR = "fiscal_year"
    CALENDAR_YEAR = "calendar_year"
    QUARTER = "quarter"
    MONTH = "month"
    LTM = "ltm"
    POINT_IN_TIME = "point_in_time"
    OTHER = "other"


class Scale(int, Enum):
    """Multiplier a reported number is expressed in (e.g. ``$42.5M`` -> MILLIONS)."""

    UNITS = 1
    THOUSANDS = 1_000
    MILLIONS = 1_000_000
    BILLIONS = 1_000_000_000


class DiscrepancyReason(str, Enum):
    """Primary reason a pair is not equivalent. Required for every non-equivalent case."""

    PERIOD = "period"  # different reporting period or period definition
    SCALE_OR_UNIT = "scale_or_unit"  # scale, currency or unit differs
    SCOPE = "scope"  # different entity, segment or consolidation basis
    DEFINITION = "definition"  # different metric definition or adjustment basis
    RESTATEMENT = "restatement"  # same fact restated between sources, supported by evidence
    UNEXPLAINED = "unexplained"  # same concept and scope, values differ, no explanation given
    MISSING_INFORMATION = "missing_information"  # a field needed to judge is absent
    ERROR = "error"  # evident extraction or reporting error
    OTHER = "other"


class SourceKind(str, Enum):
    PUBLIC = "public"
    SYNTHETIC = "synthetic"


class Split(str, Enum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRef(_Model):
    """Where a fact came from, precise enough to trace back to the original document."""

    document_id: str
    document_type: str | None = Field(
        default=None, description="e.g. 10-K, management_presentation, revenue_workbook"
    )
    location: str | None = Field(
        default=None, description="Page, sheet and cell, or section, e.g. 'p.14' or 'Revenue!C12'"
    )
    excerpt: str | None = Field(default=None, description="Verbatim surrounding text")
    extractor: str | None = Field(default=None, description="Tool that produced the fact")
    page: int | None = Field(default=None, ge=1, description="1-based page number")
    bbox: tuple[float, float, float, float] | None = Field(
        default=None, description="Bounding box (left, top, right, bottom) on the page"
    )
    cell: str | None = Field(
        default=None, description="Table or sheet cell reference, e.g. 'Revenue!C12' or 'r3c2'"
    )


class Period(_Model):
    """Reporting period a fact refers to."""

    label: str = Field(description="As reported, e.g. 'FY2025' or 'Q3 2025'")
    type: PeriodType = PeriodType.OTHER
    start: date | None = None
    end: date | None = None

    @model_validator(mode="after")
    def _ordered(self) -> Period:
        if self.start and self.end and self.start > self.end:
            raise ValueError("period start is after end")
        return self


class BusinessFact(_Model):
    """A single extracted business fact with the context needed for comparison."""

    fact_id: str
    metric: str = Field(description="Metric name exactly as reported, e.g. 'Net Revenue'")
    value: Decimal | None = Field(default=None, description="Numeric value in `scale` units")
    unit: str | None = Field(default=None, description="e.g. 'USD', 'percent', 'count'")
    scale: Scale = Scale.UNITS
    entity: str | None = Field(default=None, description="Reporting entity or segment")
    period: Period | None = None
    definition: str | None = Field(
        default=None, description="Definition or footnote attached to the metric, if any"
    )
    qualifiers: tuple[str, ...] = Field(
        default=(), description="e.g. 'GAAP', 'adjusted', 'pro forma', 'consolidated'"
    )
    source: SourceRef

    @property
    def absolute_value(self) -> Decimal | None:
        """Value with the reporting scale applied, for numeric comparison."""
        return None if self.value is None else self.value * int(self.scale)


class FactPair(_Model):
    """Two facts whose relationship is to be determined."""

    fact_a: BusinessFact
    fact_b: BusinessFact

    @model_validator(mode="after")
    def _distinct(self) -> FactPair:
        if self.fact_a.fact_id == self.fact_b.fact_id:
            raise ValueError("a pair must contain two distinct facts")
        return self


class EvalCase(_Model):
    """A reviewed, labeled pair used for training or evaluation."""

    case_id: str
    scenario_id: str = Field(
        description="Groups cases derived from the same underlying scenario. "
        "All cases in a scenario must land in the same split."
    )
    pair: FactPair
    label: Relation
    rationale: str = Field(description="Why this label is correct")
    source_kind: SourceKind
    split: Split
    reviewed: bool = False
    guideline_version: str = Field(description="Labeling guideline version the label follows")
    discrepancy_reason: DiscrepancyReason | None = Field(
        default=None,
        description="Why the pair is not equivalent. Required unless the label is equivalent.",
    )
    discriminating_fields: tuple[str, ...] = Field(
        default=(),
        description="BusinessFact fields that determine the label, e.g. ('period',). "
        "Used to score whether a system cites the right evidence.",
    )
    tags: tuple[str, ...] = Field(
        default=(), description="e.g. 'unit_mismatch', 'period_mismatch', 'synonym'"
    )

    @model_validator(mode="after")
    def _consistent(self) -> EvalCase:
        if self.label is Relation.EQUIVALENT and self.discrepancy_reason is not None:
            raise ValueError("equivalent cases must not have a discrepancy_reason")
        if self.label is not Relation.EQUIVALENT and self.discrepancy_reason is None:
            raise ValueError("non-equivalent cases require a discrepancy_reason")
        unknown = set(self.discriminating_fields) - set(BusinessFact.model_fields)
        if unknown:
            raise ValueError(f"unknown discriminating fields: {sorted(unknown)}")
        return self


class Evidence(_Model):
    """A field of one of the facts that supports a prediction."""

    fact_id: str
    field: str = Field(description="BusinessFact field name, e.g. 'period' or 'definition'")
    note: str | None = None


class Prediction(_Model):
    """A system's answer for a pair, with the evidence behind it."""

    case_id: str
    label: Relation
    concept_same: bool | None = Field(
        default=None, description="Same business concept? None = could not be determined"
    )
    scope_same: bool | None = Field(
        default=None, description="Same entity and period? None = could not be determined"
    )
    values_agree: bool | None = Field(
        default=None, description="Normalized values agree? None = not comparable"
    )
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: tuple[Evidence, ...] = ()
    rationale: str | None = None
    latency_s: float | None = Field(default=None, ge=0.0)
    cost_usd: float | None = Field(default=None, ge=0.0)
