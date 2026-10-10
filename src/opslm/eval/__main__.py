"""Command line: ``python -m opslm.eval run|compare``."""

from __future__ import annotations

import argparse

from opslm.baselines.rules import RulesBaseline
from opslm.data import load_dataset
from opslm.eval.harness import compare_runs, evaluate, format_summary, read_run, write_run
from opslm.schema import Split

SYSTEMS = ("rules", "claude")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m opslm.eval")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="evaluate a system on a dataset")
    run.add_argument("--dataset", required=True, help="path to a JSONL dataset")
    run.add_argument("--system", required=True, choices=SYSTEMS)
    run.add_argument("--split", choices=[s.value for s in Split], help="evaluate one split only")
    run.add_argument("--out", help="write the full result artifact to this JSON file")
    run.add_argument("--bootstrap", type=int, default=1000, help="bootstrap resamples")
    run.add_argument("--seed", type=int, default=0)
    run.add_argument("--model", default="claude-opus-5-5", help="claude system: model id")
    run.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"],
                     help="claude system: reasoning effort")
    run.add_argument("--show-values", action="store_true",
                     help="claude system: show numeric values to the model (off by default)")
    run.add_argument("--estimate-only", action="store_true",
                     help="claude system: print a cost estimate and exit without calling the API")
    run.add_argument("--confirm-spend", action="store_true",
                     help="claude system: required to make paid API calls")

    cmp = sub.add_parser("compare", help="paired comparison of two result artifacts")
    cmp.add_argument("a")
    cmp.add_argument("b")

    args = parser.parse_args(argv)
    if args.command == "run":
        split = Split(args.split) if args.split else None
        cases = load_dataset(args.dataset, split=split)
        if args.system == "rules":
            predictor = RulesBaseline()
        else:
            from opslm.baselines.llm import ClaudePredictor, estimate_cost

            est = estimate_cost([c.pair for c in cases], args.model, show_values=args.show_values)
            print(f"estimate ({est['pairs']} pairs, {est['model']}, prices as of "
                  f"{est['pricing_snapshot']}): ~{est['input_tokens_approx']:,} input tokens, "
                  f"${est['cost_usd_range'][0]:.2f}-${est['cost_usd_range'][1]:.2f} "
                  f"assuming {est['output_tokens_assumed'][0]}-{est['output_tokens_assumed'][1]} "
                  "output tokens per pair")
            if args.estimate_only:
                return
            if not args.confirm_spend:
                parser.error("this system makes paid API calls; re-run with --confirm-spend")
            predictor = ClaudePredictor(args.model, effort=args.effort, show_values=args.show_values)
        result = evaluate(predictor, cases, bootstrap_n=args.bootstrap, seed=args.seed)
        if hasattr(predictor, "describe"):
            result.config.update(predictor.describe())
        print(format_summary(result))
        if args.out:
            write_run(args.out, result)
            print(f"\nwrote {args.out}")
    else:
        c = compare_runs(read_run(args.a), read_run(args.b))
        print(f"{c.system_a} vs {c.system_b} on {c.n} cases")
        print(f"accuracy: {c.accuracy_a:.3f} vs {c.accuracy_b:.3f}")
        print(f"only {c.system_a} correct: {c.only_a_correct}; only {c.system_b} correct: {c.only_b_correct}")
        print(f"McNemar exact p-value: {c.p_value:.4f}")


if __name__ == "__main__":
    main()
