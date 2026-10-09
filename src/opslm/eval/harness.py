"""Run a Predictor over a dataset and produce a reproducible result artifact."""

from __future__ import annotations

import json
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

import opslm
from opslm.data import dataset_hash
from opslm.eval import metrics as m
from opslm.eval.stats import bootstrap_ci, mcnemar_exact
from opslm.labels import GUIDELINE_VERSION
from opslm.predictor import Predictor
from opslm.schema import EvalCase, Prediction, Relation


class Interval(BaseModel):
    value: float | None
    lo: float | None = None
    hi: float | None = None


class EvidenceMetrics(BaseModel):
    """Whether cited evidence covers the fields that determine the gold label."""

    n: int
    recall: float
    precision: float


class CostMetrics(BaseModel):
    total_usd: float | None
    usd_per_1k_pairs: float | None
    mean_latency_s: float | None
    p50_latency_s: float | None
    p95_latency_s: float | None


class SliceMetrics(BaseModel):
    n: int
    accuracy: float
    macro_f1: float


class CaseRecord(BaseModel):
    case_id: str
    gold: Relation
    prediction: Prediction | None
    error: str | None = None
    correct: bool
    latency_s: float | None = None
    cost_usd: float | None = None


class RunResult(BaseModel):
    system: str
    created_at: str
    opslm_version: str
    guideline_version: str
    dataset_hash: str
    config: dict[str, Any]
    n_cases: int
    n_errors: int
    metrics: dict[str, Interval]
    per_class: dict[str, m.ClassMetrics]
    confusion: dict[str, dict[str, int]]
    evidence: EvidenceMetrics | None
    cost: CostMetrics
    slices: dict[str, dict[str, SliceMetrics]]
    records: list[CaseRecord]


def _percentile(sorted_values: list[float], q: float) -> float:
    return sorted_values[min(len(sorted_values) - 1, int(q * len(sorted_values)))]


def _run_cases(predictor: Predictor, cases: Sequence[EvalCase]) -> list[CaseRecord]:
    records = []
    for case in cases:
        start = time.perf_counter()
        prediction: Prediction | None = None
        error: str | None = None
        try:
            prediction = predictor.predict(case.case_id, case.pair)
        except Exception as e:  # noqa: BLE001 - a failing system is a result, not a harness crash
            error = f"{type(e).__name__}: {e}"
        elapsed = time.perf_counter() - start
        latency = prediction.latency_s if prediction and prediction.latency_s is not None else elapsed
        records.append(
            CaseRecord(
                case_id=case.case_id,
                gold=case.label,
                prediction=prediction,
                error=error,
                correct=prediction is not None and prediction.label is case.label,
                latency_s=latency,
                cost_usd=prediction.cost_usd if prediction else None,
            )
        )
    return records


def _evidence(cases: Sequence[EvalCase], records: Sequence[CaseRecord]) -> EvidenceMetrics | None:
    recalls, precisions = [], []
    for case, rec in zip(cases, records, strict=True):
        gold = set(case.discriminating_fields)
        if not gold or rec.prediction is None:
            continue
        cited = {e.field for e in rec.prediction.evidence}
        hits = len(gold & cited)
        recalls.append(hits / len(gold))
        precisions.append(hits / len(cited) if cited else 0.0)
    if not recalls:
        return None
    return EvidenceMetrics(
        n=len(recalls), recall=sum(recalls) / len(recalls), precision=sum(precisions) / len(precisions)
    )


def _cost(records: Sequence[CaseRecord]) -> CostMetrics:
    costs = [r.cost_usd for r in records if r.cost_usd is not None]
    lats = sorted(r.latency_s for r in records if r.latency_s is not None)
    return CostMetrics(
        total_usd=sum(costs) if costs else None,
        usd_per_1k_pairs=sum(costs) / len(costs) * 1000 if costs else None,
        mean_latency_s=sum(lats) / len(lats) if lats else None,
        p50_latency_s=_percentile(lats, 0.5) if lats else None,
        p95_latency_s=_percentile(lats, 0.95) if lats else None,
    )


def _slices(
    cases: Sequence[EvalCase], gold: list[Relation], pred: list[m.Pred]
) -> dict[str, dict[str, SliceMetrics]]:
    groups: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for i, case in enumerate(cases):
        groups["source_kind"][case.source_kind.value].append(i)
        if case.discrepancy_reason:
            groups["discrepancy_reason"][case.discrepancy_reason.value].append(i)
        for tag in case.tags:
            groups["tag"][tag].append(i)
    return {
        dim: {
            key: SliceMetrics(
                n=len(idx),
                accuracy=m.accuracy([gold[i] for i in idx], [pred[i] for i in idx]),
                macro_f1=m.macro_f1([gold[i] for i in idx], [pred[i] for i in idx]),
            )
            for key, idx in sorted(by_key.items())
        }
        for dim, by_key in sorted(groups.items())
    }


def evaluate(
    predictor: Predictor,
    cases: Sequence[EvalCase],
    *,
    config: dict[str, Any] | None = None,
    bootstrap_n: int = 1000,
    seed: int = 0,
) -> RunResult:
    """Score a predictor on a set of cases.

    ``config`` records whatever is needed to reproduce the run (model version, prompt hash,
    decoding settings). The harness stores it verbatim.
    """
    cases = list(cases)
    records = _run_cases(predictor, cases)
    gold = [c.label for c in cases]
    pred: list[m.Pred] = [r.prediction.label if r.prediction else None for r in records]

    def interval(fn: Callable[[Sequence[Relation], Sequence[m.Pred]], float | None]) -> Interval:
        ci = bootstrap_ci(fn, gold, pred, n=bootstrap_n, seed=seed)
        return Interval(value=fn(gold, pred), lo=ci[0] if ci else None, hi=ci[1] if ci else None)

    def exact(judgment: str) -> Interval:
        # accuracy of the three-valued judgment (None == "cannot tell" counts as an answer)
        scored = [
            getattr(rec.prediction, judgment) == getattr(case, judgment)
            for case, rec in zip(cases, records, strict=True)
            if rec.prediction is not None
        ]
        return Interval(value=sum(scored) / len(cases) if cases else None)

    return RunResult(
        system=predictor.name,
        created_at=datetime.now(timezone.utc).isoformat(),
        opslm_version=opslm.__version__,
        guideline_version=GUIDELINE_VERSION,
        dataset_hash=dataset_hash(cases),
        config=config or {},
        n_cases=len(cases),
        n_errors=sum(r.error is not None for r in records),
        metrics={
            "macro_f1": interval(m.macro_f1),
            "accuracy": interval(m.accuracy),
            "false_match_rate": interval(m.false_match_rate),
            "missed_match_rate": interval(m.missed_match_rate),
            "concept_accuracy": exact("concept_same"),
            "scope_accuracy": exact("scope_same"),
        },
        per_class=m.per_class(gold, pred),
        confusion=m.confusion_matrix(gold, pred),
        evidence=_evidence(cases, records),
        cost=_cost(records),
        slices=_slices(cases, gold, pred),
        records=records,
    )


class Comparison(BaseModel):
    system_a: str
    system_b: str
    n: int
    accuracy_a: float
    accuracy_b: float
    only_a_correct: int
    only_b_correct: int
    p_value: float


def compare_runs(a: RunResult, b: RunResult) -> Comparison:
    """Paired comparison of two runs on the same dataset (exact McNemar test)."""
    if a.dataset_hash != b.dataset_hash:
        raise ValueError("runs were produced on different datasets and cannot be paired")
    ra = {r.case_id: r.correct for r in a.records}
    rb = {r.case_id: r.correct for r in b.records}
    only_a = sum(ra[c] and not rb[c] for c in ra)
    only_b = sum(rb[c] and not ra[c] for c in ra)
    n = len(ra)
    return Comparison(
        system_a=a.system,
        system_b=b.system,
        n=n,
        accuracy_a=sum(ra.values()) / n if n else 0.0,
        accuracy_b=sum(rb.values()) / n if n else 0.0,
        only_a_correct=only_a,
        only_b_correct=only_b,
        p_value=mcnemar_exact(only_a, only_b),
    )


def write_run(path: str | Path, run: RunResult) -> None:
    Path(path).write_text(json.dumps(run.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")


def read_run(path: str | Path) -> RunResult:
    return RunResult.model_validate_json(Path(path).read_text(encoding="utf-8"))


def _fmt(i: Interval, pct: bool = True) -> str:
    if i.value is None:
        return "n/a"
    scale = 100 if pct else 1
    text = f"{i.value * scale:.1f}{'%' if pct else ''}"
    if i.lo is not None and i.hi is not None:
        text += f"  (95% CI {i.lo * scale:.1f}-{i.hi * scale:.1f})"
    return text


def format_summary(run: RunResult) -> str:
    lines = [
        f"system: {run.system}   cases: {run.n_cases}   errors: {run.n_errors}",
        f"dataset: {run.dataset_hash[:12]}   guideline: {run.guideline_version}",
        "",
    ]
    for name, interval in run.metrics.items():
        lines.append(f"{name:<18}{_fmt(interval)}")
    lines += ["", f"{'class':<24}{'precision':>10}{'recall':>8}{'f1':>8}{'n':>6}"]
    for label, c in run.per_class.items():
        lines.append(f"{label:<24}{c.precision:>10.2f}{c.recall:>8.2f}{c.f1:>8.2f}{c.support:>6}")
    if run.evidence:
        e = run.evidence
        lines += ["", f"evidence (n={e.n}): recall {e.recall:.2f}, precision {e.precision:.2f}"]
    c = run.cost
    if c.mean_latency_s is not None:
        lines.append(f"latency: mean {c.mean_latency_s * 1000:.1f} ms, p95 {c.p95_latency_s * 1000:.1f} ms")
    if c.usd_per_1k_pairs is not None:
        lines.append(f"cost: ${c.usd_per_1k_pairs:.4f} per 1,000 pairs")
    return "\n".join(lines)
