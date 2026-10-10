# OpsLM v1 Metric Set (task 1.1)

Definitions, variants and concepts not to merge.

Five core metrics and two optional. ARR is core but only expected at subscription businesses, so it isn't required for every company in the document set. Drop free cash flow first, then cash, if the set needs to shrink.

Naming variants are treated as equivalent if definition, entity and period match.

## Summary

| Metric | Priority | Period type | Typical units |
|---|---|---|---|
| [Revenue](#revenue) | Core | Flow (fiscal year or quarter) | Currency (thousands or millions) |
| [ARR](#arr) | Core | Point in time (as of period end) | Currency (millions) |
| [Gross margin](#gross-margin) | Core | Flow (fiscal year or quarter) | Percent |
| [Adjusted EBITDA](#adjusted-ebitda) | Core | Flow (fiscal year or quarter) | Currency, or percent for margin |
| [Net income](#net-income) | Core | Flow (fiscal year or quarter) | Currency |
| [Free cash flow](#free-cash-flow) | Optional | Flow (fiscal year or quarter) | Currency, or percent for margin |
| [Cash and cash equivalents](#cash-and-cash-equivalents) | Optional | Point in time (balance sheet date) | Currency |

## Revenue

- **Canonical definition:** Total revenue recognized under GAAP/IFRS for the period, net of returns, discounts and allowances.
- **Naming variants:** Total revenue; Revenues; Net sales; Sales; Turnover
- **Related but different (never merge):** Net revenue (equivalent only when the company reports no separate gross revenue line; check the definition); ARR; Bookings; Billings; Gross revenue before discounts; Segment revenue; Subscription revenue only
- **Period type:** Flow (fiscal year or quarter)
- **Typical units:** Currency (thousands or millions)
- **Reconciliation traps:** Fiscal vs. calendar year; LTM vs. FY; gross vs. net presentation; rounding ($42.5M vs. $42,481K); restated prior-period figures; pro forma revenue including acquisitions
- **Example label cases:** Equivalent: 10-K "Total revenue" vs. deck "Revenue". Related: revenue vs. ARR. Conflicting: same FY, same definition, different value.
- **Priority:** Core

## ARR

- **Canonical definition:** Annualized value of active recurring subscription contracts at a point in time, as defined by the company.
- **Naming variants:** Annual recurring revenue; Annualized recurring revenue
- **Related but different (never merge):** Revenue; Annualized or run-rate revenue (can include nonrecurring revenue); Subscription revenue (a period flow); Bookings; RPO; Billings
- **Period type:** Point in time (as of period end)
- **Typical units:** Currency (millions)
- **Reconciliation traps:** Company-specific definition; point in time vs. period flow; whether usage-based or professional services revenue is included; definition changes between years
- **Example label cases:** Related: ARR vs. FY revenue. Insufficient evidence: deck states ARR without definition or as-of date.
- **Priority:** Core

## Gross margin

- **Canonical definition:** Gross profit (revenue minus cost of revenue) as a percentage of revenue.
- **Naming variants:** GM; Gross margin %; Gross profit margin
- **Related but different (never merge):** Gross profit in dollars (related by formula, not interchangeable); Non-GAAP gross margin; Contribution margin; Operating margin; Subscription gross margin (segment only)
- **Period type:** Flow (fiscal year or quarter)
- **Typical units:** Percent
- **Reconciliation traps:** Percent vs. dollars; GAAP vs. non-GAAP (stock comp and amortization excluded); what counts as cost of revenue; segment vs. total
- **Example label cases:** Related: gross profit $18M vs. gross margin 72%; GAAP 72% vs. non-GAAP 76%. Equivalent: 72% in the 10-K vs. 72.0% in the deck.
- **Priority:** Core

## Adjusted EBITDA

- **Canonical definition:** Net income before interest, taxes, depreciation and amortization, plus company-defined adjustments (often stock-based compensation and one-time items).
- **Naming variants:** Adj. EBITDA; Adjusted EBITDA; EBITDA (adjusted); Non-GAAP EBITDA
- **Related but different (never merge):** EBITDA (unadjusted); Operating income; Segment EBITDA; Adjusted operating income; EBITDA margin (percent)
- **Period type:** Flow (fiscal year or quarter)
- **Typical units:** Currency, or percent for margin
- **Reconciliation traps:** Adjustments differ between documents and change over time; deck figures often lack a reconciliation table; dollars vs. margin percent; management vs. audited figures
- **Example label cases:** Related: EBITDA vs. Adjusted EBITDA. Insufficient evidence: adjusted figure with no reconciliation. Conflicting: two adjusted figures for the same period with the same stated adjustments.
- **Priority:** Core

## Net income

- **Canonical definition:** Bottom-line profit or loss for the period under GAAP/IFRS.
- **Naming variants:** Net income; Net loss; Net income (loss); Net earnings; Profit for the period
- **Related but different (never merge):** Net income including noncontrolling interests vs. attributable to the company; Income from continuing operations; Adjusted net income; Comprehensive income
- **Period type:** Flow (fiscal year or quarter)
- **Typical units:** Currency
- **Reconciliation traps:** Entity boundary (attributable to parent vs. consolidated incl. NCI); sign conventions (-5.2 vs. (5.2) vs. "net loss of 5.2"); continuing vs. discontinued operations
- **Example label cases:** Equivalent: "Net loss of $5.2M" vs. "Net income (loss): (5.2)". Related: attributable to parent vs. including NCI.
- **Priority:** Core

## Free cash flow

- **Canonical definition:** Operating cash flow minus capital expenditures, as defined by the company.
- **Naming variants:** FCF; Free cash flow
- **Related but different (never merge):** Operating cash flow; Unlevered FCF; Adjusted FCF; FCF margin (percent)
- **Period type:** Flow (fiscal year or quarter)
- **Typical units:** Currency, or percent for margin
- **Reconciliation traps:** Company-specific: whether capitalized software or finance-lease payments are subtracted; levered vs. unlevered; dollars vs. margin percent
- **Example label cases:** Related: FCF vs. operating cash flow. Insufficient evidence: FCF stated without a definition.
- **Priority:** Optional

## Cash and cash equivalents

- **Canonical definition:** Cash on hand and highly liquid investments with original maturities of three months or less, as of the balance sheet date.
- **Naming variants:** Cash and cash equivalents; Cash; Cash & equivalents
- **Related but different (never merge):** Cash, cash equivalents and short-term investments; Total liquidity (incl. revolver); Restricted cash; Net cash (cash minus debt)
- **Period type:** Point in time (balance sheet date)
- **Typical units:** Currency
- **Reconciliation traps:** As-of date mismatches (quarter end vs. year end vs. deck date); scope (with or without short-term investments or restricted cash)
- **Example label cases:** Related: cash vs. cash + short-term investments. Conflicting: same as-of date and scope, different value.
- **Priority:** Optional
