#!/usr/bin/env python3
"""Step 3: Cross-TF Combinations — HTF filter + 4h entry.

Guided by Step 1 (IC scan v2/v3) and Step 2 (persistence) results.

Design:
  - Entry indicators: confirmed by v3 IC scan (IC>0.003, >50% IC+, FDR sig)
  - HTF filters: confirmed by Step 2 persistence (peak excess, half-life)
  - Risk space: DEFAULT (full 8 params) — first time exploring all of them
  - Pipeline: Optuna TPE → WFO rolling → CSCV/PBO → DSR
  - Parallelization: one process per (symbol, archetype, direction)

Usage:
  # Single study (test)
  python scripts/research/step3_cross_tf.py --symbols BTCUSDT --dry-run

  # Full run — launch parallel processes externally:
  python scripts/research/step3_cross_tf.py --symbols BTCUSDT --directions long short
  python scripts/research/step3_cross_tf.py --symbols ETHUSDT --directions long short
  # ... etc.

  # Or use the launcher:
  python scripts/research/step3_cross_tf.py --launch-parallel
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.config.archetypes import ARCHETYPE_INDICATORS

# ── Cross-TF Archetype Definitions ──────────────────────────────────
#
# Based on IC scan v3 (21 confirmed) + Step 2 persistence:
#
# ENTRY indicators at 4h (v3 confirmed, FDR significant):
#   - firestorm_tm (short, IC=0.058/0.037, 93% IC+) ← STRONGEST
#   - volatility_regime (long, IC=0.016, 85% IC+)
#   - bollinger_bands (long, IC=0.008, 67% IC+)
#   - firestorm (short, IC=0.011, 66% IC+)
#   - donchian (long, IC=0.009, 60% IC+)
#   - wavetrend_divergence (long, IC=0.008, 69% IC+)
#   - momentum_divergence (short, IC=0.006, 64% IC+)
#   - adx_filter (long, IC=0.006, 62% IC+)
#   - wavetrend_reversal (long, IC=0.005, 59% IC+)
#   - ssl_channel (long, IC=0.004, 53% IC+)
#   - ssl_channel_low (short, IC=0.004, 56% IC+)
#
# HTF FILTERS (Step 2 persistence, Tier 1-2):
#   1W: ssl_channel (long, peak 4.96%, >96 bars 1D)
#   1W: momentum_divergence (short, peak 5.70%, >96 bars 1D)
#   1W: macd (short, peak 3.83%, >96 bars 1D)
#   1D: hurst (short, 13/15 assets sig at bar 48)
#   1D: adx_filter (long, 13/15 assets sig at bar 48)
#   1D: volatility_regime (long, 12/15 assets sig at bar 48)
#
# Architecture:
#   Each archetype = (entry_4h, htf_filter, htf_timeframe)
#   Entry TF is always 4h (best single TF from prior research)
#   ssl_channel as trailing + auxiliary (proven in prior phases)


def _base(entry: list[str], htf_filter: str, htf_tf: str) -> dict:
    """Build archetype config with fullrisk + pyramid + HTF filter."""
    return {
        "entry": entry,
        "auxiliary": ["ssl_channel"],
        "exit": entry,
        "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": htf_filter,
        "htf_timeframe": htf_tf,
    }


# Archetypes: entry × htf_filter combinations
# Naming: s3_{entry}_{htf}_{htf_tf}
STEP3_ARCHETYPES: dict[str, dict] = {
    # ── LONG entries with 1W/1D filters ──
    # bollinger_bands 4h long (IC=0.008, 67% IC+, FDR 11/15)
    "s3_bband_ssl_1w":       _base(["bollinger_bands"], "ssl_channel", "1w"),
    "s3_bband_adx_1d":       _base(["bollinger_bands"], "adx_filter", "1d"),
    "s3_bband_volreg_1d":    _base(["bollinger_bands"], "volatility_regime", "1d"),

    # donchian 4h long (IC=0.009, 60% IC+, FDR 7/15)
    "s3_donch_ssl_1w":       _base(["donchian"], "ssl_channel", "1w"),
    "s3_donch_adx_1d":       _base(["donchian"], "adx_filter", "1d"),

    # wavetrend_divergence 4h long (IC=0.008, 69% IC+, FDR 6/15)
    "s3_wtdiv_ssl_1w":       _base(["wavetrend_divergence"], "ssl_channel", "1w"),
    "s3_wtdiv_adx_1d":       _base(["wavetrend_divergence"], "adx_filter", "1d"),

    # adx_filter 4h long (IC=0.006, 62% IC+, FDR 9/15)
    "s3_adx_ssl_1w":         _base(["adx_filter"], "ssl_channel", "1w"),
    "s3_adx_volreg_1d":      _base(["adx_filter"], "volatility_regime", "1d"),

    # wavetrend_reversal 4h long (IC=0.005, 59% IC+, FDR 5/15)
    "s3_wtrev_ssl_1w":       _base(["wavetrend_reversal"], "ssl_channel", "1w"),
    "s3_wtrev_adx_1d":       _base(["wavetrend_reversal"], "adx_filter", "1d"),

    # ssl_channel 4h long (IC=0.004, 53% IC+, FDR 2/15)
    "s3_ssl_adx_1d":         _base(["ssl_channel"], "adx_filter", "1d"),

    # volatility_regime 4h long (IC=0.016, 85% IC+, FDR 13/15) — as entry!
    "s3_volreg_ssl_1w":      _base(["volatility_regime"], "ssl_channel", "1w"),
    "s3_volreg_adx_1d":      _base(["volatility_regime"], "adx_filter", "1d"),

    # ── SHORT entries with 1W/1D filters ──
    # firestorm_tm 4h short (IC=0.037, 93% IC+, FDR 15/15) — BEST entry
    "s3_ftm_momdiv_1w":      _base(["firestorm_tm"], "momentum_divergence", "1w"),
    "s3_ftm_macd_1w":        _base(["firestorm_tm"], "macd", "1w"),
    "s3_ftm_hurst_1d":       _base(["firestorm_tm"], "hurst", "1d"),

    # firestorm 4h short (IC=0.011, 66% IC+, FDR 11/15)
    "s3_fire_momdiv_1w":     _base(["firestorm"], "momentum_divergence", "1w"),
    "s3_fire_macd_1w":       _base(["firestorm"], "macd", "1w"),
    "s3_fire_hurst_1d":      _base(["firestorm"], "hurst", "1d"),

    # momentum_divergence 4h short (IC=0.006, 64% IC+, FDR 4/15)
    "s3_momdiv_macd_1w":     _base(["momentum_divergence"], "macd", "1w"),
    "s3_momdiv_hurst_1d":    _base(["momentum_divergence"], "hurst", "1d"),

    # ssl_channel_low 4h short (IC=0.004, 56% IC+, FDR 3/15)
    "s3_ssllo_momdiv_1w":    _base(["ssl_channel_low"], "momentum_divergence", "1w"),
    "s3_ssllo_hurst_1d":     _base(["ssl_channel_low"], "hurst", "1d"),

    # ── DUAL entries (2 confirmed indicators) ──
    # bollinger_bands + donchian long (both FDR sig, complementary)
    "s3_bband_donch_ssl_1w": _base(["bollinger_bands", "donchian"], "ssl_channel", "1w"),

    # firestorm_tm + firestorm short (both short-confirmed)
    "s3_ftm_fire_momdiv_1w": _base(["firestorm_tm", "firestorm"], "momentum_divergence", "1w"),

    # ── NO-FILTER baselines (measure HTF filter contribution) ──
    "s3_bband_nofilt":       {
        "entry": ["bollinger_bands"], "auxiliary": ["ssl_channel"],
        "exit": ["bollinger_bands"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "s3_ftm_nofilt":         {
        "entry": ["firestorm_tm"], "auxiliary": ["ssl_channel"],
        "exit": ["firestorm_tm"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "s3_donch_nofilt":       {
        "entry": ["donchian"], "auxiliary": ["ssl_channel"],
        "exit": ["donchian"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
}

# Direction affinity: based on IC scan, each archetype has a natural direction
# "both" means run in both; "long"/"short" means only run that direction
DIRECTION_AFFINITY: dict[str, str] = {
    # Long entries
    "s3_bband_ssl_1w": "long", "s3_bband_adx_1d": "long", "s3_bband_volreg_1d": "long",
    "s3_donch_ssl_1w": "long", "s3_donch_adx_1d": "long",
    "s3_wtdiv_ssl_1w": "long", "s3_wtdiv_adx_1d": "long",
    "s3_adx_ssl_1w": "long", "s3_adx_volreg_1d": "long",
    "s3_wtrev_ssl_1w": "long", "s3_wtrev_adx_1d": "long",
    "s3_ssl_adx_1d": "long",
    "s3_volreg_ssl_1w": "long", "s3_volreg_adx_1d": "long",
    # Short entries
    "s3_ftm_momdiv_1w": "short", "s3_ftm_macd_1w": "short", "s3_ftm_hurst_1d": "short",
    "s3_fire_momdiv_1w": "short", "s3_fire_macd_1w": "short", "s3_fire_hurst_1d": "short",
    "s3_momdiv_macd_1w": "short", "s3_momdiv_hurst_1d": "short",
    "s3_ssllo_momdiv_1w": "short", "s3_ssllo_hurst_1d": "short",
    # Dual
    "s3_bband_donch_ssl_1w": "long",
    "s3_ftm_fire_momdiv_1w": "short",
    # Baselines — test both
    "s3_bband_nofilt": "both", "s3_ftm_nofilt": "both", "s3_donch_nofilt": "both",
}

STOCK_SYMBOLS = ["SPY", "QQQ", "GLD", "TLT", "XLE", "XLK", "IWM", "AAPL", "NVDA", "TSLA"]
CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT"]
ALL_SYMBOLS = STOCK_SYMBOLS + CRYPTO_SYMBOLS


def register_archetypes() -> None:
    """Register Step 3 archetypes into both indicator and risk registries."""
    from suitetrading.risk.archetypes import ARCHETYPE_REGISTRY, RiskArchetype
    from suitetrading.risk.archetypes._fullrisk_base import fullrisk_config as _fc

    for name, cfg in STEP3_ARCHETYPES.items():
        # Register indicator config
        if name not in ARCHETYPE_INDICATORS:
            ARCHETYPE_INDICATORS[name] = cfg

        # Register risk archetype class (fullrisk + pyramid, same as proven configs)
        if name not in ARCHETYPE_REGISTRY:
            cls = type(
                f"_S3_{name}",
                (RiskArchetype,),
                {
                    "__module__": __name__,
                    "name": name,
                    "build_config": lambda self, _n=name, **ov: _fc(
                        _n, pyramid_enabled=True, overrides=dict(ov),
                    ),
                },
            )
            ARCHETYPE_REGISTRY[name] = cls

    logger.info("Registered {} Step 3 cross-TF archetypes", len(STEP3_ARCHETYPES))


def get_directions(archetype: str, user_dirs: list[str]) -> list[str]:
    """Resolve directions for an archetype based on IC affinity."""
    affinity = DIRECTION_AFFINITY.get(archetype, "both")
    if affinity == "both":
        return user_dirs
    return [affinity] if affinity in user_dirs else []


def build_study_list(
    symbols: list[str],
    archetypes: list[str],
    directions: list[str],
) -> list[dict]:
    """Generate all (symbol, archetype, direction) study combinations."""
    studies = []
    for symbol in symbols:
        exchange = "alpaca" if symbol in STOCK_SYMBOLS else "binance"
        for arch in archetypes:
            for d in get_directions(arch, directions):
                studies.append({
                    "symbol": symbol,
                    "archetype": arch,
                    "direction": d,
                    "exchange": exchange,
                })
    return studies


def launch_parallel(args: argparse.Namespace) -> None:
    """Launch one process per symbol using nohup."""
    log_dir = Path(args.output_dir) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    python = str(ROOT / ".venv" / "bin" / "python")
    script = str(Path(__file__))
    base_args = [
        "--timeframe", "4h",
        "--trials", str(args.trials),
        "--top-n", str(args.top_n),
        "--months", str(args.months),
        "--holdout-months", str(args.holdout_months),
        "--output-dir", str(args.output_dir),
    ]
    if args.directions:
        base_args += ["--directions"] + args.directions

    procs = []
    for symbol in args.symbols:
        log_file = log_dir / f"step3_{symbol}.log"
        cmd = [python, script, "--symbols", symbol] + base_args
        logger.info("Launching: {}", " ".join(cmd[-6:]))
        with open(log_file, "w") as lf:
            p = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
            procs.append((symbol, p, log_file))

    logger.info("Launched {} processes. Logs in {}", len(procs), log_dir)
    for symbol, p, lf in procs:
        logger.info("  {} → PID {} → {}", symbol, p.pid, lf)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Step 3: Cross-TF discovery (4h entry + HTF filter)")
    p.add_argument("--symbols", nargs="+", default=ALL_SYMBOLS)
    p.add_argument("--archetypes", nargs="+", default=list(STEP3_ARCHETYPES.keys()),
                   help="Subset of Step 3 archetypes to run")
    p.add_argument("--directions", nargs="+", default=["long", "short"],
                   choices=["long", "short"])
    p.add_argument("--timeframe", default="4h", help="Entry timeframe (default 4h)")
    p.add_argument("--trials", type=int, default=500,
                   help="Optuna trials per study")
    p.add_argument("--top-n", type=int, default=50)
    p.add_argument("--months", type=int, default=66,
                   help="Months of data (default 66 = 5.5 years)")
    p.add_argument("--holdout-months", type=int, default=6,
                   help="Holdout months for true OOS (default 6)")
    p.add_argument("--commission", type=float, default=0.04)
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--output-dir",
                   default=str(ROOT / "artifacts" / "research" / "step3_cross_tf"))
    p.add_argument("--metric", default="sharpe")
    p.add_argument("--mode", default="fsm")
    p.add_argument("--sampler", default="tpe")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--macro-enrich", action="store_true", default=True)
    p.add_argument("--macro-cache-dir", default=str(ROOT / "data" / "raw" / "macro"))
    p.add_argument("--wfo-splits", type=int, default=5)
    p.add_argument("--wfo-min-is", type=int, default=500)
    p.add_argument("--wfo-min-oos", type=int, default=100)
    p.add_argument("--wfo-gap", type=int, default=20)
    p.add_argument("--pbo-threshold", type=float, default=0.50)
    p.add_argument("--dry-run", action="store_true",
                   help="Print study list without running")
    p.add_argument("--launch-parallel", action="store_true",
                   help="Launch one process per symbol in background")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    register_archetypes()

    studies = build_study_list(args.symbols, args.archetypes, args.directions)

    if args.dry_run:
        logger.info("DRY RUN: {} studies", len(studies))
        for s in studies:
            logger.info("  {symbol} × {archetype} × {direction}", **s)
        # Summary
        by_dir = {}
        for s in studies:
            by_dir.setdefault(s["direction"], []).append(s)
        for d, ss in by_dir.items():
            logger.info("{}: {} studies", d, len(ss))
        return

    if args.launch_parallel:
        launch_parallel(args)
        return

    # ── Import heavy deps only when running ──
    from suitetrading.backtesting._internal.datasets import build_dataset_from_df
    from suitetrading.config.archetypes import (
        get_all_indicators,
        get_auxiliary_indicators,
        get_entry_indicators,
    )
    from suitetrading.data.resampler import OHLCVResampler
    from suitetrading.data.storage import ParquetStore
    from suitetrading.optimization import (
        CSCVValidator,
        OptunaOptimizer,
        WalkForwardEngine,
        deflated_sharpe_ratio,
    )
    from suitetrading.optimization._internal.objective import BacktestObjective
    from suitetrading.optimization._internal.schemas import WFOConfig

    output_dir = Path(args.output_dir)
    studies_dir = output_dir / "studies"
    results_dir = output_dir / "results"
    evidence_dir = output_dir / "evidence"
    for d in [studies_dir, results_dir, evidence_dir]:
        d.mkdir(parents=True, exist_ok=True)

    store = ParquetStore(base_dir=Path(args.data_dir))
    resampler = OHLCVResampler()

    logger.info(
        "Step 3 Cross-TF: {} studies ({} symbols × {} archetypes), "
        "{} trials each, TF={}, holdout={}mo",
        len(studies), len(args.symbols), len(args.archetypes),
        args.trials, args.timeframe, args.holdout_months,
    )

    all_finalists = []
    study_summaries = []

    # Cache 1m data per symbol
    ohlcv_1m_cache: dict[str, pd.DataFrame] = {}

    for idx, study in enumerate(studies, 1):
        symbol = study["symbol"]
        archetype = study["archetype"]
        direction = study["direction"]
        exchange = study["exchange"]
        sname = f"{symbol}_{args.timeframe}_{archetype}_{direction}"

        separator = "=" * 70
        logger.info(
            "\n{}\n  [{}/{}] {}\n  entry={}, htf_filter={}, dir={}\n{}",
            separator, idx, len(studies), sname,
            get_entry_indicators(archetype),
            STEP3_ARCHETYPES.get(archetype, {}).get("htf_filter", "none"),
            direction, separator,
        )

        # Load and cache 1m data
        if symbol not in ohlcv_1m_cache:
            try:
                raw = store.read(exchange, symbol, "1m")
                cutoff = raw.index.max() - pd.DateOffset(months=args.months)
                ohlcv_1m_cache[symbol] = raw.loc[raw.index >= cutoff]
            except FileNotFoundError:
                logger.error("No data for {} on {}", symbol, exchange)
                continue

        df_1m = ohlcv_1m_cache[symbol]

        # Split holdout BEFORE resampling
        holdout_1m = None
        train_1m = df_1m
        if args.holdout_months > 0:
            holdout_cut = df_1m.index.max() - pd.DateOffset(months=args.holdout_months)
            holdout_1m = df_1m.loc[df_1m.index >= holdout_cut].copy()
            train_1m = df_1m.loc[df_1m.index < holdout_cut]

        ohlcv = resampler.resample(train_1m, args.timeframe, base_tf="1m")
        holdout_ohlcv = (
            resampler.resample(holdout_1m, args.timeframe, base_tf="1m")
            if holdout_1m is not None and len(holdout_1m) > 0
            else None
        )

        # Macro enrichment for stocks
        if args.macro_enrich and symbol in STOCK_SYMBOLS:
            try:
                from suitetrading.data.macro_cache import MacroCacheManager
                cache = MacroCacheManager(cache_dir=Path(args.macro_cache_dir))
                macro_keys = ["vix", "yield_spread", "hy_spread"]
                aligned = cache.get_aligned(macro_keys, ohlcv.index)
                for col in aligned.columns:
                    if not aligned[col].isna().all():
                        ohlcv[col] = aligned[col].values
                hyg_lqd = cache.get_aligned(["hyg", "lqd"], ohlcv.index)
                if not hyg_lqd["hyg"].isna().all():
                    ohlcv["credit_spread"] = (hyg_lqd["hyg"] / hyg_lqd["lqd"]).values
            except Exception as e:
                logger.warning("Macro enrichment failed for {}: {}", symbol, e)

        # Futures enrichment for crypto
        if symbol in CRYPTO_SYMBOLS:
            try:
                from suitetrading.data.futures import BinanceFuturesDownloader
                fdl = BinanceFuturesDownloader(output_dir=Path(args.data_dir))
                ohlcv = fdl.load_and_merge(symbol, ohlcv)
            except Exception:
                pass

        logger.info("{} @ {}: {} bars train, {} bars holdout",
                    symbol, args.timeframe, len(ohlcv),
                    len(holdout_ohlcv) if holdout_ohlcv is not None else 0)

        dataset = build_dataset_from_df(
            ohlcv, exchange=exchange, symbol=symbol, base_timeframe=args.timeframe,
        )
        holdout_dataset = None
        if holdout_ohlcv is not None and len(holdout_ohlcv) > 100:
            holdout_dataset = build_dataset_from_df(
                holdout_ohlcv, exchange=exchange, symbol=symbol,
                base_timeframe=args.timeframe,
            )

        entry_indicators = get_entry_indicators(archetype)
        auxiliary_indicators = get_auxiliary_indicators(archetype)
        all_indicators = get_all_indicators(archetype)

        # ── Phase A: Optuna Search ──
        t0 = time.perf_counter()
        db_path = studies_dir / f"{sname}.db"
        storage = f"sqlite:///{db_path}"

        if not args.resume and db_path.exists():
            db_path.unlink()

        objective = BacktestObjective(
            dataset=dataset,
            indicator_names=all_indicators,
            auxiliary_indicators=auxiliary_indicators,
            archetype=archetype,
            direction=direction,
            metric=args.metric,
            mode=args.mode,
            commission_pct=args.commission,
        )

        optimizer = OptunaOptimizer(
            objective=objective,
            study_name=sname,
            storage=storage,
            sampler=args.sampler,
            direction="maximize",
            seed=args.seed,
        )

        existing = len([
            t for t in optimizer.get_study().trials
            if t.state.name == "COMPLETE"
        ])
        remaining = max(0, args.trials - existing)

        if args.resume and remaining == 0:
            logger.info("'{}': {} trials exist, skipping Optuna", sname, existing)
        elif remaining > 0:
            logger.info("'{}': running {} trials ({} existing)", sname, remaining, existing)
            optimizer.optimize(n_trials=remaining)
        else:
            optimizer.optimize(n_trials=args.trials)

        top_trials = optimizer.get_top_n(args.top_n)
        total_completed = len([
            t for t in optimizer.get_study().trials
            if t.state.name == "COMPLETE"
        ])
        optuna_time = time.perf_counter() - t0

        if top_trials:
            pd.DataFrame(top_trials).to_csv(
                results_dir / f"top{args.top_n}_{sname}.csv", index=False,
            )

        summary = {
            "study": sname, "symbol": symbol, "timeframe": args.timeframe,
            "archetype": archetype, "direction": direction,
            "entry_indicators": entry_indicators,
            "htf_filter": STEP3_ARCHETYPES.get(archetype, {}).get("htf_filter"),
            "htf_timeframe": STEP3_ARCHETYPES.get(archetype, {}).get("htf_timeframe"),
            "n_trials": total_completed, "n_bars": len(ohlcv),
            "optuna_sec": round(optuna_time, 1),
            "best_value": top_trials[0]["value"] if top_trials else None,
        }

        # ── Phase B: WFO + Anti-Overfit ──
        if top_trials:
            candidates = []
            for trial in top_trials:
                flat = trial["params"]
                ind_params: dict[str, dict] = {}
                risk_overrides: dict[str, any] = {}
                for key, value in flat.items():
                    parts = key.split("__", 1)
                    if len(parts) == 2:
                        prefix, param_name = parts
                        if prefix in all_indicators:
                            ind_params.setdefault(prefix, {})[param_name] = value
                        else:
                            risk_overrides[key] = value
                    else:
                        risk_overrides[key] = value
                candidates.append({
                    "indicator_params": ind_params,
                    "risk_overrides": risk_overrides,
                    "trial_number": trial.get("trial_number"),
                    "optuna_value": trial.get("value"),
                })

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
                logger.warning("'{}': {} bars < {} required for WFO", sname, n_bars, min_required)
                study_summaries.append(summary)
                continue

            wfo = WalkForwardEngine(
                config=wfo_config, metric=args.metric,
                auxiliary_indicators=auxiliary_indicators,
                commission_pct=args.commission,
            )

            wfo_candidates = [
                {"indicator_params": c["indicator_params"], "risk_overrides": c["risk_overrides"]}
                for c in candidates
            ]

            t1 = time.perf_counter()
            logger.info("WFO '{}': {} candidates × {} folds", sname, len(wfo_candidates), wfo_config.n_splits)
            wfo_result = wfo.run(
                dataset=dataset,
                candidate_params=wfo_candidates,
                archetype=archetype,
                direction=direction,
                mode=args.mode,
            )

            # Anti-overfit
            import numpy as np
            from scipy import stats as sp_stats

            oos_curves = {
                k: v for k, v in wfo_result.oos_equity_curves.items()
                if isinstance(v, np.ndarray) and len(v) > 0
            }

            if len(oos_curves) >= 2:
                curve_ids = sorted(oos_curves.keys())
                min_len = min(len(oos_curves[k]) for k in curve_ids)

                if min_len >= args.wfo_splits * 4:  # Enough for CSCV
                    truncated = {k: oos_curves[k][:min_len] for k in curve_ids}
                    cscv = CSCVValidator(n_subsamples=16, metric=args.metric)
                    cscv_result = cscv.compute_pbo(truncated)

                    # DSR
                    dsr_results = {}
                    for cid in curve_ids:
                        curve = oos_curves[cid]
                        rets = np.diff(curve) / np.maximum(curve[:-1], 1e-10)
                        rets_clean = rets[np.isfinite(rets)]
                        std_r = float(np.std(rets_clean, ddof=1)) if len(rets_clean) > 1 else 0.0
                        obs_sr = float(np.mean(rets_clean)) / std_r if std_r > 1e-12 else 0.0
                        dsr_r = deflated_sharpe_ratio(
                            observed_sharpe=obs_sr,
                            n_trials=total_completed,
                            sample_length=len(rets_clean),
                            skewness=float(sp_stats.skew(rets_clean)) if len(rets_clean) > 2 else 0.0,
                            kurtosis=float(sp_stats.kurtosis(rets_clean, fisher=False)) if len(rets_clean) > 3 else 3.0,
                        )
                        dsr_results[cid] = {
                            "dsr": dsr_r.dsr, "observed_sharpe": obs_sr,
                            "significant": dsr_r.is_significant,
                        }

                    # Fold consistency
                    n_folds = len(wfo_result.splits)
                    fold_consistency = {}
                    for cid in curve_ids:
                        fold_mets = wfo_result.fold_metrics.get(cid, [])[:n_folds]
                        fold_consistency[cid] = sum(
                            1 for fm in fold_mets if fm.get(args.metric, 0.0) > 0
                        )

                    # Build PID → candidate mapping
                    pid_to_candidate = {}
                    for c in candidates:
                        wfo_p = {"indicator_params": c["indicator_params"], "risk_overrides": c["risk_overrides"]}
                        pid = WalkForwardEngine._param_id(wfo_p)
                        pid_to_candidate[pid] = c

                    # Select finalists
                    finalists = []
                    for cid in curve_ids:
                        passed_cscv = cscv_result.pbo < args.pbo_threshold
                        passed_folds = fold_consistency.get(cid, 0) >= 5
                        degrad = wfo_result.degradation.get(cid, float("inf"))
                        passed_degrad = abs(degrad) < 3.0
                        candidate = pid_to_candidate.get(cid, {})

                        if passed_cscv and passed_folds and passed_degrad:
                            f = {
                                "candidate_id": cid,
                                "study": sname, "symbol": symbol,
                                "timeframe": args.timeframe,
                                "archetype": archetype, "direction": direction,
                                "pbo": cscv_result.pbo,
                                "dsr": dsr_results[cid]["dsr"],
                                "dsr_significant": dsr_results[cid]["significant"],
                                "observed_sharpe": dsr_results[cid]["observed_sharpe"],
                                "fold_profitable": fold_consistency[cid],
                                "total_folds": n_folds,
                                "degradation": degrad,
                                "oos_metrics": wfo_result.oos_metrics.get(cid, {}),
                                "indicator_params": candidate.get("indicator_params", {}),
                                "risk_overrides": candidate.get("risk_overrides", {}),
                            }

                            # Holdout validation
                            if holdout_dataset is not None:
                                try:
                                    from suitetrading.backtesting.engine import BacktestEngine
                                    from suitetrading.backtesting.metrics import MetricsEngine

                                    h_obj = BacktestObjective(
                                        dataset=holdout_dataset,
                                        indicator_names=all_indicators,
                                        auxiliary_indicators=auxiliary_indicators,
                                        archetype=archetype,
                                        direction=direction,
                                        metric="sharpe",
                                        mode=args.mode,
                                        commission_pct=args.commission,
                                    )
                                    h_signals = h_obj.build_signals(f["indicator_params"])
                                    h_risk = h_obj.build_risk_config(f["risk_overrides"])
                                    h_result = BacktestEngine().run(
                                        dataset=holdout_dataset, signals=h_signals,
                                        risk_config=h_risk, mode=args.mode,
                                        direction=direction,
                                    )
                                    h_metrics = MetricsEngine().compute(
                                        equity_curve=h_result["equity_curve"],
                                        trades=h_result.get("trades"),
                                        initial_capital=h_risk.initial_capital,
                                        context={"timeframe": args.timeframe},
                                    )
                                    f["holdout_metrics"] = h_metrics
                                    logger.info(
                                        "  Holdout: sharpe={:.3f} ret={:.1f}% dd={:.1f}%",
                                        h_metrics.get("sharpe", 0),
                                        h_metrics.get("total_return_pct", 0),
                                        h_metrics.get("max_drawdown_pct", 0),
                                    )
                                except Exception as e:
                                    f["holdout_metrics"] = {"error": str(e)}

                            finalists.append(f)
                            all_finalists.append(f)

                    wfo_time = time.perf_counter() - t1
                    summary["wfo_sec"] = round(wfo_time, 1)
                    summary["pbo"] = cscv_result.pbo
                    summary["n_finalists"] = len(finalists)

                    logger.info(
                        "'{}': PBO={:.3f}, {} finalists (of {} candidates)",
                        sname, cscv_result.pbo, len(finalists), len(curve_ids),
                    )

                    # Save WFO detail
                    with open(results_dir / f"wfo_{sname}.json", "w") as fp:
                        json.dump({
                            "study": sname, "pbo": cscv_result.pbo,
                            "n_candidates": len(curve_ids),
                            "n_finalists": len(finalists),
                            "dsr_results": dsr_results,
                        }, fp, indent=2, default=str)

        study_summaries.append(summary)

    # ── Export ──
    if study_summaries:
        pd.DataFrame(study_summaries).to_csv(
            results_dir / "study_summaries.csv", index=False,
        )

    if all_finalists:
        all_finalists.sort(key=lambda f: f.get("observed_sharpe", 0.0), reverse=True)
        for i, f in enumerate(all_finalists):
            f["rank"] = i + 1
            path = evidence_dir / f"finalist_{i+1:03d}_{f['study']}.json"
            with open(path, "w") as fp:
                json.dump(f, fp, indent=2, default=str)

        rows = []
        for f in all_finalists:
            row = {
                "rank": f["rank"], "study": f["study"], "symbol": f["symbol"],
                "timeframe": f["timeframe"], "archetype": f["archetype"],
                "direction": f["direction"],
                "entry": STEP3_ARCHETYPES.get(f["archetype"], {}).get("entry", []),
                "htf_filter": STEP3_ARCHETYPES.get(f["archetype"], {}).get("htf_filter"),
                "htf_tf": STEP3_ARCHETYPES.get(f["archetype"], {}).get("htf_timeframe"),
                "oos_sharpe": f["observed_sharpe"], "pbo": f["pbo"],
                "dsr": f["dsr"], "dsr_significant": f.get("dsr_significant", False),
                "fold_profitable": f.get("fold_profitable"),
                "degradation": f["degradation"],
            }
            hm = f.get("holdout_metrics", {})
            if hm and "error" not in hm:
                row["holdout_sharpe"] = hm.get("sharpe")
                row["holdout_return_pct"] = hm.get("total_return_pct")
                row["holdout_trades"] = hm.get("total_trades")
            rows.append(row)
        pd.DataFrame(rows).to_csv(results_dir / "finalists.csv", index=False)
        logger.info("Wrote {} finalists", len(all_finalists))

    # ── Summary ──
    print("\n" + "=" * 70)
    print("  STEP 3 CROSS-TF DISCOVERY COMPLETE")
    print("=" * 70)
    print(f"  Studies: {len(study_summaries)}")
    print(f"  Finalists: {len(all_finalists)}")
    if all_finalists:
        print(f"  Best OOS Sharpe: {all_finalists[0]['observed_sharpe']:.4f}")
        print(f"  Best study: {all_finalists[0]['study']}")
        dsr_sig = sum(1 for f in all_finalists if f.get("dsr_significant"))
        print(f"  DSR significant: {dsr_sig}/{len(all_finalists)}")
        hm_pos = sum(
            1 for f in all_finalists
            if f.get("holdout_metrics", {}).get("sharpe", -1) > 0
        )
        hm_total = sum(
            1 for f in all_finalists
            if f.get("holdout_metrics") and "error" not in f.get("holdout_metrics", {})
        )
        if hm_total:
            print(f"  Holdout positive: {hm_pos}/{hm_total}")
    print(f"  Results: {results_dir}")
    print("=" * 70)


if __name__ == "__main__":
    main()
