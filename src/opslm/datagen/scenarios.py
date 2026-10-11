"""Scenario templates for the synthetic generator.

A scenario is a small data room: one company and period, a handful of facts as different
documents would report them, and the pairs worth comparing. Every pair declares the labeling
guideline judgments by construction (concept, scope) and the label it expects. The generator
derives the label from those judgments and the computed value comparison, and fails if it
differs from the template's expectation, so a template that contradicts the guidelines cannot
produce data.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from opslm.datagen import vocab as V
from opslm.labels import values_agree
from opslm.schema import (
    BusinessFact,
    DiscrepancyReason,
    Period,
    Relation,
    Scale,
    SourceRef,
)

R = DiscrepancyReason


@dataclass(frozen=True)
class PairSpec:
    a: str
    b: str
    expect: Relation
    concept: bool | None
    scope: bool | None
    reason: DiscrepancyReason | None
    fields: tuple[str, ...]
    rationale: str
    tags: tuple[str, ...] = ()


@dataclass
class Scenario:
    scenario_id: str
    kind: str
    facts: dict[str, BusinessFact]
    pairs: list[PairSpec]


_SYMBOL = {"USD": "$", "EUR": "€", "GBP": "£"}
_SCALE_WORD = {Scale.MILLIONS: " million", Scale.THOUSANDS: " thousand", Scale.UNITS: ""}


def _fmt_number(value: Decimal) -> str:
    return f"{value:,f}"


class Ctx:
    """Per-scenario random choices and fact construction."""

    def __init__(self, rng: random.Random, scenario_id: str, company: V.Company,
                 cal: V.FiscalCalendar, *, heldout: bool) -> None:
        self.rng, self.scenario_id, self.company, self.cal = rng, scenario_id, company, cal
        self.heldout = heldout
        self.unit = rng.choices(["USD", "EUR", "GBP"], [70, 15, 15])[0]
        self._n = 0
        self.facts: dict[str, BusinessFact] = {}

    # --- vocabulary ----------------------------------------------------------------------

    def concept(self, kinds: tuple[str, ...] | None = None, min_value: float = 0.0,
                keys: tuple[str, ...] = V.GENERIC) -> V.Concept:
        pool = [V.CONCEPTS[k] for k in keys
                if (kinds is None or V.CONCEPTS[k].kind in kinds)
                and V.CONCEPTS[k].high >= max(min_value, 1)]
        return self.rng.choice(pool)

    def names(self, concept: V.Concept, k: int, *, loss: bool = False) -> list[str]:
        """k names for a concept. In held-out splits the first is often a held-out name."""
        base = list(concept.names) + (["Net loss"] if loss and concept.key == "net_income" else [])
        pool = base + (list(concept.heldout) if self.heldout else [])
        chosen: list[str] = []
        if self.heldout and concept.heldout and self.rng.random() < 0.6:
            chosen.append(self.rng.choice(concept.heldout))
        remaining = [n for n in pool if n not in chosen]
        self.rng.shuffle(remaining)
        while len(chosen) < k:
            chosen.append(remaining.pop() if remaining else self.rng.choice(pool))
        self.rng.shuffle(chosen)
        return chosen

    def period(self, c: V.Concept, dated: bool, *, label: str | None = None) -> Period:
        """The concept's natural period: a fiscal year for flows, an as-of date for balances."""
        return self.cal.asof(self.rng) if c.point else self.cal.fy(self.rng, dated=dated, label=label)

    # --- numbers -------------------------------------------------------------------------

    def true_value(self, concept: V.Concept, min_value: float = 0.0, *,
                   allow_negative: bool = False) -> Decimal:
        low = max(concept.low, min_value)
        if concept.kind == "percent":
            return Decimal(f"{self.rng.uniform(concept.low, concept.high):.1f}")
        x = math.exp(self.rng.uniform(math.log(low), math.log(max(concept.high, low * 1.01))))
        value = Decimal(f"{x:.3e}")  # four significant figures
        if allow_negative and concept.signed and self.rng.random() < 0.25:
            value = -value  # a net loss
        return value

    def perturb(self, T: Decimal, kind: str) -> Decimal:
        """A clearly different value (callers re-check disagreement after display rounding)."""
        if kind == "percent":
            return Decimal(f"{float(T) + self.rng.choice([-1, 1]) * self.rng.uniform(1.0, 8.0):.1f}")
        factor = 1 + self.rng.choice([-1, 1]) * self.rng.uniform(0.02, 0.30)
        return Decimal(f"{float(T) * factor:.3e}")

    def rep(self, kind: str, T: Decimal) -> tuple[Scale, int]:
        if kind != "currency":
            return Scale.UNITS, 1 if kind == "percent" else 0
        options = [(s, dp) for s in (Scale.MILLIONS, Scale.THOUSANDS, Scale.UNITS)
                   for dp in ((1, 2) if s is not Scale.UNITS else (0,)) if abs(T) / int(s) >= 1]
        return self.rng.choice(options)

    # --- facts ---------------------------------------------------------------------------

    def fact(self, key: str, *, metric: str, T: Decimal, kind: str, entity: str | None,
             period: Period | None, scale: Scale | None = None, dp: int | None = None,
             unit: str | None = None, definition: str | None = None,
             qualifiers: tuple[str, ...] = (), excerpt: str | None = "auto",
             show_entity: bool = True, show_period: bool = True) -> BusinessFact:
        if scale is None or dp is None:
            scale, dp = self.rep(kind, T)
        unit = unit or (self.unit if kind == "currency" else "percent")
        value = (T / int(scale)).quantize(Decimal(1).scaleb(-dp), rounding=ROUND_HALF_UP)
        self._n += 1
        doc_type = self.rng.choice(V.DOC_TYPES)
        loc = (f"Sheet1!C{self.rng.randint(2, 60)}" if doc_type.endswith("workbook")
               else f"p.{self.rng.randint(2, 90)}")
        if excerpt == "auto":
            excerpt = (self._excerpt(metric, value, scale, unit, entity if show_entity else None,
                                     period.label if period and show_period else None)
                       if self.rng.random() < 0.6 else None)
        fact = BusinessFact(
            fact_id=f"{self.scenario_id}-f{self._n}", metric=metric, value=value, unit=unit,
            scale=scale, entity=entity, period=period, definition=definition,
            qualifiers=qualifiers,
            source=SourceRef(document_id=f"{self.scenario_id}-d{self._n}", document_type=doc_type,
                             location=loc, excerpt=excerpt, extractor="synthetic"),
        )
        self.facts[key] = fact
        return fact

    def amount_text(self, value: Decimal, scale: Scale, unit: str) -> str:
        v = abs(value)
        if unit == "percent":
            text = f"{v}%"
        else:
            text = f"{_SYMBOL.get(unit, '')}{_fmt_number(v)}{_SCALE_WORD[scale]}" + (
                "" if unit in _SYMBOL else f" {unit}")
        return f"({text})" if value < 0 else text

    def _excerpt(self, metric: str, value: Decimal, scale: Scale, unit: str,
                 entity: str | None, period: str | None) -> str:
        amt = self.amount_text(value, scale, unit)
        per = period or "the period"
        options = [f"{metric} was {amt} for {per}.", f"{per}: {metric} {amt}."]
        if entity:
            options += [f"{entity} reported {metric} of {amt} for {per}.",
                        f"For {per}, {entity} recorded {metric} totalling {amt}."]
        return self.rng.choice(options)

    def conflicting_with(self, other: BusinessFact, key: str, **kw: Any) -> BusinessFact:
        """A fact for the same metric whose displayed value clearly disagrees with `other`."""
        kind = kw["kind"]
        base = other.absolute_value if other.absolute_value is not None else Decimal(1)
        for _ in range(100):
            fact = self.fact(key, T=self.perturb(base, kind), **kw)
            if values_agree(other, fact) is False:
                return fact
            self._n -= 1
        raise RuntimeError("could not generate a disagreeing value")


# --- scenario templates -------------------------------------------------------------------

Template = Callable[[Ctx], tuple[str, list[PairSpec]]]


def _all_pairs(keys: list[str], make: Callable[[str, str], PairSpec]) -> list[PairSpec]:
    return [make(a, b) for i, a in enumerate(keys) for b in keys[i + 1:]]


def equivalent(a: str, b: str, rationale: str, *tags: str) -> PairSpec:
    return PairSpec(a, b, Relation.EQUIVALENT, True, True, None, (), rationale, tags)


def conflicting(a: str, b: str, reason: DiscrepancyReason, fields: tuple[str, ...],
                rationale: str, *tags: str) -> PairSpec:
    return PairSpec(a, b, Relation.CONFLICTING, True, True, reason, fields, rationale, tags)


def related(a: str, b: str, concept: bool, scope: bool | None, reason: DiscrepancyReason,
            fields: tuple[str, ...], rationale: str, *tags: str) -> PairSpec:
    return PairSpec(a, b, Relation.RELATED_BUT_DIFFERENT, concept, scope, reason, fields,
                    rationale, tags)


def insufficient(a: str, b: str, concept: bool | None, scope: bool | None,
                 reason: DiscrepancyReason, fields: tuple[str, ...], rationale: str,
                 *tags: str) -> PairSpec:
    return PairSpec(a, b, Relation.INSUFFICIENT_EVIDENCE, concept, scope, reason, fields,
                    rationale, tags)


def _same_or_conflict(ctx: Ctx, a: BusinessFact, key: str, *, same: bool, T: Decimal,
                      **kw: Any) -> BusinessFact:
    return ctx.fact(key, T=T, **kw) if same else ctx.conflicting_with(a, key, **kw)


def sc_synonym_equivalent(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    c = ctx.concept()
    T = ctx.true_value(c, allow_negative=True)
    k = ctx.rng.choice([2, 2, 3])
    names = ctx.names(c, k, loss=T < 0)
    dated = ctx.rng.random() < 0.5
    long_form = dated and not c.point and ctx.rng.random() < 0.4
    keys = []
    for i, name in enumerate(names):
        entity = ctx.company.name(ctx.rng, vary=i > 0 and ctx.rng.random() < 0.6)
        period = ctx.cal.fy_long() if long_form and i == 0 else ctx.period(c, dated)
        ctx.fact(f"f{i}", metric=name, T=T, kind=c.kind, entity=entity, period=period)
        keys.append(f"f{i}")
    tags = ["synonym"] + (["period_format"] if long_form else []) + (["negative_value"] if T < 0 else [])
    return "synonym_equivalent", _all_pairs(keys, lambda a, b: equivalent(
        a, b, f"Standard naming variants of {c.key.replace('_', ' ')} for the same entity and "
              "period, and the values agree.", *tags))


def sc_value_conflict(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    c = ctx.concept()
    T = ctx.true_value(c, allow_negative=True)
    names = ctx.names(c, 3, loss=T < 0)
    entity = ctx.company.name(ctx.rng)
    per = ctx.period(c, False, label=ctx.cal.fy_labels()[0])
    a = ctx.fact("a", metric=names[0], T=T, kind=c.kind, entity=entity, period=per)
    ctx.conflicting_with(a, "b", metric=names[1], kind=c.kind, entity=entity, period=per)
    pairs = [conflicting("a", "b", R.UNEXPLAINED, ("value",),
                         "Same concept, entity and period, but the values differ and nothing "
                         "explains it.", "value_conflict")]
    if ctx.rng.random() < 0.7:
        ctx.fact("c", metric=names[2], T=T, kind=c.kind, entity=entity, period=per)
        pairs += [conflicting("c", "b", R.UNEXPLAINED, ("value",),
                              "Same concept, entity and period, but the values differ.",
                              "value_conflict"),
                  equivalent("a", "c", "Same concept, entity and period, and the values agree.",
                             "synonym")]
    return "value_conflict", pairs


def sc_scale_error(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    c = ctx.concept(("currency",), min_value=2e6)
    names = ctx.names(c, 2)
    T = ctx.true_value(c, min_value=2e6)
    entity, per = ctx.company.name(ctx.rng), ctx.period(c, False)
    ctx.fact("a", metric=names[0], T=T, kind="currency", entity=entity, period=per,
             scale=Scale.MILLIONS, dp=1)
    shown = (T / int(Scale.MILLIONS)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    wrong_scale = ctx.rng.choice([Scale.UNITS, Scale.THOUSANDS])
    # same numeral, wrong scale: 42.5 reported as units, or 42.5 as thousands
    ctx.facts["b"] = BusinessFact(
        fact_id=f"{ctx.scenario_id}-f2", metric=names[1], value=shown, unit=ctx.unit,
        scale=wrong_scale, entity=entity, period=per,
        source=SourceRef(document_id=f"{ctx.scenario_id}-d2", document_type="revenue_workbook",
                         location="Sheet1!C12", extractor="synthetic"),
    )
    return "scale_error", [conflicting(
        "a", "b", R.SCALE_OR_UNIT, ("scale",),
        f"Same concept, entity and period, but one source reports the number in millions and "
        f"the other as {wrong_scale.name.lower()}, so the values disagree.", "scale_error")]


def sc_rounding(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    c = ctx.concept(("currency",), min_value=2e6)
    names = ctx.names(c, 3)
    T = ctx.true_value(c, min_value=2e6)
    entity, per = ctx.company.name(ctx.rng), ctx.period(c, False)
    ctx.fact("a", metric=names[0], T=T, kind="currency", entity=entity, period=per,
             scale=Scale.MILLIONS, dp=1)
    ctx.fact("b", metric=names[1], T=T, kind="currency", entity=entity, period=per,
             scale=Scale.UNITS, dp=0)
    half = Decimal(50000)  # half of the 0.1M precision in fact a
    off = half * Decimal(str(ctx.rng.uniform(2.2, 5.0)))
    ctx.fact("c", metric=names[2], T=(T + off).quantize(Decimal(1)), kind="currency",
             entity=entity, period=per, scale=Scale.UNITS, dp=0)
    return "rounding", [
        equivalent("a", "b", "Same figure; one rounds to $0.1M and the other is exact, and they "
                             "agree within that rounding.", "rounding"),
        conflicting("a", "c", R.UNEXPLAINED, ("value",),
                    "The figures differ by more than the rounding of the coarser one.",
                    "rounding", "near_miss"),
        conflicting("b", "c", R.UNEXPLAINED, ("value",),
                    "Both are exact figures and they differ.", "rounding", "near_miss"),
    ]


def sc_marker_diff(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    entity = ctx.company.name(ctx.rng)
    kind, qualifiers = "currency", ()
    if ctx.rng.random() < 0.15:  # EBITDA vs Adjusted EBITDA, the sheet's standing example
        c = V.CONCEPTS["adjusted_ebitda"]
        plain, marked, in_name = "EBITDA", "Adjusted EBITDA", True
    else:
        c = V.CONCEPTS[ctx.rng.choice(tuple(V.MARKERS_FOR))]
        kind = c.kind
        label, q = ctx.rng.choice(V.MARKERS_FOR[c.key])
        plain = c.names[0]
        in_name = ctx.rng.random() < 0.6
        marked = f"{label} {plain[0].lower()}{plain[1:]}" if in_name else plain
        qualifiers = () if in_name else (q,)
    per = ctx.period(c, False, label=ctx.cal.fy_labels()[0])
    T = ctx.true_value(c)
    a = ctx.fact("a", metric=plain, T=T, kind=kind, entity=entity, period=per)
    same = ctx.rng.random() < 0.5
    _same_or_conflict(ctx, a, "b", same=same, T=T, metric=marked, kind=kind, entity=entity,
                      period=per, qualifiers=qualifiers)
    return "marker_diff", [related(
        "a", "b", False, True, R.DEFINITION, ("metric",) if in_name else ("qualifiers",),
        "The qualifier changes what is measured, so these are different concepts regardless "
        "of the numbers.", "marker", "same_value_trap" if same else "different_value")]


def _value_of_kind(ctx: Ctx, kind: str) -> Decimal:
    if kind == "percent":
        return Decimal(f"{ctx.rng.uniform(5, 70):.1f}")
    return Decimal(f"{math.exp(ctx.rng.uniform(math.log(2e6), math.log(5e8))):.3e}")


def sc_defined_diff(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    name_a, def_a, kind_a, name_b, def_b, kind_b, point_a, point_b = ctx.rng.choice(V.RELATED_DIFFERENT)
    entity = ctx.company.name(ctx.rng)

    def period_for(point: bool) -> Period:
        return ctx.cal.asof(ctx.rng) if point else ctx.cal.fy(ctx.rng, dated=False)

    pa = period_for(point_a)
    pb = pa if point_a == point_b else period_for(point_b)
    T = _value_of_kind(ctx, kind_a)
    a = ctx.fact("a", metric=name_a, T=T, kind=kind_a, entity=entity, period=pa, definition=def_a)
    same = kind_a == kind_b and ctx.rng.random() < 0.5
    if kind_a != kind_b:
        ctx.fact("b", metric=name_b, T=_value_of_kind(ctx, kind_b), kind=kind_b, entity=entity,
                 period=pb, definition=def_b)
    else:
        _same_or_conflict(ctx, a, "b", same=same, T=T, metric=name_b, kind=kind_b, entity=entity,
                          period=pb, definition=def_b)
    tag = "unit_mismatch" if kind_a != kind_b else ("same_value_trap" if same else "different_value")
    tags = (tag,) if point_a == point_b else (tag, "flow_vs_point")
    # a flow and a point-in-time measure have no common period, so scope is left undetermined;
    # the label is settled by the concept difference either way
    return "defined_diff", [related(
        "a", "b", False, True if point_a == point_b else None, R.DEFINITION, ("metric", "definition"),
        "The stated definitions describe different measures, so these are different concepts "
        "regardless of the numbers.", "definition", *tags)]


def sc_company_defined(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    """ARR and Adjusted EBITDA mean what each company says they mean."""
    c = V.CONCEPTS[ctx.rng.choice(V.COMPANY_DEFINED)]
    groups = V.DEFINITION_GROUPS[c.key]
    names = ctx.names(c, 2)
    entity, per = ctx.company.name(ctx.rng), ctx.period(c, False)
    T = ctx.true_value(c)
    outcome = ctx.rng.choice(["same_def", "same_def", "different_def", "undefined", "undefined"])
    if outcome == "same_def":
        g = ctx.rng.choice(groups)
        def_a, def_b = (ctx.rng.sample(g, 2) if len(g) > 1 else [g[0], g[0]])
    elif outcome == "different_def":
        g1, g2 = ctx.rng.sample(groups, 2)
        def_a, def_b = ctx.rng.choice(g1), ctx.rng.choice(g2)
    else:
        text = ctx.rng.choice(ctx.rng.choice(groups))
        def_a, def_b = ctx.rng.choice([(None, None), (text, None), (None, text)])
    a = ctx.fact("a", metric=names[0], T=T, kind=c.kind, entity=entity, period=per, definition=def_a)
    same = ctx.rng.random() < 0.5
    _same_or_conflict(ctx, a, "b", same=same, T=T, metric=names[1], kind=c.kind, entity=entity,
                      period=per, definition=def_b)
    label = c.names[0]
    if outcome == "same_def":
        if same:
            pair = equivalent("a", "b", f"{label} is company-defined; both sources state the same "
                              "definition and the values agree.", "company_defined")
        else:
            pair = conflicting("a", "b", R.UNEXPLAINED, ("value",),
                               f"{label} is company-defined; both sources state the same "
                               "definition but the values differ.", "company_defined")
    elif outcome == "different_def":
        pair = related("a", "b", False, True, R.DEFINITION, ("definition",),
                       f"{label} is company-defined and the stated definitions differ, so these "
                       "are different measures.", "company_defined")
    else:
        pair = insufficient("a", "b", None, True, R.MISSING_INFORMATION, ("definition",),
                            f"{label} is company-defined and the definition is not stated on "
                            "both facts, so comparability cannot be established.",
                            "company_defined", "undefined")
    return "company_defined", [pair]


def sc_period_mismatch(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    c = ctx.concept()
    if c.point:
        variant = ctx.rng.choice(["asof_year_end_vs_quarter_end", "asof_vs_prior_year_end"])
    else:
        variant = ctx.rng.choice(["fy_vs_quarter", "fy_vs_prior_fy", "quarter_vs_quarter",
                                  "ltm_vs_fy", "calendar_vs_fiscal"])
    if variant == "calendar_vs_fiscal":
        ctx.cal = V.make_calendar(ctx.rng, non_december=True)
    dated = ctx.rng.random() < 0.5 or variant in ("ltm_vs_fy", "calendar_vs_fiscal")
    cal = ctx.cal
    if variant == "asof_year_end_vs_quarter_end":
        pa, pb = cal.asof(ctx.rng), cal.asof(ctx.rng, quarter=ctx.rng.randint(1, 3))
    elif variant == "asof_vs_prior_year_end":
        pa, pb = cal.asof(ctx.rng), cal.other_year(-1).asof(ctx.rng)
    elif variant == "fy_vs_quarter":
        pa, pb = cal.fy(ctx.rng, dated=dated), cal.quarter(ctx.rng.randint(1, 4), dated=dated)
    elif variant == "fy_vs_prior_fy":
        pa, pb = cal.fy(ctx.rng, dated=dated), cal.other_year(-1).fy(ctx.rng, dated=dated)
    elif variant == "quarter_vs_quarter":
        q1, q2 = ctx.rng.sample([1, 2, 3, 4], 2)
        pa, pb = cal.quarter(q1, dated=dated), cal.quarter(q2, dated=dated)
    elif variant == "ltm_vs_fy":
        pa, pb = cal.fy(ctx.rng, dated=True), cal.ltm()
    else:
        pa, pb = cal.fy(ctx.rng, dated=True), cal.calendar_year()
    names = ctx.names(c, 2)
    entity = ctx.company.name(ctx.rng)
    T = ctx.true_value(c)
    a = ctx.fact("a", metric=names[0], T=T, kind=c.kind, entity=entity, period=pa)
    same = ctx.rng.random() < 0.4
    _same_or_conflict(ctx, a, "b", same=same, T=T, metric=names[1], kind=c.kind, entity=entity,
                      period=pb)
    return "period_mismatch", [related(
        "a", "b", True, False, R.PERIOD, ("period",),
        "Same concept and entity, but the periods differ, so the figures are not comparable.",
        variant, "same_value_trap" if same else "different_value")]


def sc_entity_mismatch(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    ents = [ctx.company.name(ctx.rng), ctx.company.subsidiary(ctx.rng), ctx.company.segment(ctx.rng)]
    ea, eb = ctx.rng.sample(ents, 2)
    c = ctx.concept()
    names = ctx.names(c, 2)
    T = ctx.true_value(c)
    per = ctx.period(c, False)
    a = ctx.fact("a", metric=names[0], T=T, kind=c.kind, entity=ea, period=per)
    same = ctx.rng.random() < 0.3
    _same_or_conflict(ctx, a, "b", same=same, T=T, metric=names[1], kind=c.kind, entity=eb, period=per)
    return "entity_mismatch", [related(
        "a", "b", True, False, R.SCOPE, ("entity",),
        "Same concept and period, but the figures belong to different entities or segments.",
        "entity", "same_value_trap" if same else "different_value")]


def _missing_pair(ctx: Ctx, missing: str) -> tuple[str, list[PairSpec]]:
    c = ctx.concept()
    names = ctx.names(c, 2)
    T = ctx.true_value(c)
    entity, per = ctx.company.name(ctx.rng), ctx.period(c, False)
    a = ctx.fact("a", metric=names[0], T=T, kind=c.kind, entity=entity, period=per)
    kw: dict[str, Any] = {"entity": None if missing == "entity" else entity,
                          "period": None if missing == "period" else per,
                          "show_entity": missing != "entity", "show_period": missing != "period"}
    same = ctx.rng.random() < 0.5
    _same_or_conflict(ctx, a, "b", same=same, T=T, metric=names[1], kind=c.kind, **kw)
    return f"missing_{missing}", [insufficient(
        "a", "b", True, None, R.MISSING_INFORMATION, (missing,),
        f"The {missing} is missing on one fact and not stated in its excerpt, so scope cannot "
        "be established.", f"missing_{missing}")]


def sc_missing_entity(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    return _missing_pair(ctx, "entity")


def sc_missing_period(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    return _missing_pair(ctx, "period")


def _plain_revenue_name(ctx: Ctx) -> str:
    """A revenue name that is not a net-basis variant, so it cannot be confused with 'Net revenue'."""
    candidates = [n for n in ctx.names(V.CONCEPTS["revenue"], 4) if not n.startswith("Net")]
    return candidates[0] if candidates else "Revenue"


def sc_ambiguous_name(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    ambiguous = ctx.rng.choice(V.AMBIGUOUS_NAMES)
    c = V.CONCEPTS["revenue"]
    entity, per = ctx.company.name(ctx.rng), ctx.period(c, False)
    T = ctx.true_value(c)
    a = ctx.fact("a", metric=_plain_revenue_name(ctx), T=T, kind="currency", entity=entity,
                 period=per)
    _same_or_conflict(ctx, a, "b", same=ctx.rng.random() < 0.5, T=T, metric=ambiguous,
                      kind="currency", entity=entity, period=per)
    return "ambiguous_name", [insufficient(
        "a", "b", None, True, R.MISSING_INFORMATION, ("metric", "definition"),
        f"'{ambiguous}' is not a free synonym of revenue and no definition is given, so it "
        "cannot be established whether the concepts match.", "ambiguous_name")]


def sc_ambiguous_resolved(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    ambiguous = ctx.rng.choice(V.AMBIGUOUS_NAMES)
    same_concept, definition = ctx.rng.choice(V.AMBIGUOUS_RESOLUTIONS)
    c = V.CONCEPTS["revenue"]
    entity, per = ctx.company.name(ctx.rng), ctx.period(c, False)
    T = ctx.true_value(c)
    a = ctx.fact("a", metric=_plain_revenue_name(ctx), T=T, kind="currency", entity=entity,
                 period=per, definition=c.definition)
    values_same = ctx.rng.random() < 0.5
    _same_or_conflict(ctx, a, "b", same=values_same, T=T, metric=ambiguous, kind="currency",
                      entity=entity, period=per, definition=definition)
    if not same_concept:
        return "ambiguous_resolved", [related(
            "a", "b", False, True, R.DEFINITION, ("definition",),
            f"The definition of '{ambiguous}' restricts it, so it is a different measure.",
            "ambiguous_name", "definition_resolves")]
    if values_same:
        return "ambiguous_resolved", [equivalent(
            "a", "b", f"The definition of '{ambiguous}' makes it the same measure and the values "
                      "agree.", "ambiguous_name", "definition_resolves")]
    return "ambiguous_resolved", [conflicting(
        "a", "b", R.UNEXPLAINED, ("value",),
        f"The definition of '{ambiguous}' makes it the same measure, but the values differ.",
        "ambiguous_name", "definition_resolves")]


def sc_currency_mismatch(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    c = ctx.concept(("currency",), min_value=2e6)
    names = ctx.names(c, 2)
    T = ctx.true_value(c, min_value=2e6)
    entity, per = ctx.company.name(ctx.rng), ctx.period(c, False)
    other = ctx.rng.choice([u for u in ("USD", "EUR", "GBP") if u != ctx.unit])
    ctx.fact("a", metric=names[0], T=T, kind="currency", entity=entity, period=per)
    ctx.fact("b", metric=names[1], T=T * Decimal(str(round(ctx.rng.uniform(0.85, 1.15), 3))),
             kind="currency", entity=entity, period=per, unit=other)
    return "currency_mismatch", [insufficient(
        "a", "b", True, True, R.SCALE_OR_UNIT, ("unit",),
        f"Same concept, entity and period, but reported in {ctx.unit} and {other}; no conversion "
        "rate is available, so the values cannot be compared.", "currency_mismatch")]


def sc_restatement(ctx: Ctx) -> tuple[str, list[PairSpec]]:
    c = ctx.concept(("currency",), min_value=2e6)
    names = ctx.names(c, 2)
    T = ctx.true_value(c, min_value=2e6)
    entity, per = ctx.company.name(ctx.rng), ctx.period(c, False)
    a = ctx.fact("a", metric=names[0], T=T, kind="currency", entity=entity, period=per,
                 scale=Scale.MILLIONS, dp=1)
    for _ in range(50):
        new_T = ctx.perturb(T, "currency")
        shown = (new_T / int(Scale.MILLIONS)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        probe = BusinessFact(fact_id="x", metric="x", value=shown, unit=ctx.unit,
                             scale=Scale.MILLIONS, source=SourceRef(document_id="x"))
        if values_agree(a, probe) is False:
            break
    reason = ctx.rng.choice(["adoption of a new revenue standard", "correction of a prior-period error",
                             "reclassification of discontinued operations"])
    amt_new = ctx.amount_text(shown, Scale.MILLIONS, ctx.unit)
    amt_old = ctx.amount_text(a.value, Scale.MILLIONS, ctx.unit)
    ctx.fact("b", metric=names[1], T=new_T, kind="currency", entity=entity, period=per,
             scale=Scale.MILLIONS, dp=1,
             excerpt=f"{names[1]} for {per.label} was restated to {amt_new} from {amt_old} "
                     f"previously reported, following {reason}.")
    return "restatement", [conflicting(
        "a", "b", R.RESTATEMENT, ("value",),
        "Same concept, entity and period; the later source restates the earlier figure, so the "
        "two values disagree.", "restatement")]


TEMPLATES: dict[str, tuple[Template, int]] = {
    # name -> (template, default weight)
    "synonym_equivalent": (sc_synonym_equivalent, 16),
    "value_conflict": (sc_value_conflict, 10),
    "scale_error": (sc_scale_error, 4),
    "rounding": (sc_rounding, 5),
    "marker_diff": (sc_marker_diff, 8),
    "defined_diff": (sc_defined_diff, 12),
    "company_defined": (sc_company_defined, 10),
    "period_mismatch": (sc_period_mismatch, 10),
    "entity_mismatch": (sc_entity_mismatch, 6),
    "missing_entity": (sc_missing_entity, 5),
    "missing_period": (sc_missing_period, 5),
    "ambiguous_name": (sc_ambiguous_name, 6),
    "ambiguous_resolved": (sc_ambiguous_resolved, 5),
    "currency_mismatch": (sc_currency_mismatch, 5),
    "restatement": (sc_restatement, 3),
}
