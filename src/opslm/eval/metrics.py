"""Classification metrics over the four-way relation label.

Predictions may be ``None`` (the system errored or returned nothing). That counts as a miss
for the gold class and never as a correct or incorrect prediction of any class.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from opslm.schema import Relation

Pred = Relation | None


class ClassMetrics(BaseModel):
    precision: float
    recall: float
    f1: float
    support: int


def confusion_matrix(gold: Sequence[Relation], pred: Sequence[Pred]) -> dict[str, dict[str, int]]:
    """Rows are gold labels, columns predicted labels plus ``none`` for missing predictions."""
    columns = [r.value for r in Relation] + ["none"]
    matrix = {g.value: dict.fromkeys(columns, 0) for g in Relation}
    for g, p in zip(gold, pred, strict=True):
        matrix[g.value]["none" if p is None else p.value] += 1
    return matrix


def per_class(gold: Sequence[Relation], pred: Sequence[Pred]) -> dict[str, ClassMetrics]:
    out: dict[str, ClassMetrics] = {}
    for label in Relation:
        tp = sum(g is label and p is label for g, p in zip(gold, pred, strict=True))
        predicted = sum(p is label for p in pred)
        support = sum(g is label for g in gold)
        precision = tp / predicted if predicted else 0.0
        recall = tp / support if support else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        out[label.value] = ClassMetrics(precision=precision, recall=recall, f1=f1, support=support)
    return out


def accuracy(gold: Sequence[Relation], pred: Sequence[Pred]) -> float:
    if not gold:
        return 0.0
    return sum(g is p for g, p in zip(gold, pred, strict=True)) / len(gold)


def macro_f1(gold: Sequence[Relation], pred: Sequence[Pred]) -> float:
    """Mean F1 over the classes that appear in the gold labels.

    Classes absent from the gold set are excluded, so a small slice that happens to lack a
    class is not penalized for it. Predicting an absent class still hurts precision elsewhere.
    """
    scores = [m.f1 for m in per_class(gold, pred).values() if m.support > 0]
    return sum(scores) / len(scores) if scores else 0.0


def false_match_rate(gold: Sequence[Relation], pred: Sequence[Pred]) -> float | None:
    """Share of non-equivalent pairs the system called equivalent. None if there are none."""
    negatives = [p for g, p in zip(gold, pred, strict=True) if g is not Relation.EQUIVALENT]
    if not negatives:
        return None
    return sum(p is Relation.EQUIVALENT for p in negatives) / len(negatives)


def missed_match_rate(gold: Sequence[Relation], pred: Sequence[Pred]) -> float | None:
    """Share of equivalent pairs the system did not call equivalent. None if there are none."""
    positives = [p for g, p in zip(gold, pred, strict=True) if g is Relation.EQUIVALENT]
    if not positives:
        return None
    return sum(p is not Relation.EQUIVALENT for p in positives) / len(positives)
