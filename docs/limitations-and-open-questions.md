# Limitations and Open Questions

Status as of the evaluation-harness milestone. This document is for the project owner. Part 1 lists decisions that need the owner's call. Parts 2 and 3 record what is not built or not trustworthy yet, so nobody mistakes the current numbers for results.

## What exists today

| Piece | State |
|---|---|
| Schema v0.2.0: facts with evidence spans, task input and output, gold labels, reason codes | Built (`opslm.schema`; JSON Schemas in `schemas/`) |
| Label decision table and number comparison | Built (`opslm.labels`) |
| Labeling guidelines v1.0 | Written, **not yet tested by two reviewers** |
| JSONL dataset loader with leakage checks | Built (`opslm.data`) |
| Rules-based baseline | Built (`opslm.baselines.rules`) |
| LLM system, provider-agnostic (Anthropic, OpenAI-compatible endpoints, Gemini on Vertex) | Built and tested against mocks; **never run against a real model** (`opslm.baselines.llm`, `opslm.baselines.backends`) |
| Evaluation harness (metrics, confidence intervals, paired test, run artifacts, CLI) | Built (`opslm.eval`) |
| Labeling workflow (spreadsheet export, validated import, agreement, adjudication, finalize) | Built (`opslm.labeling`, [labeling-workflow.md](labeling-workflow.md)), exercised only on synthetic test data |
| Synthetic data generator | Built ([synthetic-data.md](synthetic-data.md)); labels are by construction and unreviewed |
| Benchmark dataset | **None.** Only nine illustrative examples, not benchmark data |
| Base open-weight and fine-tuned systems | Not started |
| Synthetic data generator | Not started |
| Docling / document pipeline | Not started (interface prepared via `SourceDocument` and `EvidenceSpan`) |

No number produced so far says anything about real-world performance.

## Part 1: Decisions for the project owner

Each item has what the engineering side did by default. Defaults can be changed; changes after labeling starts mean re-reviewing cases, so these are best settled **before** the labeling session.

### Labels and guidelines (most urgent, blocks labeling)

1. **Is the four-label set the right one?** The plan says the system should determine "whether differences are explainable." Today, a pair with different concepts (Revenue vs ARR) is `related_but_different`, and a pair with the same concept and different numbers is `conflicting`. There is no label for "different numbers, but we can explain why" (for example, GAAP vs adjusted, or a restatement). A fifth label such as `explained_difference` is possible. Adding it later is costly.
   - *Default:* four labels; explanations are captured only in the reason codes (`reasons`, for example `restatement` or `basis_mismatch`).
2. **Restatements.** If one source restates another, is that `conflicting` or something else?
   - *Default:* `conflicting` with reason `restatement`.
3. **Naming variants (answered by the metric set, `docs/metric-set-v1.md`, adopted in guidelines v1.1).** Revenue, Total revenue, Net sales, Sales and Turnover are equivalent when definition, entity and period match, so the plan's $42.5M vs $44.1M example is `conflicting`. "Net revenue" is conditional (equivalent only when the company reports no separate gross revenue line). Note the original plan document lists Revenue vs Net Revenue as equivalent; the board supersedes it. Please confirm.
4. **When do two numbers "agree"?** Currently: they differ by no more than the rounding implied by the coarser reported precision (42.5M agrees with 42.54M, not 42.7M). An alternative is a fixed percentage tolerance (for example 0.5%) that an analyst would accept.
   - *Default:* precision-based rounding.
5. **Different currencies.** No conversion is attempted, so the label is `insufficient_evidence`. Is that the intended behavior, or should currency differences be a distinct case?
6. **Fiscal vs calendar years and period naming.** What counts as the same period when labels differ ("FY2025" vs "2025" vs "year ended June 30, 2025")? The guidelines lean on exact dates when available and are vague otherwise.
7. **Unrelated pairs** (Revenue vs headcount) are discarded, not labeled. Confirm.
8. **Who settles reviewer disagreements?** The process says reviewers discuss and write down the rule. If they cannot agree, someone needs the final say. Suggest: the owner.

### Benchmark and success criteria

9. **What counts as success?** The plan says "competitive accuracy at lower cost." That needs numbers. For example: within X macro-F1 points of the frontier baseline at under Y% of the cost per 1,000 pairs, with false-match rate no worse than Z%. Without thresholds, any result can be described as a win.
10. **Which metric is the headline?** The harness reports macro-F1, accuracy, false-match rate, missed-match rate, concept and scope accuracy, and evidence coverage. Engineering suggests false-match rate as the headline because wrongly merging distinct concepts is the costly error. Confirm or reorder.
11. **Acceptable benchmark size.** 100-200 cases gives wide error bars (see limitations below). Is a larger set worth the labeling time, or is a small, high-quality set the goal?

### Data

12. **Public data sources.** Suggested: SEC filings (including XBRL tags) for the public portion, and synthetic cases built around fictional companies. Which companies or sectors? Check each source's terms of use before redistribution.
13. **No CircleEngage or MagnoliaHealth data.** This is a personal project, so no employer or customer documents, figures or terminology should appear in the data, repo or prompts. Confirm this boundary is understood on both sides.
14. **Dataset and model license.** Code is Apache 2.0. The dataset and model weights are separate. Suggested: CC BY 4.0 for the data, Apache 2.0 for weights. The base model's own license may restrict this (some open-weight models do).

### Models and budget

15. **Base model family and size.** Suggested: one Apache-2.0 family (e.g. Qwen), a small size (1.5-3B) locally on the M2, optionally 7-8B on a rented GPU.
16. **Which models to compare, and how to price them.** The system is provider-agnostic, so this is now a pure selection question. Suggested shape: one or two frontier models (for example Claude Opus 5.5 or Fable 5.1, or Gemini on Vertex), one mid-size open-weight model served from Vertex AI or vLLM, the same small model fine-tuned, and the rules baseline. A stronger frontier baseline makes a small model's win more credible. A single 200-case pass on Opus 5.5 is estimated at roughly $2-11 (the CLI prints an estimate first and will not run without `--confirm-spend`), so API budget is not the constraint. The harder decision is the cost-comparison method for self-hosted models (see the LLM system limitations).
17. **GPU quota** on the new Google Cloud project (`opslm-511123`) must be requested ahead of time and can take days. Not yet requested.

### Scope

18. **Docling priority.** Agreed as important for adoption, scheduled after the benchmark. Is a working end-to-end demo on one public filing required for the November 9 milestone, or after?
19. **Public visibility.** The repo is already public. Is that intended from day one, or should it go private until there is something presentable?

## Part 2: Known limitations of what is built

### Rules baseline
- Cannot read definitions or footnotes, so it misses differences stated only in text.
- The synonym table covers every naming variant on `docs/metric-set-v1.md` (a test checks) plus about 15 general concepts, and is hand-written. Other metrics become "cannot tell", so it over-predicts `insufficient_evidence` on real data.
- Company-defined metrics (ARR, Adjusted EBITDA, FCF) count as the same concept only when both facts state identical definition text; any other wording difference makes it abstain, because it cannot compare meanings.
- It cites every span of both facts (it cannot choose), so its evidence recall is a ceiling and its precision a floor.
- On generated data it scores about 85%, because it knows every name; it scores near 0% on cases that need a definition read.
- Fiscal vs calendar periods with no dates may be judged the same.
- Its 100% score on the nine examples is by construction: the rules and examples were written together.

### LLM system and its backends
- **Never run for real.** No model credentials were available while building it, so everything is tested against mocks. The OpenAI-compatible and Vertex Gemini parameter names were checked against the installed SDKs' signatures, not against live services. Expect a first real run per provider to surface small problems.
- **Structured output varies by provider.** Anthropic, vLLM and recent Ollama can constrain output to the JSON schema. Servers or models without that fall back to JSON mode or plain text with the schema in the prompt (`--structured`), which is less reliable and will raise the error count. Error counts should be reported alongside accuracy when comparing systems.
- **Non-deterministic or not controllable.** Current Claude models reject temperature and seed settings. The other backends default to temperature 0, which reduces but does not eliminate variation. Report several runs before claiming small differences.
- **The model chooses its evidence spans.** Each span is shown with its id, and the answer schema limits citations to the case's own ids where the backend supports constrained decoding. With weaker modes it can cite ids that do not exist; the harness counts those as invalid references. Citing nothing is an error unless the answer is insufficient evidence.
- **`metric_id` is hidden from the model by default** (`--show-metric-id` shows it). It predicts the label, the rules baseline does not use it, and a model that leans on it would not transfer to real extractor output. Run with and without before drawing conclusions about it.
- **Numeric values are hidden from the model by default.** This follows the guidelines (concept never depends on the numbers) and lets code do the arithmetic. The tradeoff: if an excerpt or definition only makes sense with the number, the model cannot use it. `--show-values` exists to test this.
- **No silent model fallback.** No provider-side fallback is enabled, since it would change which model answered mid-benchmark. A refusal or content-filter block is recorded as an error and scored wrong. If these turn out to be common on financial text, this needs a decision.
- **One prompt for every model.** The prompt is a condensed copy of the guidelines plus five abbreviated examples, not tuned per model. Smaller open models may need different wording or few-shot examples, and a single shared prompt may understate them. The prompt must be updated by hand when the guidelines change (its hash is recorded with each run). Keep benchmark cases distinct from the prompt's examples.
- **Cost is only known for hosted models with a price.** Built-in prices are a dated snapshot of Anthropic list prices; for any other hosted model pass `--price-in` and `--price-out`. Self-hosted and fine-tuned models show no cost, because their cost is compute time, which is not attributed yet. This matters for the plan's central cost claim: **a fair cost comparison between a hosted frontier model and a self-hosted small model needs a stated method** (for example GPU-hours per 1,000 pairs at a quoted instance price). That method is not designed.
- **Output tokens include reasoning tokens** where the provider bills them, so estimates are a range.

### Schema
- Each fact holds one numeric value. Ranges, "approximately", multi-value cells and non-numeric facts are not represented.
- Units are an enum (currency, percent, ratio, count) with no finer ontology. Currency is normalized and must be a three-letter code, but is not checked against the ISO 4217 list.
- Precision comes from the decimal places as typed. A source reported as "42.5" (rounded) and one reported as "42.50" are treated as differently precise.
- English-language documents only.

### Dataset loader
- Fact- and pair-level leakage checks compare exact content. Near-duplicates (a fact reworded or a value shifted by one digit) are not detected.
- It is strict by design, so a dataset with any leakage will not load through `load_dataset`.
- Companies are compared by name after dropping case, punctuation and legal suffix. Two spellings of one company that differ in more than that (a rebrand, an abbreviation) are not merged, so company-level leakage across them would go unnoticed.

### Evaluation harness
- **Confidence intervals resample individual cases.** Cases from the same scenario are correlated, so intervals are somewhat too narrow. Resampling by scenario would be more honest.
- The paired significance test (McNemar) assumes cases are independent, which has the same issue.
- With 100-200 cases and four classes, expect differences of under about 8-10 points to be indistinguishable from noise.
- Evidence is scored at the span level: recall and precision of the cited spans against the spans the gold label requires. Synthetic gold requires both facts' spans, so on synthetic data this mostly tests whether a system cites sensibly at all; it becomes informative with human-marked spans on real documents.
- Concept and scope accuracy treat "cannot tell" as an answer that must match the gold judgment.
- Macro-F1 averages only over classes present in the gold labels.
- Latency is wall-clock on whatever machine runs it. Cost covers API spend only, not local compute time. Neither is comparable across machines without recording the hardware.
- A system that raises an exception on a case is scored wrong for that case. This is deliberate but penalizes flaky APIs.

### Process and infrastructure
- Labeling guidelines have never been used by a second person. Expect the first overlap batch to expose gaps.
- No continuous integration, no pre-commit hooks, no type checking beyond ruff.
- **Labeling tool is spreadsheet-based, not an app.** Chosen because it needs no hosting and fits two reviewers. Limits: no live collaboration on one sheet (each reviewer has their own), no row locking, no in-sheet display of the derived label, and the dropdowns are not enforced if a sheet is edited elsewhere (the importer re-checks everything). A web review app is possible later; if built it should be hosted on Google Cloud, not run from a laptop.
- **Candidate sources.** The synthetic generator now produces candidate pairs (test split). Real candidates need the extraction adapter and a pair-mining tool, neither of which exists.
- **Kappa on about 30 shared cases is noisy.** Treat the 0.7 target as a rough signal; a handful of disagreements can move it a lot.

## Part 3: Not yet designed

- **Candidate generation.** Real data rooms hold thousands of facts. Comparing every pair is quadratic, so a blocking step (by entity, period and metric similarity) is needed before pairwise judgment. The benchmark deliberately starts from given pairs. Documented as a gap, not addressed.
- **Turning documents into facts.** Docling gives tables and text with locations, not business facts. Mapping table headers to metric, period, scale and entity is its own task and may need a model.
- **Prompting and output format** for LLM systems (input serialization, structured output, constrained decoding for open models).
- **Training data design:** how many synthetic pairs, how to keep generator artifacts from leaking into the model, whether to distill rationales from a stronger model.
- **Reproducibility of model runs:** pinned model versions, prompt hashing and seed handling beyond what the run artifact's `config` field stores.

## Suggested order for the next steps

1. Owner settles items 1-8 (labels and guidelines).
2. Dry-run the labeling workflow on the nine examples, then both reviewers label the shared 30-case overlap and compare. Revise the guidelines.
3. Build the frontier-LLM system and run it on the overlap batch for a first real comparison against the rules baseline.
4. Review a first batch of generated test candidates and compare with the construction labels (`opslm.datagen.audit`).
5. Fine-tuning experiment.


See also [board-alignment.md](board-alignment.md) for the comparison with the project board.
