# Decisions for the Project Owner

One place for every question that needs the project owner's call, so none is buried in a PR thread.
Updated 2026-11-03 with the owner's answers to Part B (D-10, D-12 to D-19), now X-17 to X-25, a new decision X-26, and the confirmed replan to November 30 (D-08, now X-27). IDs are stable: decided items move to the Decided table under a new X- number that records the old D- number. Where a default is listed, engineering has already applied it; changing it
later costs rework in proportion to how much was built or labeled on top of it.

**How to answer:** reply in a PR or message, and the answer moves to the "Decided" table with the
date. Items are grouped by when they bite.

## A. Blocking the next two weeks

These gate the extraction work, the holdout and the release. Nothing else on this list blocks as
much.

| ID | Decision | Recommendation (and what is applied now) | Blocks |
|---|---|---|---|
| D-29 | **The synthetic coverage grid** (the requirements page's first open item): which metric × reason code × label cells are required, optional or impossible. Task 3.1 was to start Oct 15 and waits on this. | Engineering drafts the grid from the schema's reason-to-relationship rules and the generator's current coverage; the owner marks it up. | Generator work against the requirements |
| D-30 | **Whether an LLM may rephrase template text** (the requirements page's second open item). | Templates only for the first release: reproducible, no provider terms to check, labels cannot drift. Revisit with the automatic meaning-preservation check the page describes. | Wording variety; not blocking |
| D-02 | **Redistribution (task 2.4).** What may be published: the documents, only references (URL, hash, page and cell pointers), or references plus the short evidence text. Engineering cannot decide this and gives no legal advice. | Applied now: raw documents stay out of the repo (`local_path` is never committed), and each `SourceDocument` has a `license_note` to fill in. Needs the owner's reading of the sources' terms before any dataset is published. | The public holdout and the release write-up (6.3) |
| D-03 | **Extraction scope for the release.** Tables only (spreadsheets, 10-K and 10-Q statements) plus targeted deck facts for ARR and Adjusted EBITDA, or also narrative facts. May a model help with mapping labels to metrics? | MVP: tables, plus targeted decks; rules for mapping, with `other` for anything unmatched; no model in the extraction path. Narrative facts after the holdout is labeled. | The size of the adapter work (about 12 to 14 days against 17 to 19) |
| D-04 | **Use SEC XBRL data?** The 10-K and 10-Q filings carry machine-readable tagged values with periods and entities. | Use it to cross-check extracted facts at least; consider it as the primary source for 10-K statement values. It changes what "extraction accuracy" means, so the owner should agree. | How the adapter is verified and, optionally, how much of it is needed |
| D-05 | **Sign conventions (board question).** Should extraction normalize "net loss of 5.2" and "(5.2)" to -5.2, or should the reconciler handle raw signs? | The adapter normalizes (a loss is stored negative) and keeps the printed form in `raw_text`; the reconciler compares signed values. This is already how the schema and the generator behave. | The number parser (W2) |
| D-06 | **Who verifies extracted facts, and the accuracy bar.** | A hand-checked sample of about 60 facts across the document set; target at least 95% correct (value, scale, period, entity, basis) on the core metrics from tables. Split between the owner and engineering. | Trusting any result that depends on extraction |
| D-07 | **Success criteria and the fine-tuning threshold (board task 1.5, limitations #9).** What improvement counts as meaningful, in numbers (for example within X macro-F1 points of the frontier model at under Y% of the cost per 1,000 pairs, with false-match rate no worse than Z). | None applied. It must be written before any results exist, and the go/no-go decision D1 depends on it. | Reading any baseline result honestly |

## B. Needed before the labeling session

All decided on 2026-11-03 (X-17 to X-26 below), except one new question that came out of the
engineering work on them (D-31). Their engineering follow-ups, with status, are listed after the
Decided table.

| ID | Decision | Recommendation | Blocks |
|---|---|---|---|
| D-31 | **How does a fact record that it is preliminary rather than restated?** X-17 and X-26 use two reasons (`restatement`, `preliminary_vs_final`) for pairs linked by `supersedes_fact_id`, but nothing in the data says which applies. | Add `preliminary` as a value of `reporting_status` on the earlier fact (an additive change); a superseded fact marked `preliminary` gives `preliminary_vs_final`, otherwise `restatement`. Until decided, the guidelines say to choose from what the sources say and default to `restatement`. | The reason a labeler or system should give; the generator cannot produce preliminary pairs until then |

## C. Needed before the release

| ID | Decision | Recommendation or default | Origin |
|---|---|---|---|
| D-20 | Headline metric | False-match rate (wrongly merging distinct concepts is the costly error) | #10 |
| D-21 | Benchmark size | 100 to 200 cases per the board; wide error bars below about 8 to 10 points | #11 |
| D-22 | Employer boundary: no documents, figures or terminology from either contributor's employers or customers anywhere in the repo, data or prompts. Confirm both sides understand. | Applied; assumed | #13 |
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
| X-01 | The v1 metric set: Revenue, Gross margin, Adjusted EBITDA and Net income core; ARR optional; FCF and cash dropped | 2026-10-11 | [PR #5](https://github.com/iamdirk-gc/opslm/pull/5) |
| X-02 | Net revenue is not a free variant of revenue (limitations #3) | 2026-10-11 | Metric page |
| X-03 | Schema v0.2.0 (facts with evidence spans, input and output, gold labels) | 2026-10-11 | [PR #6](https://github.com/iamdirk-gc/opslm/pull/6) and #7 |
| X-04 | Reasons: only the primary reason is checked against the relationship; secondary reasons are free | 2026-10-18 | Review of [PR #8](https://github.com/iamdirk-gc/opslm/pull/8) |
| X-05 | Reviewers who differ on the primary reason block finalize; different evidence is unioned and flagged | 2026-10-18 | Review of [PR #8](https://github.com/iamdirk-gc/opslm/pull/8) |
| X-06 | `metric_id` is hidden from the LLM by default; the model chooses its own evidence spans | 2026-10-18 | Review of [PR #8](https://github.com/iamdirk-gc/opslm/pull/8) |
| X-07 | The rules baseline knowing the held-out names is accepted; the real human-labeled holdout is the headline result (limitations #20) | 2026-10-18 | Review of [PR #8](https://github.com/iamdirk-gc/opslm/pull/8) |
| X-08 | Planning stays in the spreadsheet; no GitHub Projects (board question 7) | October 2026, before 11 Oct | Message |
| X-10 | **The document set (task 2.2):** 15 public companies, 9 holdout (benchmark pairs only, never mined for templates) and 6 pattern sources (mined for templates, may supply real training pairs); the roles and the documents in the set are on the [wiki](https://github.com/iamdirk-gc/opslm/wiki/OpsLM-Synthetic-Data-Requirements) | 2026-10-12 | Wiki page |
| X-11 | Four labels; explainable differences live in reason codes, not a fifth label (was D-09) | 2026-10-12 | Wiki page |
| X-12 | Two values agree if they differ by no more than the rounding implied by the less precise figure (was D-11) | 2026-10-12 | Wiki page |
| X-13 | Headline numbers come only from the real holdout; a synthetic test slice is reported separately, in its own table, labeled synthetic | 2026-10-12 | Wiki page |
| X-14 | Review gate: the owner reviews 50 random generated cases per release and two or more wrong labels blocks it; about 150 reviewed before the synthetic test slice is published | 2026-10-12 | Wiki page |
| X-15 | First synthetic release: about 2,000 pairs, about 25% per label in training, a realistic mix in the dev set | 2026-10-12 | Wiki page |
| X-16 | Synthetic cases use the same schema as real cases (v0.2.0), with `source = synthetic` | 2026-10-12 | Wiki page |
| X-17 | **Restatements** (was D-10). A restated value is stored as its own fact, never overwritten. A pair of the original and the restated value is labeled `conflicting` with reason `restatement`. When resolving, the reconciler selects the latest restated value (resolution status `resolved_with_conflict`, canonical value from the restated fact). | 2026-11-03 | Owner decisions, Part B |
| X-18 | **Currencies** (was D-12). v1 is USD only. A pair in different currencies, if one ever appears, is `insufficient_evidence` with reason `currency_mismatch`; no conversion. | 2026-11-03 | Owner decisions, Part B |
| X-19 | **Periods** (was D-13). Compare exact dates when available; otherwise normalized labels and fiscal year; if still unclear, `insufficient_evidence`. Record full period start and end dates (or the as-of date for ARR) whenever the source states them. | 2026-11-03 | Owner decisions, Part B |
| X-20 | **Unrelated pairs** (revenue vs headcount) are discarded, not labeled (was D-14). | 2026-11-03 | Owner decisions, Part B |
| X-21 | **Final say on reviewer disagreements:** the project owner (was D-15). Each tiebreak is written up as a rule in the guidelines so it is not argued again. | 2026-11-03 | Owner decisions, Part B |
| X-22 | **Net sales vs Net revenue** (was D-16). Net sales is a standard revenue variant; Net revenue is equivalent only when the company reports no separate gross revenue line. Intended. | 2026-11-03 | Owner decisions, Part B |
| X-23 | **Flow vs point-in-time pairs** (revenue vs ARR): the concept difference settles the label (`related_but_different`); scope is left undetermined (was D-18). | 2026-11-03 | Owner decisions, Part B |
| X-24 | **Mined set and splits** (was D-19). (1) The release write-up states that the holdout's label mix is deliberate and does not reflect real data rooms. (2) The default stratum weights are accepted as a starting point and may be adjusted after the first candidate pool. (3) The 0.5 / 0.1 / 0.4 random split by company is replaced by the company roles decided Oct 12 (X-10): the 9 holdout companies go to test only; the 6 pattern-source companies go to train and dev. | 2026-11-03 | Owner decisions, Part B |
| X-25 | **Definitions for company-defined metrics** (ARR, adjusted EBITDA) are recorded when facts are built, not looked up at comparison time (was D-17). Each fact carries its definition with an evidence span, taken from the same document or another document of the same company and period (for example a deck's adjusted EBITDA uses the release's reconciliation table). Definitions are stored per company and period, since they change between years. The reconciler compares the attached definitions: match = same concept; differ = `related_but_different` (`definition_mismatch`); none found in the document set = `insufficient_evidence` (`missing_definition`). | 2026-11-03 | Owner decisions, Part B |
| X-26 | **Preliminary vs final results** (new) are handled like restatements: both stored as separate facts, the pair labeled `conflicting` with new reason `preliminary_vs_final`, and the reconciler selects the final value. | 2026-11-03 | Owner decisions, Part B |
| X-27 | **The replan** (was D-08). The release moves from November 9 to November 30, 2026, with the milestone dates in the tracker. The extraction adapter is the critical path (due Nov 20); the holdout is built from hand-built facts (task 2.5), so labeling does not wait for the adapter; fine-tuning is decided at D1 once baselines exist and otherwise left out. | 2026-11-03 | Tracker, replanned Nov 3 |

### Follow-ups from the 2026-11-03 decisions

| ID | Engineering follow-up |
|---|---|
| X-17 | Schema: record each source document's filing or publication date, and link a restated fact to the fact it supersedes (for example `supersedes_fact_id`), so "latest" is determined from data, not guessed. Resolution scoring in the harness should check that the restated value wins. **Done:** schema 0.2.1 has `published_at` and `supersedes_fact_id`, and the generator's restatements use them. **Open:** resolution scoring (board task 4.1). |
| X-18 | Extraction and hand-built facts: record currency on every fact; flag any non-USD fact for review. All 15 companies report in USD. |
| X-19 | Hand-built facts (task 2.5) and the extraction adapter always fill `start`, `end` or `as_of` when the document gives them. |
| X-20 | None; the pair miner already avoids them. |
| X-21 | Labeling workflow: adjudication note required on every owner tiebreak. **Done:** the adjudication sheet already rejects a resolution without a `rule_decided`, which becomes the case's `adjudication_note`; the guidelines now say so. |
| X-22 | Fix the plan page example that treats Revenue and Net Revenue as equivalent. **Done in the repository copy** (`docs/plan.md`); the wiki plan page is the owner's and still has the old example. |
| X-23 | None; already applied in the generator. |
| X-24 | Replace the pair miner's hash-based split assignment with role-based assignment. [PR #9](https://github.com/iamdirk-gc/opslm/pull/9) merged on 2026-11-03 with the hash-based default, so this needed a follow-up PR. **Done:** the miner takes a roles CSV (`--roles`); holdout companies go to test only, pattern companies to train and dev, and a company with no role is an error. |
| X-25 | Hand-built facts (task 2.5) and the extraction adapter fill `stated_definition` and add the defining text as an evidence span; a per-company, per-period definition lookup lets many facts share one definition. Guidelines: a definition may come from a context span in another document of the same company and period. **Done:** guidelines v1.2. **Open:** the adapter and hand-built facts. |
| X-26 | Schema: add reason code `preliminary_vs_final` (allowed as a primary reason for `conflicting`). Resolution: select the final value, using the same supersedes link as X-17. Guidelines: add the rule and the reason. **Done:** the reason code and the guidelines rule (v1.2). **Open:** resolution selects the final value, and D-31 (how a preliminary fact is marked). |
| X-27 | Plan page and status snapshot use the Nov 30 date and the tracker's milestones. |
