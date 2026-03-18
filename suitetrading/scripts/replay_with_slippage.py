#!/usr/bin/env python3
"""Replay candidate pool with realistic slippage and compare to zero-slippage baseline.

Usage
-----
python scripts/replay_with_slippage.py \
    --pool-dir artifacts/FINAL_POOL_v2 \
    --output-dir artifacts/slippage_analysis
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
from suitetrading.backtesting.slippage import estimate_slippage_pct, get_slippage_table
from suitetrading.config.archetypes import get_auxiliary_indicators
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.optimization._internal.objective import BacktestObjective


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Replay pool with slippage")
    p.add_argument("--pool-dir", default=str(ROOT / "artifacts" / "FINAL_POOL_v2"))
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "slippage_analysis"))
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--exchange", default="binance")
    p.add_argument("--months", type=int, default=36)
    p.add_argument("--mode", default="fsm")
    p.add_argument("--commission", type=float, default=0.04)
    p.add_argument("--slippage-multiplier", type=float, default=1.0,
                   help="Scale the slippage model (1.0 = base, 2.0 = conservative)")
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
    pool_dir = Path(args.pool_dir)

    # Print slippage table
    table = get_slippage_table()
    print("\nSlippage model (one-way %):")
    print(f"{'':>12}", end="")
    tfs = ["15m", "1h", "4h", "1d"]
    for tf in tfs:
        print(f"  {tf:>6}", end="")
    print()
    for sym in sorted(table):
        print(f"  {sym[:4]:>10}", end="")
        for tf in tfs:
            val = table[sym].get(tf, 0)
            print(f"  {val:6.3f}%", end="")
        print()
    print()

    # Load all pool candidates
    candidates: list[dict[str, Any]] = []
    for f in sorted(pool_dir.glob("*.json")):
        if "pool_summary" in f.name or "errors" in f.name:
            continue
        data = json.load(open(f))
        if "equity_curve" in data and "indicator_params" in data:
            candidates.append(data)

    logger.info("Loaded {} candidates from pool", len(candidates))

    # Group by symbol × timeframe
    by_data: dict[str, list[dict]] = {}
    for c in candidates:
        key = f"{c['symbol']}_{c['timeframe']}"
        by_data.setdefault(key, []).append(c)

    ohlcv_cache: dict[str, pd.DataFrame] = {}
    results: list[dict[str, Any]] = []

    for data_key, entries in by_data.items():
        symbol, tf = data_key.rsplit("_", 1)
        if data_key not in ohlcv_cache:
            try:
                ohlcv_cache[data_key] = load_ohlcv(
                    args.exchange, symbol, tf, args.months, Path(args.data_dir),
                )
            except Exception as e:
                logger.error("Failed to load {}: {}", data_key, e)
                continue

        ohlcv = ohlcv_cache[data_key]
        dataset = build_dataset_from_df(
            ohlcv, exchange=args.exchange, symbol=symbol, base_timeframe=tf,
        )

        # Calculate slippage for this symbol × TF
        slip_pct = estimate_slippage_pct(symbol, tf) * args.slippage_multiplier

        for c in entries:
            cid = c.get("candidate_id", "?")
            archetype = c.get("archetype", "?")
            direction = c.get("direction", "long")
            indicator_params = c.get("indicator_params", {})
            risk_overrides = c.get("risk_overrides", {})

            try:
                all_indicators = list(indicator_params.keys())
                auxiliary = get_auxiliary_indicators(archetype)

                # Run WITHOUT slippage (baseline)
                obj_no_slip = BacktestObjective(
                    dataset=dataset,
                    indicator_names=all_indicators,
                    auxiliary_indicators=auxiliary,
                    archetype=archetype,
                    direction=direction,
                    metric="sharpe",
                    mode=args.mode,
                    commission_pct=args.commission,
                )
                flat_params = {
                    **{f"{ind}__{p}": v for ind, params in indicator_params.items() for p, v in params.items()},
                    **risk_overrides,
                }
                res_no_slip = obj_no_slip.run_single(flat_params)

                # Run WITH slippage
                obj_slip = BacktestObjective(
                    dataset=dataset,
                    indicator_names=all_indicators,
                    auxiliary_indicators=auxiliary,
                    archetype=archetype,
                    direction=direction,
                    metric="sharpe",
                    mode=args.mode,
                    commission_pct=args.commission,
                )
                # Override slippage via risk_overrides
                flat_params_slip = {**flat_params, "slippage_pct": slip_pct}
                res_slip = obj_slip.run_single(flat_params_slip)

                m_no = res_no_slip["metrics"]
                m_slip = res_slip["metrics"]

                sharpe_no = m_no.get("sharpe", 0)
                sharpe_slip = m_slip.get("sharpe", 0)
                sharpe_decay = (sharpe_no - sharpe_slip) / abs(sharpe_no) * 100 if abs(sharpe_no) > 0.001 else 0

                results.append({
                    "candidate_id": cid,
                    "symbol": symbol,
                    "timeframe": tf,
                    "archetype": archetype,
                    "direction": direction,
                    "slippage_pct": slip_pct,
                    "sharpe_no_slip": sharpe_no,
                    "sharpe_with_slip": sharpe_slip,
                    "sharpe_decay_pct": round(sharpe_decay, 1),
                    "dd_no_slip": m_no.get("max_drawdown_pct", 0),
                    "dd_with_slip": m_slip.get("max_drawdown_pct", 0),
                    "trades": m_no.get("total_trades", 0),
                    "survived": sharpe_slip > 0,
                })

                # Save slippage equity curve
                enriched = dict(c)
                enriched["equity_curve"] = (
                    res_slip["equity_curve"].tolist()
                    if isinstance(res_slip["equity_curve"], np.ndarray)
                    else list(res_slip["equity_curve"])
                )
                enriched["replay_metrics"] = m_slip
                enriched["slippage_pct"] = slip_pct
                out_f = output_dir / f"{cid}.json"
                with open(out_f, "w") as fp:
                    json.dump(enriched, fp, default=str)

            except Exception as e:
                logger.warning("Error replaying {}: {}", cid[:12], e)

    # Save summary
    if results:
        df = pd.DataFrame(results).sort_values("sharpe_with_slip", ascending=False)
        df.to_csv(output_dir / "slippage_summary.csv", index=False)

        survived = sum(1 for r in results if r["survived"])
        avg_decay = np.mean([r["sharpe_decay_pct"] for r in results])
        avg_slip_sharpe = np.mean([r["sharpe_with_slip"] for r in results])

        print("\n" + "=" * 60)
        print("  SLIPPAGE ANALYSIS")
        print("=" * 60)
        print(f"  Candidates: {len(results)}")
        print(f"  Survived (Sharpe > 0 with slippage): {survived}/{len(results)} ({survived/len(results)*100:.1f}%)")
        print(f"  Avg Sharpe decay: {avg_decay:.1f}%")
        print(f"  Avg Sharpe w/slip: {avg_slip_sharpe:.3f}")
        print(f"  Avg Sharpe no slip: {np.mean([r['sharpe_no_slip'] for r in results]):.3f}")

        # By timeframe
        print("\n  By timeframe:")
        for tf in sorted(set(r["timeframe"] for r in results)):
            tf_results = [r for r in results if r["timeframe"] == tf]
            tf_survived = sum(1 for r in tf_results if r["survived"])
            tf_decay = np.mean([r["sharpe_decay_pct"] for r in tf_results])
            print(f"    {tf}: {tf_survived}/{len(tf_results)} survived, avg decay {tf_decay:.1f}%")

        print(f"\n  Output: {output_dir}")
        print("=" * 60)


if __name__ == "__main__":
    main()
