# Project Board Alignment

Compares the project board ("OpsLM Milestones & To-Dos", read on 2026-10-09) with the state of
the repository, and lists what the board implies for engineering and what needs the project
owner's decision. Dates are from the board's Tracker sheet.

## Applied to the repository from the board

- Generator vocabulary re-based on the v1 metric set ([metric-set-v1.md](metric-set-v1.md)), already merged to main.
- Labeling guidelines v1.1 (a **draft for the owner's review**, task 1.3) adopt the board's rules: Net revenue is conditional, company-defined metrics need stated definitions, point-in-time metrics compare on as-of date.
- Rules baseline and the LLM prompt updated to match (prompt version 2).
- A bug fix surfaced while building the generator: `derive_label` returned `insufficient_evidence` for a different concept with an undeterminable scope, contradicting the guideline table. A different concept now settles the label.

## Task status against the repository

| Task | Board status | Repository state |
|---|---|---|
| 1.2 Schema | In progress | Typed models exist (`schema.py`). Mapping to the board's output fields: resolution_status = `label`, reason = `discrepancy_reason`, abstention = `insufficient_evidence`, provenance = `SourceRef`, evidence_refs = `Prediction.evidence`. **Gap:** evidence references name a fact and field, not an exact span (page, table, cell), which tasks 2.3 and 4.1 require |
| 1.3 Guidelines | Not started | Drafted (v1.1), unreviewed by a second person |
| 1.4 Repo | In progress | License, packaging, layout and 170 tests exist. **No CI yet** |
| 1.5 Eval contract and threshold | Not started | Metrics implemented. **The fine-tuning success threshold is not defined** |
| 1.6 Seed examples | Not started | Nine illustrative examples exist; they are not the owner's hand-labeled seed set |
| 2.1-2.4 Extraction | Not started | **Nothing built.** `SourceRef` has page, bbox and cell fields for it |
| 3.1 Generator | In progress | Built ([synthetic-data.md](synthetic-data.md)) |
| 3.2 Mine real pairs | Not started | **No tool.** Needs pairing and blocking logic over extracted facts |
| 3.3 Split by company and document family | Not started | Synthetic data splits by scenario (one company each). Real data needs a company or document-family group id; the loader enforces separation on `scenario_id`, so real cases should use that field for the company group |
| 3.4 Label 100-200 cases | Not started | Workflow built ([labeling-workflow.md](labeling-workflow.md)); not yet used by two people |
| 3.5 Training set | Not started | Generator produces it; label distribution is in the manifest |
| 4.1 Harness | Not started | Built for reconciliation-only evaluation. **Not built:** the end-to-end (with extraction) mode and the "difficulty slice" definitions |
| 4.2 Rules baseline | Not started | Built; vocabulary updated to v1.1; needs the owner's review of the synonym map |
| 4.3 Frontier LLM baseline | Not started | Built provider-agnostic; **never run** (needs credentials and a budget decision) |
| 4.4 Small open-weight baseline | Not started | Backend exists (OpenAI-compatible: vLLM, Ollama, Vertex); **no model is hosted yet** |
| 5.x Fine-tuning | Not started | Nothing built. The board says no training spend before the D1 decision |
| 6.x Release | Not started | README and quickstart are partial; no demo, no reproduction guide |

## Schedule risk

The critical path is 2.3 (extraction adapter, due Oct 17) to 3.2 (mining real pairs, Oct 17-21) to
3.4 (labeling 100-200 cases, Oct 20-24). Neither the adapter nor the pair-mining tool exists, and
labeling has four days. Suggested mitigations:
- Start 2.1 and 2.3 immediately; the board has them starting Oct 13-14.
- Add an explicit task for the pair-mining tool. It is not on the board and nobody owns it.
- Decide a fallback: if real pairs are late, label the human-reviewed synthetic test candidates first, and label real pairs as they arrive.

## Gaps not on the board

- Continuous integration (part of 1.4).
- Candidate-pair mining tool (3.2).
- End-to-end evaluation mode and defined difficulty slices (4.1).
- Evidence-span references on predictions (1.2, 2.3, 4.1).
- A dry run of the labeling workflow with both reviewers before the real overlap batch.
- Hosting an open-weight model for 4.4 (Vertex AI or a GPU VM) and the self-hosted cost-comparison method.

## Questions for the project owner

1. **Net revenue.** The original plan lists Revenue vs Net Revenue as equivalent; the board says conditional. Guidelines v1.1 follow the board. Confirm.
2. **Net sales vs Net revenue.** The board lists "Net sales" as an unconditional revenue variant and "Net revenue" as conditional. Is that distinction intended?
3. **Adjusted EBITDA names.** The board says variants are equivalent "if definition, entity and period match". v1.1 reads that as: without stated definitions the label is insufficient evidence, even for identical names. Confirm.
4. **Sign conventions.** Should extraction normalize "net loss of 5.2" to -5.2, or should the reconciler handle it? The schema currently compares signed values as recorded.
5. **Flow vs point-in-time pairs** such as Revenue vs ARR: the generator leaves scope undetermined (the label is settled by the concept difference). Is that the intended judgment?
6. **Fine-tuning threshold (1.5).** What improvement counts as meaningful? It must be written before any results, and D1 depends on it.
7. **Tracking.** GitHub Projects and Milestones could replace or complement the spreadsheet; issues in this public repo are public. Decide whether to migrate the engineering tasks.
