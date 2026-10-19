"""Write the JSON Schemas for the task's records: ``python -m opslm.export_schemas --out-dir schemas``.

The checked-in copies under ``schemas/`` are what other tools use: an LLM API's structured-output
mode (``reconciliation_output``), extraction pipelines that produce inputs, and labeling tools.
A test fails when they drift from ``opslm.schema``, so rerun this after any schema change.

pydantic's JSON Schema output can change between releases, so the version used is recorded in
``schemas/pydantic_version.txt``. The drift test is enforced for installs of that major.minor
version and skipped for any other (CI has a job that installs the exact version and never
skips), so a pydantic minor upgrade cannot break the build on its own.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pydantic

from opslm.schema import EvalCase, GoldLabel, ReconciliationInput, ReconciliationOutput

MODELS = {
    "reconciliation_input": ReconciliationInput,
    "reconciliation_output": ReconciliationOutput,
    "gold_label": GoldLabel,
    "eval_case": EvalCase,
}


def json_schemas() -> dict[str, dict[str, Any]]:
    return {name: model.model_json_schema() for name, model in MODELS.items()}


def render(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def write_schemas(out_dir: str | Path) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, schema in json_schemas().items():
        path = out / f"{name}.schema.json"
        path.write_text(render(schema), encoding="utf-8")
        paths.append(path)
    version = out / "pydantic_version.txt"
    version.write_text(pydantic.VERSION + "\n", encoding="utf-8")
    paths.append(version)
    return paths


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m opslm.export_schemas")
    p.add_argument("--out-dir", default="schemas")
    for path in write_schemas(p.parse_args(argv).out_dir):
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
