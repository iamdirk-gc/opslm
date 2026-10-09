# Limitations and Open Questions

Status as of the evaluation-harness milestone. This document is for the project owner. Part 1 lists decisions that need the owner's call. Parts 2 and 3 record what is not built or not trustworthy yet, so nobody mistakes the current numbers for results.

## What exists today

| Piece | State |
|---|---|
| Business-fact schema, labels, discrepancy reasons | Built (`opslm.schema`) |
| Label decision table and number comparison | Built (`opslm.labels`) |
| Labeling guidelines v1.0 | Written, **not yet tested by two reviewers** |
| JSONL dataset loader with leakage checks | Built (`opslm.data`) |
| Rules-based baseline | Built (`opslm.baselines.rules`) |
| Evaluation harness (metrics, confidence intervals, paired test, run artifacts, CLI) | Built (`opslm.eval`) |
| Benchmark dataset | **None.** Only nine illustrative examples, not benchmark data |
| Frontier-LLM, base open-weight, fine-tuned systems | Not started |
| Synthetic data generator | Not started |
| Docling / document pipeline | Not started (interface prepared via `SourceRef`) |

No number produced so far says anything about real-world performance.

## Part 1: Decisions for the project owner

Each item has what the engineering side did by default. Defaults can be changed; changes after labeling starts mean re-reviewing cases, so these are best settled **before** the labeling session.

### Labels and guidelines (most urgent, blocks labeling)

1. **Is the four-label set the right one?** The plan says the system should determine "whether differences are explainable." Today, a pair with different concepts (Revenue vs ARR) is `related_but_different`, and a pair with the same concept and different numbers is `conflicting`. There is no label for "different numbers, but we can explain why" (for example, GAAP vs adjusted, or a restatement). A fifth label such as `explained_difference` is possible. Adding it later is costly.
   - *Default:* four labels; explanations are captured only in `discrepancy_reason`.
2. **Restatements.** If one source restates another, is that `conflicting` or something else?
   - *Default:* `conflicting` with reason `restatement`.
3. **Are "Revenue", "Sales" and "Net Revenue" the same concept by default?** The guidelines say yes unless a definition or qualifier says otherwise, so the plan's $42.5M vs $44.1M example is `conflicting`. If the owner's intent was that this pair is *related but possibly different* (gross vs net), the rule changes.
   - *Default:* standard synonyms are the same concept.
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
16. **Frontier comparison model and API budget.** Not chosen. Rough token estimates are in the planning discussion; exact prices should be checked before committing a budget.
17. **GPU quota** on the new Google Cloud project (`opslm-511123`) must be requested ahead of time and can take days. Not yet requested.

### Scope

18. **Docling priority.** Agreed as important for adoption, scheduled after the benchmark. Is a working end-to-end demo on one public filing required for the November 9 milestone, or after?
19. **Public visibility.** The repo is already public. Is that intended from day one, or should it go private until there is something presentable?

## Part 2: Known limitations of what is built

### Rules baseline
- Cannot read definitions or footnotes, so it misses differences stated only in text.
- Synonym table is small (about 20 concepts) and hand-written. Unlisted metrics become "cannot tell", so it over-predicts `insufficient_evidence` on real data.
- Fiscal vs calendar periods with no dates may be judged the same.
- Its 100% score on the nine examples is by construction: the rules and examples were written together.

### Schema
- Each fact holds one numeric value. Ranges, "approximately", multi-value cells and non-numeric facts are not represented.
- Currency and unit are free strings compared case-insensitively, with no unit ontology.
- Precision comes from the decimal places as typed. A source reported as "42.5" (rounded) and one reported as "42.50" are treated as differently precise.
- English-language documents only.

### Dataset loader
- Fact- and pair-level leakage checks compare exact content. Near-duplicates (a fact reworded or a value shifted by one digit) are not detected.
- It is strict by design, so a dataset with any leakage will not load through `load_dataset`.

### Evaluation harness
- **Confidence intervals resample individual cases.** Cases from the same scenario are correlated, so intervals are somewhat too narrow. Resampling by scenario would be more honest.
- The paired significance test (McNemar) assumes cases are independent, which has the same issue.
- With 100-200 cases and four classes, expect differences of under about 8-10 points to be indistinguishable from noise.
- Evidence scoring compares field names only (`period`, `metric`), not whether the system pointed at the right fact or quoted the right text.
- Concept and scope accuracy treat "cannot tell" as an answer that must match the gold judgment.
- Macro-F1 averages only over classes present in the gold labels.
- Latency is wall-clock on whatever machine runs it. Cost covers API spend only, not local compute time. Neither is comparable across machines without recording the hardware.
- A system that raises an exception on a case is scored wrong for that case. This is deliberate but penalizes flaky APIs.

### Process and infrastructure
- Labeling guidelines have never been used by a second person. Expect the first overlap batch to expose gaps.
- No continuous integration, no pre-commit hooks, no type checking beyond ruff.
- No tooling for labeling (spreadsheet or small review app). Decide how the two reviewers will actually enter labels.

## Part 3: Not yet designed

- **Candidate generation.** Real data rooms hold thousands of facts. Comparing every pair is quadratic, so a blocking step (by entity, period and metric similarity) is needed before pairwise judgment. The benchmark deliberately starts from given pairs. Documented as a gap, not addressed.
- **Turning documents into facts.** Docling gives tables and text with locations, not business facts. Mapping table headers to metric, period, scale and entity is its own task and may need a model.
- **Prompting and output format** for LLM systems (input serialization, structured output, constrained decoding for open models).
- **Training data design:** how many synthetic pairs, how to keep generator artifacts from leaking into the model, whether to distill rationales from a stronger model.
- **Reproducibility of model runs:** pinned model versions, prompt hashing and seed handling beyond what the run artifact's `config` field stores.

## Suggested order for the next steps

1. Owner settles items 1-8 (labels and guidelines).
2. Both reviewers label the shared 30-case overlap and compare. Revise the guidelines.
3. Build the frontier-LLM system and run it on the overlap batch for a first real comparison against the rules baseline.
4. Build the synthetic generator and the labeling tool.
5. Fine-tuning experiment.
