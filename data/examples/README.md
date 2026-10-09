# Example cases

`guideline_examples.jsonl` holds nine cases that illustrate the labeling guidelines
(`docs/labeling-guidelines.md`). They were written by hand to demonstrate each label and
discrepancy reason, are marked `reviewed: false`, and are **not benchmark data**.

The rules baseline scores 100% on them because the rules were written alongside them. That
says nothing about real performance; it only shows the pipeline runs end to end:

```bash
python -m opslm.eval run --dataset data/examples/guideline_examples.jsonl --system rules
```
