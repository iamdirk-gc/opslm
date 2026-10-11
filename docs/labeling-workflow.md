# Labeling Workflow

How two reviewers turn candidate pairs into reviewed evaluation cases. The rules for *what* to
label are in [labeling-guidelines.md](labeling-guidelines.md); this document covers the mechanics.
Reviewers work in Excel or Google Sheets. Only the engineer runs the commands.

Install once: `pip install -e ".[labeling]"` (adds the spreadsheet library).

## Dry run first

Practice on the nine example pairs before the real batch, so the first overlap does not double
as tool testing:

```bash
python -m opslm.labeling_cli plan --candidates data/examples/candidates_example.jsonl \
  --reviewers gerry partner --overlap 4 --out-dir /tmp/dryrun
```

## Steps

**1. Plan and export.** Splits the candidates between reviewers, with a shared overlap that both
label (the plan to use for real is about 30 shared cases, plus an equal split of the rest). Each
reviewer gets their own sheet, in an independent random order. Reviewers should not know which
rows are shared.

```bash
python -m opslm.labeling_cli plan --candidates candidates.jsonl \
  --reviewers gerry partner --overlap 30 --out-dir labeling/round1
```

**2. Label.** Each reviewer opens their sheet (upload the `.xlsx` to Google Sheets if preferred)
and fills the yellow columns only:

| Column | Enter |
|---|---|
| `concept_same` | `yes`, `no` or `cannot_tell` (dropdown) |
| `scope_same` | `yes`, `no` or `cannot_tell` (dropdown) |
| `primary_reason` | Required (dropdown). The main reason the facts match or differ; codes are in the guidelines |
| `other_reasons` | Optional. Further reason codes, comma separated |
| `evidence_refs` | Required unless the label is `insufficient_evidence`. The span ids shown in brackets in the `A_evidence` and `B_evidence` columns, comma separated, e.g. `s-a1, s-b1` |
| `rationale` | One or two sentences |
| `flag` | Optional. Anything to raise at the adjudication meeting, such as a guideline question |

You never enter the final label. It is worked out from your two judgments and the computed
`values_agree` column. If the label you would expect differs from what your judgments imply,
write that in `flag`; do not bend the judgments. Leave a row blank to skip it. Do not edit the grey
columns (they are ignored on import). Do not compare notes with the other reviewer.

**3. Import and fix problems.** The importer lists problems in plain language with sheet row
numbers (for example `row 14 (c13): evidence_refs is required for 'conflicting'`). Fix the sheet and re-run.

```bash
python -m opslm.labeling_cli import --candidates candidates.jsonl \
  --sheet labeling/round1/sheet_gerry.xlsx --reviewer gerry --out labeling/round1/gerry.jsonl
```

**4. Agreement and adjudication sheet.** Run once both reviewers have imported. This prints
agreement and Cohen's kappa on the shared cases (target for the label: at least 0.7) and writes
a sheet containing every disagreement, every case where the reviewers agree on the judgments
but differ on the primary reason or the evidence spans, and every flagged case.

```bash
python -m opslm.labeling_cli agreement --candidates candidates.jsonl \
  --a labeling/round1/gerry.jsonl --b labeling/round1/partner.jsonl \
  --out labeling/round1/adjudication.xlsx
```

**5. Adjudicate together.** In the meeting, fill the `resolved_*` columns for each row and write
the deciding rule in `rule_decided`. A row without a rule is rejected. The project owner has the
final say. Every new rule goes into `labeling-guidelines.md` and bumps the guideline version.

```bash
python -m opslm.labeling_cli resolutions --candidates candidates.jsonl \
  --sheet labeling/round1/adjudication.xlsx --out labeling/round1/resolutions.jsonl
```

**6. Finalize.** Builds the evaluation dataset. A shared case where the reviewers disagree and
no resolution exists blocks the build. Unreviewed candidates are skipped and counted. The result
is checked for split leakage before it is written.

```bash
python -m opslm.labeling_cli finalize --candidates candidates.jsonl \
  --reviews labeling/round1/gerry.jsonl labeling/round1/partner.jsonl \
  --resolutions labeling/round1/resolutions.jsonl --out data/benchmark.jsonl
```

## Candidate file format

One JSON object per line (`CandidatePair` in `src/opslm/labeling.py`): `input` (a
`ReconciliationInput`: the case id, two business facts and their source documents), `source`
(`real` or `synthetic`), `split` and optional `tags`. Splits are decided when candidates are
created, by document family, so a company's documents never span splits. See
`data/examples/candidates_example.jsonl`.

Finalized cases are `{"input": ..., "gold": ...}` lines (`EvalCase` in `src/opslm/schema.py`).
The gold label records the reviewers' judgments, reasons and evidence, `labeled_by` (the first
reviewer), `reviewed_by` (the second reviewer on overlap cases, or `adjudicated`) and, for
adjudicated cases, the deciding rule as `adjudication_note`.

## Safety notes

- Text from documents is written into sheet cells. Cells that would start with `=`, `+`, `@` or a
  leading `-` followed by a non-digit get a leading apostrophe so spreadsheet apps cannot run them
  as formulas. Do not remove it.
- Reviews contain only judgments and free text. Do not paste confidential or employer data into
  rationales.
