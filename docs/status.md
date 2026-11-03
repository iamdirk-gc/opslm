# Status: 2026-11-03

Snapshot of where the project stands against the board and the release, which the owner has moved
from November 9 to November 30 (the board replanned on Nov 3; about 4 weeks out).
Task-level detail is in [board-alignment.md](board-alignment.md); open questions for the project
owner are in [decisions.md](decisions.md).

## Headline

- **Since the Oct 18 snapshot the repository has been quiet.** The only changes were merging
  the pair miner and the scope, decisions and status docs. None of the Oct 19 to Nov 3 work in
  the old plan (parser spike, adapter layers, generator fixes) is in the repository, so the position
  is the Oct 18 one with about 27 days left instead of 22. Anything done outside the repository
  (documents, the board sheet, labeling) is not visible here.
- **The evaluation machinery is built and tested; the real data is not.** Schema, loader, labeling
  workflow, rules and LLM baselines, harness, synthetic generator, pair miner and CI all exist.
  What does not exist is the extraction adapter, so nothing has touched a real document, and the
  holdout set that is the headline result cannot be started.
- **The document set is chosen and the generator has a written spec.** On Oct 12 the owner fixed
  15 real companies (9 holdout, 6 pattern sources) and published the synthetic data requirements
  (draft v0.3) on the wiki. The generator built before that spec meets some of it and not the rest;
  see below.
- **The extraction adapter is the critical path, and the board's dates for it have passed** (due
  Oct 17; the owner's new dates are in the board sheet, which this page has not seen). It is scoped in [extraction-adapter-scope.md](extraction-adapter-scope.md): about 12 to
  14 engineering days for an MVP, of which about 5.5 days need no documents and can start now.
- **No model has been run.** The LLM system is tested against mocks only; no API credentials,
  hosted open-weight model or GPU quota exist yet.
- **Fine-tuning is still a stretch.** The board marks it as one with a go/no-go decision (D1), and
  "the release is publishable either way". With four weeks it could fit only if the baselines are
  done by about Nov 20; decide at D1, not before.

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
| Pair miner | **Merged ([PR #9](https://github.com/iamdirk-gc/opslm/pull/9)).** Blocks by company and metric family, samples by stratum, assigns splits by company; checked against synthetic gold labels, never run on real facts |
| CI | Lint, tests on Python 3.10 to 3.14, a schema job, a smoke job, a package build; 358 tests |

## Where the board stands

The owner replanned the board on Nov 3 (release Nov 30, critical path "extraction adapter (2.3) by
Nov 20", 42 tasks, 5 done). **The board is now the source of truth for task status and dates**; this
page no longer keeps a copy of its Status column. Two changes in it matter for engineering:

- **Labeling no longer waits for the adapter.** Task 2.5 has the owner and engineering build the
  holdout facts by hand from the 9 holdout companies, checked against SEC XBRL values. The hand-built
  facts are both the candidate pool for labeling and the answer key for scoring the adapter later
  (2.7). The adapter (2.3) is still on the release list, with an accuracy report.
- **The owner's decisions on the labeling questions are in** (X-17 to X-26, Nov 3), and the
  guidelines (v1.2) now carry them. Approving them is task 1.3, "the last item blocking labeling".

Engineering-owned tasks, with the board's dates:

| Task | Dates | State |
|---|---|---|
| 4.5 Request GPU quota (`opslm-511123`) | Nov 4 | A console action; not requested yet |
| 2.1 Parser spike on two holdout filings | Nov 4-6 | Needs the document set in the GCS bucket (2.6) |
| 2.3 Extraction adapter MVP | Nov 4-20 | Scoped; the document-independent layers can start now |
| 3.6 Draft the synthetic coverage grid | Nov 5-6 | Engineering drafts, the owner marks it up |
| 3.1 Generator to the requirements page | Nov 6-12 | Waits on the grid; fixes that need no decision can start |
| 3.2 Mine candidates from the holdout facts | Nov 10-13 | Role-based splits done; waits on 2.5 |
| 3.5 Generate the training set (about 2,000 pairs) | Nov 12-14 | Waits on 3.1 and the guidelines |
| 4.1 Finish the harness (resolution scoring, difficulty slices, end-to-end) | Nov 10-22 | Reconciliation-only mode built |
| 4.4 Host an open-weight model, run the untuned baseline | Nov 12-22 | Backend ready; needs the GPU quota |
| 6.2 End-to-end demo; 6.4 reproducibility check | Nov 22-29 | After the adapter |

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
6. **Momentum.** Three weeks passed with no repository activity. The plan above has the same work
   as the Oct 18 one; it needs a start this week and a short check-in each week.

## Needed from the project owner this week

Approve guidelines v1.2 (board 1.3, Nov 4-6), the last item blocking labeling. Mark up the coverage
grid that engineering drafts (3.6, D-29). Settle D-31 (how a preliminary fact is marked). Write the
success criteria and headline metric (1.5, D-07, D-20). Decide what may be published (2.4, D-02) and
the extraction scope (D-03). Confirm sign normalization (D-05). The full list is in
[decisions.md](decisions.md).

## Done since the Nov 3 snapshot

The owner's decisions are recorded and written into the guidelines (v1.2); schema 0.2.1 adds the
supersedes link, publication date and the `preliminary_vs_final` reason; the pair miner assigns
splits by company role; the plan page example is fixed in the repository copy.
