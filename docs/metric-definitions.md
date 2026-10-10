# v1 Metric Set

The v1 metrics, with their definitions, accepted naming variants and traps. Source: the project
owner's "Metric Definitions" sheet on the project board (task 1.1). The generator's vocabulary
(`src/opslm/datagen/vocab.py`) and guidelines v1.1 follow this page.

Naming variants are equivalent only if definition, entity and period also match. "Related but
different" metrics are never merged.

| Metric | Priority | Definition | Naming variants | Related but different (never merge) |
|---|---|---|---|---|
| Revenue | Core | Total revenue recognized under GAAP/IFRS for the period, net of returns, discounts and allowances | Total revenue, Revenues, Net sales, Sales, Turnover | Net revenue (equivalent only if the company reports no separate gross revenue line), ARR, bookings, billings, gross revenue before discounts, segment revenue, subscription revenue only |
| ARR | Core | Annualized value of active recurring subscription contracts at a point in time, as defined by the company | Annual recurring revenue, Annualized recurring revenue | Revenue, annualized or run-rate revenue, subscription revenue (a period flow), bookings, RPO, billings |
| Gross margin | Core | Gross profit as a percentage of revenue | GM, Gross margin %, Gross profit margin | Gross profit in dollars, non-GAAP gross margin, contribution margin, operating margin, subscription gross margin (segment only) |
| Adjusted EBITDA | Core | Net income before interest, taxes, depreciation and amortization, plus company-defined adjustments | Adj. EBITDA, EBITDA (adjusted), Non-GAAP EBITDA | EBITDA (unadjusted), operating income, segment EBITDA, adjusted operating income, EBITDA margin |
| Net income | Core | Bottom-line profit or loss for the period under GAAP/IFRS | Net earnings, Net loss, Net income (loss), Profit for the period | Including vs attributable to noncontrolling interests, income from continuing operations, adjusted net income, comprehensive income |
| Free cash flow | Optional | Operating cash flow minus capital expenditures, as defined by the company | FCF | Operating cash flow, unlevered FCF, adjusted FCF, FCF margin |
| Cash and cash equivalents | Optional | Cash and highly liquid investments with original maturities of three months or less, at the balance sheet date | Cash, Cash & equivalents | Cash plus short-term investments, total liquidity, restricted cash, net cash |

## Period types

- Flow (fiscal year or quarter): revenue, gross margin, adjusted EBITDA, net income, free cash flow.
- Point in time (as-of date): ARR, cash.

## Traps called out by the sheet

- **Revenue:** fiscal vs calendar year, LTM vs FY, gross vs net presentation, rounding ($42.5M vs $42,481K), restated prior-period figures, pro forma revenue.
- **ARR:** company-specific definitions, point in time vs period flow, whether usage or services revenue is included, definition changes between years.
- **Gross margin:** percent vs dollars, GAAP vs non-GAAP, what counts as cost of revenue, segment vs total.
- **Adjusted EBITDA:** adjustments differ between documents and over time, deck figures often lack a reconciliation, dollars vs margin percent.
- **Net income:** attributable to parent vs consolidated, sign conventions (-5.2 vs (5.2) vs "net loss of 5.2"), continuing vs discontinued operations.
- **Free cash flow:** whether capitalized software or finance-lease payments are subtracted, levered vs unlevered, dollars vs margin.
- **Cash:** as-of date mismatches, scope (short-term investments, restricted cash).
