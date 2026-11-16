# Decisions for the Project Owner

One place for every question that needs the project owner's call, so none is buried in a PR thread.
Updated 2026-11-16 with the owner's answers to everything still open except D-02 (X-33 to X-46). Earlier: the Part B answers and the replan on 2026-11-03 (X-17 to X-27) and the success criteria ([OpsLM Success Criteria](https://github.com/iamdirk-gc/opslm/wiki/OpsLM-Success-Criteria) on the wiki, X-28 to X-32). IDs are stable: decided items move to the Decided table under a new X- number that records the old D- number. Where a default is listed, engineering has already applied it; changing it
later costs rework in proportion to how much was built or labeled on top of it.

**How to answer:** reply in a PR or message, and the answer moves to the "Decided" table with the
date. Items are grouped by when they bite.

## A. Blocking the next two weeks

These gate the extraction work, the holdout and the release. As of 2026-11-16 only D-02 is open:
it waits on the owner's reading of the sources' terms.

| ID | Decision | Recommendation (and what is applied now) | Blocks |
|---|---|---|---|
| D-02 | **Redistribution (task 2.4).** What may be published: the documents, only references (URL, hash, page and cell pointers), or references plus the short evidence text. Engineering cannot decide this and gives no legal advice. | Applied now: raw documents stay out of the repo (`local_path` is never committed), and each `SourceDocument` has a `license_note` to fill in. Needs the owner's reading of the sources' terms before any dataset is published. | The public holdout and the release write-up (6.3) |

## B. Needed before the labeling session

All decided: X-17 to X-26 on 2026-11-03, and D-31 on 2026-11-16 (X-33). Their engineering follow-ups, with status, are listed after the Decided table.

## C. Needed before the release

| ID | Decision | Recommendation or default | Origin |
|---|---|---|---|
| D-26 | GPU quota on the Google Cloud project `opslm-511123` | An action, not a choice: request it a week before it is needed. Not yet requested. | #17 |

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
| X-28 | **Headline metric** (was D-20): the false-match rate, how often a system says two facts are the same when they are not (a wrong merge silently corrupts downstream analysis). Reported alongside it: macro-F1 (the four labels weighted equally) and cost per 1,000 pairs. | 2026-11-03 | [OpsLM Success Criteria](https://github.com/iamdirk-gc/opslm/wiki/OpsLM-Success-Criteria) |
| X-29 | **The benchmark is trustworthy** when all hold: at least 150 labeled holdout cases from the 9 holdout companies; the two reviewers agree on at least 80% of the overlap cases before adjudication; extraction is at least 95% correct on the hand-checked fact sample. (Sets the floor in D-21 and the accuracy bar in D-06.) | 2026-11-03 | [OpsLM Success Criteria](https://github.com/iamdirk-gc/opslm/wiki/OpsLM-Success-Criteria) |
| X-30 | **A small model is competitive with the frontier model** (was D-07) when all hold: macro-F1 within 5 points of the frontier model; false-match rate at most 5% and no more than 2 points above the frontier model; at most 20% of the frontier model's cost per 1,000 pairs; p95 latency no slower than the frontier model. The release is a success even if the answer is "not competitive yet", as long as results are judged against these targets. | 2026-11-03 | [OpsLM Success Criteria](https://github.com/iamdirk-gc/opslm/wiki/OpsLM-Success-Criteria) |
| X-31 | **Self-hosted cost** (part of D-24) is GPU-hours at a published hourly price, at a stated volume (for example 100,000 pairs a month), so idle time at benchmark scale does not distort the comparison. | 2026-11-03 | [OpsLM Success Criteria](https://github.com/iamdirk-gc/opslm/wiki/OpsLM-Success-Criteria) |
| X-32 | **Fine-tuning go/no-go (D1, Nov 23) and the reporting rule.** Go if the untuned small model meets the cost target but misses quality or safety; no-go if it meets every target, or misses on cost. Fine-tuning worked if it improves macro-F1 by at least 5 points over the untuned small model and lowers the false-match rate. Every number is reported with its confidence interval, and a difference is claimed only when the intervals support it. | 2026-11-03 | [OpsLM Success Criteria](https://github.com/iamdirk-gc/opslm/wiki/OpsLM-Success-Criteria) |
| X-33 | **Preliminary vs restated facts** (was D-31). Add `preliminary` as a value of `reporting_status` on the earlier fact. A superseded fact marked `preliminary` gives reason `preliminary_vs_final`; any other superseded fact gives `restatement`. | 2026-11-16 | Owner decisions, Nov 16 |
| X-34 | **Extraction scope** (was D-03). The adapter covers tables (10-K and 10-Q statements, spreadsheets) plus targeted deck facts for ARR and Adjusted EBITDA. Mapping labels to metrics is rule-based, with `other` for anything unmatched; no model in the extraction path. Narrative facts come later. | 2026-11-16 | Owner decisions, Nov 16 |
| X-35 | **SEC XBRL data** (was D-04). XBRL cross-checks every extracted fact and is the main source for 10-K statement values. | 2026-11-16 | Owner decisions, Nov 16 |
| X-36 | **Sign conventions** (was D-05). Extraction normalizes signs (a loss is stored negative) and keeps the printed form in `raw_text`; the reconciler compares signed values. | 2026-11-16 | Owner decisions, Nov 16 |
| X-37 | **Who verifies extracted facts** (was D-06). A hand-checked sample of about 60 facts across the document set, split between the owner and engineering, against the 95% bar in X-29. | 2026-11-16 | Owner decisions, Nov 16 |
| X-38 | **The second replan.** Extraction stays in the release, so the release moves from November 30 to **early January 2027**; the exact date is set with engineering. Every milestone moves, including the fine-tuning go/no-go (D1, was Nov 23). Supersedes the date in X-27. | 2026-11-16 | Owner decisions, Nov 16 |
| X-39 | **Synthetic coverage grid** (was D-29). Rule-based: required, every valid label and primary-reason pair on the four core metrics; optional, ARR; impossible, `currency_mismatch` (v1 is USD only, X-18) and any pair the schema rejects. | 2026-11-16 | Owner decisions, Nov 16 |
| X-40 | **LLM rephrasing** (was D-30). Templates only for v1; no LLM rephrasing. | 2026-11-16 | Owner decisions, Nov 16 |
| X-41 | **Benchmark size** (was D-21). 150 to 200 holdout cases (the floor of 150 is X-29). | 2026-11-16 | Owner decisions, Nov 16 |
| X-42 | **Employer boundary** (was D-22). No employer or customer material anywhere in the repo, data or prompts. | 2026-11-16 | Owner decisions, Nov 16 |
| X-43 | **Licenses** (was D-23). CC BY 4.0 for the data (subject to D-02), Apache 2.0 for weights; code stays Apache 2.0. | 2026-11-16 | Owner decisions, Nov 16 |
| X-44 | **Models compared** (was D-24 and D-25). One or two frontier models, one mid-size open-weight model, one small Apache-2.0 model (1.5 to 3B locally, optionally 7 to 8B on a rented GPU) for fine-tuning, and the rules baseline. | 2026-11-16 | Owner decisions, Nov 16 |
| X-45 | **Repository visibility** (was D-27). The repository stays public. | 2026-11-16 | Owner decisions, Nov 16 |
| X-46 | **`metric_id`** (was D-28). A hint the systems do not see by default; the adapter produces it with mapping rules. | 2026-11-16 | Owner decisions, Nov 16 |

### Follow-ups from the 2026-11-03 decisions

| ID | Engineering follow-up |
|---|---|
| X-17 | Schema: record each source document's filing or publication date, and link a restated fact to the fact it supersedes (for example `supersedes_fact_id`), so "latest" is determined from data, not guessed. Resolution scoring in the harness should check that the restated value wins. **Done:** schema 0.2.1 has `published_at` and `supersedes_fact_id`, and the generator's restatements use them. **Open:** resolution scoring (board task 4.1). |
| X-18 | Extraction and hand-built facts: record currency on every fact; flag any non-USD fact for review. All 15 companies report in USD. |
| X-19 | Hand-built facts (task 2.5) and the extraction adapter always fill `start`, `end` or `as_of` when the document gives them. |
| X-20 | None; the pair miner already avoids them. |
| X-21 | Labeling workflow: adjudication note required on every owner tiebreak. **Done:** the adjudication sheet already rejects a resolution without a `rule_decided`, which becomes the case's `adjudication_note`; the guidelines now say so. |
| X-22 | Fix the plan page example that treats Revenue and Net Revenue as equivalent. **Done:** the repository copy (`docs/plan.md`) and the wiki plan page. |
| X-23 | None; already applied in the generator. |
| X-24 | Replace the pair miner's hash-based split assignment with role-based assignment. [PR #9](https://github.com/iamdirk-gc/opslm/pull/9) merged on 2026-11-03 with the hash-based default, so this needed a follow-up PR. **Done:** the miner takes a roles CSV (`--roles`); holdout companies go to test only, pattern companies to train and dev, and a company with no role is an error. |
| X-25 | Hand-built facts (task 2.5) and the extraction adapter fill `stated_definition` and add the defining text as an evidence span; a per-company, per-period definition lookup lets many facts share one definition. Guidelines: a definition may come from a context span in another document of the same company and period. **Done:** guidelines v1.2. **Open:** the adapter and hand-built facts. |
| X-26 | Schema: add reason code `preliminary_vs_final` (allowed as a primary reason for `conflicting`). Resolution: select the final value, using the same supersedes link as X-17. Guidelines: add the rule and the reason. **Done:** the reason code and the guidelines rule (v1.2). **Open:** resolution selects the final value, and D-31 (how a preliminary fact is marked). |
| X-27 | Plan page and status snapshot use the Nov 30 date and the tracker's milestones. |
| X-28 | Harness: lead the summary with the false-match rate. Already reported, with macro-F1 and cost per 1,000 pairs. |
| X-29 | Labeling: report raw agreement on the overlap against the 80% target (the agreement command already prints it), next to Cohen's kappa. Extraction scoring (2.7) reports accuracy against 95%. |
| X-30 | Harness: a comparison table that checks each target (quality, safety, cost, p95 latency) against the frontier model, with intervals. |
| X-31 | Cost: record GPU type, hourly price and throughput for self-hosted runs, and compute cost per 1,000 pairs at the stated monthly volume. Not built. |
| X-32 | Harness comparisons claim a difference only when the intervals support it (the paired test exists). D1 is decided from the X-30 table on Nov 23. |
| X-33 | Schema: add `preliminary` to `ReportingStatus` (additive) and derive the reason from it; guidelines: replace the interim "default to `restatement`" with the rule. Not built. |
| X-34 | None beyond the scope in [extraction-adapter-scope.md](extraction-adapter-scope.md), which already assumes it. |
| X-35 | Adapter: an XBRL reader used as the source for 10-K statement values and as a cross-check on every other extracted fact; extraction scoring (2.7) reports agreement with XBRL. Not built. |
| X-36 | None; already how the schema and the generator behave. The adapter's number parser follows it. |
| X-37 | Task 2.7: split the ~60-fact sample between the owner and engineering. |
| X-38 | Tracker and [status.md](status.md): new milestone dates once the exact release date is set. |
| X-39 | Write the grid into [synthetic-data.md](synthetic-data.md) from `PRIMARY_REASONS` and the four core metrics, and test the generator's coverage against it (3.1, 3.6). Remove `currency_mismatch` scenarios and non-USD companies from the generator (X-18). |
| X-40 | None; the generator is templates only. |
| X-41 | Labeling target 150 to 200 (3.4). |
| X-42 | None; applied. |
| X-43 | State the licenses in the dataset card and the release write-up (6.3). |
| X-44 | Harness run configs for the lineup; choose the base model within the Apache-2.0 family (5.1). |
| X-45 | None. |
| X-46 | None; applied (`--show-metric-id`). |
