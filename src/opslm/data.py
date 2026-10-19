"""Reading, writing and validating evaluation datasets (JSONL, one ``EvalCase`` per line).

Each line is ``{"input": ReconciliationInput, "gold": GoldLabel}``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from opslm.labels import GUIDELINE_VERSION
from opslm.schema import BusinessFact, EvalCase, Split


class DatasetError(ValueError):
    """Raised when a dataset file is malformed or fails validation."""


def read_cases(path: str | Path) -> list[EvalCase]:
    """Parse a JSONL file without cross-case validation. Errors name the offending line."""
    cases: list[EvalCase] = []
    with open(path, encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            if not line.strip():
                continue
            try:
                cases.append(EvalCase.model_validate_json(line))
            except ValidationError as e:
                raise DatasetError(f"{path}:{lineno}: {e}") from e
    return cases


def write_cases(path: str | Path, cases: Iterable[EvalCase]) -> None:
    """Write cases as JSONL, sorted by case_id so files diff cleanly."""
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(case.model_dump_json() + "\n" for case in sorted(cases, key=lambda c: c.case_id))


_COMPANY_SUFFIXES = {"inc", "incorporated", "corp", "corporation", "co", "company", "llc", "ltd",
                     "limited", "plc", "lp", "llp", "gmbh", "sa", "ag"}


def company_key(name: str) -> str:
    """A company name reduced to what identifies it: case, punctuation and legal suffix removed,
    so 'Acme Corp.' and 'ACME, Inc.' are the same company for split-leakage purposes."""
    tokens = re.sub(r"[^a-z0-9]+", " ", name.casefold().replace("&", " and ")).split()
    return " ".join(t for t in tokens if t not in _COMPANY_SUFFIXES)


def _fact_content(fact: BusinessFact) -> str:
    """What a fact claims, without ids and locations, so a copy under new ids still matches."""
    return fact.model_dump_json(exclude={"fact_id", "evidence", "extraction"})


def validate_cases(cases: list[EvalCase]) -> list[str]:
    """Cross-case checks. Returns a list of problems; empty means the dataset is sound.

    Checks that matter for a trustworthy benchmark:
    - case_ids are unique
    - a company never spans more than one split, and neither does a document family
    - a fact_id never appears in more than one split, and always means the same fact
    - the same pair of facts never appears in more than one split, even under new ids
    - test cases are labeled by people, and their labels follow the current guideline version
    """
    problems: list[str] = []

    seen_ids: set[str] = set()
    for case in cases:
        if case.case_id in seen_ids:
            problems.append(f"duplicate case_id: {case.case_id}")
        seen_ids.add(case.case_id)

    company_splits: dict[str, set[str]] = defaultdict(set)
    company_names: dict[str, str] = {}
    family_splits: dict[str, set[str]] = defaultdict(set)
    fact_splits: dict[str, set[str]] = defaultdict(set)
    fact_content: dict[str, str] = {}
    pair_splits: dict[tuple[str, str], set[str]] = defaultdict(set)

    for case in cases:
        split = case.gold.split
        for family in case.input.document_families():
            family_splits[family].add(split)
        for doc in case.input.documents:
            key = company_key(doc.company)
            company_splits[key].add(split)
            company_names.setdefault(key, doc.company)
        pair = case.input
        for fact in (pair.fact_a, pair.fact_b):
            fact_splits[fact.fact_id].add(split)
            content = fact.model_dump_json()
            if fact_content.setdefault(fact.fact_id, content) != content:
                problems.append(
                    f"fact_id {fact.fact_id} has different content in different cases "
                    f"(seen again in {case.case_id})"
                )
        key = tuple(sorted((_fact_content(pair.fact_a), _fact_content(pair.fact_b))))
        pair_splits[key].add(split)  # type: ignore[index]

        if split == Split.TEST and not case.human_labeled:
            problems.append(f"{case.case_id}: test cases must be labeled by people, not the generator")
        if case.human_labeled and case.gold.guideline_version != GUIDELINE_VERSION:
            problems.append(
                f"{case.case_id}: labeled under guideline {case.gold.guideline_version}, "
                f"current is {GUIDELINE_VERSION}"
            )

    for key, splits in sorted(company_splits.items()):
        if len(splits) > 1:
            problems.append(f"company {company_names[key]!r} spans multiple splits: {sorted(splits)}")
    for family, splits in sorted(family_splits.items()):
        if len(splits) > 1:
            problems.append(f"document family {family} spans multiple splits: {sorted(splits)}")
    for fact_id, splits in sorted(fact_splits.items()):
        if len(splits) > 1:
            problems.append(f"fact {fact_id} appears in multiple splits: {sorted(splits)}")
    leaked_pairs = sum(1 for splits in pair_splits.values() if len(splits) > 1)
    if leaked_pairs:
        problems.append(f"{leaked_pairs} identical fact pair(s) appear in multiple splits")

    return problems


def load_dataset(path: str | Path, *, split: Split | None = None) -> list[EvalCase]:
    """Load, validate and optionally filter a dataset. Raises DatasetError on any problem."""
    cases = read_cases(path)
    problems = validate_cases(cases)
    if problems:
        shown = "\n  ".join(problems[:20])
        more = f"\n  ... and {len(problems) - 20} more" if len(problems) > 20 else ""
        raise DatasetError(f"{path} failed validation:\n  {shown}{more}")
    return [c for c in cases if split is None or c.gold.split == split]


def dataset_hash(cases: Iterable[EvalCase]) -> str:
    """Stable content hash, recorded with every evaluation run so results can be tied to data."""
    digest = hashlib.sha256()
    for case in sorted(cases, key=lambda c: c.case_id):
        digest.update(json.dumps(case.model_dump(mode="json"), sort_keys=True).encode())
        digest.update(b"\n")
    return digest.hexdigest()
