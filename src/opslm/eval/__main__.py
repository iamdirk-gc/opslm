"""Command line: ``python -m opslm.eval run|compare``."""

from __future__ import annotations

import argparse
from typing import Any

from opslm.baselines.rules import RulesBaseline
from opslm.data import load_dataset
from opslm.eval.harness import compare_runs, evaluate, format_summary, read_run, write_run
from opslm.schema import Split

PROVIDERS = ("anthropic", "openai-compatible", "vertex-gemini")


def _backend(args: argparse.Namespace) -> Any:
    from opslm.baselines import backends as b

    if args.provider == "anthropic":
        return b.AnthropicBackend(args.model, effort=args.effort)
    if args.provider == "openai-compatible":
        return b.OpenAICompatibleBackend(
            args.model, base_url=args.base_url, api_key_env=args.api_key_env,
            temperature=args.temperature, structured=args.structured,
            max_tokens_param=args.max_tokens_param,
        )
    return b.VertexGeminiBackend(
        args.model, project=args.project, location=args.location, temperature=args.temperature
    )


def _add_run_args(run: argparse.ArgumentParser) -> None:
    run.add_argument("--dataset", required=True, help="path to a JSONL dataset")
    run.add_argument("--system", required=True, choices=["rules", "llm"])
    run.add_argument("--split", choices=[s.value for s in Split], help="evaluate one split only")
    run.add_argument("--out", help="write the full result artifact to this JSON file")
    run.add_argument("--bootstrap", type=int, default=1000, help="bootstrap resamples")
    run.add_argument("--seed", type=int, default=0)
    g = run.add_argument_group("llm system")
    g.add_argument("--provider", choices=PROVIDERS)
    g.add_argument("--model", help="model id as the provider names it (required)")
    g.add_argument("--show-values", action="store_true",
                   help="show numeric values to the model (off by default)")
    g.add_argument("--price-in", type=float, help="USD per million input tokens")
    g.add_argument("--price-out", type=float, help="USD per million output tokens")
    g.add_argument("--estimate-only", action="store_true",
                   help="print a cost estimate and exit without calling any model")
    g.add_argument("--confirm-spend", action="store_true",
                   help="required to make model calls, which may cost money")
    g.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"],
                   help="anthropic: reasoning effort")
    g.add_argument("--base-url", help="openai-compatible: server URL, e.g. http://localhost:8000/v1")
    g.add_argument("--api-key-env", default="OPENAI_API_KEY",
                   help="openai-compatible: env var holding the API key")
    g.add_argument("--structured", default="json_schema", choices=["json_schema", "json_object", "none"],
                   help="openai-compatible: how JSON output is requested")
    g.add_argument("--max-tokens-param", default="max_tokens",
                   choices=["max_tokens", "max_completion_tokens"])
    g.add_argument("--temperature", type=float, default=0.0,
                   help="openai-compatible and vertex-gemini")
    g.add_argument("--project", help="vertex-gemini: Google Cloud project id")
    g.add_argument("--location", default="global", help="vertex-gemini: location")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m opslm.eval")
    sub = parser.add_subparsers(dest="command", required=True)
    _add_run_args(sub.add_parser("run", help="evaluate a system on a dataset"))
    cmp = sub.add_parser("compare", help="paired comparison of two result artifacts")
    cmp.add_argument("a")
    cmp.add_argument("b")

    args = parser.parse_args(argv)
    if args.command == "run":
        split = Split(args.split) if args.split else None
        cases = load_dataset(args.dataset, split=split)
        if args.system == "rules":
            predictor: Any = RulesBaseline()
        else:
            from opslm.baselines.llm import MODEL_PRICES, LLMPredictor, estimate_cost

            if not args.provider or not args.model:
                parser.error("--system llm requires --provider and --model")
            prices = (
                (args.price_in, args.price_out)
                if args.price_in is not None and args.price_out is not None
                else MODEL_PRICES.get(args.model)
            )
            est = estimate_cost([c.pair for c in cases], prices, show_values=args.show_values)
            lo, hi = est["output_tokens_assumed_per_pair"]
            cost = (
                f"${est['cost_usd_range'][0]:.2f}-${est['cost_usd_range'][1]:.2f}"
                if est["cost_usd_range"]
                else "cost unknown (no price on file; pass --price-in and --price-out)"
            )
            print(f"estimate: {est['pairs']} pairs, ~{est['input_tokens_approx']:,} input tokens, "
                  f"{cost}, assuming {lo}-{hi} output tokens per pair")
            if args.estimate_only:
                return
            if not args.confirm_spend:
                parser.error("this system makes model calls; re-run with --confirm-spend")
            predictor = LLMPredictor(_backend(args), show_values=args.show_values, prices=prices)
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
