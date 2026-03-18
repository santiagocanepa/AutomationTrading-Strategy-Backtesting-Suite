#!/usr/bin/env python3
"""Build candidate pool from ALL WFO results with PBO below threshold.

Scans all discovery directories, extracts candidates with PBO < threshold,
replays each to generate equity curves, and consolidates into a single pool.

Usage
-----
python scripts/build_candidate_pool.py \
    --pbo-threshold 0.30 \
    --output-dir artifacts/candidate_pool
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
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
from suitetrading.config.archetypes import get_auxiliary_indicators
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.optimization._internal.objective import BacktestObjective
from suitetrading.optimization.walk_forward import WalkForwardEngine


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build candidate pool from WFO results")
    p.add_argument("--pbo-threshold", type=float, default=0.30)
    p.add_argument("--min-oos-sharpe", type=float, default=-999.0,
                   help="Minimum OOS Sharpe (per-bar) to include")
    p.add_argument("--max-per-study", type=int, default=3,
                   help="Max candidates per study to avoid concentration")
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "candidate_pool"))
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--exchange", default="binance")
    p.add_argument("--months", type=int, default=36)
    p.add_argument("--commission", type=float, default=0.04)
    p.add_argument("--mode", default="fsm")
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


def collect_candidates(pbo_threshold: float, max_per_study: int) -> list[dict[str, Any]]:
    """Scan all WFO results and collect candidates below PBO threshold."""
    candidates: list[dict[str, Any]] = []
    wfo_files = sorted(ROOT.glob("artifacts/discovery/*/results/wfo_*.json"))

    for wfo_file in wfo_files:
        with open(wfo_file) as fp:
            wfo_data = json.load(fp)

        pbo = wfo_data.get("pbo")
        if pbo is None or pbo >= pbo_threshold:
            continue

        study = wfo_data.get("study", "")
        finalists = wfo_data.get("finalists", [])
        run_dir = wfo_file.parent.parent.name

        # Parse study name: SYMBOL_TF_ARCHETYPE_DIRECTION
        parts = study.split("_")
        if len(parts) < 4:
            continue
        symbol = parts[0]
        tf = parts[1]
        direction = parts[-1]
        archetype = "_".join(parts[2:-1])

        # If we have explicit finalists with params, use them
        if finalists:
            for i, fin in enumerate(finalists[:max_per_study]):
                candidates.append({
                    "study": study,
                    "run": run_dir,
                    "symbol": symbol,
                    "timeframe": tf,
                    "archetype": archetype,
                    "direction": direction,
                    "pbo": pbo,
                    "indicator_params": fin.get("indicator_params", {}),
                    "risk_overrides": fin.get("risk_overrides", {}),
                    "oos_sharpe": fin.get("observed_sharpe", 0),
                    "dsr": fin.get("dsr", 0),
                })
        else:
            # No finalists but PBO passes — load top-N from Optuna study
            top_csv = wfo_file.parent / f"top50_{study}.csv"
            if not top_csv.exists():
                top_csv = wfo_file.parent / f"top20_{study}.csv"
            if not top_csv.exists():
                # Try any top file
                candidates_csvs = list(wfo_file.parent.glob(f"top*_{study}.csv"))
                if candidates_csvs:
                    top_csv = candidates_csvs[0]

            if top_csv.exists():
                try:
                    df = pd.read_csv(top_csv)
                    if "params" in df.columns and len(df) > 0:
                        for _, row in df.head(max_per_study).iterrows():
                            params_raw = row.get("params", "{}")
                            if isinstance(params_raw, str):
                                flat_params = json.loads(params_raw.replace("'", '"'))
                            else:
                                flat_params = {}

                            # Split flat params
                            ind_params: dict[str, dict] = {}
                            risk_ov: dict[str, Any] = {}
                            for k, v in flat_params.items():
                                kparts = k.split("__", 1)
                                if len(kparts) == 2:
                                    prefix, param = kparts
                                    # Heuristic: if prefix looks like an indicator name
                                    if prefix in ("roc", "macd", "ema", "ssl_channel",
                                                   "rsi", "donchian", "adx_filter",
                                                   "ma_crossover", "bollinger_bands",
                                                   "firestorm_tm", "wavetrend_reversal",
                                                   "squeeze", "stoch_rsi", "ichimoku", "obv"):
                                        ind_params.setdefault(prefix, {})[param] = v
                                    else:
                                        risk_ov[k] = v
                                else:
                                    risk_ov[k] = v

                            candidates.append({
                                "study": study,
                                "run": run_dir,
                                "symbol": symbol,
                                "timeframe": tf,
                                "archetype": archetype,
                                "direction": direction,
                                "pbo": pbo,
                                "indicator_params": ind_params,
                                "risk_overrides": risk_ov,
                                "oos_sharpe": 0,
                                "dsr": 0,
                                "optuna_value": row.get("value", 0),
                            })
                except Exception as e:
                    logger.warning("Error reading {}: {}", top_csv, e)

    return candidates


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()

    # Collect candidates
    logger.info("Scanning WFO results for PBO < {:.2f}...", args.pbo_threshold)
    candidates = collect_candidates(args.pbo_threshold, args.max_per_study)
    logger.info("Found {} candidates from {} unique studies",
                len(candidates), len({c["study"] for c in candidates}))

    if not candidates:
        logger.error("No candidates found!")
        sys.exit(1)

    # Deduplicate by indicator_params + risk_overrides hash
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for c in candidates:
        key_data = json.dumps(
            {"i": c["indicator_params"], "r": c["risk_overrides"],
             "s": c["symbol"], "t": c["timeframe"], "d": c["direction"],
             "a": c["archetype"]},
            sort_keys=True,
        )
        h = hashlib.md5(key_data.encode()).hexdigest()[:12]
        if h not in seen:
            seen.add(h)
            c["candidate_id"] = h
            unique.append(c)

    logger.info("After dedup: {} unique candidates", len(unique))

    # Group by symbol+timeframe for efficient data loading
    by_data: dict[str, list[dict]] = {}
    for c in unique:
        key = f"{c['symbol']}_{c['timeframe']}"
        by_data.setdefault(key, []).append(c)

    # Replay each candidate
    ohlcv_cache: dict[str, pd.DataFrame] = {}
    results: list[dict[str, Any]] = []
    errors: list[str] = []

    for data_key, entries in by_data.items():
        symbol, tf = data_key.rsplit("_", 1)
        if data_key not in ohlcv_cache:
            try:
                ohlcv_cache[data_key] = load_ohlcv(
                    args.exchange, symbol, tf, args.months, Path(args.data_dir),
                )
                logger.info("{} @ {}: {} bars", symbol, tf, len(ohlcv_cache[data_key]))
            except Exception as e:
                logger.error("Failed to load {}: {}", data_key, e)
                for c in entries:
                    errors.append(f"Data load: {data_key}: {e}")
                continue

        ohlcv = ohlcv_cache[data_key]
        dataset = build_dataset_from_df(
            ohlcv, exchange=args.exchange, symbol=symbol, base_timeframe=tf,
        )

        for c in entries:
            archetype = c["archetype"]
            direction = c["direction"]
            indicator_params = c["indicator_params"]
            risk_overrides_flat = c["risk_overrides"]
            cid = c["candidate_id"]

            try:
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

                eq = result["equity_curve"]
                metrics = result["metrics"]
                sharpe = metrics.get("sharpe", 0)
                total_trades = metrics.get("total_trades", 0)

                # Save enriched candidate
                enriched = dict(c)
                enriched["equity_curve"] = (
                    eq.tolist() if isinstance(eq, np.ndarray) else list(eq)
                )
                enriched["replay_metrics"] = metrics

                out_path = output_dir / f"{cid}.json"
                with open(out_path, "w") as fp:
                    json.dump(enriched, fp, default=str)

                results.append({
                    "candidate_id": cid,
                    "study": c["study"],
                    "symbol": symbol,
                    "timeframe": tf,
                    "archetype": archetype,
                    "direction": direction,
                    "pbo": c["pbo"],
                    "sharpe": sharpe,
                    "max_dd": metrics.get("max_drawdown_pct", 0),
                    "total_trades": total_trades,
                    "calmar": metrics.get("calmar", 0),
                })

            except Exception as e:
                errors.append(f"Replay {cid} ({archetype}): {e}")

    elapsed = time.perf_counter() - t0

    # Save summary
    if results:
        df = pd.DataFrame(results)
        df = df.sort_values("sharpe", ascending=False)
        df.to_csv(output_dir / "pool_summary.csv", index=False)

    if errors:
        with open(output_dir / "errors.txt", "w") as fp:
            fp.write("\n".join(errors))

    print("\n" + "=" * 60)
    print("  CANDIDATE POOL BUILT")
    print("=" * 60)
    print(f"  PBO threshold: {args.pbo_threshold}")
    print(f"  Candidates replayed: {len(results)}")
    print(f"  Errors: {len(errors)}")
    if results:
        sharpes = [r["sharpe"] for r in results]
        positive = sum(1 for s in sharpes if s > 0)
        print(f"  Sharpe > 0: {positive}/{len(results)}")
        print(f"  Best Sharpe: {max(sharpes):.3f}")
        print(f"  Unique studies: {len({r['study'] for r in results})}")
        print(f"  Unique archetypes: {len({r['archetype'] for r in results})}")
        syms = {r["symbol"] for r in results}
        tfs = {r["timeframe"] for r in results}
        dirs = {r["direction"] for r in results}
        print(f"  Symbols: {syms}")
        print(f"  Timeframes: {tfs}")
        print(f"  Directions: {dirs}")
    print(f"  Time: {elapsed:.1f}s")
    print(f"  Output: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
