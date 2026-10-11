"""Small builders for schema records, so tests state only what they are about."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from opslm.labels import GUIDELINE_VERSION
from opslm.schema import (
    BusinessFact,
    Entity,
    EvalCase,
    EvidenceSpan,
    ExtractionInfo,
    GoldLabel,
    Period,
    Quantity,
    ReconciliationInput,
    SourceDocument,
)

FY25 = Period(type="duration", label="FY2025", fiscal_year=2025)
_DEFAULT: Any = object()


def quantity(value: str = "42.5", scale: str = "1000000", currency: str | None = "USD",
             unit: str = "currency") -> Quantity:
    """A quantity reported as ``value`` in ``scale`` (42.5 in millions by default)."""
    return Quantity(value=Decimal(value) * Decimal(scale), unit=unit,
                    currency=currency if unit == "currency" else None,
                    reported_scale=Decimal(scale), raw_text=value)


def fact(fid: str = "f1", metric: str = "Revenue", value: str = "42.5", *,
         scale: str = "1000000", currency: str = "USD", unit: str = "currency",
         entity: Any = "Acme Corp", period: Any = _DEFAULT, metric_id: str = "revenue",
         basis: str = "unknown", definition: str | None = None, text: str | None = None,
         doc: str | None = None) -> BusinessFact:
    if isinstance(entity, str):
        entity = Entity(name=entity)
    return BusinessFact(
        fact_id=fid, metric_label=metric, metric_id=metric_id, entity=entity,
        period=FY25 if period is _DEFAULT else period,
        quantity=quantity(value, scale, currency, unit), accounting_basis=basis,
        stated_definition=definition,
        evidence=[EvidenceSpan(span_id=f"s-{fid}", doc_id=doc or f"doc-{fid}", page=1,
                               text=text or f"{metric}  {value}")],
        extraction=ExtractionInfo(extractor="manual"),
    )


def case_input(a: BusinessFact, b: BusinessFact, case_id: str = "c1", *,
               family: str | None = None, company: str | None = None) -> ReconciliationInput:
    """By default each document family is its own company, so cases do not leak across splits."""
    doc_ids = sorted({s.doc_id for f in (a, b) for s in f.evidence})
    docs = [SourceDocument(doc_id=d, company=company or f"Company {family or case_id}",
                           document_family=family or case_id, doc_type="10-K") for d in doc_ids]
    return ReconciliationInput(case_id=case_id, fact_a=a, fact_b=b, documents=docs)


def gold(case_id: str, relationship: str, concept: bool | None = True, scope: bool | None = True,
         *, reasons: tuple[str, ...] = ("synonym",), refs: tuple[str, ...] = (),
         split: str = "train", labeled_by: str = "tester", **kw: Any) -> GoldLabel:
    return GoldLabel(case_id=case_id, relationship=relationship, concept_same=concept,
                     scope_same=scope, reasons=list(reasons), required_evidence_refs=list(refs),
                     rationale=kw.pop("rationale", "r"), split=split,
                     source=kw.pop("source", "synthetic"), labeled_by=labeled_by,
                     guideline_version=kw.pop("guideline_version", GUIDELINE_VERSION), **kw)


def case(case_id: str, a: BusinessFact, b: BusinessFact, relationship: str,
         concept: bool | None = True, scope: bool | None = True, *, family: str | None = None,
         cite: bool = True, **kw: Any) -> EvalCase:
    """An EvalCase whose gold label requires both facts' spans unless ``cite`` is False."""
    inp = case_input(a, b, case_id, family=family)
    refs = tuple(sorted(inp.span_ids())) if cite else ()
    return EvalCase(input=inp, gold=gold(case_id, relationship, concept, scope, refs=refs, **kw))
