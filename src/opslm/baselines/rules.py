"""Rules-based baseline: synonym tables and normalization, no model.

This is the floor every other system has to beat. It uses the same deterministic value
comparison and label table as the model-backed systems, and replaces the model's
judgment of meaning with a synonym dictionary, marker detection ("adjusted", "pro forma"),
and normalized comparison of entity and period.
"""

from __future__ import annotations

import re
import time

from opslm.labels import derive_label, values_agree
from opslm.schema import BusinessFact, Evidence, FactPair, Period, Prediction

# canonical concept -> names it is reported under
DEFAULT_SYNONYMS: dict[str, tuple[str, ...]] = {
    "revenue": (
        "revenue", "revenues", "sales", "net sales", "total revenue", "total revenues",
        "total sales", "turnover", "top line",
    ),
    "cogs": ("cost of goods sold", "cogs", "cost of sales", "cost of revenue"),
    "gross_profit": ("gross profit", "gross income"),
    "gross_margin": ("gross margin",),
    "operating_income": ("operating income", "operating profit", "ebit", "income from operations"),
    "ebitda": ("ebitda",),
    "net_income": ("net income", "net earnings", "net profit", "profit after tax"),
    "arr": ("arr", "annual recurring revenue"),
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

# Words that change a metric's meaning. Two facts with different marker sets are different
# concepts even if the core metric matches ("EBITDA" vs "Adjusted EBITDA").
_MARKERS = {
    "adjusted", "proforma", "normalized", "underlying", "organic", "gross", "recurring",
    "annualized", "constantcurrency", "diluted", "basic",
}
# Markers that do not change meaning: the default reporting basis.
_NEUTRAL = {"gaap", "reported", "audited", "unaudited"}
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
        text = normalize_text(fact.metric)
        qualifiers = " ".join(normalize_text(q) for q in fact.qualifiers)
        for phrase, repl in _PHRASES.items():
            text = text.replace(phrase, repl)
            qualifiers = qualifiers.replace(phrase, repl)
        tokens = [t for t in text.split() if t not in _NEUTRAL]
        markers = {t for t in qualifiers.split() if t in _MARKERS}
        full = " ".join(tokens)
        if full in self._canonical:  # e.g. "gross profit", "net revenue" are concepts themselves
            return self._canonical[full], frozenset(markers)
        markers |= {t for t in tokens if t in _MARKERS}
        core = " ".join(t for t in tokens if t not in _MARKERS)
        return self._canonical.get(core, core), frozenset(markers)

    def _concept_same(self, a: BusinessFact, b: BusinessFact) -> bool | None:
        core_a, markers_a = self._parse_metric(a)
        core_b, markers_b = self._parse_metric(b)
        known = set(self._canonical.values())
        if core_a != core_b:
            # both recognised and different -> different concepts; otherwise we can't tell
            return False if core_a in known and core_b in known else None
        return markers_a == markers_b

    # --- scope -------------------------------------------------------------------

    @staticmethod
    def _entity_same(a: BusinessFact, b: BusinessFact) -> bool | None:
        if not a.entity or not b.entity:
            return None
        return normalize_entity(a.entity) == normalize_entity(b.entity)

    @staticmethod
    def _period_same(a: Period | None, b: Period | None) -> bool | None:
        if a is None or b is None:
            return None
        if a.start and a.end and b.start and b.end:
            return (a.start, a.end) == (b.start, b.end)
        if a.type != b.type and "other" not in (a.type.value, b.type.value):
            return False
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

    def predict(self, case_id: str, pair: FactPair) -> Prediction:
        start = time.perf_counter()
        a, b = pair.fact_a, pair.fact_b
        concept = self._concept_same(a, b)
        scope, scope_fields = self._scope_same(a, b)
        agree = values_agree(a, b)
        label = derive_label(concept, scope, agree)

        if concept is not True:
            fields = ["metric", "qualifiers"]
        elif scope is not True:
            fields = scope_fields
        elif agree is not True:
            fields = ["value", "scale"] if agree is False else ["value", "unit"]
        else:
            fields = []
        evidence = tuple(
            Evidence(fact_id=f.fact_id, field=name) for name in fields for f in (a, b)
        )
        return Prediction(
            case_id=case_id,
            label=label,
            concept_same=concept,
            scope_same=scope,
            values_agree=agree,
            evidence=evidence,
            latency_s=time.perf_counter() - start,
            cost_usd=0.0,
        )
