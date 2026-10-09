"""Uncertainty and significance for small evaluation sets."""

from __future__ import annotations

import random
from collections.abc import Callable, Sequence
from math import comb
from typing import TypeVar

G = TypeVar("G")
P = TypeVar("P")


def bootstrap_ci(
    metric: Callable[[Sequence[G], Sequence[P]], float | None],
    gold: Sequence[G],
    pred: Sequence[P],
    *,
    n: int = 1000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float] | None:
    """Percentile bootstrap interval, resampling cases with replacement.

    Resamples where the metric is undefined (e.g. no negatives drawn) are skipped.
    Returns None when the interval cannot be computed.
    """
    if not gold or n <= 0:
        return None
    rng = random.Random(seed)
    size = len(gold)
    values: list[float] = []
    for _ in range(n):
        idx = [rng.randrange(size) for _ in range(size)]
        value = metric([gold[i] for i in idx], [pred[i] for i in idx])
        if value is not None:
            values.append(value)
    if not values:
        return None
    values.sort()
    lo = values[int(alpha / 2 * (len(values) - 1))]
    hi = values[int((1 - alpha / 2) * (len(values) - 1))]
    return lo, hi


def mcnemar_exact(only_a_correct: int, only_b_correct: int) -> float:
    """Two-sided exact McNemar test on the cases where exactly one system was right.

    Under the null hypothesis the two systems are equally likely to win each such case.
    """
    n = only_a_correct + only_b_correct
    if n == 0:
        return 1.0
    k = min(only_a_correct, only_b_correct)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2 * tail)
