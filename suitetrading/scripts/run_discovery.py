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
from suitetrading.optimization._internal.objective import (
    BacktestObjective,
    DEFAULT_RISK_SEARCH_SPACE,
    EXHAUSTIVE_RISK_SPACE,
    LEAN_RISK_SEARCH_SPACE,
    RICH_RISK_SEARCH_SPACE,
    V8_RISK_SEARCH_SPACE,
)

_RISK_SPACE_MAP = {
    "default": DEFAULT_RISK_SEARCH_SPACE,
    "rich": RICH_RISK_SEARCH_SPACE,
    "lean": LEAN_RISK_SEARCH_SPACE,
    "v8": V8_RISK_SEARCH_SPACE,
    "exhaustive": EXHAUSTIVE_RISK_SPACE,
}
from suitetrading.optimization._internal.schemas import WFOConfig
from suitetrading.risk.archetypes import get_archetype
from suitetrading.config.archetypes import (
    ARCHETYPE_INDICATORS,
    get_all_indicators,
    get_auxiliary_indicators,
    get_entry_indicators,
)

ALL_TIMEFRAMES = ["15m", "1h", "4h", "1d"]
ALL_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT", "LINKUSDT",
    "DOTUSDT", "ADAUSDT", "DOGEUSDT", "XRPUSDT",
]

STOCK_SYMBOLS = [
    "SPY", "QQQ", "IWM", "AAPL", "MSFT", "AMZN", "NVDA", "TSLA",
    "GLD", "XLK", "XLE", "TLT",
]
ALL_ARCHETYPES = list(ARCHETYPE_INDICATORS.keys())


# ── Helpers ───────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Mass strategy discovery pipeline")
    p.add_argument("--symbols", nargs="+", default=ALL_SYMBOLS)
    p.add_argument("--timeframes", nargs="+", default=ALL_TIMEFRAMES)
    p.add_argument("--archetypes", nargs="+", default=ALL_ARCHETYPES)
    p.add_argument("--directions", nargs="+", default=["long"],
                   choices=["long", "short"],
                   help="Trade directions to search (independent tracks)")
    p.add_argument("--trials", type=int, default=500,
                   help="Optuna trials per study")
    p.add_argument("--top-n", type=int, default=50,
                   help="Top N trials to extract per study for WFO")
    p.add_argument("--months", type=int, default=12,
                   help="Months of data to use")
    p.add_argument("--commission", type=float, default=0.04,
                   help="Commission pct per side (default 0.04 = Binance maker)")
    p.add_argument("--exchange", default="binance")
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "discovery"))
    p.add_argument("--metric", default="sharpe")
    p.add_argument("--mode", default="fsm", choices=["fsm", "simple", "auto"])
    p.add_argument("--sampler", default="tpe", choices=["tpe", "random", "nsga2"])
    p.add_argument("--n-jobs", type=int, default=1,
                   help="Parallel trial workers per study (default 1)")
    p.add_argument("--step-factor", type=int, default=1,
                   help="Coarse search multiplier for param steps (1=fine, 4=coarse)")
    p.add_argument("--risk-space", default="auto",
                   choices=["auto", "default", "rich", "lean", "v8", "exhaustive"],
                   help="Risk search space: auto (rich if dynamic), exhaustive (v9: no pyramid, focused)")
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
    p.add_argument("--min-fold-profit", type=int, default=5,
                   help="Min OOS folds with positive metric (5/5 → p=0.031)")
    p.add_argument("--max-degradation", type=float, default=3.0,
                   help="Max IS/OOS degradation ratio (lower = less overfit)")
    p.add_argument("--holdout-months", type=int, default=0,
                   help="Months to reserve as true out-of-sample holdout (0=disabled)")
    p.add_argument("--factory-mode", action="store_true",
                   help="Use archetype factory for combinatorial discovery")
    p.add_argument("--factory-pruning-trials", type=int, default=50,
                   help="Trials for Phase 1 factory pruning (quick filter)")
    p.add_argument("--macro-enrich", action="store_true",
                   help="Inject macro columns (VIX, yield curve, credit spread) into OHLCV")
    p.add_argument("--macro-cache-dir",
                   default=str(ROOT / "data" / "raw" / "macro"),
                   help="Directory for cached macro data")
    return p.parse_args()


def study_name(symbol: str, tf: str, archetype: str, direction: str = "long") -> str:
    return f"{symbol}_{tf}_{archetype}_{direction}"


def enrich_with_macro(
    ohlcv: pd.DataFrame, cache_dir: str,
) -> pd.DataFrame:
    """Inject macro columns (VIX, yield curve, credit spread) into OHLCV.

    Macro data is daily and gets forward-filled to the OHLCV index.
    Also computes ``credit_spread`` ratio from HYG/LQD close prices.
    """
    from suitetrading.data.macro_cache import MacroCacheManager

    cache = MacroCacheManager(cache_dir=Path(cache_dir))

    # FRED series → direct columns
    macro_keys = ["vix", "yield_spread", "hy_spread"]
    aligned = cache.get_aligned(macro_keys, ohlcv.index)
    for col in aligned.columns:
        if not aligned[col].isna().all():
            ohlcv[col] = aligned[col].values

    # Credit spread: HYG / LQD close ratio
    hyg_lqd = cache.get_aligned(["hyg", "lqd"], ohlcv.index)
    if not hyg_lqd["hyg"].isna().all() and not hyg_lqd["lqd"].isna().all():
        ratio = hyg_lqd["hyg"] / hyg_lqd["lqd"]
        ohlcv["credit_spread"] = ratio.values

    injected = [c for c in ["vix", "yield_spread", "hy_spread", "credit_spread"] if c in ohlcv.columns]
    if injected:
        logger.debug("Macro enrichment: injected {} columns", injected)
    return ohlcv


def load_ohlcv(
    exchange: str, symbol: str, timeframe: str,
    months: int, data_dir: Path,
    holdout_months: int = 0,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Load 1m data, trim, optionally split holdout, resample to target TF.

    The holdout split happens on 1m data BEFORE resampling to prevent
    any data leakage across the boundary.

    Returns
    -------
    (train_ohlcv, holdout_ohlcv)
        holdout_ohlcv is None when holdout_months <= 0.
    """
    store = ParquetStore(base_dir=data_dir)
    df_1m = store.read(exchange, symbol, "1m")
    cutoff = df_1m.index.max() - pd.DateOffset(months=months)
    df_1m = df_1m.loc[df_1m.index >= cutoff]

    # Split holdout BEFORE resampling — prevents leakage at boundary
    holdout_1m = None
    if holdout_months > 0:
        holdout_cut = df_1m.index.max() - pd.DateOffset(months=holdout_months)
        holdout_1m = df_1m.loc[df_1m.index >= holdout_cut].copy()
        df_1m = df_1m.loc[df_1m.index < holdout_cut]

    resampler = OHLCVResampler()
    if timeframe == "1m":
        train = df_1m
        holdout = holdout_1m
    else:
        train = resampler.resample(df_1m, timeframe, base_tf="1m")
        holdout = (
            resampler.resample(holdout_1m, timeframe, base_tf="1m")
            if holdout_1m is not None and len(holdout_1m) > 0
            else None
        )
    return train, holdout


def extract_candidate_params(top_trials: list[dict[str, Any]],
                             indicator_names: list[str]) -> list[dict[str, Any]]:
    """Convert flat Optuna params to the structured format WFO expects.

    WFO requires each candidate to have ``indicator_params`` (dict of
    indicator_name → {param: value}) and ``risk_overrides`` (flat keys
    like ``stop__atr_multiple``).

    Rich archetype meta-params (``__state``, ``__timeframe``) are stored
    inside each indicator's param dict via the ``ind____state`` naming
    convention.  ``num_optional_required`` is a global param injected as
    ``indicator_params["__num_optional_required"]`` for ``build_signals``.
    """
    indicator_set = set(indicator_names)
    candidates = []
    for trial in top_trials:
        flat = trial["params"]
        ind_params: dict[str, dict[str, Any]] = {}
        risk_overrides: dict[str, Any] = {}

        for key, value in flat.items():
            # num_optional_required is a global meta-param for build_signals
            if key == "num_optional_required":
                ind_params["__num_optional_required"] = value
                continue

            parts = key.split("__", 1)
            if len(parts) == 2:
                prefix, param_name = parts
                if prefix in indicator_set:
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


def validate_on_holdout(
    *,
    holdout_dataset: BacktestDataset,
    indicator_params: dict[str, dict[str, Any]],
    risk_overrides: dict[str, Any],
    archetype: str,
    direction: str,
    auxiliary_indicators: list[str] | None,
    commission_pct: float,
    mode: str,
) -> dict[str, Any]:
    """Run finalist params on true out-of-sample holdout data.

    Returns the holdout metrics dict (sharpe, total_return_pct, etc.).
    """
    all_ind = list(indicator_params.keys())
    if auxiliary_indicators:
        all_ind += [a for a in auxiliary_indicators if a not in indicator_params]

    objective = BacktestObjective(
        dataset=holdout_dataset,
        indicator_names=all_ind,
        auxiliary_indicators=auxiliary_indicators,
        archetype=archetype,
        direction=direction,
        metric="sharpe",
        mode=mode,
        commission_pct=commission_pct,
    )

    signals = objective.build_signals(indicator_params)
    risk_config = objective.build_risk_config(risk_overrides)

    result = BacktestEngine().run(
        dataset=holdout_dataset,
        signals=signals,
        risk_config=risk_config,
        mode=mode,
        direction=direction,
    )

    return MetricsEngine().compute(
        equity_curve=result["equity_curve"],
        trades=result.get("trades"),
        initial_capital=risk_config.initial_capital,
        context={"timeframe": holdout_dataset.base_timeframe},
    )


# ── Phase A: Optuna Discovery ─────────────────────────────────────────


def run_optuna_study(
    *,
    sname: str,
    dataset: BacktestDataset,
    indicator_names: list[str],
    auxiliary_indicators: list[str] | None = None,
    archetype: str,
    direction: str = "long",
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

    # Use NSGA-II multi-objective for rich archetypes (5+ entry indicators)
    use_multi = args.sampler == "nsga2"

    # Resolve risk search space: "auto" delegates to BacktestObjective (rich if dynamic)
    risk_space_choice = getattr(args, "risk_space", "auto")
    risk_space = _RISK_SPACE_MAP.get(risk_space_choice)  # None for "auto"

    objective = BacktestObjective(
        dataset=dataset,
        indicator_names=indicator_names,
        auxiliary_indicators=auxiliary_indicators,
        archetype=archetype,
        direction=direction,
        metric=args.metric,
        risk_search_space=risk_space,
        mode=args.mode,
        commission_pct=args.commission,
        multi_objective=use_multi,
        step_factor=getattr(args, "step_factor", 1),
    )

    optimizer = OptunaOptimizer(
        objective=objective,
        study_name=sname,
        storage=storage,
        sampler=args.sampler,
        direction="maximize",
        directions=["maximize", "maximize"] if use_multi else None,
        seed=args.seed,
    )

    # Check if we should skip (resume mode)
    existing = len([
        t for t in optimizer.get_study().trials
        if t.state.name == "COMPLETE"
    ])
    remaining = max(0, args.trials - existing)

    n_jobs = getattr(args, "n_jobs", 1)
    if args.resume and remaining == 0:
        logger.info("Study '{}': already has {} trials, skipping", sname, existing)
    elif remaining > 0:
        logger.info(
            "Study '{}': {} existing + {} new = {} target (n_jobs={})",
            sname, existing, remaining, args.trials, n_jobs,
        )
        optimizer.optimize(n_trials=remaining, n_jobs=n_jobs)
    else:
        logger.info("Study '{}': running {} trials (n_jobs={})", sname, args.trials, n_jobs)
        optimizer.optimize(n_trials=args.trials, n_jobs=n_jobs)

    min_trades_filter = BacktestObjective.MIN_TRADES if use_multi else 0
    top = optimizer.get_top_n(args.top_n, min_trades=min_trades_filter)
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
    direction: str = "long",
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

    wfo = WalkForwardEngine(
        config=wfo_config, metric=args.metric,
        auxiliary_indicators=auxiliary_indicators,
        commission_pct=args.commission,
    )

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
        direction=direction,
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

    # ── Fold consistency: per-fold OOS profitability ────────────
    # Binomial test: profitable in k/n folds under H0(p=0.5)
    # 5/5 → p=0.031, 4/5 → p=0.188
    n_folds = len(wfo_result.splits)
    fold_consistency: dict[str, int] = {}
    for cid in curve_ids:
        # Cap at n_folds to handle duplicate PIDs from identical params
        fold_mets = wfo_result.fold_metrics.get(cid, [])[:n_folds]
        n_profitable = sum(
            1 for fm in fold_mets
            if fm.get(args.metric, 0.0) > 0
        )
        fold_consistency[cid] = n_profitable

    # ── Identify finalists (PBO + fold consistency) ──────────
    min_folds = getattr(args, "min_fold_profit", 5)
    max_degrad = getattr(args, "max_degradation", 3.0)
    finalists = []
    for cid in curve_ids:
        passed_cscv = cscv_result.pbo < args.pbo_threshold
        passed_folds = fold_consistency.get(cid, 0) >= min_folds
        degrad = wfo_result.degradation.get(cid, float("inf"))
        passed_degrad = abs(degrad) < max_degrad
        candidate = pid_to_candidate.get(cid, {})

        if passed_cscv and passed_folds and passed_degrad:
            finalists.append({
                "candidate_id": cid,
                "trial_number": candidate.get("trial_number"),
                "pbo": cscv_result.pbo,
                "dsr": dsr_results[cid]["dsr"],
                "observed_sharpe": dsr_results[cid]["observed_sharpe"],
                "fold_profitable": fold_consistency[cid],
                "total_folds": len(wfo_result.splits),
                "degradation": degrad,
                "oos_metrics": wfo_result.oos_metrics.get(cid, {}),
                "indicator_params": candidate.get("indicator_params", {}),
                "risk_overrides": candidate.get("risk_overrides", {}),
            })

    logger.info(
        "Study '{}': {} candidates → {} passed PBO+folds+degrad "
        "(PBO={:.3f}, best_folds={}/{})",
        sname, len(curve_ids), len(finalists),
        cscv_result.pbo,
        max(fold_consistency.values()) if fold_consistency else 0,
        len(wfo_result.splits),
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


def _load_factory_archetypes(args: argparse.Namespace) -> None:
    """Register factory-generated archetypes when --factory-mode is active."""
    from suitetrading.risk.archetypes._factory import generate_factory_archetypes
    from suitetrading.risk.archetypes import ARCHETYPE_REGISTRY

    registry_add, indicator_add = generate_factory_archetypes()
    # Merge into existing registries (skip duplicates)
    new_count = 0
    for name, cls in registry_add.items():
        if name not in ARCHETYPE_REGISTRY:
            ARCHETYPE_REGISTRY[name] = cls
            new_count += 1
    for name, cfg in indicator_add.items():
        if name not in ARCHETYPE_INDICATORS:
            ARCHETYPE_INDICATORS[name] = cfg
    logger.info("Factory mode: registered {} new archetypes", new_count)

    # Override archetypes list with all available
    if not args.archetypes or args.archetypes == ALL_ARCHETYPES:
        args.archetypes = list(ARCHETYPE_INDICATORS.keys())


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    studies_dir = output_dir / "studies"
    results_dir = output_dir / "results"
    evidence_dir = output_dir / "evidence"

    for d in [studies_dir, results_dir, evidence_dir]:
        d.mkdir(parents=True, exist_ok=True)

    if args.holdout_months > 0:
        if args.holdout_months >= args.months:
            logger.error(
                "--holdout-months ({}) must be < --months ({})",
                args.holdout_months, args.months,
            )
            return
        logger.info(
            "Holdout mode: {} months reserved for true out-of-sample validation",
            args.holdout_months,
        )

    if args.factory_mode:
        _load_factory_archetypes(args)

    total_studies = (
        len(args.symbols) * len(args.timeframes)
        * len(args.archetypes) * len(args.directions)
    )
    logger.info(
        "Discovery: {} symbols × {} TFs × {} archetypes × {} dirs = {} studies, {} trials each",
        len(args.symbols), len(args.timeframes), len(args.archetypes),
        len(args.directions), total_studies, args.trials,
    )

    all_finalists: list[dict[str, Any]] = []
    study_summaries: list[dict[str, Any]] = []
    study_idx = 0

    for symbol in args.symbols:
        logger.info("Loading 1m data for {}", symbol)
        ohlcv_cache: dict[str, tuple[pd.DataFrame, pd.DataFrame | None]] = {}

        for tf in args.timeframes:
            if tf not in ohlcv_cache:
                ohlcv_cache[tf] = load_ohlcv(
                    args.exchange, symbol, tf, args.months, Path(args.data_dir),
                    holdout_months=args.holdout_months,
                )
            ohlcv, holdout_ohlcv = ohlcv_cache[tf]

            # Inject macro columns if requested
            if args.macro_enrich:
                ohlcv = enrich_with_macro(ohlcv, args.macro_cache_dir)
                if holdout_ohlcv is not None:
                    holdout_ohlcv = enrich_with_macro(holdout_ohlcv, args.macro_cache_dir)

            logger.info(
                "{} @ {}: {} bars{}",
                symbol, tf, len(ohlcv),
                f" + {len(holdout_ohlcv)} holdout" if holdout_ohlcv is not None else "",
            )

            dataset = build_dataset_from_df(
                ohlcv, exchange=args.exchange, symbol=symbol, base_timeframe=tf,
            )
            holdout_dataset = None
            if holdout_ohlcv is not None and len(holdout_ohlcv) > 0:
                holdout_dataset = build_dataset_from_df(
                    holdout_ohlcv, exchange=args.exchange, symbol=symbol,
                    base_timeframe=tf,
                )

            for archetype in args.archetypes:
                entry_indicators = get_entry_indicators(archetype)
                auxiliary_indicators = get_auxiliary_indicators(archetype)
                all_indicators = entry_indicators + auxiliary_indicators

                for direction in args.directions:
                    study_idx += 1
                    sname = study_name(symbol, tf, archetype, direction)

                    separator = "=" * 60
                    logger.info(
                        "\n{}\n  [{}/{}] {} — entry: {}, auxiliary: {}, dir: {}\n{}",
                        separator, study_idx, total_studies, sname,
                        entry_indicators, auxiliary_indicators, direction, separator,
                    )

                    # Phase A: Optuna search
                    t0 = time.perf_counter()
                    top_trials, total_completed = run_optuna_study(
                        sname=sname,
                        dataset=dataset,
                        indicator_names=all_indicators,
                        auxiliary_indicators=auxiliary_indicators,
                        archetype=archetype,
                        direction=direction,
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
                        "direction": direction,
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
                            direction=direction,
                            auxiliary_indicators=auxiliary_indicators,
                            total_trials=total_completed,
                            args=args,
                        )
                        wfo_time = time.perf_counter() - t1
                        summary["wfo_sec"] = round(wfo_time, 1)
                        summary["pbo"] = wfo_result.get("pbo")
                        summary["n_finalists"] = wfo_result.get("n_finalists", 0)

                        # Collect finalists + holdout validation
                        for f in wfo_result.get("finalists", []):
                            f["study"] = sname
                            f["symbol"] = symbol
                            f["timeframe"] = tf
                            f["archetype"] = archetype
                            f["direction"] = direction

                            if holdout_dataset is not None:
                                try:
                                    h = validate_on_holdout(
                                        holdout_dataset=holdout_dataset,
                                        indicator_params=f.get("indicator_params", {}),
                                        risk_overrides=f.get("risk_overrides", {}),
                                        archetype=archetype,
                                        direction=direction,
                                        auxiliary_indicators=auxiliary_indicators,
                                        commission_pct=args.commission,
                                        mode=args.mode,
                                    )
                                    f["holdout_metrics"] = h
                                    logger.info(
                                        "  Holdout: sharpe={:.4f} return={:.1f}% dd={:.1f}% trades={}",
                                        h.get("sharpe", 0),
                                        h.get("total_return_pct", 0),
                                        h.get("max_drawdown_pct", 0),
                                        h.get("total_trades", 0),
                                    )
                                except Exception as e:
                                    logger.warning("  Holdout validation failed: {}", e)
                                    f["holdout_metrics"] = {"error": str(e)}

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
            row = {
                "rank": f["rank"],
                "study": f["study"],
                "symbol": f["symbol"],
                "timeframe": f["timeframe"],
                "archetype": f["archetype"],
                "direction": f.get("direction", "long"),
                "oos_sharpe": f["observed_sharpe"],
                "pbo": f["pbo"],
                "dsr": f["dsr"],
                "fold_profitable": f.get("fold_profitable"),
                "total_folds": f.get("total_folds"),
                "degradation": f["degradation"],
            }
            hm = f.get("holdout_metrics", {})
            if hm and "error" not in hm:
                row["holdout_sharpe"] = hm.get("sharpe")
                row["holdout_return_pct"] = hm.get("total_return_pct")
                row["holdout_max_dd_pct"] = hm.get("max_drawdown_pct")
                row["holdout_trades"] = hm.get("total_trades")
            finalist_rows.append(row)
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
        # Holdout summary
        holdout_sharpes = [
            f.get("holdout_metrics", {}).get("sharpe", 0)
            for f in all_finalists
            if f.get("holdout_metrics") and "error" not in f.get("holdout_metrics", {})
        ]
        if holdout_sharpes:
            avg_h = sum(holdout_sharpes) / len(holdout_sharpes)
            n_pos = sum(1 for s in holdout_sharpes if s > 0)
            print(f"  Holdout avg Sharpe: {avg_h:.4f}")
            print(f"  Holdout positive:   {n_pos}/{len(holdout_sharpes)}")
    print(f"  Results: {results_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
