"""Rules-based baseline: synonym tables and normalization, no model.

This is the floor every other system has to beat. It uses the same deterministic value
comparison and label table as the model-backed systems, and replaces the model's
judgment of meaning with a synonym dictionary, marker detection ("adjusted", "pro forma"),
and normalized comparison of entity and period.
"""

from __future__ import annotations

import re
import time

from opslm.labels import derive_label, infer_reasons, values_agree
from opslm.schema import (
    AccountingBasis,
    BusinessFact,
    ModelRunInfo,
    Period,
    PeriodType,
    ReconciliationInput,
    ReconciliationOutput,
)

# canonical concept -> names it is reported under. The names for the v1 metrics must cover every
# naming variant on docs/metric-set-v1.md (a test checks); the rest is a general synonym list.
DEFAULT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "revenue", "revenues", "sales", "net sales", "total revenue", "total revenues",
        "total sales", "turnover", "top line",
    ),
    "cogs": ("cost of goods sold", "cogs", "cost of sales", "cost of revenue"),
    "gross_profit": ("gross profit", "gross income"),
    "gross_margin": ("gross margin", "gm", "gross profit margin"),
    "operating_income": ("operating income", "operating profit", "ebit", "income from operations"),
    "ebitda": ("ebitda",),
    "adjusted_ebitda": ("adjusted ebitda", "adj ebitda", "ebitda adjusted"),
    "net_income": ("net income", "net earnings", "net profit", "profit after tax", "net loss",
                   "net income loss", "profit for the period"),
    "arr": ("arr", "annual recurring revenue", "annualized recurring revenue"),
    "mrr": ("mrr", "monthly recurring revenue"),
    "opex": ("operating expenses", "opex"),
    "sga": ("sg and a", "sga", "selling general and administrative expenses",
            "selling general and administrative"),
    "rd": ("research and development", "r and d", "rd"),
    "cash": ("cash", "cash and cash equivalents"),
    "total_assets": ("total assets",),
    "total_liabilities": ("total liabilities",),
    "total_equity": ("total equity", "shareholders equity", "stockholders equity"),
    "headcount": ("headcount", "employees", "number of employees"),
    "capex": ("capex", "capital expenditures"),
    "fcf": ("fcf", "free cash flow"),
    "customers": ("customers", "number of customers", "customer count"),
}

# Metrics that mean what each company defines them to mean (docs/labeling-guidelines.md): the
# same name is the same concept only when both facts state matching definitions.
_COMPANY_DEFINED = {"arr", "adjusted_ebitda", "fcf"}

# Words that change a metric's meaning. Two facts with different marker sets are different
# concepts even if the core metric matches ("EBITDA" vs "Adjusted EBITDA").
_MARKERS = {
    "adjusted", "proforma", "normalized", "underlying", "organic", "gross", "recurring",
    "annualized", "constantcurrency", "diluted", "basic",
}
# Markers that do not change meaning: the default reporting basis.
_NEUTRAL = {"gaap", "reported", "audited", "unaudited"}
# Marker implied by a non-GAAP accounting basis, so "EBITDA" (non-GAAP) reads as adjusted.
_BASIS_MARKER = "adjusted"
_PHRASES = {
    "non gaap": "adjusted",
    "pro forma": "proforma",
    "constant currency": "constantcurrency",
}
_ENTITY_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co", "company", "llc", "ltd", "limited",
    "plc", "lp", "llp", "gmbh", "sa", "ag", "holdings",
}


def normalize_text(text: str) -> str:
    """Lowercase, expand '&', drop punctuation, collapse whitespace."""
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_entity(name: str) -> str:
    # dotted abbreviations are one word: 'L.L.C.' is 'llc', not three letters
    name = re.sub(r"(?<=\b\w)\.", "", name)
    tokens = [t for t in normalize_text(name).split() if t not in _ENTITY_SUFFIXES]
    return " ".join(tokens)


def normalize_period_label(label: str) -> str:
    text = normalize_text(label)
    text = re.sub(r"\b(fiscal|year|fy)\b", "", text)
    text = re.sub(r"\b20(\d\d)\b", r"\1", text)  # 2025 -> 25
    return text.replace(" ", "")


class RulesBaseline:
    name = "rules"

    def __init__(self, synonyms: dict[str, tuple[str, ...]] | None = None) -> None:
        table = DEFAULT_SYNONYMS if synonyms is None else synonyms
        self._canonical = {normalize_text(n): c for c, names in table.items() for n in names}

    # --- concept -----------------------------------------------------------------

    def _parse_metric(self, fact: BusinessFact) -> tuple[str, frozenset[str]]:
        """Return (core metric, markers). The core is a canonical concept name when known."""
        text = normalize_text(fact.metric_label)
        for phrase, repl in _PHRASES.items():
            text = text.replace(phrase, repl)
        tokens = [t for t in text.split() if t not in _NEUTRAL]
        markers = {_BASIS_MARKER} if fact.accounting_basis == AccountingBasis.NON_GAAP else set()
        full = " ".join(tokens)
        if full in self._canonical:  # e.g. "gross profit", "net revenue" are concepts themselves
            return self._canonical[full], frozenset(markers)
        markers |= {t for t in tokens if t in _MARKERS}
        core = " ".join(t for t in tokens if t not in _MARKERS)
        return self._canonical.get(core, core), frozenset(markers)

    def _concept_same(self, a: BusinessFact, b: BusinessFact) -> tuple[bool | None, list[str]]:
        """Return (verdict, fields responsible for anything other than a clean yes)."""
        core_a, markers_a = self._parse_metric(a)
        core_b, markers_b = self._parse_metric(b)
        known = set(self._canonical.values())
        if core_a != core_b:
            # both recognised and different -> different concepts; otherwise we can't tell
            return (False if core_a in known and core_b in known else None), ["metric"]
        if markers_a == markers_b:
            if core_a in _COMPANY_DEFINED:
                da, db = a.stated_definition, b.stated_definition
                # a baseline cannot compare meanings, so only identical definition text counts
                if da and db and normalize_text(da) == normalize_text(db):
                    return True, []
                return None, ["definition"]
            return True, []
        basis_only = (markers_a ^ markers_b) == {_BASIS_MARKER} and a.accounting_basis != b.accounting_basis
        return False, ["basis"] if basis_only else ["metric"]

    # --- scope -------------------------------------------------------------------

    @staticmethod
    def _entity_same(a: BusinessFact, b: BusinessFact) -> bool | None:
        if a.entity is None or b.entity is None:
            return None
        ea, eb = a.entity, b.entity
        return (normalize_entity(ea.name) == normalize_entity(eb.name) and ea.scope == eb.scope
                and normalize_text(ea.segment or "") == normalize_text(eb.segment or ""))

    @staticmethod
    def _period_same(a: Period | None, b: Period | None) -> bool | None:
        if a is None or b is None:
            return None
        if a.type != b.type:
            return False
        if a.type == PeriodType.INSTANT and a.as_of and b.as_of:
            return a.as_of == b.as_of
        if a.type == PeriodType.DURATION and a.dates_known and b.dates_known:
            return (a.start, a.end) == (b.start, b.end)
        if a.fiscal_year is not None and b.fiscal_year is not None:
            return (a.fiscal_year, a.fiscal_quarter, a.is_ltm) == (b.fiscal_year, b.fiscal_quarter, b.is_ltm)
        return normalize_period_label(a.label) == normalize_period_label(b.label)

    def _scope_same(self, a: BusinessFact, b: BusinessFact) -> tuple[bool | None, list[str]]:
        """Return (verdict, fields responsible for anything other than a clean yes)."""
        results = {"entity": self._entity_same(a, b), "period": self._period_same(a.period, b.period)}
        culprits = [f for f, r in results.items() if r is False]
        if culprits:
            return False, culprits
        unknown = [f for f, r in results.items() if r is None]
        return (None, unknown) if unknown else (True, [])

    # --- prediction --------------------------------------------------------------

    def predict(self, case: ReconciliationInput) -> ReconciliationOutput:
        start = time.perf_counter()
        a, b = case.fact_a, case.fact_b
        concept, concept_fields = self._concept_same(a, b)
        scope, scope_fields = self._scope_same(a, b)
        agree = values_agree(a.quantity, b.quantity)
        label = derive_label(concept, scope, agree)
        culprits = concept_fields if concept is not True else scope_fields
        return ReconciliationOutput(
            case_id=case.case_id,
            relationship=label,
            reasons=infer_reasons(a, b, concept, scope, agree, culprits),
            explanation=explain(concept, scope, agree, culprits),
            evidence_refs=[s.span_id for f in (a, b) for s in f.evidence],
            concept_same=concept,
            scope_same=scope,
            values_agree=agree,
            run=ModelRunInfo(system=self.name, latency_ms=(time.perf_counter() - start) * 1000,
                             cost_usd=0.0),
        )


def _verdict(v: bool | None) -> str:
    return "cannot tell" if v is None else "yes" if v else "no"


def explain(concept: bool | None, scope: bool | None, agree: bool | None,
            culprits: list[str]) -> str:
    """A one-line account of the judgments behind a label."""
    text = (f"Same concept: {_verdict(concept)}; same scope: {_verdict(scope)}; "
            f"values agree: {'not comparable' if agree is None else _verdict(agree)}.")
    return text + (f" Decided by: {', '.join(culprits)}." if culprits else "")


# Public names for the entity and period comparisons, shared with the pair miner.
entity_same = RulesBaseline._entity_same
period_same = RulesBaseline._period_same
