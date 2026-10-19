# Decisions for the Project Owner

One place for every question that needs the project owner's call, so none is buried in a PR thread.
Updated 2026-10-18. Where a default is listed, engineering has already applied it; changing it
later costs rework in proportion to how much was built or labeled on top of it.

**How to answer:** reply in a PR or message, and the answer moves to the "Decided" table with the
date. Items are grouped by when they bite.

## A. Blocking the next two weeks

These gate the extraction work, the holdout and the release. Nothing else on this list blocks as
much.

| ID | Decision | Recommendation (and what is applied now) | Blocks |
|---|---|---|---|
| D-01 | **Which documents (board task 2.2).** Which 10 to 20 companies, and which documents for each. | 12 to 15 companies; at least 4 subscription businesses (so ARR exists); for each a 10-K plus an earnings deck or investor presentation; at least 2 with a published financial-supplement workbook; at least 2 with a non-GAAP reconciliation; mid-size companies and not all December year ends. Document the choice in the manifest ([extraction-adapter-scope.md](extraction-adapter-scope.md#the-manifest-the-owners-task-22-deliverable)). | The parser spike, the adapter on real documents, the holdout set |
| D-02 | **Redistribution (task 2.4).** What may be published: the documents, only references (URL, hash, page and cell pointers), or references plus the short evidence text. Engineering cannot decide this and gives no legal advice. | Applied now: raw documents stay out of the repo (`local_path` is never committed), and each `SourceDocument` has a `license_note` to fill in. Needs the owner's reading of the sources' terms before any dataset is published. | The public holdout and the release write-up (6.3) |
| D-03 | **Extraction scope for November 9.** Tables only (spreadsheets, 10-K and 10-Q statements) plus targeted deck facts for ARR and Adjusted EBITDA, or also narrative facts. May a model help with mapping labels to metrics? | MVP: tables, plus targeted decks; rules for mapping, with `other` for anything unmatched; no model in the extraction path. Narrative facts after the holdout is labeled. | The size of the adapter work (about 12 to 14 days against 17 to 19) |
| D-04 | **Use SEC XBRL data?** The 10-K and 10-Q filings carry machine-readable tagged values with periods and entities. | Use it to cross-check extracted facts at least; consider it as the primary source for 10-K statement values. It changes what "extraction accuracy" means, so the owner should agree. | How the adapter is verified and, optionally, how much of it is needed |
| D-05 | **Sign conventions (board question).** Should extraction normalize "net loss of 5.2" and "(5.2)" to -5.2, or should the reconciler handle raw signs? | The adapter normalizes (a loss is stored negative) and keeps the printed form in `raw_text`; the reconciler compares signed values. This is already how the schema and the generator behave. | The number parser (W2) |
| D-06 | **Who verifies extracted facts, and the accuracy bar.** | A hand-checked sample of about 60 facts across the document set; target at least 95% correct (value, scale, period, entity, basis) on the core metrics from tables. Split between the owner and engineering. | Trusting any result that depends on extraction |
| D-07 | **Success criteria and the fine-tuning threshold (board task 1.5, limitations #9).** What improvement counts as meaningful, in numbers (for example within X macro-F1 points of the frontier model at under Y% of the cost per 1,000 pairs, with false-match rate no worse than Z). | None applied. It must be written before any results exist, and the go/no-go decision D1 depends on it. | Reading any baseline result honestly |
| D-08 | **The replan.** The board's dates have slipped (M1 Oct 14, M2 Oct 17 are past). Accept the plan in [status.md](status.md): extraction MVP as the critical path, fine-tuning dropped from the November 9 release unless D1 says go early. | Accept. The release stays publishable either way, as the board says. | Everything dated |

## B. Needed before the labeling session

Changing any of these after labeling starts means relabeling. Defaults are what the guidelines and
code do today.

| ID | Decision | Default applied | Origin |
|---|---|---|---|
| D-09 | Is the four-label set right, given the plan's "whether differences are explainable"? A fifth label such as `explained_difference` is possible and costly to add later. | Four labels; the explanation lives in the reason codes | Limitations #1 |
| D-10 | Restatements: `conflicting` or something else? | `conflicting` with reason `restatement` | #2 |
| D-11 | When do two numbers agree: rounding implied by the coarser reported precision, or a fixed tolerance such as 0.5%? | Precision-based rounding | #4 |
| D-12 | Different currencies, with no conversion available | `insufficient_evidence` | #5 |
| D-13 | What counts as the same period when labels differ ("FY2025", "2025", "year ended June 30, 2025")? | Exact dates when available; otherwise normalized labels and fiscal year | #6 |
| D-14 | Unrelated pairs (revenue vs headcount) | Discarded, not labeled | #7 |
| D-15 | Who settles reviewer disagreements the reviewers cannot settle? | The owner | #8 |
| D-16 | "Net sales" is an unconditional revenue variant but "Net revenue" is conditional. Intended? And the plan page's example (Revenue vs Net Revenue equivalent) contradicts the metric page. | The metric page wins; guidelines v1.1 follow it. The plan page example still needs rewording. | Board question 2 |
| D-17 | Adjusted EBITDA, ARR and FCF names are the same concept only when both facts state matching definitions; otherwise insufficient evidence, even for identical names. | Applied in guidelines v1.1 | Board question 3 |
| D-18 | Flow vs point-in-time pairs (revenue vs ARR): the scope judgment is left undetermined and the concept difference settles the label. | Applied in the generator | Board question 5 |
| D-19 | The mined set is not representative: the mix of strata is deliberate, so base rates cannot be read off it. Agree to say so in the release write-up. Also the defaults for stratum weights and the 50/10/40 split of companies. | Defaults in [pair-mining.md](pair-mining.md) | PR #9 |

## C. Needed before the release

| ID | Decision | Recommendation or default | Origin |
|---|---|---|---|
| D-20 | Headline metric | False-match rate (wrongly merging distinct concepts is the costly error) | #10 |
| D-21 | Benchmark size | 100 to 200 cases per the board; wide error bars below about 8 to 10 points | #11 |
| D-22 | Employer boundary: no CircleEngage or MagnoliaHealth data, documents, figures or terminology anywhere in the repo, data or prompts. Confirm both sides understand. | Applied; assumed | #13 |
| D-23 | Dataset and model licenses. Code is Apache 2.0; data and weights are separate. | CC BY 4.0 for the data (subject to D-02) and Apache 2.0 for weights; the base model's license may restrict | #14 |
| D-24 | Which models to compare, and the cost method for self-hosted models. | One or two frontier models, one mid-size open-weight model (Vertex AI or vLLM), the same small model fine-tuned if D1 goes ahead, and the rules baseline. The self-hosted cost method (for example GPU-hours per 1,000 pairs at a quoted price) is undesigned. | #16 |
| D-25 | Base model family and size | One Apache-2.0 family, 1.5 to 3B locally, optionally 7 to 8B on a rented GPU | #15 |
| D-26 | GPU quota on the Google Cloud project `opslm-511123` | An action, not a choice: request it a week before it is needed. Not yet requested. | #17 |
| D-27 | Repository visibility | Public, as it is | #19 |
| D-28 | Is `metric_id` an extractor output on real data, and does the end-to-end evaluation give it to the reconciler? | Treated as a hint that systems do not see by default (the LLM system's `--show-metric-id`); the adapter will produce it by mapping rules | Review of #6 and #8 |

## D. Decided

Every question from the limitations doc (Part 1) and the board-alignment questions appears above or here; the "Origin" column gives the old number.

| ID | Decision | Decided | How |
|---|---|---|---|
| X-01 | The v1 metric set: Revenue, Gross margin, Adjusted EBITDA and Net income core; ARR optional; FCF and cash dropped | 2026-10-11 | PR #5 |
| X-02 | Net revenue is not a free variant of revenue (limitations #3) | 2026-10-11 | Metric page |
| X-03 | Schema v0.2.0 (facts with evidence spans, input and output, gold labels) | 2026-10-11 | PR #6 and #7 |
| X-04 | Reasons: only the primary reason is checked against the relationship; secondary reasons are free | 2026-10-18 | Review of PR #8 |
| X-05 | Reviewers who differ on the primary reason block finalize; different evidence is unioned and flagged | 2026-10-18 | Review of PR #8 |
| X-06 | `metric_id` is hidden from the LLM by default; the model chooses its own evidence spans | 2026-10-18 | Review of PR #8 |
| X-07 | The rules baseline knowing the held-out names is accepted; the real human-labeled holdout is the headline result (limitations #20) | 2026-10-18 | Review of PR #8 |
| X-08 | Planning stays in the spreadsheet; no GitHub Projects (board question 7) | October 2026, before 11 Oct | Message |
