# OpsLM

Open-source toolkit for semantic data harmonization and model evaluation.

Extracting values from business documents is increasingly easy. Deciding whether two extracted facts mean the same thing, differ for an explainable reason, or genuinely conflict is harder. OpsLM provides a way to measure how well rules, frontier LLMs, and small open-weight models do that, and to fine-tune a specialized model for it.

Given two extracted business facts (metric, value, entity, period, units, definition, source), OpsLM classifies their relationship as one of:

- `equivalent`
- `related_but_different`
- `conflicting`
- `insufficient_evidence`

## Components

| Package | Purpose |
|---|---|
| `opslm.eval` | Benchmark harness: accuracy, false matches, evidence traceability, latency, cost |
| `opslm.datagen` | Synthetic generator for labeled equivalent, conflicting, and ambiguous fact pairs |
| `opslm.baselines` | Rules-based, frontier LLM, and untuned open-weight baselines |
| `opslm.train` | SFT/LoRA fine-tuning pipeline |
| `opslm.pipeline` | Integration with existing extraction tools (e.g. Docling) |

See [docs/plan.md](docs/plan.md) for the full plan and the November 9 milestone, and [docs/labeling-guidelines.md](docs/labeling-guidelines.md) for how evaluation cases are labeled.

## Status

Early scaffolding. Nothing is usable yet.

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0. See [LICENSE](LICENSE).
