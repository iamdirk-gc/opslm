# Synthetic Data Generator

`python -m opslm.datagen --scenarios 400 --seed 0 --out-dir data/synthetic/v1`

Generates labeled fact pairs for **training** and for **candidate test pairs awaiting human
review**. Per the project plan, the benchmark itself rests on real, human-reviewed cases; the
generator exists to produce training data and to exercise the pipeline.

## Design

A **scenario** is a small synthetic data room: one fictional company, a fiscal calendar, a few
facts as different documents would report them, and the pairs worth comparing. Because each
scenario is its own company, splitting by scenario also splits by company.

Eighteen scenario templates cover the cases on the project board:

| Template | Produces |
|---|---|
| `synonym_equivalent` | Equivalent: naming variants, scale and rounding differences, entity and period formatting, negative values |
| `rounding` | Equivalent within rounding (42.5M vs 42,540,000) and near-miss conflicts just outside it |
| `value_conflict`, `restatement` | Conflicting: same concept, entity and period, different values (restatements carry evidence text saying so) |
| `scale_error`, `currency_mismatch` | Conflicting (scale) and insufficient evidence (currency, no conversion) |
| `marker_diff` | Related: Adjusted/Non-GAAP/Pro forma/Gross qualifiers, EBITDA vs Adjusted EBITDA |
| `basis_diff` | Related: the same metric label under a GAAP and a non-GAAP basis |
| `defined_diff` | Related: different measures with stated definitions (revenue vs ARR, gross margin vs gross profit, EBITDA vs Adjusted EBITDA, and others from the board) |
| `company_defined` | ARR and Adjusted EBITDA: equivalent or conflicting when definitions match, related when they differ, insufficient evidence when a definition is missing |
| `period_mismatch` | Related: FY vs quarter, FY vs prior FY, LTM vs FY, calendar vs fiscal year |
| `as_of_mismatch` | Related: ARR (point in time) with matching stated definitions at different as-of dates |
| `sign_convention` | Equivalent: the same loss written as (5.2), -5.2 or 5.2 under "Net loss"; conflicting: a loss recorded as a profit |
| `entity_mismatch` | Related: parent vs subsidiary vs segment |
| `missing_entity`, `missing_period` | Insufficient evidence; the fact's evidence text never states the missing field |
| `ambiguous_name`, `ambiguous_resolved` | "Net revenue", "Core revenue" without a definition (insufficient) and with a resolving definition |

Many related and conflicting templates include a **same-value trap** (identical numbers that must
not be merged) alongside different-value cases.

## Guarantees

- **Labels follow the guidelines by construction.** Each pair declares the guideline judgments
  (concept, scope); the label is derived with the same `derive_label` and `values_agree` code the
  systems use, and generation fails if it differs from what the template expects. `EvalCase`
  validation also rejects evidence references that are not in the input.
- **No leakage.** Scenarios, facts and identical pairs never cross splits (the dataset loader's
  checks run on the output). Each scenario's documents share one `document_family`, which is
  what the loader keeps inside one split.
- **`metric_id` is a hint, not the answer.** Each fact's id comes from its name alone, as a
  name-based mapper would assign it. "Adjusted EBITDA" with different stated adjustments keeps
  `adjusted_ebitda` on both facts, and "Net revenue" maps to `other`.
- **Held-out vocabulary.** Some naming variants (for example "Turnover", "GM", "EBITDA
  (adjusted)") appear only in validation and test scenarios, so for any *trained* system those
  splits measure generalization to names it never saw. Cases that use one carry the tag
  `heldout_name`, so results can be sliced by it. A system that looks names up in the metric page,
  like the rules baseline, knows them already (it recognizes 7 of the 8) and scores higher on
  that slice than on the rest, so for lookup systems the slice is not a generalization test.
- **Not solvable by lookup.** The rules baseline knows every naming variant on the metric page (a
  test requires it), so it scores about 85% on generated data. The cases that need a definition
  read must stay out of its reach: a test fails if it scores above 95% overall or above 50% on
  the `definition_resolves` cases (it scores near 0%).
- **Deterministic** for a given seed and generator version; the manifest records both, plus
  label counts and dataset hashes.

## Outputs

| File | Contents | Use |
|---|---|---|
| `train.jsonl`, `validation.jsonl` | `EvalCase` labeled by construction, `labeled_by: generator` | Training and validation |
| `test_candidates.jsonl` | Unlabeled `CandidatePair` | Input to the labeling workflow ([labeling-workflow.md](labeling-workflow.md)) |
| `test_construction_labels.jsonl` | The generator's labels for the test candidates | **Quality check only.** Never gold labels |
| `manifest.json` | Version, seed, counts, distributions, hashes | Provenance |

## Checking the generator with human reviewers

After reviewers label the test candidates, compare their reviews with the construction labels
(`opslm.datagen.audit.compare_to_construction`). Disagreement concentrated in one template means
the template or the guideline is wrong. Do this on a first batch before generating training data
at scale.

## Limitations

- Language is templated. Excerpts are short and uniform, and definitions are canned. Models can
  learn the templates. An LLM paraphrasing step would add realism but is not built, and it would
  need its own validation that labels survive rewording.
- Five metrics and eighteen templates. No multi-hop reconciliation, tables, footnotes or
  documents. Reason codes `unsupported_claim`, `unit_scale` and `rounding` are never the primary
  reason in generated data (the last two only appear as secondary reasons).
- Company names are invented and could coincide with real companies.
- Synthetic labels encode the guideline authors' reading. They are only as good as the guidelines,
  which is why a human review of test candidates is part of the process.
