"""Command line: ``python -m opslm.mining_cli`` mines candidate pairs for the labeling workflow."""

from __future__ import annotations

import argparse
import json
import sys

from opslm.labeling import write_candidates
from opslm.mining import (
    DEFAULT_WEIGHTS,
    MiningConfig,
    corpus_from_cases,
    load_corpus,
    mine,
    write_report,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m opslm.mining_cli",
                                description="Mine candidate fact pairs from extracted facts.")
    src = p.add_argument_group("input (one of)")
    src.add_argument("--facts", help="JSONL of BusinessFact records (the extraction output)")
    src.add_argument("--documents", help="JSONL of SourceDocument records for those facts")
    src.add_argument("--synthetic", type=int, metavar="N",
                     help="instead, mine a corpus built from N synthetic scenarios (a dry run)")
    p.add_argument("--out", required=True, help="candidates JSONL to write")
    p.add_argument("--report", help="mining report JSON to write")
    p.add_argument("--target", type=int, default=200, help="candidate pairs to select")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--fractions", type=float, nargs=3, default=(0.5, 0.1, 0.4),
                   metavar=("TRAIN", "VAL", "TEST"), help="share of companies per split")
    p.add_argument("--max-company-share", type=float, default=0.25)
    p.add_argument("--max-fact-reuse", type=int, default=3)
    p.add_argument("--allow-same-document", action="store_true",
                   help="also pair facts that share a source document (default: cross-document only)")
    p.add_argument("--source", choices=["real", "synthetic"], default=None,
                   help="provenance recorded on the candidates (default: real, or synthetic with --synthetic)")
    p.add_argument("--weight", action="append", default=[], metavar="STRATUM=W",
                   help=f"override a stratum weight; strata: {', '.join(DEFAULT_WEIGHTS)}")
    args = p.parse_args(argv)

    if args.synthetic:
        from opslm.datagen.generate import generate

        run = generate(args.synthetic, seed=args.seed)
        corpus = corpus_from_cases(run.train + run.validation + run.test_construction)
    elif args.facts and args.documents:
        corpus = load_corpus(args.facts, args.documents)
    else:
        p.error("give --facts and --documents, or --synthetic N")

    weights = dict(DEFAULT_WEIGHTS)
    for item in args.weight:
        name, _, value = item.partition("=")
        if name not in weights:
            p.error(f"unknown stratum {name!r}")
        weights[name] = float(value)
    config = MiningConfig(
        target=args.target, seed=args.seed, fractions=tuple(args.fractions), weights=weights,
        max_company_share=args.max_company_share, max_fact_reuse=args.max_fact_reuse,
        cross_document_only=not args.allow_same_document,
        source=args.source or ("synthetic" if args.synthetic else "real"),
    )
    result = mine(corpus, config)
    write_candidates(args.out, result.candidates)
    if args.report:
        write_report(args.report, result.report)

    r = result.report
    print(f"corpus: {r['corpus']['facts']} facts, {r['corpus']['documents']} documents, "
          f"{r['corpus']['companies']} companies; {r['pairs_available']} interesting pairs found")
    print(f"selected {r['selected']} of {config.target}" + (f" ({r['shortfall']} short)" if r["shortfall"] else ""))
    for name, s in r["strata"].items():
        print(f"  {name:28} quota {s['quota']:>4}  available {s['available']:>5}  selected {s['selected']:>4}")
    print("per split:", json.dumps({k: v["pairs"] for k, v in r["per_split"].items()}))
    if r["unsupported_facts"]:
        print(f"{len(r['unsupported_facts'])} fact(s) whose evidence does not contain their number "
              "(see the report)")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
