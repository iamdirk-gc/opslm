# Status: 2026-11-03

Snapshot of where the project stands against the tracker and the November 30 release (27 days
out). The release was replanned on Nov 3 from November 9 (X-27). Task-level detail is in
[board-alignment.md](board-alignment.md); open questions for the project owner are in
[decisions.md](decisions.md).

## Headline

- **The evaluation machinery is built and tested; the real data is not.** Schema, loader, labeling
  workflow, rules and LLM baselines, harness, synthetic generator, pair miner and CI all exist.
  What does not exist is the extraction adapter or any hand-built holdout facts, so nothing has
  touched a real document yet.
- **Since the Oct 18 snapshot the repository has been quiet.** The only changes were merging
  the pair miner and the scope, decisions and status docs. None of the Oct 19 to Nov 3 work in
  the old plan (parser spike, adapter layers, generator fixes) is in the repository, so the
  engineering position is the Oct 18 one with 27 days left instead of 22.
- **The labeling decisions are settled.** The owner answered all of Part B on Nov 3 (X-17 to
  X-26): restatements and preliminary results are separate facts and the latest value wins; v1 is
  USD only; full period dates are recorded; definitions are attached when facts are built; splits
  follow the company roles. What remains before labeling is the owner's review of guidelines v1.1
  (1.3) and the success criteria (1.5).
- **The extraction adapter (2.3) is the critical path**, due Nov 20. It is scoped in
  [extraction-adapter-scope.md](extraction-adapter-scope.md): about 12 to 14 engineering days for
  an MVP, of which about 5.5 need no documents. Labeling does not wait for it: the holdout facts
  are built by hand (2.5) and also serve as the answer key for scoring extraction.
- **No model has been run.** The LLM system is tested against mocks only; no API credentials,
  hosted open-weight model or GPU quota exist yet. The GPU quota request (4.5) is due Nov 4.
- **Fine-tuning is a stretch goal.** It goes ahead only if the baselines show a gap it could close
  (D1, Nov 23); the release is publishable either way.

## What is built

| Area | State |
|---|---|
| Schema v0.2.0 | Merged; facts with evidence spans, task input and output, gold labels; JSON Schemas checked in and verified in CI at their recorded pydantic version. Not yet: document dates and the supersedes link for restatements and preliminary results (X-17, X-26) |
| Labeling guidelines | v1.1, a draft awaiting the owner's review (1.3); the Nov 3 decisions still need to be written into it |
| Dataset loader | Leakage checks by company, document family, fact and pair |
| Labeling workflow | Spreadsheet export, validated import, agreement, adjudication, finalize; never used by two people yet |
| Systems | Rules baseline (covers every metric-page variant; abstains on company-defined metrics without definitions); provider-agnostic LLM system (Anthropic, OpenAI-compatible, Vertex Gemini), never run against a real model |
| Evaluation harness | Reconciliation-only mode: macro-F1, false-match rate, judgment accuracy, span-level evidence, cost and latency, slices, bootstrap intervals, paired test. Not built: resolution scoring, difficulty slices, end-to-end mode with extraction (4.1) |
| Synthetic generator (v1, built before the requirements page) | 18 scenario templates over the five v1 metrics, labels checked against the guideline table at build time, held-out vocabulary tagged `heldout_name`. **Does not yet meet the requirements page; gaps below** |
| Pair miner | Merged ([PR #9](https://github.com/iamdirk-gc/opslm/pull/9)). Blocks by company and metric family, samples by stratum; checked against synthetic gold labels, never run on real facts. **Still assigns splits by hash; X-24 requires the company roles** (holdout companies to test only, pattern sources to train and dev) |
| CI | Lint, tests on Python 3.10 to 3.14, a schema job, a smoke job, a package build; 358 tests |

## Tasks in the tracker

Status and due date as in the tracker (the "OpsLM Milestones & To-Dos" sheet) on Nov 3. 5 of 42
tasks are done and none is overdue.

| ID | Task | Status | Due | Note |
|---|---|---|---|---|
| 1.1 | v1 metric set | Done | Oct 12 | `docs/metric-set-v1.md` and the wiki page |
| 1.2 | Schema | Done | Oct 13 | Schema v0.2.0 |
| 1.3 | Review and approve guidelines v1.1 | In progress | Nov 6 | The last item blocking labeling |
| 1.4 | Repo setup and CI | Done | Oct 12 | |
| 1.5 | Success criteria in numbers; headline metric | In progress | Nov 6 | D-07, D-20 |
| 1.6 | Hand-label 10 to 15 seed examples from holdout documents | Not started | Nov 8 | Needs 1.3 and 2.5 |
| 1.7 | Settle the labeling decisions | Done | Nov 5 | X-17 to X-26, decided Nov 3 |
| M1 | Guidelines, decisions and success criteria locked | Not started | Nov 8 | |
| 2.1 | Parser comparison on two holdout filings | Not started | Nov 6 | Section 5 of the scope doc |
| 2.2 | Source documents and provenance | Done | Oct 15 | 50 files; the CrowdStrike deck is still missing |
| 2.3 | Extraction adapter MVP | Not started | Nov 20 | **Critical path** (D-03 scope) |
| 2.4 | What can be published | Not started | Nov 7 | D-02 |
| 2.5 | Hand-built holdout facts, checked against SEC XBRL | Not started | Nov 12 | Candidate pool for labeling and the extraction answer key (D-04) |
| 2.6 | Upload the document set to the project's private bucket | Not started | Nov 4 | |
| M2 | Evidence-linked facts for all 15 companies | Not started | Nov 20 | |
| 2.7 | Score extraction against the hand-built facts | Not started | Nov 22 | D-06: at least 95% on core-metric table facts |
| 3.1 | Generator brought up to the requirements page | In progress | Nov 12 | Gaps below |
| 3.2 | Mine candidate pairs from the holdout facts | In progress | Nov 13 | Miner merged; role-based splits first (X-24) |
| 3.3 | Split rules for real data | In progress | Nov 7 | Company separation enforced; roles not yet |
| 3.4 | Label 150 to 200 holdout cases with overlap and adjudication | Not started | Nov 20 | About 8 to 12 hours of labeling |
| 3.5 | Generate the training set (about 2,000 pairs) | Not started | Nov 14 | About 25% per label |
| 3.6 | Mark up the synthetic coverage grid | Not started | Nov 6 | D-29 |
| 3.7 | Review 50 random synthetic cases | Not started | Nov 15 | Fewer than 2 wrong labels to pass |
| M3 | Holdout frozen, training set generated | Not started | Nov 20 | |
| 4.1 | Harness: resolution scoring, difficulty slices, end-to-end mode | In progress | Nov 22 | |
| 4.2 | Rules baseline on the holdout | In progress | Nov 21 | Owner reviews the synonym map |
| 4.3 | Frontier model on the holdout | In progress | Nov 22 | Run on the seed set first; D-24 |
| 4.4 | Untuned open-weight model on the holdout | In progress | Nov 22 | No model hosted yet; D-24, D-25 |
| 4.5 | Request GPU quota | Not started | Nov 4 | D-26; approval can take days |
| M4 | Baseline results table | Not started | Nov 23 | |
| D1 | Fine-tuning go/no-go | Not started | Nov 23 | Against the success criteria (1.5) |
| 5.1 to 5.4, M5 | Fine-tuning (stretch) | Not started | Nov 22 to 27 | Pipeline prep only before D1 |
| 6.1 | README, architecture overview, quickstart | In progress | Nov 27 | |
| 6.2 | End-to-end demo | Not started | Nov 27 | |
| 6.3 | Results write-up | Not started | Nov 29 | Synthetic slice in its own table |
| 6.4 | Reproducibility check from a fresh clone | Not started | Nov 29 | |
| 6.5 | Outreach list and message | Not started | Nov 30 | |
| M6 | Public release | Not started | Nov 30 | |

## The generator against the requirements page

The owner's [Synthetic Data Requirements](https://github.com/iamdirk-gc/opslm/wiki/OpsLM-Synthetic-Data-Requirements) page sets what the generator
must do. Measured on Oct 18 on 800 scenarios (the most it could make then):

| Requirement | State |
|---|---|
| First release of about 2,000 pairs | **Cannot: it runs out of fictional company names at about 850 scenarios (about 1,060 pairs).** A vocabulary fix, not a design problem |
| About 25% per label in training, a realistic mix in dev | **Not met:** training is 34% equivalent, 31% related, 22% conflicting, 14% insufficient evidence; the dev split has the same mix as training |
| Coverage grid: metric × reason code × label | Not started; the grid itself is undecided (D-29, tracker 3.6) |
| Correct by construction | Met: labels and reasons are fixed from the template and checked against the guideline table before any case exists |
| No shortcuts: surface features alone score near chance | **Not met, and not yet properly tested.** Structure-only features (same metric id, fields missing, definitions present, ...) already reach 66% against 25% chance. Real data has such structure too, so this is a measurement, not a verdict; a text-only shortcut test is still to be built |
| Hold some templates and companies out of training | Companies: met. Templates: not done (only names are held out) |
| Realism from the real set | Partly: parenthesized losses, fiscal labels, footnote-style definitions. Missing: "(in thousands)" captions, prepared-remarks prose, workbook rows in the real layout |
| Hard negatives | The four core examples are covered. The traps seen in the real set are not: constant-currency ARR, ARR including payments fees, preliminary vs final results (now a decided rule, X-26) ("ARR as quarterly revenue times four" is covered in part) |
| Reproducible: each case records version, seed, config | The manifest does; individual cases do not yet |
| Quality gate: the owner reviews 50 random cases per release | No sampling tool yet (the blind-review audit module covers the comparison) |
| LLM rephrasing (open) | Not used: templates only. Recommendation in D-30 |

## The plan to November 30

From the tracker. The holdout is built from hand-built facts, so labeling does not wait for the
extraction adapter; the adapter is scored against those same facts.

| Window | Work | Needs |
|---|---|---|
| Nov 4-8 | Owner approves guidelines v1.1 and writes the success criteria (M1, Nov 8); parser comparison (2.1); coverage grid (3.6); licensing (2.4); GPU quota request and document upload (Nov 4); seed examples (1.6) | D-02, D-07, D-29 |
| Nov 6-14 | Hand-built holdout facts (2.5, Nov 12); role-based splits and candidate mining (3.2, 3.3); generator to the requirements and the training set (3.1, 3.5); synthetic quality gate (3.7) | X-24 |
| Nov 13-20 | Label the holdout with overlap and adjudication (3.4); extraction adapter MVP (2.3, M2); holdout frozen (M3) | The owner and engineering both labeling |
| Nov 20-23 | Score extraction (2.7); harness end-to-end mode (4.1); run the three baselines (4.2 to 4.4, M4); fine-tuning go/no-go (D1) | API credentials, a hosted open-weight model (D-24) |
| Nov 24-29 | Fine-tuning if D1 says go (5.x); demo, results write-up, docs and a fresh-clone reproduction (6.1 to 6.4) | |
| Nov 30 | Release (M6) | |

The release is publishable without fine-tuning. The tightest stretch is Nov 13 to 20, when
labeling and the adapter both finish; if the adapter slips, the release can still report
reconciliation-only results on the hand-built holdout and state the end-to-end limitation.

## Risks, in order

1. **No real data yet.** Every quality claim so far is against synthetic data, which the generator's
   own authors wrote. The hand-built facts and the first labeling session will find problems.
2. **Extraction accuracy is unknown.** Decks may yield few usable facts; scoring against the
   hand-built facts (2.7) will say.
3. **Licensing (D-02)** can block publishing the holdout in its intended form.
4. **Two labelers, one week.** The overlap batch, the adjudication meeting and the guideline
   revisions it triggers all happen in Nov 13 to 20.
5. **No model has run.** First real runs per provider will surface small problems; budget for a
   day, and run on the seed set first.

## Needed from the project owner this week

Review and approve guidelines v1.1 (1.3, Nov 6), the success threshold (D-07, Nov 6), the
synthetic coverage grid (D-29, Nov 6), redistribution (D-02, Nov 7), extraction scope (D-03) and
sign normalization (D-05). The full list is in [decisions.md](decisions.md).

## In review now

This snapshot, lined up with the tracker (task IDs, due dates and the Nov 30 release, X-27).
