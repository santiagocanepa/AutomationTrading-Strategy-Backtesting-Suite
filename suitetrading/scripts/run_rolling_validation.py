#!/usr/bin/env python3
"""Rolling portfolio validation across multiple time windows.

Loads evidence cards from discovery runs, backtests each strategy across
rolling windows, combines into portfolio, and validates that the portfolio
is profitable across diverse market regimes.

Usage
-----
python scripts/run_rolling_validation.py \
    --evidence-dir artifacts/discovery/phase5_fold_consistency/evidence/ \
    --evidence-dir artifacts/discovery/phase5_shorts_holdout/evidence/ \
    --months 84 --holdout-months 6

python scripts/run_rolling_validation.py \
    --evidence-dir artifacts/discovery/phase5_fold_consistency/evidence/ \
    --window-months 6 --slide-months 2 \
    --weight-methods equal risk_parity regime_adaptive \
    --top-n 5 --max-pbo 0.20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.optimization.rolling_validation import (
    RollingPortfolioEvaluator,
    StrategySpec,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Rolling portfolio validation")
    p.add_argument(
        "--evidence-dir", action="append", required=True,
        help="Directory containing evidence card JSONs (can repeat)",
    )
    p.add_argument("--months", type=int, default=84, help="Total data months")
    p.add_argument("--holdout-months", type=int, default=6, help="Last N months as OOS")
    p.add_argument("--window-months", type=int, default=6, help="Window size in months")
    p.add_argument("--slide-months", type=int, default=2, help="Slide step in months")
    p.add_argument(
        "--weight-methods", nargs="+",
        default=["equal", "risk_parity", "regime_adaptive"],
    )
    p.add_argument("--initial-capital", type=float, default=100_000.0)
    p.add_argument("--commission-pct", type=float, default=0.04)
    p.add_argument("--mode", default="fsm", choices=["fsm", "simple", "auto"])
    p.add_argument("--top-n", type=int, default=0, help="Limit to top-N per direction (0=all)")
    p.add_argument("--max-pbo", type=float, default=1.0, help="Filter by max PBO")
    p.add_argument("--data-dir", default="data/raw", help="Parquet data directory")
    p.add_argument("--exchange", default="binance")
    p.add_argument(
        "--output-dir", default="artifacts/rolling_validation",
        help="Output directory",
    )
    p.add_argument("--run-stress", action="store_true", help="Run stress tests too")
    p.add_argument("--asset-class", default="crypto", choices=["crypto", "stocks"])
    return p.parse_args()


def load_specs(evidence_dirs: list[str], max_pbo: float, top_n: int) -> list[StrategySpec]:
    """Load and filter evidence cards from directories."""
    specs: list[StrategySpec] = []
    for d in evidence_dirs:
        edir = Path(d)
        if not edir.is_dir():
            # Try relative to ROOT
            edir = ROOT / d
        if not edir.is_dir():
            logger.warning("Evidence dir not found: {}", d)
            continue
        for f in sorted(edir.glob("finalist_*.json")):
            try:
                spec = StrategySpec.from_evidence_card(f)
                if spec.pbo <= max_pbo:
                    specs.append(spec)
            except Exception:
                logger.exception("Failed to parse {}", f)

    # Deduplicate: keep best PBO per unique (symbol, TF, archetype, direction)
    best_per_study: dict[tuple, StrategySpec] = {}
    for s in specs:
        key = (s.symbol, s.timeframe, s.archetype, s.direction)
        if key not in best_per_study or s.pbo < best_per_study[key].pbo:
            best_per_study[key] = s
    specs = list(best_per_study.values())

    if top_n > 0:
        longs = sorted([s for s in specs if s.direction == "long"], key=lambda s: s.pbo)[:top_n]
        shorts = sorted([s for s in specs if s.direction == "short"], key=lambda s: s.pbo)[:top_n]
        specs = longs + shorts

    logger.info(
        "Loaded {} specs ({} long, {} short)",
        len(specs),
        sum(1 for s in specs if s.direction == "long"),
        sum(1 for s in specs if s.direction == "short"),
    )
    return specs


def load_ohlcv_cache(
    specs: list[StrategySpec],
    exchange: str,
    data_dir: str,
) -> dict[str, pd.DataFrame]:
    """Load OHLCV data for each unique (symbol, timeframe) pair.

    Data is stored at 1m resolution; higher TFs are resampled on the fly.
    """
    store = ParquetStore(base_dir=Path(data_dir))
    resampler = OHLCVResampler()
    cache: dict[str, pd.DataFrame] = {}
    raw_cache: dict[str, pd.DataFrame] = {}  # symbol → 1m data
    seen: set[str] = set()

    for spec in specs:
        key = f"{spec.symbol}_{spec.timeframe}"
        if key in seen:
            continue
        seen.add(key)

        # Load 1m base data (cached per symbol)
        if spec.symbol not in raw_cache:
            try:
                raw = store.read(exchange, spec.symbol, "1m")
            except FileNotFoundError:
                logger.warning("No 1m data for {}/{}", exchange, spec.symbol)
                continue
            if raw.empty:
                logger.warning("Empty 1m data for {}/{}", exchange, spec.symbol)
                continue
            raw_cache[spec.symbol] = raw
            logger.info("Loaded {} 1m bars for {}", len(raw), spec.symbol)

        raw_1m = raw_cache[spec.symbol]

        # Resample to target TF
        if spec.timeframe == "1m":
            ohlcv = raw_1m
        else:
            ohlcv = resampler.resample(raw_1m, spec.timeframe, base_tf="1m")
            logger.info("Resampled {} → {} bars for {}", spec.timeframe, len(ohlcv), key)

        cache[key] = ohlcv

    return cache


def main() -> None:
    args = parse_args()

    specs = load_specs(args.evidence_dir, args.max_pbo, args.top_n)
    if not specs:
        logger.error("No specs loaded, exiting")
        sys.exit(1)

    ohlcv_cache = load_ohlcv_cache(specs, args.exchange, args.data_dir)
    if not ohlcv_cache:
        logger.error("No OHLCV data loaded, exiting")
        sys.exit(1)

    # Trim data to --months window from the end
    all_ends = [df.index.max() for df in ohlcv_cache.values()]
    global_end = max(all_ends)
    if args.months > 0:
        data_start = global_end - pd.DateOffset(months=args.months)
        for key in ohlcv_cache:
            ohlcv_cache[key] = ohlcv_cache[key].loc[data_start:]
        logger.info("Trimmed data to last {} months (from {})", args.months, data_start)

    holdout_start = global_end - pd.DateOffset(months=args.holdout_months)

    evaluator = RollingPortfolioEvaluator(
        window_months=args.window_months,
        slide_months=args.slide_months,
        weight_methods=tuple(args.weight_methods),
        initial_capital=args.initial_capital,
        commission_pct=args.commission_pct,
        mode=args.mode,
        holdout_start=holdout_start,
        asset_class=args.asset_class,
    )

    result = evaluator.evaluate(specs, ohlcv_cache)

    output_dir = ROOT / args.output_dir
    evaluator.save_results(result, output_dir)
    RollingPortfolioEvaluator.print_report(result)

    if args.run_stress and result.validation_pass:
        logger.info("Running stress tests on best method...")
        _run_stress(result, specs, ohlcv_cache, evaluator, output_dir)


def _run_stress(result, specs, ohlcv_cache, evaluator, output_dir):
    """Run PortfolioValidator + StressTester on the combined returns."""
    from suitetrading.risk.portfolio_validation import PortfolioValidator
    from suitetrading.risk.stress_testing import PortfolioStressTester

    # TODO: extract combined daily returns from windows for full-period stress test
    logger.info("Stress testing not yet integrated — run separately with run_stress_tests.py")


if __name__ == "__main__":
    main()
