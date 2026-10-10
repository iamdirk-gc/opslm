# ruff: noqa: ISC004
"""Vocabulary for the synthetic generator, based on the v1 metric set on the project board.

The metric definitions, naming variants, "related but different" lists and reconciliation traps
come from the project owner's "Metric Definitions" sheet (task 1.1). Where the generator
encodes a rule it follows that sheet:

- Naming variants are equivalent when definition, entity and period match.
- Company-defined metrics (ARR, Adjusted EBITDA, free cash flow) are only comparable when the
  definitions or adjustments are stated and match. Without them the label is insufficient
  evidence, with different stated definitions the facts are related but different.
- Point-in-time metrics (ARR, cash) are compared on their as-of date.
- "Net revenue" is equivalent to revenue only when the company reports no separate gross line,
  so it is never a free synonym here.

This vocabulary is independent of the rules baseline's synonym table. Names marked ``heldout``
appear only in validation and test scenarios, so those splits measure generalization beyond
the surface forms seen in training.
"""

from __future__ import annotations

import calendar
import random
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from opslm.schema import Period, PeriodType

Kind = Literal["currency", "percent"]


@dataclass(frozen=True)
class Concept:
    key: str
    kind: Kind
    low: float  # magnitude range for generated true values
    high: float
    names: tuple[str, ...]
    heldout: tuple[str, ...]
    definition: str
    point: bool = False  # point-in-time (as-of date) rather than a period flow
    signed: bool = False  # can be negative (net loss)
    company_defined: bool = False  # comparable only when definitions are stated and match


_REV_DEF = "Total revenue recognized under GAAP for the period, net of returns, discounts and allowances."

CONCEPTS: dict[str, Concept] = {c.key: c for c in [
    Concept("revenue", "currency", 2e6, 9e8,
            ("Revenue", "Total revenue", "Net sales", "Revenues"), ("Sales", "Turnover"), _REV_DEF),
    Concept("gross_margin", "percent", 8, 85,
            ("Gross margin", "Gross margin %"), ("GM", "Gross profit margin"),
            "Gross profit (revenue minus cost of revenue) as a percentage of revenue."),
    Concept("net_income", "currency", 3e5, 1.5e8,
            ("Net income", "Net earnings", "Net income (loss)"), ("Profit for the period",),
            "Bottom-line profit or loss for the period under GAAP.", signed=True),
    Concept("cash", "currency", 2e5, 3e8,
            ("Cash and cash equivalents", "Cash & equivalents"), ("Cash",),
            "Cash on hand and highly liquid investments with original maturities of three "
            "months or less, as of the balance sheet date.", point=True),
    Concept("arr", "currency", 1e6, 5e8,
            ("ARR", "Annual recurring revenue"), ("Annualized recurring revenue",),
            "Annualized value of active recurring subscription contracts at a point in time.",
            point=True, company_defined=True),
    Concept("adjusted_ebitda", "currency", 5e5, 2e8,
            ("Adjusted EBITDA", "Adj. EBITDA"), ("EBITDA (adjusted)", "Non-GAAP EBITDA"),
            "Net income before interest, taxes, depreciation and amortization, plus adjustments.",
            company_defined=True),
    Concept("fcf", "currency", 2e5, 1e8,
            ("Free cash flow", "FCF"), (), "Operating cash flow minus capital expenditures.",
            company_defined=True),
]}
GENERIC = tuple(k for k, c in CONCEPTS.items() if not c.company_defined)
COMPANY_DEFINED = tuple(k for k, c in CONCEPTS.items() if c.company_defined)

# Company-defined metrics: each inner tuple is a group of wordings with the SAME meaning;
# different groups mean different definitions (for example different adjustments).
DEFINITION_GROUPS: dict[str, tuple[tuple[str, ...], ...]] = {
    "arr": (
        ("Annualized value of active recurring subscription contracts at period end.",
         "Annualized value of recurring subscription contracts in force as of the period end date."),
        ("Annualized recurring revenue including usage-based and professional services revenue.",),
    ),
    "adjusted_ebitda": (
        ("Net income before interest, taxes, depreciation and amortization, excluding "
         "stock-based compensation and one-time items.",
         "Earnings before interest, taxes, depreciation and amortization, adjusted to exclude "
         "stock-based compensation and one-time items."),
        ("Net income before interest, taxes, depreciation and amortization, excluding "
         "stock-based compensation only.",),
        ("Net income before interest, taxes, depreciation and amortization, excluding "
         "stock-based compensation, restructuring and acquisition costs.",),
    ),
    "fcf": (
        ("Operating cash flow minus capital expenditures.",
         "Cash provided by operating activities less purchases of property and equipment."),
        ("Operating cash flow minus capital expenditures and capitalized software costs.",),
    ),
}

# Markers that change meaning when added to a metric name: concept -> (label, qualifier form)
MARKERS_FOR: dict[str, tuple[tuple[str, str], ...]] = {
    "revenue": (("Gross", "gross"), ("Pro forma", "pro forma"),
                ("Constant currency", "constant currency")),
    "gross_margin": (("Non-GAAP", "non-gaap"),),
    "net_income": (("Adjusted", "adjusted"), ("Non-GAAP", "non-gaap")),
}

# Different measures where each fact states its definition (the signal required for a "no"):
# (name A, definition A, kind A, name B, definition B, kind B, point-in-time)
_ARR = CONCEPTS["arr"].definition
_NI = "Bottom-line profit or loss for the period under GAAP, including noncontrolling interests."
RELATED_DIFFERENT: tuple[tuple[str, str, str, str, str, str, bool, bool], ...] = (
    ("Revenue", _REV_DEF, "currency", "ARR", _ARR, "currency", False, True),
    ("Revenue", _REV_DEF, "currency", "Bookings",
     "Total contract value signed during the period, whether or not yet recognized.", "currency", False, False),
    ("Revenue", _REV_DEF, "currency", "Billings",
     "Amounts invoiced to customers during the period.", "currency", False, False),
    ("Revenue", _REV_DEF, "currency", "Subscription revenue",
     "Revenue recognized from subscription contracts only.", "currency", False, False),
    ("ARR", _ARR, "currency", "Annualized revenue",
     "Current-quarter revenue multiplied by four, including nonrecurring revenue.", "currency", True, True),
    ("ARR", _ARR, "currency", "Remaining performance obligations",
     "Contracted revenue not yet recognized at the balance sheet date.", "currency", True, True),
    ("Gross margin", CONCEPTS["gross_margin"].definition, "percent", "Gross profit",
     "Revenue minus cost of revenue, in currency.", "currency", False, False),
    ("Gross margin", CONCEPTS["gross_margin"].definition, "percent", "Operating margin",
     "Operating income as a percentage of revenue.", "percent", False, False),
    ("Gross margin", CONCEPTS["gross_margin"].definition, "percent", "Contribution margin",
     "Revenue less all variable costs, as a percentage of revenue.", "percent", False, False),
    ("Adjusted EBITDA", DEFINITION_GROUPS["adjusted_ebitda"][0][0], "currency", "EBITDA",
     "Net income before interest, taxes, depreciation and amortization, with no adjustments.",
     "currency", False, False),
    ("Adjusted EBITDA", DEFINITION_GROUPS["adjusted_ebitda"][0][0], "currency", "Operating income",
     "Revenue less cost of revenue and operating expenses.", "currency", False, False),
    ("Adjusted EBITDA", DEFINITION_GROUPS["adjusted_ebitda"][0][0], "currency",
     "Adjusted EBITDA margin", "Adjusted EBITDA as a percentage of revenue.", "percent", False, False),
    ("Net income", _NI, "currency", "Net income attributable to the company",
     "Net income after deducting the share attributable to noncontrolling interests.", "currency", False, False),
    ("Net income", _NI, "currency", "Income from continuing operations",
     "Profit before the results of discontinued operations.", "currency", False, False),
    ("Net income", _NI, "currency", "Comprehensive income",
     "Net income plus other comprehensive income items.", "currency", False, False),
    ("Free cash flow", DEFINITION_GROUPS["fcf"][0][0], "currency", "Operating cash flow",
     "Cash generated by operating activities before capital expenditures.", "currency", False, False),
    ("Free cash flow", DEFINITION_GROUPS["fcf"][0][0], "currency", "FCF margin",
     "Free cash flow as a percentage of revenue.", "percent", False, False),
    ("Cash and cash equivalents", CONCEPTS["cash"].definition, "currency",
     "Cash, cash equivalents and short-term investments",
     "Cash and cash equivalents plus investments maturing within one year.", "currency", True, True),
    ("Cash and cash equivalents", CONCEPTS["cash"].definition, "currency", "Restricted cash",
     "Cash held that is not available for general use.", "currency", True, True),
    ("Cash and cash equivalents", CONCEPTS["cash"].definition, "currency", "Net cash",
     "Cash and cash equivalents minus total debt.", "currency", True, True),
    ("Cash and cash equivalents", CONCEPTS["cash"].definition, "currency", "Total liquidity",
     "Cash plus undrawn committed credit facilities.", "currency", True, True),
)

# Names that are not free synonyms: without a definition the guidelines call for "cannot tell".
AMBIGUOUS_NAMES: tuple[str, ...] = ("Net revenue", "Net revenue", "Core revenue", "Platform revenue")
# Definitions that settle an ambiguous revenue name: (same concept as revenue?, text)
AMBIGUOUS_RESOLUTIONS: tuple[tuple[bool, str], ...] = (
    (True, "Total revenue recognized under GAAP, net of returns, discounts and allowances; the "
           "company reports no separate gross revenue line."),
    (True, "All revenue recognized in the period under GAAP; the company reports no gross "
           "revenue before discounts."),
    (False, "Revenue after deducting platform fees and sales taxes; a separate gross revenue "
            "line is also reported."),
    (False, "Revenue from subscription contracts only, excluding professional services."),
)

DOC_TYPES = ("10-K", "annual_report", "financial_statements", "management_presentation",
             "investor_presentation", "revenue_workbook", "board_deck", "lender_report")

_ONSETS = ("Ve", "Qua", "Nor", "Alt", "Zen", "Mar", "Bri", "Cal", "Dyn", "Ful", "Ori", "Tal", "Sol")
_ENDINGS = ("trix", "vance", "lume", "gard", "spire", "tek", "ora", "nova", "field", "works", "dex")
SUFFIX_FORMS: dict[str, tuple[str, ...]] = {
    "Inc": ("Inc.", ", Inc.", "Inc", "Incorporated"),
    "Corp": ("Corp.", "Corp", "Corporation"),
    "Ltd": ("Ltd.", "Ltd", "Limited"),
    "LLC": ("LLC", "L.L.C."),
}
REGIONS = ("Europe", "Asia Pacific", "UK", "Canada", "Germany", "Latin America")
SEGMENTS = ("Cloud", "Services", "Hardware", "Consumer", "Enterprise")


@dataclass(frozen=True)
class Company:
    base: str
    suffix_family: str

    def name(self, rng: random.Random, *, vary: bool = False) -> str:
        forms = SUFFIX_FORMS[self.suffix_family]
        form = rng.choice(forms) if vary else forms[0]
        text = f"{self.base}{form}" if form.startswith(",") else f"{self.base} {form}"
        if vary and rng.random() < 0.2:
            text = text.upper()
        return text

    def subsidiary(self, rng: random.Random) -> str:
        return f"{self.base} {rng.choice(REGIONS)} {rng.choice(SUFFIX_FORMS['Ltd'][:2])}"

    def segment(self, rng: random.Random) -> str:
        return f"{self.base} {rng.choice(SEGMENTS)} segment"


def make_company(rng: random.Random, used: set[str]) -> Company:
    for _ in range(1000):
        base = rng.choice(_ONSETS) + rng.choice(_ENDINGS)
        if rng.random() < 0.5:
            base += " " + rng.choice(("Holdings", "Systems", "Industries", "Labs", "Partners"))
        if base not in used:
            used.add(base)
            return Company(base, rng.choice(tuple(SUFFIX_FORMS)))
    raise RuntimeError("company name space exhausted; generate fewer scenarios")


# --- periods ---------------------------------------------------------------------------


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _add_months(d: date, months: int) -> date:
    """Last day of the month `months` after the month of d (d is a month end)."""
    total = d.year * 12 + (d.month - 1) + months
    return _month_end(total // 12, total % 12 + 1)


class FiscalCalendar:
    """A company's fiscal year, with the surface forms its documents use."""

    def __init__(self, year: int, end_month: int) -> None:
        self.year, self.end_month = year, end_month
        self.end = _month_end(year, end_month)
        self.start = _add_months(self.end, -12) + timedelta(days=1)

    def fy_labels(self) -> tuple[str, ...]:
        y = self.year
        return (f"FY{y}", f"FY {y}", f"Fiscal {y}", f"Fiscal Year {y}", f"FY{y % 100:02d}")

    def fy(self, rng: random.Random, *, dated: bool, label: str | None = None) -> Period:
        return Period(label=label or rng.choice(self.fy_labels()), type=PeriodType.FISCAL_YEAR,
                      start=self.start if dated else None, end=self.end if dated else None)

    def fy_long(self) -> Period:
        text = f"Year ended {self.end.strftime('%B')} {self.end.day}, {self.end.year}"
        return Period(label=text, type=PeriodType.FISCAL_YEAR, start=self.start, end=self.end)

    def other_year(self, delta: int) -> FiscalCalendar:
        return FiscalCalendar(self.year + delta, self.end_month)

    def quarter(self, q: int, *, dated: bool) -> Period:
        q_end = _add_months(self.start - timedelta(days=1), 3 * q)
        q_start = _add_months(self.start - timedelta(days=1), 3 * (q - 1)) + timedelta(days=1)
        return Period(label=f"Q{q} FY{self.year}", type=PeriodType.QUARTER,
                      start=q_start if dated else None, end=q_end if dated else None)

    def ltm(self) -> Period:
        end = _add_months(self.start - timedelta(days=1), 9)  # trailing twelve months to Q3 end
        start = _add_months(end, -12) + timedelta(days=1)
        return Period(label=f"LTM {end.strftime('%b %Y')}", type=PeriodType.LTM, start=start, end=end)

    def calendar_year(self) -> Period:
        return Period(label=f"Calendar {self.year}", type=PeriodType.CALENDAR_YEAR,
                      start=date(self.year, 1, 1), end=date(self.year, 12, 31))

    def asof(self, rng: random.Random, quarter: int | None = None) -> Period:
        """A point-in-time period: fiscal year end, or the end of fiscal quarter 1-3."""
        d = self.end if quarter is None else _add_months(self.start - timedelta(days=1), 3 * quarter)
        forms = (f"As of {d.strftime('%B')} {d.day}, {d.year}", f"{d.strftime('%B')} {d.day}, {d.year}",
                 f"At {d.strftime('%b')} {d.day}, {d.year}")
        return Period(label=rng.choice(forms), type=PeriodType.POINT_IN_TIME, start=d, end=d)


def make_calendar(rng: random.Random, *, non_december: bool = False) -> FiscalCalendar:
    months = [m for m in range(1, 13) if m != 12] if non_december else [12, 12, 12, 6, 9, 3]
    return FiscalCalendar(rng.randint(2021, 2025), rng.choice(months))
