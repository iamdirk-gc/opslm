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
| `opslm.datagen` | Synthetic generator: labeled fact pairs for training and candidate pairs for review ([docs](docs/synthetic-data.md)) |
| `opslm.baselines` | Rules-based and LLM systems. The LLM system is provider-agnostic: Anthropic, any OpenAI-compatible endpoint (vLLM, Ollama, Vertex AI open models), and Gemini on Vertex |
| `opslm.labeling` | Spreadsheet workflow for two reviewers: export, validated import, agreement, adjudication ([docs](docs/labeling-workflow.md)) |
| `opslm.train` | SFT/LoRA fine-tuning pipeline |
| `opslm.pipeline` | Integration with existing extraction tools (e.g. Docling) |

See [docs/plan.md](docs/plan.md) for the full plan and the November 9 milestone, and [docs/labeling-guidelines.md](docs/labeling-guidelines.md) for how evaluation cases are labeled.

## Status

Early development. The schema, dataset loader, rules baseline and evaluation harness work;
the synthetic generator exists; no real benchmark data, evaluated model-backed results or document pipeline exist yet. See
[docs/limitations-and-open-questions.md](docs/limitations-and-open-questions.md) and
[docs/board-alignment.md](docs/board-alignment.md) for what is missing and what is still undecided.

Try the harness on the illustrative examples:

```bash
python -m opslm.eval run --dataset data/examples/guideline_examples.jsonl --system rules
```

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## License

Apache 2.0. See [LICENSE](LICENSE).
