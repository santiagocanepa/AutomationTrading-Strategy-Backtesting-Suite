#!/usr/bin/env python3
"""Null Hypothesis Permutation Test — CLI runner.

Validates pipeline methodology by running the full discovery pipeline
(Optuna → WFO → CSCV/PBO) on data with permuted returns, destroying
all temporal signal.  Measures false positive rate.

Usage
-----
# Quick smoke test (2 seeds, 50 trials)
python scripts/run_null_hypothesis.py \
    --symbols BTCUSDT --timeframes 1h --seeds 100 101 --trials 50

# Full run (default: 800 studies, ~30-45 min)
python scripts/run_null_hypothesis.py

# Custom configuration
python scripts/run_null_hypothesis.py \
    --symbols BTCUSDT SOLUSDT SPY GLD \
    --timeframes 4h 1h \
    --archetypes roc_fullrisk_pyr ema_fullrisk_pyr macd_fullrisk_pyr \
    --seeds 100 101 102 103 104 \
    --trials 200 --max-workers 8
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.optimization.null_hypothesis import NullHypothesisTest


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Null hypothesis permutation test for the discovery pipeline",
    )
    p.add_argument(
        "--symbols", nargs="+",
        default=["BTCUSDT", "SOLUSDT", "SPY", "GLD"],
        help="Symbols to test (2 crypto + 2 stock by default)",
    )
    p.add_argument(
        "--timeframes", nargs="+",
        default=["4h", "1h"],
    )
    p.add_argument(
        "--archetypes", nargs="+",
        default=[
            "roc_fullrisk_pyr",
            "ema_fullrisk_pyr",
            "macd_fullrisk_pyr",
            "roc_adx_fullrisk_pyr",
            "donchian_fullrisk_pyr",
        ],
    )
    p.add_argument(
        "--directions", nargs="+",
        default=["long", "short"],
        choices=["long", "short"],
    )
    p.add_argument(
        "--seeds", nargs="+", type=int,
        default=list(range(100, 110)),
        help="RNG seeds for permutations (default: 100..109 = 10 seeds)",
    )
    p.add_argument("--trials", type=int, default=200,
                   help="Optuna trials per study")
    p.add_argument("--top-n", type=int, default=50,
                   help="Top N trials to extract per study for WFO")
    p.add_argument("--months", type=int, default=12,
                   help="Months of data to use")
    p.add_argument("--max-workers", type=int, default=8,
                   help="ProcessPoolExecutor workers (leave 2 cores free)")
    p.add_argument("--pbo-threshold", type=float, default=0.20,
                   help="PBO threshold for a study to 'pass'")
    p.add_argument("--real-hit-rate", type=float, default=0.126,
                   help="Observed hit rate from real discovery")
    p.add_argument("--real-total", type=int, default=2619,
                   help="Total studies in real discovery run")
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--output-dir",
                   default=str(ROOT / "artifacts" / "null_hypothesis"))
    return p.parse_args()


def main() -> None:
    args = parse_args()

    total = (
        len(args.symbols)
        * len(args.timeframes)
        * len(args.archetypes)
        * len(args.directions)
        * len(args.seeds)
    )
    logger.info("Starting null hypothesis test: {} total studies", total)

    test = NullHypothesisTest(
        symbols=args.symbols,
        timeframes=args.timeframes,
        archetypes=args.archetypes,
        directions=args.directions,
        seeds=args.seeds,
        n_trials=args.trials,
        top_n=args.top_n,
        months=args.months,
        pbo_threshold=args.pbo_threshold,
        real_hit_rate=args.real_hit_rate,
        real_total=args.real_total,
        max_workers=args.max_workers,
        data_dir=Path(args.data_dir),
    )

    result = test.run()
    test.print_report(result)

    output_dir = Path(args.output_dir)
    path = test.save_results(result, output_dir)
    logger.info("Done. Results at {}", path)


if __name__ == "__main__":
    main()
