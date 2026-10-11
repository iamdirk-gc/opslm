# Synthetic Data Generator

`python -m opslm.datagen --scenarios 400 --seed 0 --out-dir data/synthetic/v1`

Generates labeled fact pairs for **training** and for **candidate test pairs awaiting human
review**. Per the project plan, the benchmark itself rests on real, human-reviewed cases; the
generator exists to produce training data and to exercise the pipeline.

## Design

A **scenario** is a small synthetic data room: one fictional company, a fiscal calendar, a few
facts as different documents would report them, and the pairs worth comparing. Because each
scenario is its own company, splitting by scenario also splits by company.

Fifteen scenario templates cover the cases on the project board:

| Template | Produces |
|---|---|
| `synonym_equivalent` | Equivalent: naming variants, scale and rounding differences, entity and period formatting, negative values |
| `rounding` | Equivalent within rounding (42.5M vs 42,540,000) and near-miss conflicts just outside it |
| `value_conflict`, `restatement` | Conflicting: same concept, entity and period, different values (restatements carry an excerpt saying so) |
| `scale_error`, `currency_mismatch` | Conflicting (scale) and insufficient evidence (currency, no conversion) |
| `marker_diff` | Related: Adjusted/Non-GAAP/Pro forma/Gross qualifiers, EBITDA vs Adjusted EBITDA |
| `defined_diff` | Related: different measures with stated definitions (revenue vs ARR, gross margin vs gross profit, EBITDA vs Adjusted EBITDA, and others from the board) |
| `company_defined` | ARR and Adjusted EBITDA: equivalent or conflicting when definitions match, related when they differ, insufficient evidence when a definition is missing |
| `period_mismatch` | Related: FY vs quarter, FY vs prior FY, LTM vs FY, calendar vs fiscal year |
| `entity_mismatch` | Related: parent vs subsidiary vs segment |
| `missing_entity`, `missing_period` | Insufficient evidence; the excerpt never states the missing field |
| `ambiguous_name`, `ambiguous_resolved` | "Net revenue", "Core revenue" without a definition (insufficient) and with a resolving definition |

Many related and conflicting templates include a **same-value trap** (identical numbers that must
not be merged) alongside different-value cases.

## Guarantees

- **Labels follow the guidelines by construction.** Each pair declares the guideline judgments
  (concept, scope); the label is derived with the same `derive_label` and `values_agree` code the
  systems use, and generation fails if it differs from what the template expects. `EvalCase`
  validation also rejects inconsistent reasons and fields.
- **No leakage.** Scenarios, facts and identical pairs never cross splits (the dataset loader's
  checks run on the output).
- **Held-out vocabulary.** Some naming variants (for example "Turnover", "GM", "EBITDA
  (adjusted)") appear only in validation and test scenarios, so those splits measure
  generalization to unseen surface forms.
- **Not circular.** The vocabulary is independent of the rules baseline. A test fails if the
  baseline scores above 80% on the training data (it scores roughly 50%).
- **Deterministic** for a given seed and generator version; the manifest records both, plus
  label counts and dataset hashes.

## Outputs

| File | Contents | Use |
|---|---|---|
| `train.jsonl`, `validation.jsonl` | `EvalCase` labeled by construction, `reviewed: false` | Training and validation |
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
- Seven metrics and fifteen templates. No multi-hop reconciliation, tables, footnotes or
  documents, and no sign-convention variants beyond signed values.
- Company names are invented and could coincide with real companies.
- Synthetic labels encode the guideline authors' reading. They are only as good as the guidelines,
  which is why a human review of test candidates is part of the process.
