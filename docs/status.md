# Status: 2026-10-18

Snapshot of where the project stands against the board and the November 9 release (22 days out).
Task-level detail is in [board-alignment.md](board-alignment.md); open questions for the project
owner are in [decisions.md](decisions.md).

## Headline

- **The evaluation machinery is built and tested; the real data is not.** Schema, loader, labeling
  workflow, rules and LLM baselines, harness, synthetic generator, pair miner and CI all exist.
  What does not exist is the extraction adapter, so nothing has touched a real document, and the
  holdout set that is the headline result cannot be started.
- **The document set is chosen and the generator has a written spec.** On Oct 12 the owner fixed
  15 real companies (9 holdout, 6 pattern sources) and published the synthetic data requirements
  (draft v0.3) on the wiki. The generator built before that spec meets some of it and not the rest;
  see below.
- **The extraction adapter is the critical path, and the board's dates for it have passed** (due
  Oct 17). It is scoped in [extraction-adapter-scope.md](extraction-adapter-scope.md): about 12 to
  14 engineering days for an MVP, of which about 5.5 days need no documents and can start now.
- **No model has been run.** The LLM system is tested against mocks only; no API credentials,
  hosted open-weight model or GPU quota exist yet.
- **Fine-tuning does not fit before November 9.** The board already marks it a stretch with a
  go/no-go decision (D1), and "the release is publishable either way".

## What is built

| Area | State |
|---|---|
| Schema v0.2.0 | Merged; facts with evidence spans, task input and output, gold labels; JSON Schemas checked in and verified in CI at their recorded pydantic version |
| Labeling guidelines | v1.1, a draft awaiting the owner's review (board 1.3) |
| Dataset loader | Leakage checks by company, document family, fact and pair |
| Labeling workflow | Spreadsheet export, validated import, agreement, adjudication, finalize; never used by two people yet |
| Systems | Rules baseline (covers every metric-page variant; abstains on company-defined metrics without definitions); provider-agnostic LLM system (Anthropic, OpenAI-compatible, Vertex Gemini), never run against a real model |
| Evaluation harness | Reconciliation-only mode: macro-F1, false-match rate, judgment accuracy, span-level evidence, cost and latency, slices, bootstrap intervals, paired test. Not built: end-to-end mode with extraction, difficulty slices |
| Synthetic generator (v1, built before the requirements page) | 18 scenario templates over the five v1 metrics, labels checked against the guideline table at build time, held-out vocabulary tagged `heldout_name`. **Does not yet meet the requirements page; gaps below** |
| Pair miner | **In review (PR #9).** Blocks by company and metric family, samples by stratum, assigns splits by company; checked against synthetic gold labels, never run on real facts |
| CI | Lint, tests on Python 3.10 to 3.14, a schema job, a smoke job, a package build; 349 tests |

## Where the board stands

Suggested values for the board's Status column. "Done" means built and tested here, still subject
to the owner's review where noted.

| ID | Suggested status | Note |
|---|---|---|
| 1.1 | Done | `docs/metric-set-v1.md` and the wiki page |
| 1.2 | Done | Schema v0.2.0 adopted and merged; validation tightened after review |
| 1.3 | In progress | Guidelines v1.1 drafted; needs the owner's review and the Part B decisions |
| 1.4 | Done | License, packaging, layout, CI |
| 1.5 | In progress | Metrics implemented; the success threshold is undefined (D-07) |
| 1.6 | Not started | Nine illustrative examples exist; not the owner's hand-labeled seed set |
| M1 | Not started | Waiting on 1.3 and 1.5 |
| 2.1 | Not started | Spike planned (section 5 of the scope doc) |
| 2.2 | In progress | Document set decided Oct 12 (15 companies, roles fixed); per-company folders and `manifest.csv` files are the owner's deliverable |
| 2.3 | Not started | Scoped; 5.5 days of it can start now |
| 2.4 | Not started | Needs D-02 |
| M2 | Not started | Blocked on 2.1 to 2.3 |
| 3.1 | In progress | Generator v1 exists but does not meet the requirements page (next section); blocked on the coverage grid (D-29) |
| 3.2 | In progress | Tool built, in review as PR #9; waits on extraction output. Still to change: it assigns splits by hash, but the roles are fixed (holdout companies to the test split only) |
| 3.3 | In progress | Company and document-family separation enforced in code; the rule is not yet written up for real data |
| 3.4 | Not started | Workflow ready; waits on candidates from real facts |
| 3.5 | Not started | The generator can produce it; run after M1 so it follows the frozen guidelines |
| M3 | Not started | Blocked on 3.4 |
| 4.1 | In progress | Reconciliation-only done; end-to-end mode and difficulty slices missing |
| 4.2 | In progress | Built; needs the owner's review of the synonym map; no holdout to score on |
| 4.3 | In progress | Built; never run; needs credentials and a budget (D-24) |
| 4.4 | In progress | Backend ready; no open-weight model hosted |
| M4, D1 | Not started | Depend on a holdout and baseline results |
| 5.1 to 5.4, M5 | Not started | Nothing built; no training spend before D1 |
| 6.1 | In progress | README and docs exist; no quickstart or architecture overview yet |
| 6.2 to 6.5, M6 | Not started | No demo, reproduction guide or outreach list |

## The generator against the requirements page

The owner's [Synthetic Data Requirements](https://github.com/iamdirk-gc/opslm/wiki/OpsLM-Synthetic-Data-Requirements) page (draft v0.3) sets what the generator
must do. Measured on 800 scenarios (the most it can make):

| Requirement | State |
|---|---|
| First release of about 2,000 pairs | **Cannot: it runs out of fictional company names at about 850 scenarios (about 1,060 pairs).** A vocabulary fix, not a design problem |
| About 25% per label in training, a realistic mix in dev | **Not met:** training is 34% equivalent, 31% related, 22% conflicting, 14% insufficient evidence; the dev split has the same mix as training |
| Coverage grid: metric × reason code × label | Not started; the grid itself is undecided (D-29) |
| Correct by construction | Met: labels and reasons are fixed from the template and checked against the guideline table before any case exists |
| No shortcuts: surface features alone score near chance | **Not met, and not yet properly tested.** Structure-only features (same metric id, fields missing, definitions present, ...) already reach 66% against 25% chance. Real data has such structure too, so this is a measurement, not a verdict; a text-only shortcut test is still to be built |
| Hold some templates and companies out of training | Companies: met. Templates: not done (only names are held out) |
| Realism from the real set | Partly: parenthesized losses, fiscal labels, footnote-style definitions. Missing: "(in thousands)" captions, prepared-remarks prose, workbook rows in the real layout |
| Hard negatives | The four core examples are covered. The traps seen in the real set are not: constant-currency ARR, ARR including payments fees, preliminary vs final results ("ARR as quarterly revenue times four" is covered in part) |
| Reproducible: each case records version, seed, config | The manifest does; individual cases do not yet |
| Quality gate: the owner reviews 50 random cases per release | No sampling tool yet (the blind-review audit module covers the comparison) |
| LLM rephrasing (open) | Not used: templates only. Recommendation in D-30 |

## A realistic plan to November 9

The board's M2 (Oct 17) and M3 (Oct 24) cannot be met. This keeps the board's must-haves for M6
(holdout dataset, schema, harness, three baselines, evidence-linked outputs, documented results)
and drops fine-tuning:

| Window | Work | Needs |
|---|---|---|
| Oct 19-23 | Parser spike (W0); build the document-independent adapter layers (W1, W2, W3, W6); owner finishes the document folders and manifests, answers licensing (D-02), and marks up the coverage grid (D-29); generator brought up to the requirements; owner reviews guidelines v1.1 and the remaining decisions | D-02, D-03, D-05, D-29 |
| Oct 26-30 | Adapter on spreadsheets and filing tables (W4, W5); extraction verification sample (D-06); first mining run on real facts | Documents on disk |
| Nov 2-4 | Mine candidates; labeling dry run, then the shared overlap and adjudication; freeze the holdout | The owner and engineering both labeling |
| Nov 4-7 | Run the three baselines on the holdout (needs API credentials and a hosted open-weight model); results write-up; README and quickstart; reproducibility check from a fresh clone | D-24 |
| Nov 9 | Release | |

This is tight: any slip in document choice or in the first extraction results moves the holdout.
The fallback, if real pairs arrive late, is to label the human-reviewed synthetic test candidates
first and release a smaller real holdout with the limitation stated.

## Risks, in order

1. **No real data yet.** Every quality claim so far is against synthetic data, which the generator's
   own authors wrote. The first real extraction and the first labeling session will find problems.
2. **Extraction accuracy is unknown.** Decks may yield few usable facts; the verification sample
   will say.
3. **Licensing (D-02)** can block publishing the holdout in its intended form.
4. **Two labelers, one week.** The overlap batch, the adjudication meeting and the guideline
   revisions it triggers all happen in the same few days.
5. **No model has run.** First real runs per provider will surface small problems; budget for a
   day.

## Needed from the project owner this week

D-02 (redistribution), D-03 (extraction scope), D-05 (sign normalization), D-07 (success
threshold), D-08 (accept the replan), D-29 (the synthetic coverage grid, which the generator is
waiting on), and a review of guidelines v1.1. The full list is in
[decisions.md](decisions.md).

## In review now

PR #9, the pair-mining tool. Merge it directly into `main`.
