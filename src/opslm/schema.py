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
    tags: tuple[str, ...] = Field(
        default=(), description="e.g. 'unit_mismatch', 'period_mismatch', 'synonym'"
    )


class Evidence(_Model):
    """A field of one of the facts that supports a prediction."""

    fact_id: str
    field: str = Field(description="BusinessFact field name, e.g. 'period' or 'definition'")
    note: str | None = None


class Prediction(_Model):
    """A system's answer for a pair, with the evidence behind it."""

    case_id: str
    label: Relation
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence: tuple[Evidence, ...] = ()
    rationale: str | None = None
    latency_s: float | None = Field(default=None, ge=0.0)
    cost_usd: float | None = Field(default=None, ge=0.0)
