#!/usr/bin/env python3
"""Replay finalists to generate equity curves for portfolio analysis.

Reads finalist evidence cards, re-runs each backtest, and saves
equity curves alongside the original metadata.

Usage
-----
python scripts/replay_finalists.py \
    --evidence-dirs artifacts/discovery/*/evidence \
    --output-dir artifacts/portfolio_candidates \
    --months 24
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.backtesting._internal.datasets import build_dataset_from_df
from suitetrading.backtesting.engine import BacktestEngine
from suitetrading.backtesting.metrics import MetricsEngine
from suitetrading.config.archetypes import get_all_indicators, get_auxiliary_indicators
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.optimization._internal.objective import BacktestObjective
from suitetrading.risk.archetypes import get_archetype


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay finalists to generate equity curves")
    p.add_argument("--evidence-dirs", nargs="+",
                   default=[str(d) for d in sorted(ROOT.glob("artifacts/discovery/*/evidence"))])
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "portfolio_candidates"))
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--exchange", default="binance")
    p.add_argument("--months", type=int, default=24)
    p.add_argument("--mode", default="fsm")
    p.add_argument("--commission", type=float, default=0.04)
    return p.parse_args()


def load_ohlcv(exchange: str, symbol: str, timeframe: str,
               months: int, data_dir: Path) -> pd.DataFrame:
    store = ParquetStore(base_dir=data_dir)
    df_1m = store.read(exchange, symbol, "1m")
    cutoff = df_1m.index.max() - pd.DateOffset(months=months)
    df_1m = df_1m.loc[df_1m.index >= cutoff]
    if timeframe == "1m":
        return df_1m
    resampler = OHLCVResampler()
    return resampler.resample(df_1m, timeframe, base_tf="1m")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect all finalist files
    finalist_files: list[Path] = []
    for ed in args.evidence_dirs:
        ed_path = Path(ed)
        if ed_path.is_dir():
            finalist_files.extend(sorted(ed_path.glob("finalist_*.json")))

    logger.info("Found {} finalist evidence cards", len(finalist_files))

    # Group by symbol+timeframe to avoid reloading data
    by_data: dict[str, list[tuple[Path, dict]]] = {}
    for f in finalist_files:
        with open(f) as fp:
            data = json.load(fp)
        key = f"{data.get('symbol', 'BTCUSDT')}_{data.get('timeframe', '1h')}"
        by_data.setdefault(key, []).append((f, data))

    engine = BacktestEngine()
    metrics_engine = MetricsEngine()
    ohlcv_cache: dict[str, pd.DataFrame] = {}
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for data_key, entries in by_data.items():
        symbol, tf = data_key.rsplit("_", 1)
        cache_key = f"{symbol}_{tf}"

        if cache_key not in ohlcv_cache:
            try:
                ohlcv_cache[cache_key] = load_ohlcv(
                    args.exchange, symbol, tf, args.months, Path(args.data_dir),
                )
                logger.info("{} @ {}: {} bars loaded", symbol, tf, len(ohlcv_cache[cache_key]))
            except Exception as e:
                logger.error("Failed to load {}: {}", cache_key, e)
                errors.append(f"Data load error for {cache_key}: {e}")
                continue

        ohlcv = ohlcv_cache[cache_key]
        dataset = build_dataset_from_df(
            ohlcv, exchange=args.exchange, symbol=symbol, base_timeframe=tf,
        )

        for filepath, finalist in entries:
            archetype = finalist.get("archetype", "roc_fullrisk_pyr")
            direction = finalist.get("direction", "long")
            indicator_params = finalist.get("indicator_params", {})
            risk_overrides_flat = finalist.get("risk_overrides", {})
            candidate_id = finalist.get("candidate_id", filepath.stem)

            try:
                # Build objective for signal construction
                all_indicators = list(indicator_params.keys())
                auxiliary = get_auxiliary_indicators(archetype)

                objective = BacktestObjective(
                    dataset=dataset,
                    indicator_names=all_indicators,
                    auxiliary_indicators=auxiliary,
                    archetype=archetype,
                    direction=direction,
                    metric="sharpe",
                    mode=args.mode,
                    commission_pct=args.commission,
                )

                result = objective.run_single({
                    **{f"{ind}__{p}": v
                       for ind, params in indicator_params.items()
                       for p, v in params.items()},
                    **risk_overrides_flat,
                })

                equity_curve = result["equity_curve"]
                metrics = result["metrics"]

                # Save enriched evidence card
                enriched = dict(finalist)
                enriched["equity_curve"] = (
                    equity_curve.tolist() if isinstance(equity_curve, np.ndarray)
                    else list(equity_curve)
                )
                enriched["replay_metrics"] = metrics
                enriched["replay_bars"] = len(equity_curve)

                out_path = output_dir / f"{candidate_id}_{symbol}_{tf}_{archetype}_{direction}.json"
                with open(out_path, "w") as fp:
                    json.dump(enriched, fp, indent=2, default=str)

                results.append({
                    "candidate_id": candidate_id,
                    "symbol": symbol,
                    "timeframe": tf,
                    "archetype": archetype,
                    "direction": direction,
                    "sharpe": metrics.get("sharpe", 0),
                    "max_dd": metrics.get("max_drawdown_pct", 0),
                    "total_trades": metrics.get("total_trades", 0),
                    "pbo": finalist.get("pbo", None),
                    "bars": len(equity_curve),
                })

                logger.info(
                    "  {} {} {} {}: Sharpe={:.3f} DD={:.1f}% Trades={}",
                    symbol, tf, archetype, direction,
                    metrics.get("sharpe", 0),
                    metrics.get("max_drawdown_pct", 0),
                    metrics.get("total_trades", 0),
                )

            except Exception as e:
                err = f"Replay error {candidate_id} ({archetype}): {e}"
                logger.error(err)
                errors.append(err)

    # Summary
    if results:
        df = pd.DataFrame(results)
        df.to_csv(output_dir / "replay_summary.csv", index=False)
        logger.info("Replayed {} finalists → {}", len(results), output_dir / "replay_summary.csv")

    if errors:
        logger.warning("{} errors during replay", len(errors))
        for e in errors:
            logger.warning("  {}", e)

    print("\n" + "=" * 60)
    print("  REPLAY COMPLETE")
    print("=" * 60)
    print(f"  Finalists replayed: {len(results)}")
    print(f"  Errors: {len(errors)}")
    if results:
        sharpes = [r["sharpe"] for r in results]
        print(f"  Sharpe range: [{min(sharpes):.3f}, {max(sharpes):.3f}]")
        print(f"  Avg trades: {sum(r['total_trades'] for r in results) / len(results):.0f}")
    print(f"  Output: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
