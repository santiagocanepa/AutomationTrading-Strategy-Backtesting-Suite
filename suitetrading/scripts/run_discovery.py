#!/usr/bin/env python3
"""Mass discovery pipeline: Optuna search → WFO → CSCV + DSR → finalists.

Usage
-----
# Quick smoke test (1 symbol, 1 TF, 1 archetype, 20 trials)
python scripts/run_discovery.py \
    --symbols BTCUSDT --timeframes 1h --archetypes trend_following \
    --trials 20 --top-n 10

# Full discovery run
python scripts/run_discovery.py \
    --symbols BTCUSDT ETHUSDT SOLUSDT \
    --timeframes 15m 1h 4h 1d \
    --archetypes trend_following mean_reversion mixed \
    --trials 500 --top-n 50

# Resume interrupted run (Optuna auto-resumes from SQLite)
python scripts/run_discovery.py \
    --symbols BTCUSDT ETHUSDT SOLUSDT \
    --timeframes 15m 1h 4h 1d \
    --archetypes trend_following mean_reversion mixed \
    --trials 500 --resume
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.backtesting._internal.datasets import build_dataset_from_df
from suitetrading.backtesting._internal.schemas import BacktestDataset, StrategySignals
from suitetrading.backtesting.engine import BacktestEngine
from suitetrading.backtesting.metrics import MetricsEngine
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.indicators.base import IndicatorState
from suitetrading.indicators.registry import get_indicator
from suitetrading.indicators.signal_combiner import combine_signals
from suitetrading.optimization import (
    AntiOverfitPipeline,
    CSCVValidator,
    OptunaOptimizer,
    WalkForwardEngine,
    deflated_sharpe_ratio,
)
from suitetrading.optimization._internal.objective import BacktestObjective
from suitetrading.optimization._internal.schemas import WFOConfig
from suitetrading.risk.archetypes import get_archetype
from suitetrading.config.archetypes import (
    ARCHETYPE_INDICATORS,
    get_all_indicators,
    get_auxiliary_indicators,
    get_entry_indicators,
)

ALL_TIMEFRAMES = ["15m", "1h", "4h", "1d"]
ALL_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
ALL_ARCHETYPES = list(ARCHETYPE_INDICATORS.keys())


# ── Helpers ───────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mass strategy discovery pipeline")
    p.add_argument("--symbols", nargs="+", default=ALL_SYMBOLS)
    p.add_argument("--timeframes", nargs="+", default=ALL_TIMEFRAMES)
    p.add_argument("--archetypes", nargs="+", default=ALL_ARCHETYPES,
                   choices=ALL_ARCHETYPES)
    p.add_argument("--trials", type=int, default=500,
                   help="Optuna trials per study")
    p.add_argument("--top-n", type=int, default=50,
                   help="Top N trials to extract per study for WFO")
    p.add_argument("--months", type=int, default=12,
                   help="Months of data to use")
    p.add_argument("--exchange", default="binance")
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "discovery"))
    p.add_argument("--metric", default="sharpe")
    p.add_argument("--mode", default="fsm", choices=["fsm", "simple", "auto"])
    p.add_argument("--sampler", default="tpe", choices=["tpe", "random", "nsga2"])
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--resume", action="store_true",
                   help="Skip studies that already have enough trials")
    p.add_argument("--skip-wfo", action="store_true",
                   help="Skip WFO + anti-overfit (only run Optuna search)")
    p.add_argument("--wfo-splits", type=int, default=5)
    p.add_argument("--wfo-min-is", type=int, default=500)
    p.add_argument("--wfo-min-oos", type=int, default=100)
    p.add_argument("--wfo-gap", type=int, default=20)
    p.add_argument("--cscv-subsamples", type=int, default=16)
    p.add_argument("--dsr-alpha", type=float, default=0.05)
    p.add_argument("--pbo-threshold", type=float, default=0.50,
                   help="Maximum PBO for a strategy to pass CSCV (default 0.50)")
    return p.parse_args()


def study_name(symbol: str, tf: str, archetype: str) -> str:
    return f"{symbol}_{tf}_{archetype}"


def load_ohlcv(
    exchange: str, symbol: str, timeframe: str,
    months: int, data_dir: Path,
) -> pd.DataFrame:
    """Load 1m data, trim to requested months, resample to target TF."""
    store = ParquetStore(base_dir=data_dir)
    df_1m = store.read(exchange, symbol, "1m")
    cutoff = df_1m.index.max() - pd.DateOffset(months=months)
    df_1m = df_1m.loc[df_1m.index >= cutoff]

    if timeframe == "1m":
        return df_1m

    resampler = OHLCVResampler()
    return resampler.resample(df_1m, timeframe, base_tf="1m")


def extract_candidate_params(top_trials: list[dict[str, Any]],
                             indicator_names: list[str]) -> list[dict[str, Any]]:
    """Convert flat Optuna params to the structured format WFO expects.

    WFO requires each candidate to have ``indicator_params`` (dict of
    indicator_name → {param: value}) and ``risk_overrides`` (flat keys
    like ``stop__atr_multiple``).
    """
    candidates = []
    for trial in top_trials:
        flat = trial["params"]
        ind_params: dict[str, dict[str, Any]] = {}
        risk_overrides: dict[str, Any] = {}

        for key, value in flat.items():
            parts = key.split("__", 1)
            if len(parts) == 2:
                prefix, param_name = parts
                if prefix in indicator_names:
                    ind_params.setdefault(prefix, {})[param_name] = value
                else:
                    # Risk override (e.g., stop__atr_multiple)
                    risk_overrides[key] = value
            else:
                risk_overrides[key] = value

        candidates.append({
            "indicator_params": ind_params,
            "risk_overrides": risk_overrides,
            "trial_number": trial.get("trial_number"),
            "optuna_value": trial.get("value"),
        })
    return candidates


# ── Phase A: Optuna Discovery ─────────────────────────────────────────


def run_optuna_study(
    *,
    sname: str,
    dataset: BacktestDataset,
    indicator_names: list[str],
    auxiliary_indicators: list[str] | None = None,
    archetype: str,
    args: argparse.Namespace,
    studies_dir: Path,
) -> tuple[list[dict[str, Any]], int]:
    """Run Optuna study and return top-N trials + total completed count."""
    db_path = studies_dir / f"{sname}.db"
    storage = f"sqlite:///{db_path}"

    # Clean slate when NOT resuming — avoids mixing trials across code versions
    if not args.resume and db_path.exists():
        logger.info("Study '{}': removing stale DB for clean run", sname)
        db_path.unlink()

    objective = BacktestObjective(
        dataset=dataset,
        indicator_names=indicator_names,
        auxiliary_indicators=auxiliary_indicators,
        archetype=archetype,
        metric=args.metric,
        mode=args.mode,
    )

    optimizer = OptunaOptimizer(
        objective=objective,
        study_name=sname,
        storage=storage,
        sampler=args.sampler,
        direction="maximize",
        seed=args.seed,
    )

    # Check if we should skip (resume mode)
    existing = len([
        t for t in optimizer.get_study().trials
        if t.state.name == "COMPLETE"
    ])
    remaining = max(0, args.trials - existing)

    if args.resume and remaining == 0:
        logger.info("Study '{}': already has {} trials, skipping", sname, existing)
    elif remaining > 0:
        logger.info(
            "Study '{}': {} existing + {} new = {} target",
            sname, existing, remaining, args.trials,
        )
        optimizer.optimize(n_trials=remaining)
    else:
        logger.info("Study '{}': running {} trials", sname, args.trials)
        optimizer.optimize(n_trials=args.trials)

    top = optimizer.get_top_n(args.top_n)
    total = len([
        t for t in optimizer.get_study().trials
        if t.state.name == "COMPLETE"
    ])
    return top, total


# ── Phase B: WFO + Anti-Overfit ───────────────────────────────────────


def run_wfo_and_filter(
    *,
    sname: str,
    dataset: BacktestDataset,
    candidates: list[dict[str, Any]],
    archetype: str,
    auxiliary_indicators: list[str] | None = None,
    total_trials: int,
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Run Walk-Forward + CSCV + DSR on candidate param sets."""
    wfo_config = WFOConfig(
        n_splits=args.wfo_splits,
        min_is_bars=args.wfo_min_is,
        min_oos_bars=args.wfo_min_oos,
        gap_bars=args.wfo_gap,
        mode="rolling",
    )

    n_bars = len(dataset.ohlcv)
    min_required = wfo_config.min_is_bars + wfo_config.gap_bars + wfo_config.min_oos_bars
    if n_bars < min_required:
        logger.warning(
            "Study '{}': only {} bars, need {} for WFO — skipping",
            sname, n_bars, min_required,
        )
        return {"study": sname, "skipped": True, "reason": "insufficient_bars"}

    wfo = WalkForwardEngine(config=wfo_config, metric=args.metric, auxiliary_indicators=auxiliary_indicators)

    # Format candidates for WFO
    wfo_candidates = [
        {"indicator_params": c["indicator_params"], "risk_overrides": c["risk_overrides"]}
        for c in candidates
    ]

    logger.info("WFO for '{}': {} candidates × {} folds", sname, len(wfo_candidates), wfo_config.n_splits)
    wfo_result = wfo.run(
        dataset=dataset,
        candidate_params=wfo_candidates,
        archetype=archetype,
        mode=args.mode,
    )

    # Anti-overfit: CSCV + DSR
    oos_curves = {
        k: v for k, v in wfo_result.oos_equity_curves.items()
        if isinstance(v, np.ndarray) and len(v) > 0
    }

    if len(oos_curves) < 2:
        logger.warning("Study '{}': fewer than 2 OOS curves — skipping anti-overfit", sname)
        return {
            "study": sname,
            "wfo_done": True,
            "anti_overfit_skipped": True,
            "reason": "insufficient_oos_curves",
            "degradation": dict(wfo_result.degradation),
            "oos_metrics": {k: v for k, v in wfo_result.oos_metrics.items()},
        }

    # CSCV
    cscv = CSCVValidator(n_subsamples=args.cscv_subsamples, metric=args.metric)

    # Build return matrices for CSCV (convert equity curves to returns)
    curve_ids = sorted(oos_curves.keys())
    min_len = min(len(oos_curves[k]) for k in curve_ids)
    max_len = max(len(oos_curves[k]) for k in curve_ids)
    if min_len < max_len:
        logger.warning(
            "CSCV truncation: {} curves, min_len={}, max_len={}, "
            "discarding up to {} bars from longest",
            len(curve_ids), min_len, max_len, max_len - min_len,
        )
    if min_len < args.cscv_subsamples * 2:
        logger.warning("Study '{}': OOS curves too short for CSCV — skipping", sname)
        return {
            "study": sname,
            "wfo_done": True,
            "anti_overfit_skipped": True,
            "reason": "oos_curves_too_short",
            "degradation": dict(wfo_result.degradation),
            "oos_metrics": {k: v for k, v in wfo_result.oos_metrics.items()},
        }

    # Build truncated equity curves for CSCV (all same length)
    truncated_curves = {
        k: oos_curves[k][:min_len] for k in curve_ids
    }

    cscv_result = cscv.compute_pbo(truncated_curves)
    logger.info("Study '{}': PBO = {:.3f}", sname, cscv_result.pbo)

    # DSR for each candidate
    dsr_results = {}
    for i, cid in enumerate(curve_ids):
        curve = oos_curves[cid]
        rets = np.diff(curve) / np.maximum(curve[:-1], 1e-10)
        rets_clean = rets[np.isfinite(rets)]

        # Per-bar Sharpe (NOT annualised) — required by DSR formula
        std_r = float(np.std(rets_clean, ddof=1)) if len(rets_clean) > 1 else 0.0
        obs_sharpe_per_bar = float(np.mean(rets_clean)) / std_r if std_r > 1e-12 else 0.0

        dsr_result = deflated_sharpe_ratio(
            observed_sharpe=obs_sharpe_per_bar,
            n_trials=total_trials,
            sample_length=len(rets_clean),
            skewness=float(stats.skew(rets_clean)) if len(rets_clean) > 2 else 0.0,
            kurtosis=float(stats.kurtosis(rets_clean, fisher=False)) if len(rets_clean) > 3 else 3.0,
        )
        dsr_results[cid] = {
            "dsr": dsr_result.dsr,
            "observed_sharpe": obs_sharpe_per_bar,
            "significant": dsr_result.is_significant,
        }

    # Build hash → candidate index mapping for correct lookups
    pid_to_candidate: dict[str, dict[str, Any]] = {}
    for c in candidates:
        wfo_params = {"indicator_params": c["indicator_params"], "risk_overrides": c["risk_overrides"]}
        pid = WalkForwardEngine._param_id(wfo_params)
        pid_to_candidate[pid] = c

    # Identify finalists
    finalists = []
    for cid in curve_ids:
        passed_cscv = cscv_result.pbo < args.pbo_threshold
        passed_dsr = dsr_results[cid]["significant"]
        candidate = pid_to_candidate.get(cid, {})
        if passed_cscv and passed_dsr:
            finalists.append({
                "candidate_id": cid,
                "trial_number": candidate.get("trial_number"),
                "pbo": cscv_result.pbo,
                "dsr": dsr_results[cid]["dsr"],
                "observed_sharpe": dsr_results[cid]["observed_sharpe"],
                "degradation": wfo_result.degradation.get(cid, float("inf")),
                "oos_metrics": wfo_result.oos_metrics.get(cid, {}),
                "indicator_params": candidate.get("indicator_params", {}),
                "risk_overrides": candidate.get("risk_overrides", {}),
            })

    logger.info(
        "Study '{}': {} candidates → {} passed CSCV+DSR",
        sname, len(curve_ids), len(finalists),
    )

    return {
        "study": sname,
        "wfo_done": True,
        "pbo": cscv_result.pbo,
        "n_candidates": len(curve_ids),
        "n_finalists": len(finalists),
        "finalists": finalists,
        "dsr_results": {k: v for k, v in dsr_results.items()},
        "degradation": dict(wfo_result.degradation),
    }


# ── Main ──────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    studies_dir = output_dir / "studies"
    results_dir = output_dir / "results"
    evidence_dir = output_dir / "evidence"

    for d in [studies_dir, results_dir, evidence_dir]:
        d.mkdir(parents=True, exist_ok=True)

    total_studies = len(args.symbols) * len(args.timeframes) * len(args.archetypes)
    logger.info(
        "Discovery: {} symbols × {} TFs × {} archetypes = {} studies, {} trials each",
        len(args.symbols), len(args.timeframes), len(args.archetypes),
        total_studies, args.trials,
    )

    all_finalists: list[dict[str, Any]] = []
    study_summaries: list[dict[str, Any]] = []
    study_idx = 0

    for symbol in args.symbols:
        logger.info("Loading 1m data for {}", symbol)
        ohlcv_cache: dict[str, pd.DataFrame] = {}

        for tf in args.timeframes:
            if tf not in ohlcv_cache:
                ohlcv_cache[tf] = load_ohlcv(
                    args.exchange, symbol, tf, args.months, Path(args.data_dir),
                )
            ohlcv = ohlcv_cache[tf]
            logger.info("{} @ {}: {} bars", symbol, tf, len(ohlcv))

            dataset = build_dataset_from_df(
                ohlcv, exchange=args.exchange, symbol=symbol, base_timeframe=tf,
            )

            for archetype in args.archetypes:
                study_idx += 1
                sname = study_name(symbol, tf, archetype)
                entry_indicators = get_entry_indicators(archetype)
                auxiliary_indicators = get_auxiliary_indicators(archetype)
                all_indicators = entry_indicators + auxiliary_indicators

                separator = "=" * 60
                logger.info(
                    "\n{}\n  [{}/{}] {} — entry: {}, auxiliary: {}\n{}",
                    separator, study_idx, total_studies, sname,
                    entry_indicators, auxiliary_indicators, separator,
                )

                # Phase A: Optuna search
                t0 = time.perf_counter()
                top_trials, total_completed = run_optuna_study(
                    sname=sname,
                    dataset=dataset,
                    indicator_names=all_indicators,
                    auxiliary_indicators=auxiliary_indicators,
                    archetype=archetype,
                    args=args,
                    studies_dir=studies_dir,
                )
                optuna_time = time.perf_counter() - t0

                # Export top-N
                if top_trials:
                    pd.DataFrame(top_trials).to_csv(
                        results_dir / f"top{args.top_n}_{sname}.csv", index=False,
                    )

                summary: dict[str, Any] = {
                    "study": sname,
                    "symbol": symbol,
                    "timeframe": tf,
                    "archetype": archetype,
                    "indicators": all_indicators,
                    "n_trials": total_completed,
                    "n_bars": len(ohlcv),
                    "optuna_sec": round(optuna_time, 1),
                    "best_value": top_trials[0]["value"] if top_trials else None,
                }

                # Phase B: WFO + anti-overfit
                if not args.skip_wfo and top_trials:
                    candidates = extract_candidate_params(top_trials, all_indicators)
                    t1 = time.perf_counter()
                    wfo_result = run_wfo_and_filter(
                        sname=sname,
                        dataset=dataset,
                        candidates=candidates,
                        archetype=archetype,
                        auxiliary_indicators=auxiliary_indicators,
                        total_trials=total_completed,
                        args=args,
                    )
                    wfo_time = time.perf_counter() - t1
                    summary["wfo_sec"] = round(wfo_time, 1)
                    summary["pbo"] = wfo_result.get("pbo")
                    summary["n_finalists"] = wfo_result.get("n_finalists", 0)

                    # Collect finalists
                    for f in wfo_result.get("finalists", []):
                        f["study"] = sname
                        f["symbol"] = symbol
                        f["timeframe"] = tf
                        f["archetype"] = archetype
                        all_finalists.append(f)

                    # Save WFO result
                    wfo_export = {
                        k: v for k, v in wfo_result.items()
                        if k not in ("dsr_results",)
                    }
                    with open(results_dir / f"wfo_{sname}.json", "w") as fp:
                        json.dump(wfo_export, fp, indent=2, default=str)

                study_summaries.append(summary)

    # ── Export aggregated results ─────────────────────────────────────

    if study_summaries:
        pd.DataFrame(study_summaries).to_csv(
            results_dir / "study_summaries.csv", index=False,
        )
        logger.info("Wrote study summaries to {}", results_dir / "study_summaries.csv")

    if all_finalists:
        # Sort by OOS Sharpe descending
        all_finalists.sort(
            key=lambda f: f.get("observed_sharpe", 0.0), reverse=True,
        )
        # Save evidence cards
        for i, f in enumerate(all_finalists):
            f["rank"] = i + 1
            evidence_path = evidence_dir / f"finalist_{i+1:03d}_{f['study']}.json"
            with open(evidence_path, "w") as fp:
                json.dump(f, fp, indent=2, default=str)

        # Save finalists CSV
        finalist_rows = []
        for f in all_finalists:
            finalist_rows.append({
                "rank": f["rank"],
                "study": f["study"],
                "symbol": f["symbol"],
                "timeframe": f["timeframe"],
                "archetype": f["archetype"],
                "oos_sharpe": f["observed_sharpe"],
                "pbo": f["pbo"],
                "dsr": f["dsr"],
                "degradation": f["degradation"],
            })
        pd.DataFrame(finalist_rows).to_csv(
            results_dir / "finalists.csv", index=False,
        )
        logger.info("Wrote {} finalists to {}", len(all_finalists), results_dir / "finalists.csv")
    else:
        logger.warning("No finalists survived the anti-overfit pipeline")

    # ── Final summary ─────────────────────────────────────────────────

    print("\n" + "=" * 60)
    print("  DISCOVERY COMPLETE")
    print("=" * 60)
    print(f"  Studies run: {len(study_summaries)}")
    print(f"  Total finalists: {len(all_finalists)}")
    if all_finalists:
        print(f"  Best OOS Sharpe: {all_finalists[0]['observed_sharpe']:.4f}")
        print(f"  Best study: {all_finalists[0]['study']}")
    print(f"  Results: {results_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
