"""Generate synthetic scenarios and turn them into labeled datasets.

Outputs, by split:
- train, validation: ``EvalCase`` records labeled by construction (``labeled_by`` is
  "generator").
- test: ``CandidatePair`` records for human review via the labeling workflow, plus a separate
  file of the construction labels. The construction labels exist to measure how often careful
  reviewers disagree with the generator (a check on the generator and the guidelines). They must
  never be used as the benchmark's gold labels: the benchmark rests on human-reviewed cases.

Every case is checked as it is built: the label derived from the declared judgments and the
computed value comparison must equal the template's expectation, and the dataset as a whole is
checked for split leakage. Scenario = one synthetic company, so splits are also company-level.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opslm.data import dataset_hash, validate_cases, write_cases
from opslm.datagen import vocab as V
from opslm.datagen.scenarios import TEMPLATES, Ctx, PairSpec
from opslm.labeling import CandidatePair, write_candidates
from opslm.labels import GUIDELINE_VERSION, derive_label, infer_reasons, values_agree
from opslm.schema import (
    CONSTRUCTION_LABELER,
    EvalCase,
    GoldLabel,
    ReconciliationInput,
    Source,
    Split,
)

GENERATOR_VERSION = "1"


class GeneratorError(RuntimeError):
    """A template produced data that contradicts the labeling guidelines."""


@dataclass
class GenerationResult:
    train: list[EvalCase]
    validation: list[EvalCase]
    test_candidates: list[CandidatePair]
    test_construction: list[EvalCase]
    manifest: dict[str, Any] = field(default_factory=dict)


def _case(spec: PairSpec, ctx: Ctx, kind: str, j: int, split: Split) -> EvalCase:
    a, b = ctx.facts[spec.a], ctx.facts[spec.b]
    agree = values_agree(a.quantity, b.quantity)
    label = derive_label(spec.concept, spec.scope, agree)
    if label != spec.expect:
        raise GeneratorError(
            f"{ctx.scenario_id} ({kind}): template expected {spec.expect.value} but the guideline "
            f"decision table gives {label.value} for {a.metric_label!r} vs {b.metric_label!r} "
            f"(values {a.quantity.raw_text} / {b.quantity.raw_text})"
        )
    reasons = list(spec.reasons) or infer_reasons(a, b, spec.concept, spec.scope, agree)
    case_id = f"{ctx.scenario_id}-p{j}"
    doc_ids = {s.doc_id for f in (a, b) for s in f.evidence}
    return EvalCase(
        input=ReconciliationInput(case_id=case_id, fact_a=a, fact_b=b,
                                  documents=[ctx.docs[d] for d in sorted(doc_ids)]),
        gold=GoldLabel(
            case_id=case_id, relationship=label, concept_same=spec.concept,
            scope_same=spec.scope, reasons=reasons,
            # each fact has one span, and every judgment rests on what both facts say
            required_evidence_refs=[s.span_id for f in (a, b) for s in f.evidence],
            rationale=spec.rationale, tags=list(dict.fromkeys((kind, *spec.tags))), split=split,
            source=Source.SYNTHETIC, labeled_by=CONSTRUCTION_LABELER,
            guideline_version=GUIDELINE_VERSION,
        ),
    )


def _split_plan(n: int, fractions: tuple[float, float, float], rng: random.Random) -> list[Split]:
    n_train, n_val = round(n * fractions[0]), round(n * fractions[1])
    plan = ([Split.TRAIN] * n_train + [Split.VALIDATION] * n_val
            + [Split.TEST] * max(0, n - n_train - n_val))[:n]
    rng.shuffle(plan)
    return plan


def generate(
    n_scenarios: int = 400,
    *,
    seed: int = 0,
    fractions: tuple[float, float, float] = (0.7, 0.1, 0.2),
    weights: dict[str, int] | None = None,
) -> GenerationResult:
    """Generate ``n_scenarios`` scenarios, deterministically for a given seed and version."""
    if abs(sum(fractions) - 1.0) > 1e-9:
        raise ValueError("split fractions must sum to 1")
    names = list(TEMPLATES)
    w = [(weights or {}).get(k, TEMPLATES[k][1]) for k in names]
    plan = _split_plan(n_scenarios, fractions, random.Random(f"{seed}:splits"))
    used: set[str] = set()
    result = GenerationResult([], [], [], [])

    for i, split in enumerate(plan):
        rng = random.Random(f"{seed}:{i}")
        kind_name = rng.choices(names, w)[0]
        scenario_id = f"syn{seed}-{i:05d}"
        ctx = Ctx(rng, scenario_id, V.make_company(rng, used), V.make_calendar(rng),
                  heldout=split is not Split.TRAIN)
        kind, specs = TEMPLATES[kind_name][0](ctx)
        cases = [_case(s, ctx, kind, j, split) for j, s in enumerate(specs, 1)]
        if split is Split.TRAIN:
            result.train += cases
        elif split is Split.VALIDATION:
            result.validation += cases
        else:
            result.test_construction += cases
            result.test_candidates += [
                CandidatePair(input=c.input, source=c.gold.source, split=Split.TEST,
                              tags=tuple(c.gold.tags))
                for c in cases
            ]

    # leakage check across all splits (test labels count as human only for this check)
    checked = result.train + result.validation + [
        c.model_copy(update={"gold": c.gold.model_copy(update={"labeled_by": "leakage-check"})})
        for c in result.test_construction]
    problems = validate_cases(checked)
    if problems:
        raise GeneratorError("generated data failed validation: " + "; ".join(problems[:5]))

    result.manifest = _manifest(result, n_scenarios, seed, fractions, dict(zip(names, w, strict=True)))
    return result


def _distribution(cases: list[EvalCase]) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in cases:
        out[c.gold.relationship] = out.get(c.gold.relationship, 0) + 1
    return dict(sorted(out.items()))


def _manifest(r: GenerationResult, n: int, seed: int, fractions: tuple[float, ...],
              weights: dict[str, int]) -> dict[str, Any]:
    kinds: dict[str, int] = {}
    for c in r.train + r.validation + r.test_construction:
        kinds[c.gold.tags[0]] = kinds.get(c.gold.tags[0], 0) + 1
    splits = {"train": r.train, "validation": r.validation, "test": r.test_construction}
    return {
        "generator_version": GENERATOR_VERSION,
        "guideline_version": GUIDELINE_VERSION,
        "seed": seed,
        "scenarios": n,
        "fractions": list(fractions),
        "template_weights": weights,
        "pairs_by_kind": dict(sorted(kinds.items())),
        "splits": {
            name: {"pairs": len(cs),
                   "scenarios": len({f for c in cs for f in c.input.document_families()}),
                   "labels": _distribution(cs), "dataset_hash": dataset_hash(cs)}
            for name, cs in splits.items()
        },
        "notes": "Labels are by construction and unreviewed. The test split is for human review "
                 "only; test_construction_labels.jsonl must not be used as gold labels.",
    }


def write_outputs(result: GenerationResult, out_dir: str | Path) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "train": out / "train.jsonl",
        "validation": out / "validation.jsonl",
        "test_candidates": out / "test_candidates.jsonl",
        "test_construction_labels": out / "test_construction_labels.jsonl",
        "manifest": out / "manifest.json",
    }
    write_cases(paths["train"], result.train)
    write_cases(paths["validation"], result.validation)
    write_candidates(paths["test_candidates"], result.test_candidates)
    write_cases(paths["test_construction_labels"], result.test_construction)
    paths["manifest"].write_text(json.dumps(result.manifest, indent=2) + "\n", encoding="utf-8")
    return paths
