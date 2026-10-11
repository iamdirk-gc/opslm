# Example cases

`guideline_examples.jsonl` holds nine cases that illustrate the labeling guidelines
(`docs/labeling-guidelines.md`). They were written by hand to demonstrate each label and
reason code, are labeled by `guideline-examples` in the train split, and are **not benchmark
data**.

The rules baseline scores 100% on them because the rules were written alongside them. That
says nothing about real performance; it only shows the pipeline runs end to end:

```bash
python -m opslm.eval run --dataset data/examples/guideline_examples.jsonl --system rules
```

`candidates_example.jsonl` is the same nine pairs without labels, for a dry run of the labeling
workflow (see `docs/labeling-workflow.md`).

`example_case.json` is one worked input and system output (a revenue conflict between a 10-K and
an investor deck, resolved to the audited figure) showing every field of the v0.2.0 schema,
including the optional resolution fields. JSON Schemas for these records are in `schemas/`;
regenerate them with `python -m opslm.export_schemas` after changing `src/opslm/schema.py`.
