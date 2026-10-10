"""Command line: ``python -m opslm.datagen --scenarios 400 --seed 0 --out-dir data/synthetic/v1``."""

from __future__ import annotations

import argparse

from opslm.datagen.generate import generate, write_outputs


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="python -m opslm.datagen")
    p.add_argument("--scenarios", type=int, default=400, help="number of scenarios (one per synthetic company)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--fractions", type=float, nargs=3, default=(0.7, 0.1, 0.2),
                   metavar=("TRAIN", "VAL", "TEST"))
    args = p.parse_args(argv)

    result = generate(args.scenarios, seed=args.seed, fractions=tuple(args.fractions))
    paths = write_outputs(result, args.out_dir)
    m = result.manifest
    print(f"generator v{m['generator_version']}, guidelines v{m['guideline_version']}, seed {m['seed']}")
    for name, info in m["splits"].items():
        print(f"{name:<11} {info['scenarios']:>4} scenarios {info['pairs']:>5} pairs  {info['labels']}")
    print("pairs by kind:", m["pairs_by_kind"])
    for key, path in paths.items():
        print(f"wrote {key}: {path}")


if __name__ == "__main__":
    main()
