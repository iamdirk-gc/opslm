# Labeling Guidelines (v1.0)

These rules define the gold labels for OpsLM evaluation cases. Two reviewers must reach the same label from the same pair by following them. Any change to the rules bumps the version (`GUIDELINE_VERSION` in `src/opslm/labels.py`) and cases labeled under the old version are re-reviewed.

## The task

Each case is a pair of extracted business facts. Decide how fact A relates to fact B, **using only the fields shown in the pair** (metric, value, unit, scale, entity, period, definition, qualifiers, source excerpt). Do not use outside knowledge about the real company, and do not look up the filing.

## The four labels

| Label | Meaning |
|---|---|
| `equivalent` | Same concept, same scope, and the values agree |
| `conflicting` | Same concept, same scope, but the values disagree |
| `related_but_different` | The facts are about different things: different concepts, or the same concept for a different entity or period |
| `insufficient_evidence` | A judgment needed to choose a label cannot be made from the fields shown |

## How to decide

Make three judgments in order. Each is **yes**, **no**, or **cannot tell**.

1. **Same concept?** Would a careful analyst substitute one metric for the other in a model without changing its meaning, given the definitions and qualifiers shown?
2. **Same scope?** Same entity (legal entity, segment, consolidation basis) **and** same period.
3. **Values agree?** Computed by code, not by the reviewer (see below).

| Same concept | Same scope | Values agree | Label |
|---|---|---|---|
| yes | yes | yes | `equivalent` |
| yes | yes | no | `conflicting` |
| no | any | any | `related_but_different` |
| yes | no | any | `related_but_different` |
| cannot tell | any | any | `insufficient_evidence` |
| any | cannot tell | any | `insufficient_evidence` |
| yes | yes | cannot tell | `insufficient_evidence` |

This table is implemented in `derive_label`. If you disagree with it for a case, raise it as a guideline question instead of overriding it.

### 1. Same concept

- **Default to the same concept for standard synonyms** unless a qualifier or definition on either fact signals a difference. Revenue, Sales and Net Revenue are the same concept when nothing says otherwise.
- **Different concept** when either fact carries a qualifier or definition that changes meaning: GAAP vs adjusted, gross vs net, recognized revenue vs a run-rate metric such as ARR, EBITDA vs Adjusted EBITDA, pro forma vs reported.
- **Cannot tell** when the metric names are not standard synonyms and no definition is provided, for example "Core Revenue" vs "Revenue" with no definition for Core.
- Different concept never depends on the numbers. Two different metrics with the same value are still `related_but_different`.

### 2. Same scope

- **Entity:** the same entity, or explicitly the same consolidation basis. A subsidiary vs its parent is a different scope.
- **Period:** the same period. Labels like "FY2025" are the same only if the dates match or the periods are plainly the same. A fiscal year ending June and a calendar year are different periods. Quarter vs full year is different. LTM vs fiscal year is different.
- **Cannot tell** if the entity or period is missing on either fact and the source excerpt does not state it.

### 3. Values agree

Computed by `values_agree`, not judged by eye:

- Scale is applied first (42.5 in millions equals 42,500 in thousands).
- Values agree if they differ by no more than the rounding implied by the coarser reported precision. 42.5M agrees with 42,540,000 but not with 42,700,000.
- Different units or currencies are **not comparable** (no currency conversion), which gives `insufficient_evidence`.
- A scale error (42.5 reported in units vs 42.5 in millions) is a disagreement, not a match.

## Principles

- **Label what the evidence supports, not what is plausible.** Do not invent explanations. If the same concept and scope show different values and nothing explains it, the label is `conflicting`, even if you suspect gross vs net.
- **Prefer `insufficient_evidence` to guessing,** but only when a required judgment truly cannot be made. Do not use it to avoid a hard but answerable case.
- **Pairs should be plausible candidates.** If two facts are wholly unrelated (Revenue vs headcount), discard the case and flag it. It would not be produced by a candidate generator and teaches the model nothing.

## Required fields on every case

- **`discrepancy_reason`** (required unless `equivalent`): the primary reason.

| Reason | Use when |
|---|---|
| `period` | The periods differ |
| `scale_or_unit` | Scale, currency or unit differs or is mis-stated |
| `scope` | Entity, segment or consolidation basis differs |
| `definition` | Concepts differ by definition or adjustment basis (GAAP vs adjusted, ARR vs revenue) |
| `restatement` | One source restates the other, and the pair or excerpt shows it |
| `unexplained` | Same concept and scope, values differ, nothing explains it |
| `missing_information` | A field needed to judge is absent |
| `error` | An evident extraction or reporting error (e.g. misplaced decimal) |
| `other` | None of the above (explain in the rationale) |

- **`discriminating_fields`**: the `BusinessFact` fields that determine the label (for example `["period"]` or `["definition", "qualifiers"]`). For `equivalent` cases this may be empty. Systems are scored on whether their cited evidence includes these.
- **`rationale`**: one or two sentences naming the judgments, e.g. "Same entity and period; Sales is a standard synonym of Revenue; $42.5M vs $44.1M disagree."
- **`tags`**: free-form, for slicing results (`synonym`, `unit_mismatch`, `period_mismatch`, `adjusted_vs_gaap`).

## Worked examples

From the plan's example data room (all FY2025, same company):

| A | B | Label | Reason |
|---|---|---|---|
| Financial statements: Revenue $42.5M | Revenue workbook: Net Revenue $42.5M | `equivalent` | none (standard synonyms, values agree) |
| Financial statements: Revenue $42.5M | Management presentation: Sales $44.1M | `conflicting` | `unexplained` (same concept and scope, values differ, no definition given) |
| Financial statements: Revenue $42.5M | Investor presentation: ARR $39.2M | `related_but_different` | `definition` (ARR is a run-rate metric, not recognized revenue) |

More cases:

| A | B | Label | Reason |
|---|---|---|---|
| Revenue, FY2025, $42.5M | Revenue, Q3 2025, $11.0M | `related_but_different` | `period` |
| EBITDA $8.0M | Adjusted EBITDA $8.0M | `related_but_different` | `definition` (same number, different concept) |
| Revenue $42.5M (USD) | Revenue €39.0M (EUR) | `insufficient_evidence` | `scale_or_unit` (no conversion available) |
| Revenue, FY2025, entity missing | Revenue, FY2025, Acme Corp | `insufficient_evidence` | `missing_information` |
| Revenue $42.5M (millions) | Revenue 42.5 (units) | `conflicting` | `scale_or_unit` |
| Revenue $42.5M in Q3 deck | Revenue $43.1M, note: "restated for ASC 606 adoption" | `conflicting` | `restatement` |

## Review process

1. Each reviewer labels independently, without seeing the other's answers.
2. Each reviewer labels their own batch (about 75 cases) **plus a shared overlap batch of about 30 cases** that both label.
3. Compute agreement on the overlap (Cohen's kappa on the four labels, and on the same-concept judgment alone). Target kappa of at least 0.7.
4. Review every disagreement together, decide the correct label, and **write down the rule** that settled it. If the rule is not already in this document, add it and bump the version.
5. Only after the overlap is reconciled, finish the individual batches. Keep the shared overlap cases in the final test set with the reconciled label.
6. Set `reviewed: true` only once a case has been labeled under the current guideline version.

Cases marked `reviewed: false` can be used for training but never for the reported test results.

## Open questions

- Is a restatement `conflicting` or `related_but_different`? v1.0 treats it as `conflicting` with reason `restatement`, since the same fact has two values. Revisit if reviewers disagree.
- How to treat facts that carry an explicit tolerance or "approximately" qualifier. Not handled in v1.0.
