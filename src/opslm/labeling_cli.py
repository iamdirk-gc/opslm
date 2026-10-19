"""Command line for the labeling workflow: ``python -m opslm.labeling_cli <command>``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from opslm import labeling as L
from opslm.data import write_cases


def _report(problems: list[str], unlabeled: list[str]) -> None:
    for p in problems:
        print(f"  problem: {p}")
    if unlabeled:
        print(f"  {len(unlabeled)} row(s) left blank")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m opslm.labeling_cli")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plan", help="split candidates between reviewers and write their sheets")
    p.add_argument("--candidates", required=True)
    p.add_argument("--reviewers", nargs="+", required=True)
    p.add_argument("--overlap", type=int, default=30, help="cases both reviewers label")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--format", choices=["xlsx", "csv"], default="xlsx")

    p = sub.add_parser("import", help="validate a filled-in review sheet")
    p.add_argument("--candidates", required=True)
    p.add_argument("--sheet", required=True)
    p.add_argument("--reviewer", required=True)
    p.add_argument("--out", required=True, help="reviews JSONL to write")

    p = sub.add_parser("agreement", help="agreement on the overlap and an adjudication sheet")
    p.add_argument("--candidates", required=True)
    p.add_argument("--a", required=True, help="reviews JSONL from reviewer 1")
    p.add_argument("--b", required=True, help="reviews JSONL from reviewer 2")
    p.add_argument("--out", required=True, help="adjudication sheet (.xlsx or .csv)")

    p = sub.add_parser("resolutions", help="validate the filled-in adjudication sheet")
    p.add_argument("--candidates", required=True)
    p.add_argument("--sheet", required=True)
    p.add_argument("--out", required=True, help="resolutions JSONL to write")

    p = sub.add_parser("finalize", help="build the evaluation dataset from reviews")
    p.add_argument("--candidates", required=True)
    p.add_argument("--reviews", nargs="+", required=True, help="reviews JSONL, one per reviewer")
    p.add_argument("--resolutions", help="resolutions JSONL")
    p.add_argument("--out", required=True, help="dataset JSONL to write")

    args = parser.parse_args(argv)
    candidates = L.read_candidates(args.candidates)

    if args.command == "plan":
        plan = L.plan_batches(candidates, args.reviewers, overlap=args.overlap, seed=args.seed)
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        by_id = {c.case_id: c for c in candidates}
        for reviewer, ids in plan.items():
            path = out / f"sheet_{reviewer}.{args.format}"
            L.export_review_sheet(path, [by_id[i] for i in ids])
            print(f"{reviewer}: {len(ids)} cases -> {path}")
        (out / "plan.json").write_text(json.dumps(plan, indent=2) + "\n")
        shared = set.intersection(*(set(v) for v in plan.values()))
        print(f"{len(shared)} cases are shared by all reviewers (plan saved to plan.json)")
        return 0

    if args.command == "import":
        result = L.import_review_sheet(L.read_sheet(args.sheet), candidates, args.reviewer)
        L.write_reviews(args.out, result.reviews)
        print(f"{len(result.reviews)} valid review(s) written to {args.out}")
        _report(result.problems, result.unlabeled)
        return 1 if result.problems else 0

    if args.command == "agreement":
        a, b = L.read_reviews(args.a), L.read_reviews(args.b)
        ag = L.compare_reviews(a, b, candidates)
        fmt = lambda v: "n/a" if v is None else f"{v:.2f}"
        print(f"shared cases: {ag.n}")
        print(f"label:   agreement {ag.label_agreement:.0%}, kappa {fmt(ag.label_kappa)}")
        print(f"concept: agreement {ag.concept_agreement:.0%}, kappa {fmt(ag.concept_kappa)}")
        print(f"scope:   agreement {ag.scope_agreement:.0%}, kappa {fmt(ag.scope_kappa)}")
        print(f"{len(ag.disagreements)} disagreement(s), {len(ag.reason_differs)} differing in primary "
              f"reason only, {len(ag.flagged)} flagged")
        print(f"{len(ag.evidence_differs)} case(s) where only the cited evidence differs (finalize "
              "will take the union and note it)")
        L.export_disagreement_sheet(args.out, a, b, candidates, ag)
        print(f"adjudication sheet written to {args.out}")
        return 0

    if args.command == "resolutions":
        result = L.import_resolutions(L.read_sheet(args.sheet), candidates)
        L.write_reviews(args.out, result.reviews)
        print(f"{len(result.reviews)} resolution(s) written to {args.out}")
        _report(result.problems, result.unlabeled)
        return 1 if result.problems else 0

    sets = [L.read_reviews(p) for p in args.reviews]
    res = L.read_reviews(args.resolutions) if args.resolutions else []
    final = L.finalize(candidates, sets, res)
    print(f"{len(final.cases)} case(s) finalized, {len(final.unlabeled)} not yet reviewed")
    if final.evidence_unioned:
        print(f"  {len(final.evidence_unioned)} case(s) had different cited evidence; the union was "
              "taken and noted in adjudication_note: " + ", ".join(final.evidence_unioned))
    _report(final.problems, [])
    if final.problems:
        return 1
    write_cases(args.out, final.cases)
    print(f"dataset written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
