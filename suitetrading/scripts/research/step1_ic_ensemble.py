#!/usr/bin/env python3
"""Ensemble IC scanner — combines cross-asset momentum (entry) + TA filters (timing).

Tests the core thesis: cross-asset momentum provides DIRECTION (IC ~0.025),
TA provides TIMING (IC ~0.017). Together, IC should exceed 0.04.

Measures:
  1. IC of cross-asset signal ALONE (baseline)
  2. IC of TA filter ALONE (baseline)
  3. IC of cross-asset signal CONDITIONED on TA filter active (conditional)
  4. IC of ensemble (both active simultaneously)
  5. Correlation between cross-asset and TA signals

Usage:
    python scripts/research/step1_ic_ensemble.py
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats as sp_stats

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.indicators.cross_asset.momentum import (
    CrossAssetMomentum,
    VolScaledMomentum,
)
from suitetrading.indicators.registry import get_indicator

# ── Config ─────────────────────────────────────────────────────────

FORWARD_HORIZONS = [1, 2, 3, 5, 8, 10, 15, 20]
TRAIN_RATIO = 0.60

# Best cross-asset configs from v2 scan
CROSS_ASSET_PAIRS = [
    # (ref_exchange, ref_symbol, tgt_exchange, tgt_symbol, label, best_lookback)
    ("binance", "BTCUSDT", "binance", "ETHUSDT", "BTC→ETH", 12),
    ("binance", "BTCUSDT", "binance", "BNBUSDT", "BTC→BNB", 12),
    ("binance", "BTCUSDT", "binance", "SOLUSDT", "BTC→SOL", 12),
    ("binance", "BTCUSDT", "binance", "AVAXUSDT", "BTC→AVAX", 12),
]

# Best TA indicators from IC scan (as timing filters)
TA_FILTERS = [
    # (indicator_name, long_mode, short_mode, best_params)
    ("bollinger_bands", "lower", "upper", [
        {"period": 20, "nbdev": 1.0},
        {"period": 20, "nbdev": 1.5},
        {"period": 20, "nbdev": 2.0},
    ]),
    ("rsi", "oversold", "overbought", [
        {"period": 14, "threshold": 30},
        {"period": 14, "threshold": 40},
        {"period": 21, "threshold": 30},
    ]),
    ("volatility_regime", "trending", "trending", [
        {"vol_lookback": 100, "vol_high_pctile": 90},
        {"vol_lookback": 60, "vol_high_pctile": 80},
    ]),
    ("firestorm", "bullish", "bearish", [
        {"period": 10, "multiplier": 0.9},
        {"period": 14, "multiplier": 0.9},
    ]),
]

# Vol-scaled configs to test
VOL_SCALED_CONFIGS = [
    {"lookback": 6, "vol_window": 40, "z_threshold": 0.5, "hold_bars": 1},
    {"lookback": 12, "vol_window": 60, "z_threshold": 0.5, "hold_bars": 1},
    {"lookback": 12, "vol_window": 60, "z_threshold": 0.3, "hold_bars": 3},
    {"lookback": 24, "vol_window": 60, "z_threshold": 0.5, "hold_bars": 1},
]


@dataclass
class EnsembleICResult:
    pair_label: str = ""
    ta_indicator: str = ""
    ta_config: str = ""
    target: str = ""
    timeframe: str = ""
    direction: str = ""
    cross_config: str = ""
    horizon: int = 1
    # Individual ICs
    ic_cross_alone: float = 0.0
    ic_ta_alone: float = 0.0
    # Conditional: IC of cross-asset WHEN ta filter is active
    ic_cross_given_ta: float = 0.0
    # Ensemble: both active simultaneously
    ic_ensemble: float = 0.0
    # Correlation between signals
    signal_correlation: float = 0.0
    # Ensemble stats
    n_ensemble_signals: int = 0
    pct_bars_ensemble: float = 0.0
    hr_ensemble: float = 0.0
    edge_ret_ensemble: float = 0.0
    pvalue_ensemble: float = 1.0
    status: str = "ok"


def compute_ic_on_subset(signal, close, direction, horizon, mask=None):
    """Compute IC, optionally restricted to bars where mask is True."""
    fwd = close.pct_change(horizon).shift(-horizon)
    if direction == "short":
        fwd = -fwd

    df = pd.DataFrame({"sig": signal, "ret": fwd})
    if mask is not None:
        df = df[mask]
    df = df.dropna()

    if len(df) < 50 or df["sig"].sum() < 5 or df["sig"].std() == 0:
        return None

    corr, pval = sp_stats.spearmanr(df["sig"].astype(float), df["ret"])
    if not np.isfinite(corr):
        return None

    sig_b = df["sig"].astype(bool)
    sig_rets = df["ret"][sig_b]
    nosig_rets = df["ret"][~sig_b]

    return {
        "ic": float(corr),
        "p": float(pval) if np.isfinite(pval) else 1.0,
        "hr": float((sig_rets > 0).mean()) if len(sig_rets) > 0 else 0.5,
        "n_sig": int(sig_b.sum()),
        "n_bars": len(df),
        "edge_ret": float(sig_rets.mean() - nosig_rets.mean()) if len(nosig_rets) > 0 else 0.0,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "research" / "ensemble_ic"))
    p.add_argument("--timeframes", nargs="+", default=["4h", "1h"])
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    store = ParquetStore(base_dir=Path(args.data_dir))
    resampler = OHLCVResampler()

    ohlcv_cache = {}

    def get_ohlcv(exchange, symbol, tf):
        key = (exchange, symbol, tf)
        if key not in ohlcv_cache:
            try:
                raw = store.read(exchange, symbol, "1m")
                ohlcv_cache[key] = resampler.resample(raw, tf, base_tf="1m")
            except Exception:
                ohlcv_cache[key] = None
        return ohlcv_cache[key]

    vol_mom = VolScaledMomentum()
    all_results = []

    for ref_ex, ref_sym, tgt_ex, tgt_sym, pair_label, _ in CROSS_ASSET_PAIRS:
        for tf in args.timeframes:
            ref_ohlcv = get_ohlcv(ref_ex, ref_sym, tf)
            tgt_ohlcv = get_ohlcv(tgt_ex, tgt_sym, tf)
            if ref_ohlcv is None or tgt_ohlcv is None:
                continue

            merged = tgt_ohlcv.copy()
            merged["ref_close"] = ref_ohlcv["close"].reindex(merged.index, method="ffill")
            if merged["ref_close"].isna().sum() > len(merged) * 0.3:
                continue

            split_idx = int(len(merged) * TRAIN_RATIO)

            for direction in ["long", "short"]:
                cross_mode = "bullish" if direction == "long" else "bearish"
                ta_long = direction == "long"

                for vcfg in VOL_SCALED_CONFIGS:
                    cross_signal = vol_mom.compute(
                        merged, reference_col="ref_close",
                        mode=cross_mode, **vcfg,
                    )
                    cross_cfg_label = f"lb={vcfg['lookback']}_vw={vcfg['vol_window']}_z={vcfg['z_threshold']}"

                    for ta_name, ta_long_mode, ta_short_mode, ta_param_list in TA_FILTERS:
                        ta_mode = ta_long_mode if ta_long else ta_short_mode
                        ta_ind = get_indicator(ta_name)

                        for ta_params in ta_param_list:
                            try:
                                ta_signal = ta_ind.compute(merged, mode=ta_mode, hold_bars=1, **ta_params)
                            except Exception:
                                continue

                            ta_cfg_label = "&".join(f"{k}={v}" for k, v in sorted(ta_params.items()))

                            # Ensemble: both signals active
                            ensemble = cross_signal & ta_signal

                            # Signal correlation (on validation set)
                            val_cross = cross_signal.iloc[split_idx:].astype(float)
                            val_ta = ta_signal.iloc[split_idx:].astype(float)
                            if val_cross.std() > 0 and val_ta.std() > 0:
                                sig_corr = float(val_cross.corr(val_ta))
                            else:
                                sig_corr = 0.0

                            for horizon in FORWARD_HORIZONS:
                                # Validation-only IC computations
                                val_mask_all = pd.Series(False, index=merged.index)
                                val_mask_all.iloc[split_idx:] = True

                                ic_cross = compute_ic_on_subset(
                                    cross_signal, merged["close"], direction, horizon, val_mask_all)
                                ic_ta = compute_ic_on_subset(
                                    ta_signal, merged["close"], direction, horizon, val_mask_all)

                                # Conditional: IC of cross when TA is active
                                ta_active_mask = val_mask_all & ta_signal
                                ic_conditional = compute_ic_on_subset(
                                    cross_signal, merged["close"], direction, horizon, ta_active_mask)

                                # Ensemble IC
                                ic_ens = compute_ic_on_subset(
                                    ensemble, merged["close"], direction, horizon, val_mask_all)

                                r = EnsembleICResult(
                                    pair_label=pair_label,
                                    ta_indicator=ta_name,
                                    ta_config=ta_cfg_label,
                                    target=tgt_sym,
                                    timeframe=tf,
                                    direction=direction,
                                    cross_config=cross_cfg_label,
                                    horizon=horizon,
                                    ic_cross_alone=ic_cross["ic"] if ic_cross else 0.0,
                                    ic_ta_alone=ic_ta["ic"] if ic_ta else 0.0,
                                    ic_cross_given_ta=ic_conditional["ic"] if ic_conditional else 0.0,
                                    signal_correlation=sig_corr,
                                )

                                if ic_ens:
                                    r.ic_ensemble = ic_ens["ic"]
                                    r.n_ensemble_signals = ic_ens["n_sig"]
                                    r.pct_bars_ensemble = ic_ens["n_sig"] / ic_ens["n_bars"]
                                    r.hr_ensemble = ic_ens["hr"]
                                    r.edge_ret_ensemble = ic_ens["edge_ret"]
                                    r.pvalue_ensemble = ic_ens["p"]
                                else:
                                    r.status = "insufficient_ensemble"

                                all_results.append(asdict(r))

            logger.info("Done {} {} — {} results so far", pair_label, tf, len(all_results))

    df = pd.DataFrame(all_results)
    csv_path = output_dir / "ensemble_ic.csv"
    df.to_csv(csv_path, index=False)
    logger.info("Saved {} measurements to {}", len(df), csv_path)

    # ── Report ──
    ok = df[df["status"] == "ok"]
    h1 = ok[ok["horizon"] == 1]

    print("\n" + "=" * 140)
    print("  ENSEMBLE IC SCAN — cross-asset momentum × TA filters")
    print(f"  {len(df)} measurements | {len(ok)} valid | {len(h1)} at h=1")
    print("=" * 140)

    for direction in ["long", "short"]:
        sub = h1[h1["direction"] == direction]
        if sub.empty:
            continue

        # Aggregate by pair × TA indicator
        ranking = sub.groupby(["pair_label", "ta_indicator"]).agg(
            ic_cross=("ic_cross_alone", "mean"),
            ic_ta=("ic_ta_alone", "mean"),
            ic_conditional=("ic_cross_given_ta", "mean"),
            ic_ensemble_avg=("ic_ensemble", "mean"),
            ic_ensemble_best=("ic_ensemble", "max"),
            sig_corr=("signal_correlation", "mean"),
            hr=("hr_ensemble", "mean"),
            pct_bars=("pct_bars_ensemble", "mean"),
            n_cfgs=("ic_ensemble", "count"),
            edge_ret=("edge_ret_ensemble", "mean"),
        ).sort_values("ic_ensemble_avg", ascending=False)

        n_target = (ranking["ic_ensemble_avg"] > 0.04).sum()
        n_promising = (ranking["ic_ensemble_avg"] > 0.03).sum()

        print(f"\n  ── {direction.upper()} ({n_target} IC>0.04, {n_promising} IC>0.03) ──")
        print(f"  {'Pair × TA':<40s} {'IC_cross':>8s} {'IC_ta':>7s} {'IC_cond':>8s} "
              f"{'IC_ens':>7s} {'IC_best':>8s} {'corr':>6s} {'HR':>6s} {'%bars':>6s} "
              f"{'EdgeRet':>8s}")
        print(f"  {'-'*40} {'-'*8} {'-'*7} {'-'*8} {'-'*7} {'-'*8} {'-'*6} "
              f"{'-'*6} {'-'*6} {'-'*8}")

        for (pair, ta), r in ranking.head(25).iterrows():
            label = f"{pair} × {ta}"
            if r["ic_ensemble_avg"] > 0.04:
                status = " ***"
            elif r["ic_ensemble_avg"] > 0.03:
                status = " ++"
            elif r["ic_ensemble_avg"] > 0.02:
                status = " +"
            else:
                status = ""

            print(f"  {label:<40s} {r['ic_cross']:>8.4f} {r['ic_ta']:>7.4f} "
                  f"{r['ic_conditional']:>8.4f} {r['ic_ensemble_avg']:>7.4f} "
                  f"{r['ic_ensemble_best']:>8.4f} {r['sig_corr']:>6.3f} "
                  f"{r['hr']:>5.1%} {r['pct_bars']:>5.1%} "
                  f"{r['edge_ret']*100:>7.3f}%{status}")

    # Multi-horizon for top ensembles
    top = h1.groupby(["pair_label", "ta_indicator", "direction"]).agg(
        ic=("ic_ensemble", "mean")).reset_index()
    top = top[top["ic"] > 0.025].sort_values("ic", ascending=False).head(8)

    if not top.empty:
        print(f"\n  ── MULTI-HORIZON (top ensembles) ──")
        for _, row in top.iterrows():
            pair, ta, d = row["pair_label"], row["ta_indicator"], row["direction"]
            sub = ok[(ok["pair_label"] == pair) & (ok["ta_indicator"] == ta) & (ok["direction"] == d)]
            print(f"  {pair}×{ta} {d}:", end="")
            for h in FORWARD_HORIZONS:
                hd = sub[sub["horizon"] == h]
                v = hd["ic_ensemble"].mean() if not hd.empty else 0
                marker = "*" if v > 0.04 else ""
                print(f"  h={h}:{v:+.4f}{marker}", end="")
            print()

    # Key comparison: ensemble vs individual
    print(f"\n  ── ENSEMBLE vs INDIVIDUAL (h=1 averages) ──")
    for direction in ["long", "short"]:
        sub = h1[h1["direction"] == direction]
        if sub.empty:
            continue
        avg_cross = sub["ic_cross_alone"].mean()
        avg_ta = sub["ic_ta_alone"].mean()
        avg_cond = sub["ic_cross_given_ta"].mean()
        avg_ens = sub["ic_ensemble"].mean()
        avg_corr = sub["signal_correlation"].mean()
        print(f"  {direction}: cross={avg_cross:.4f} ta={avg_ta:.4f} "
              f"conditional={avg_cond:.4f} ensemble={avg_ens:.4f} "
              f"signal_corr={avg_corr:.3f}")

    print("\n" + "=" * 140)


if __name__ == "__main__":
    main()
