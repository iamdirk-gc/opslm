"""Mine candidate fact pairs from a corpus of extracted facts (board tasks 3.2 and 3.4).

The input is what the extraction step produces: ``BusinessFact`` records, each with evidence
spans, plus ``SourceDocument`` metadata. The output is unlabeled ``CandidatePair`` records for the
labeling workflow, drawn so that the labeled set is informative rather than a random sample:

- **Blocking.** Only facts of the same company and the same metric family (or two families the
  metric page lists as related) are paired, so thousands of facts do not mean millions of pairs.
- **Strata.** Each pair falls in one stratum describing why it is interesting: a likely match,
  the hard negatives (different period, entity, accounting basis, or a related but different
  metric), pairs where a field or a definition is missing, and pairs where a fact's own
  evidence does not support its number. A sample takes a quota from each stratum, so the
  subtle negatives the benchmark needs are not drowned out by easy matches.
- **Diversity.** No company supplies more than a set share, and no fact appears in more than a few
  pairs.
- **Company-level splits.** Every pair of a company goes to the same split, assigned
  deterministically, so the dataset loader's leakage checks hold by construction.

Strata are assigned from what the extraction shows (labels, ids, periods, entities, bases,
definitions), never from gold labels, so mining works on real documents. A pair's stratum says why
it was picked, not what its label is: humans still decide that.
"""

from __future__ import annotations

import hashlib
import itertools
import json
import math
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from opslm.baselines.rules import entity_same, period_same
from opslm.data import company_key
from opslm.labeling import CandidatePair
from opslm.schema import (
    BusinessFact,
    ReconciliationInput,
    SourceDocument,
    Split,
)

MINER_VERSION = "1"

# --- strata ---------------------------------------------------------------------------------

UNSUPPORTED = "unsupported_claim"
COMPANY_DEFINED_DEFINITION = "company_defined_definition"
MISSING_SCOPE = "missing_scope"
OTHER_BASIS = "same_metric_other_basis"
OTHER_PERIOD = "same_metric_other_period"
OTHER_ENTITY = "same_metric_other_entity"
SAME_SCOPE = "same_metric_same_scope"
RELATED_METRIC = "related_metric"

# Order matters: a pair takes the first stratum it matches.
STRATA = (UNSUPPORTED, COMPANY_DEFINED_DEFINITION, MISSING_SCOPE, OTHER_BASIS, OTHER_PERIOD,
          OTHER_ENTITY, SAME_SCOPE, RELATED_METRIC)

DEFAULT_WEIGHTS: dict[str, float] = {
    SAME_SCOPE: 0.30,           # likely equivalents and conflicts
    OTHER_PERIOD: 0.10,
    OTHER_ENTITY: 0.07,
    OTHER_BASIS: 0.05,
    RELATED_METRIC: 0.20,       # different metrics that must never merge
    MISSING_SCOPE: 0.10,
    COMPANY_DEFINED_DEFINITION: 0.13,
    UNSUPPORTED: 0.05,
}

_COMPANY_DEFINED = frozenset({"arr", "adjusted_ebitda"})

# Metrics the metric page (docs/metric-set-v1.md) lists as related but different, by family: the
# metric id for the v1 metrics, the normalized label for anything else. A test keeps this in step
# with the page.
RELATED_FAMILIES: dict[str, frozenset[str]] = {
    "revenue": frozenset({
        "arr", "bookings", "billings", "gross revenue", "gross revenue before discounts",
        "segment revenue", "subscription revenue", "subscription revenue only", "net revenue",
        "pro forma revenue", "annualized revenue"}),
    "arr": frozenset({
        "revenue", "annualized revenue", "annualized or run rate revenue", "run rate revenue",
        "subscription revenue", "bookings", "rpo", "remaining performance obligations",
        "billings"}),
    "gross_margin": frozenset({
        "gross profit", "gross profit in dollars", "non gaap gross margin", "contribution margin",
        "operating margin", "subscription gross margin"}),
    "adjusted_ebitda": frozenset({
        "ebitda", "ebitda unadjusted", "operating income", "segment ebitda",
        "adjusted operating income", "ebitda margin", "adjusted ebitda margin"}),
    "net_income": frozenset({
        "adjusted net income", "income from continuing operations", "comprehensive income",
        "net income attributable to the company", "net income including noncontrolling interests"}),
}


# Words that mark a qualified variant of a v1 metric, as in "Core revenue" or "Constant currency
# revenue": such a fact is not on the metric page but is exactly the subtle negative worth labeling.
# Checked in this order, so "recurring revenue" is read as ARR before "revenue" as revenue.
QUALIFIED_KEYWORDS: dict[str, tuple[str, ...]] = {
    "arr": ("recurring revenue",),
    "revenue": ("revenue", "sales"),
    "gross_margin": ("gross margin",),
    "adjusted_ebitda": ("ebitda",),
    "net_income": ("net income", "net earnings", "net loss"),
}


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text.casefold()).split())


def family(fact: BusinessFact) -> str:
    """A fact's metric family: its metric id, or its normalized label when the id is 'other'."""
    return fact.metric_id if fact.metric_id != "other" else _norm(fact.metric_label)


def qualified_family(fact: BusinessFact) -> str | None:
    """The v1 metric a fact is a qualified variant of, judged from its label, or None. Only facts
    the extraction could not map to a v1 metric (metric_id 'other') qualify."""
    if fact.metric_id != "other":
        return None
    label = _norm(fact.metric_label)
    for metric, words in QUALIFIED_KEYWORDS.items():
        if any(re.search(rf"\b{w}\b", label) for w in words):
            return metric
    return None


def same_metric(a: BusinessFact, b: BusinessFact) -> bool:
    return family(a) == family(b)


def related_metric(a: BusinessFact, b: BusinessFact) -> bool:
    fa, fb = family(a), family(b)
    if fb in RELATED_FAMILIES.get(fa, ()) or fa in RELATED_FAMILIES.get(fb, ()):
        return True
    qa, qb = qualified_family(a), qualified_family(b)
    if qb and a.metric_id == qb or qa and b.metric_id == qa:
        return True  # one is a v1 metric, the other a qualified variant of it
    return bool(qa and qa == qb)  # two different qualified variants of the same metric


def supported(fact: BusinessFact) -> bool:
    """Whether the fact's printed number appears in its own evidence text. A False here means the
    extraction may have attached the wrong span or misread the number (an 'unsupported claim')."""
    printed = re.sub(r"[^0-9.,]", "", fact.quantity.raw_text).strip(".,")
    if not printed:
        return True  # nothing numeric to look for
    return any(printed in s.text.replace(" ", "") or printed in s.text for s in fact.evidence)


def classify(a: BusinessFact, b: BusinessFact) -> str | None:
    """The stratum for a pair of facts of one company, or None if the pair is not interesting."""
    if same_metric(a, b):
        if not (supported(a) and supported(b)):
            return UNSUPPORTED
        entity, period = entity_same(a, b), period_same(a.period, b.period)
        if (family(a) in _COMPANY_DEFINED and entity is not False and period is not False
                and not _definitions_match(a, b)):
            return COMPANY_DEFINED_DEFINITION
        if entity is None or period is None:
            return MISSING_SCOPE
        if a.accounting_basis != b.accounting_basis and "unknown" not in (
                a.accounting_basis, b.accounting_basis) and entity and period:
            return OTHER_BASIS
        if entity and not period:
            return OTHER_PERIOD
        if not entity:
            return OTHER_ENTITY
        return SAME_SCOPE
    if related_metric(a, b) and entity_same(a, b) is not False \
            and period_same(a.period, b.period) is not False:
        return RELATED_METRIC
    return None


def _definitions_match(a: BusinessFact, b: BusinessFact) -> bool:
    da, db = a.stated_definition, b.stated_definition
    return bool(da and db and _norm(da) == _norm(db))


# --- corpus ---------------------------------------------------------------------------------


@dataclass
class Corpus:
    facts: list[BusinessFact]
    documents: dict[str, SourceDocument]

    def company_of(self, fact: BusinessFact) -> str:
        keys = {company_key(self.documents[s.doc_id].company) for s in fact.evidence}
        if len(keys) != 1:
            raise CorpusError(f"fact {fact.fact_id} has evidence from {len(keys)} companies")
        return next(iter(keys))

    def doc_ids(self, fact: BusinessFact) -> set[str]:
        return {s.doc_id for s in fact.evidence}


class CorpusError(ValueError):
    """The facts and documents are inconsistent with each other."""


def build_corpus(facts: Iterable[BusinessFact], documents: Iterable[SourceDocument]) -> Corpus:
    facts, docs = list(facts), {}
    for d in documents:
        if d.doc_id in docs:
            raise CorpusError(f"duplicate doc_id {d.doc_id}")
        docs[d.doc_id] = d
    seen: set[str] = set()
    for f in facts:
        if f.fact_id in seen:
            raise CorpusError(f"duplicate fact_id {f.fact_id}")
        seen.add(f.fact_id)
        for s in f.evidence:
            if s.doc_id not in docs:
                raise CorpusError(f"fact {f.fact_id} cites span {s.span_id} of unknown document "
                                  f"{s.doc_id}")
    corpus = Corpus(facts, docs)
    for f in facts:
        corpus.company_of(f)  # raises if a fact spans companies
    return corpus


def load_corpus(facts_path: str | Path, documents_path: str | Path) -> Corpus:
    def lines(path: str | Path) -> list[str]:
        with open(path, encoding="utf-8") as fh:
            return [ln for ln in fh if ln.strip()]

    return build_corpus(
        (BusinessFact.model_validate_json(ln) for ln in lines(facts_path)),
        (SourceDocument.model_validate_json(ln) for ln in lines(documents_path)),
    )


def corpus_from_cases(cases: Iterable[Any]) -> Corpus:
    """The facts and documents inside labeled or candidate cases, deduplicated. Lets the miner be
    exercised on synthetic data and checked against the labels those cases carry."""
    facts: dict[str, BusinessFact] = {}
    docs: dict[str, SourceDocument] = {}
    for c in cases:
        inp = c.input
        for f in (inp.fact_a, inp.fact_b):
            facts.setdefault(f.fact_id, f)
        for d in inp.documents:
            docs.setdefault(d.doc_id, d)
    return build_corpus(facts.values(), docs.values())


# --- pairing --------------------------------------------------------------------------------


@dataclass(frozen=True)
class MinedPair:
    a: BusinessFact
    b: BusinessFact
    stratum: str
    company: str

    @property
    def key(self) -> str:
        ids = sorted((self.a.fact_id, self.b.fact_id))
        return f"{ids[0]}|{ids[1]}"


def _h(*parts: object) -> str:
    return hashlib.sha256(":".join(map(str, parts)).encode()).hexdigest()


def enumerate_pairs(corpus: Corpus, *, cross_document_only: bool = True) -> list[MinedPair]:
    """Every interesting pair, found by blocking on company and metric family."""
    by_company: dict[str, dict[str, list[BusinessFact]]] = defaultdict(lambda: defaultdict(list))
    for f in corpus.facts:
        by_company[corpus.company_of(f)][family(f)].append(f)

    pairs: list[MinedPair] = []
    for company, families in sorted(by_company.items()):
        blocks: list[Iterable[tuple[BusinessFact, BusinessFact]]] = []
        qualified: dict[str, list[BusinessFact]] = defaultdict(list)
        for facts in families.values():
            for f in facts:
                if (q := qualified_family(f)):
                    qualified[q].append(f)
        for fam, facts in families.items():
            blocks.append(itertools.combinations(facts, 2))
            for other in sorted(RELATED_FAMILIES.get(fam, ())):
                if other in families:  # a pair found from both sides is dropped by `seen` below
                    blocks.append(itertools.product(facts, families[other]))
            if fam in qualified:  # qualified variants of this v1 metric
                blocks.append(itertools.product(facts, qualified[fam]))
        for variants in qualified.values():
            blocks.append(itertools.combinations(variants, 2))
        seen: set[str] = set()
        for a, b in itertools.chain.from_iterable(blocks):
            if cross_document_only and corpus.doc_ids(a) & corpus.doc_ids(b):
                continue
            pair_key = "|".join(sorted((a.fact_id, b.fact_id)))
            if pair_key in seen:
                continue
            seen.add(pair_key)
            stratum = classify(a, b)
            if stratum:
                pairs.append(MinedPair(a, b, stratum, company))
    return pairs


# --- sampling -------------------------------------------------------------------------------


@dataclass
class MiningConfig:
    target: int = 200
    seed: int = 0
    fractions: tuple[float, float, float] = (0.5, 0.1, 0.4)  # train, validation, test (by company)
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    max_company_share: float = 0.25
    max_fact_reuse: int = 3
    cross_document_only: bool = True
    source: str = "real"


def assign_splits(companies: Sequence[str], fractions: Sequence[float], seed: int) -> dict[str, Split]:
    """Give each company one split, deterministically. Every split with a non-zero fraction gets at
    least one company when there are enough companies."""
    if len(fractions) != 3 or abs(sum(fractions) - 1.0) > 1e-9:
        raise ValueError("fractions must be three numbers that sum to 1")
    order = sorted(set(companies), key=lambda c: _h(seed, c))
    n = len(order)
    splits = [Split.TRAIN, Split.VALIDATION, Split.TEST]
    counts = [round(n * f) for f in fractions]
    for i, f in enumerate(fractions):  # guarantee a non-empty split where one is requested
        if f > 0 and counts[i] == 0 and n >= sum(1 for x in fractions if x > 0):
            counts[i] = 1
    while sum(counts) > n:
        counts[counts.index(max(counts))] -= 1
    while sum(counts) < n:
        counts[fractions.index(max(fractions))] += 1
    out: dict[str, Split] = {}
    start = 0
    for split, count in zip(splits, counts, strict=True):
        for company in order[start:start + count]:
            out[company] = split
        start += count
    return out


def select_pairs(pairs: Sequence[MinedPair], config: MiningConfig) -> tuple[list[MinedPair], dict[str, Any]]:
    """Take a quota from each stratum, subject to the company-share and fact-reuse limits."""
    total_w = sum(config.weights.values())
    quotas = {s: round(config.target * w / total_w) for s, w in config.weights.items()}
    pool: dict[str, list[MinedPair]] = defaultdict(list)
    for p in pairs:
        pool[p.stratum].append(p)
    for s, members in pool.items():
        members.sort(key=lambda p: _h(config.seed, s, p.key))

    companies = {p.company for p in pairs}
    cap = max(math.ceil(config.target * config.max_company_share),
              math.ceil(config.target / max(1, len(companies))))
    chosen: list[MinedPair] = []
    per_company: dict[str, int] = defaultdict(int)
    reuse: dict[str, int] = defaultdict(int)
    taken: dict[str, int] = defaultdict(int)

    def take(p: MinedPair) -> bool:
        if per_company[p.company] >= cap:
            return False
        if reuse[p.a.fact_id] >= config.max_fact_reuse or reuse[p.b.fact_id] >= config.max_fact_reuse:
            return False
        chosen.append(p)
        per_company[p.company] += 1
        reuse[p.a.fact_id] += 1
        reuse[p.b.fact_id] += 1
        taken[p.stratum] += 1
        return True

    cursor: dict[str, int] = defaultdict(int)

    def fill(stratum: str, limit: int) -> None:
        while taken[stratum] < limit and len(chosen) < config.target and cursor[stratum] < len(pool[stratum]):
            p = pool[stratum][cursor[stratum]]
            cursor[stratum] += 1
            take(p)

    for s in config.weights:
        fill(s, quotas[s])
    # strata that could not fill their quota hand the remainder to the others, heaviest first
    for s in sorted(config.weights, key=config.weights.get, reverse=True):
        fill(s, config.target)
    stats = {
        s: {"weight": config.weights[s], "quota": quotas[s], "available": len(pool.get(s, [])),
            "selected": taken[s], "shortfall": max(0, quotas[s] - taken[s])}
        for s in config.weights
    }
    return chosen, stats


# --- candidates -----------------------------------------------------------------------------


def to_candidate(pair: MinedPair, corpus: Corpus, split: Split, config: MiningConfig) -> CandidatePair:
    a, b = pair.a, pair.b
    if int(_h(config.seed, "order", pair.key), 16) % 2:  # so position does not carry information
        a, b = b, a
    doc_ids = sorted(corpus.doc_ids(a) | corpus.doc_ids(b))
    slug = pair.company.replace(" ", "-") or "company"
    case_id = f"{slug}-{_h('case', pair.key)[:10]}"
    return CandidatePair(
        input=ReconciliationInput(
            case_id=case_id, fact_a=a, fact_b=b,
            documents=[corpus.documents[d] for d in doc_ids]),
        source=config.source, split=split, tags=("mined", pair.stratum),
    )


@dataclass
class MiningResult:
    candidates: list[CandidatePair]
    report: dict[str, Any]


def mine(corpus: Corpus, config: MiningConfig | None = None) -> MiningResult:
    config = config or MiningConfig()
    unknown = set(config.weights) - set(STRATA)
    if unknown:
        raise ValueError(f"unknown strata: {sorted(unknown)}")
    pairs = enumerate_pairs(corpus, cross_document_only=config.cross_document_only)
    chosen, stats = select_pairs(pairs, config)
    companies = sorted({corpus.company_of(f) for f in corpus.facts})
    splits = assign_splits(companies, config.fractions, config.seed)
    candidates = [to_candidate(p, corpus, splits[p.company], config) for p in chosen]
    report = {
        "miner_version": MINER_VERSION,
        "config": {
            "target": config.target, "seed": config.seed, "fractions": list(config.fractions),
            "max_company_share": config.max_company_share, "max_fact_reuse": config.max_fact_reuse,
            "cross_document_only": config.cross_document_only, "source": config.source,
        },
        "corpus": {"facts": len(corpus.facts), "documents": len(corpus.documents),
                   "companies": len(companies)},
        "pairs_available": len(pairs),
        "selected": len(candidates),
        "shortfall": max(0, config.target - len(candidates)),
        "strata": stats,
        "per_company": {c: sum(1 for p in chosen if p.company == c) for c in companies},
        "per_split": {
            s.value: {"companies": sorted(c for c, sp in splits.items() if sp == s),
                      "pairs": sum(1 for x in candidates if x.split == s)}
            for s in (Split.TRAIN, Split.VALIDATION, Split.TEST)
        },
        "unsupported_facts": sorted(f.fact_id for f in corpus.facts if not supported(f)),
    }
    return MiningResult(candidates, report)


def write_report(path: str | Path, report: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
