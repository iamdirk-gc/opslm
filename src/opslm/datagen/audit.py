"""Compare human reviews of generated test candidates with the generator's construction labels.

Disagreement points at a template that contradicts how careful reviewers read the guidelines,
or at a guideline gap. Either is worth fixing before generating training data at scale.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from opslm.labeling import CandidatePair, Review, derived_label
from opslm.schema import EvalCase


def compare_to_construction(
    reviews: Iterable[Review], construction: Iterable[EvalCase], candidates: Iterable[CandidatePair]
) -> dict[str, Any]:
    by_case = {c.case_id: c for c in construction}
    by_cand = {c.case_id: c for c in candidates}
    n = agree = 0
    by_kind: dict[str, list[int]] = {}
    disagreements: list[dict[str, str]] = []
    for r in reviews:
        gold = by_case.get(r.case_id)
        if gold is None:
            continue
        human = derived_label(by_cand[r.case_id], r)
        ok = human is gold.label and (r.concept_same, r.scope_same) == (gold.concept_same, gold.scope_same)
        n += 1
        agree += ok
        stats = by_kind.setdefault(gold.tags[0], [0, 0])
        stats[0] += 1
        stats[1] += ok
        if not ok:
            disagreements.append({"case_id": r.case_id, "kind": gold.tags[0],
                                  "construction": gold.label.value, "human": human.value})
    return {
        "n": n,
        "agreement": agree / n if n else None,
        "by_kind": {k: {"n": v[0], "agreement": v[1] / v[0]} for k, v in sorted(by_kind.items())},
        "disagreements": disagreements,
    }
