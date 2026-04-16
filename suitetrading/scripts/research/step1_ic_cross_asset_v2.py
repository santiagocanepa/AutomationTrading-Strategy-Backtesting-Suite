#!/usr/bin/env python3
"""Cross-asset IC scanner v2 — refined with VIX, vol-scaled momentum, macro regime.

Improvements over v1:
  - VIX, HY spread, dollar index, yield spread as macro references
  - Vol-scaled momentum (Moskowitz 2012) alongside simple ROC
  - MacroRegimeSignal (z-score level) for VIX/spread-based signals
  - More lookback/z_threshold combinations

Usage:
    python scripts/research/step1_ic_cross_asset_v2.py
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
    CrossAssetMomentumInverse,
    MacroRegimeSignal,
    VolScaledMomentum,
)

# ── Config ─────────────────────────────────────────────────────────

FORWARD_HORIZONS = [1, 2, 3, 5, 8, 10, 15, 20]
TRAIN_RATIO = 0.60

# Indicator configs to sweep
SIMPLE_LOOKBACKS = [3, 6, 12, 24, 48]
SIMPLE_HOLDS = [1, 3, 5]

VOLSCALED_CONFIGS = [
    {"lookback": lb, "vol_window": vw, "z_threshold": zt, "hold_bars": hb}
    for lb in [6, 12, 24]
    for vw in [40, 60]
    for zt in [0.3, 0.5, 1.0, 1.5]
    for hb in [1, 3]
]

MACRO_REGIME_CONFIGS = [
    {"z_window": zw, "z_threshold": zt, "hold_bars": hb}
    for zw in [20, 40, 60, 120]
    for zt in [0.5, 1.0, 1.5, 2.0]
    for hb in [1, 3, 5]
]

# ── Pair definitions ───────────────────────────────────────────────

# (ref_type, ref_source, ref_col_override, target_exchange, target_symbol, inverse, label, indicator_types)
# ref_type: "ohlcv" = from ParquetStore, "macro" = from macro parquet
# indicator_types: which indicator classes to test for this pair

PAIRS = [
    # === Crypto leader-follower (simple + vol-scaled) ===
    ("ohlcv", ("binance", "BTCUSDT"), None, "binance", "ETHUSDT", False, "BTC→ETH", ["simple", "volscaled"]),
    ("ohlcv", ("binance", "BTCUSDT"), None, "binance", "SOLUSDT", False, "BTC→SOL", ["simple", "volscaled"]),
    ("ohlcv", ("binance", "BTCUSDT"), None, "binance", "BNBUSDT", False, "BTC→BNB", ["simple", "volscaled"]),
    ("ohlcv", ("binance", "BTCUSDT"), None, "binance", "AVAXUSDT", False, "BTC→AVAX", ["simple", "volscaled"]),
    ("ohlcv", ("binance", "ETHUSDT"), None, "binance", "SOLUSDT", False, "ETH→SOL", ["simple", "volscaled"]),
    # === Cross-market (daily only) ===
    ("ohlcv", ("alpaca", "SPY"), None, "binance", "BTCUSDT", False, "SPY→BTC", ["simple", "volscaled"]),
    ("ohlcv", ("alpaca", "SPY"), None, "binance", "ETHUSDT", False, "SPY→ETH", ["simple", "volscaled"]),
    ("ohlcv", ("alpaca", "GLD"), None, "alpaca", "SPY", True, "GLD→SPY(inv)", ["simple", "volscaled"]),
    ("ohlcv", ("alpaca", "TLT"), None, "alpaca", "SPY", True, "TLT→SPY(inv)", ["simple", "volscaled"]),
    # === Stock sector ===
    ("ohlcv", ("alpaca", "SPY"), None, "alpaca", "QQQ", False, "SPY→QQQ", ["simple", "volscaled"]),
    ("ohlcv", ("alpaca", "QQQ"), None, "alpaca", "NVDA", False, "QQQ→NVDA", ["simple", "volscaled"]),
    ("ohlcv", ("alpaca", "QQQ"), None, "alpaca", "TSLA", False, "QQQ→TSLA", ["simple", "volscaled"]),
    # === VIX → everything (macro regime, inverse) ===
    ("macro", "vix.parquet", "vix", "binance", "BTCUSDT", True, "VIX→BTC", ["macro", "volscaled_inv"]),
    ("macro", "vix.parquet", "vix", "binance", "ETHUSDT", True, "VIX→ETH", ["macro", "volscaled_inv"]),
    ("macro", "vix.parquet", "vix", "binance", "SOLUSDT", True, "VIX→SOL", ["macro", "volscaled_inv"]),
    ("macro", "vix.parquet", "vix", "alpaca", "SPY", True, "VIX→SPY", ["macro", "volscaled_inv"]),
    ("macro", "vix.parquet", "vix", "alpaca", "QQQ", True, "VIX→QQQ", ["macro", "volscaled_inv"]),
    # === HY Spread → equities/crypto (macro regime) ===
    ("macro", "hy_spread.parquet", "hy_spread", "alpaca", "SPY", True, "HYspread→SPY", ["macro"]),
    ("macro", "hy_spread.parquet", "hy_spread", "binance", "BTCUSDT", True, "HYspread→BTC", ["macro"]),
    # === Dollar index → crypto (inverse) ===
    ("macro", "dollar_index.parquet", "dollar_index", "binance", "BTCUSDT", True, "DXY→BTC", ["macro", "volscaled_inv"]),
    ("macro", "dollar_index.parquet", "dollar_index", "binance", "ETHUSDT", True, "DXY→ETH", ["macro", "volscaled_inv"]),
    # === Yield spread → equities ===
    ("macro", "yield_spread.parquet", "yield_spread", "alpaca", "SPY", False, "YieldSpread→SPY", ["macro"]),
]


@dataclass
class ICResult:
    pair_label: str = ""
    indicator_type: str = ""
    reference: str = ""
    target: str = ""
    timeframe: str = ""
    direction: str = ""
    config_label: str = ""
    horizon: int = 1
    ic_train: float = 0.0
    ic_val: float = 0.0
    hr_val: float = 0.0
    edge_ret_val: float = 0.0
    n_signals_val: int = 0
    n_bars_train: int = 0
    n_bars_val: int = 0
    pvalue: float = 1.0
    status: str = "ok"


def compute_ic(signal, close, direction, horizon, split_idx):
    fwd = close.pct_change(horizon).shift(-horizon)
    if direction == "short":
        fwd = -fwd
    df = pd.DataFrame({"sig": signal, "ret": fwd}).dropna()
    train, val = df.iloc[:split_idx], df.iloc[split_idx:]

    def _ic(chunk):
        if len(chunk) < 30 or chunk["sig"].sum() < 3 or chunk["sig"].std() == 0:
            return None
        corr, pval = sp_stats.spearmanr(chunk["sig"].astype(float), chunk["ret"])
        if not np.isfinite(corr):
            return None
        sig_b = chunk["sig"].astype(bool)
        sig_rets = chunk["ret"][sig_b]
        nosig_rets = chunk["ret"][~sig_b]
        return {
            "ic": float(corr), "p": float(pval) if np.isfinite(pval) else 1.0,
            "hr": float((sig_rets > 0).mean()) if len(sig_rets) > 0 else 0.5,
            "n_sig": int(sig_b.sum()), "n_bars": len(chunk),
            "edge_ret": float(sig_rets.mean() - nosig_rets.mean()) if len(nosig_rets) > 0 else 0.0,
        }
    return _ic(train), _ic(val)


def scan_configs(merged_df, pair_label, ref_name, tgt_name, tf, inverse, indicator_types):
    """Run all indicator configs for a given pair."""
    results = []
    split_idx = int(len(merged_df) * TRAIN_RATIO)

    for direction in ["long", "short"]:
        mode_simple = "bullish" if direction == "long" else "bearish"
        mode_regime = "risk_on" if direction == "long" else "risk_off"

        configs_to_run = []  # (indicator_instance, params_dict, type_label, config_label)

        if "simple" in indicator_types:
            ind_cls = CrossAssetMomentumInverse if inverse else CrossAssetMomentum
            ind = ind_cls()
            for lb in SIMPLE_LOOKBACKS:
                for hb in SIMPLE_HOLDS:
                    params = {"reference_col": "ref_close", "lookback": lb, "hold_bars": hb, "mode": mode_simple}
                    configs_to_run.append((ind, params, "simple", f"lb={lb}_hb={hb}"))

        if "volscaled" in indicator_types:
            ind = VolScaledMomentum()
            for cfg in VOLSCALED_CONFIGS:
                params = {"reference_col": "ref_close", "mode": mode_simple, **cfg}
                configs_to_run.append((ind, params, "volscaled", f"lb={cfg['lookback']}_vw={cfg['vol_window']}_z={cfg['z_threshold']}_hb={cfg['hold_bars']}"))

        if "volscaled_inv" in indicator_types:
            # For VIX/DXY: vol-scaled on the macro variable, inverse logic
            ind = VolScaledMomentum()
            for cfg in VOLSCALED_CONFIGS:
                # Inverse: for bullish target, we want ref DOWN (bearish mode on ref)
                inv_mode = "bearish" if direction == "long" else "bullish"
                params = {"reference_col": "ref_close", "mode": inv_mode, **cfg}
                configs_to_run.append((ind, params, "volscaled_inv", f"lb={cfg['lookback']}_vw={cfg['vol_window']}_z={cfg['z_threshold']}_hb={cfg['hold_bars']}"))

        if "macro" in indicator_types:
            ind = MacroRegimeSignal()
            for cfg in MACRO_REGIME_CONFIGS:
                params = {"reference_col": "ref_close", "mode": mode_regime, **cfg}
                configs_to_run.append((ind, params, "macro_regime", f"zw={cfg['z_window']}_zt={cfg['z_threshold']}_hb={cfg['hold_bars']}"))

        for ind, params, type_label, cfg_label in configs_to_run:
            try:
                sig = ind.compute(merged_df, **params)
            except Exception:
                continue

            for horizon in FORWARD_HORIZONS:
                t, v = compute_ic(sig, merged_df["close"], direction, horizon, split_idx)
                r = ICResult(
                    pair_label=pair_label, indicator_type=type_label,
                    reference=ref_name, target=tgt_name,
                    timeframe=tf, direction=direction,
                    config_label=cfg_label, horizon=horizon,
                )
                if t is None:
                    r.status = "insufficient"
                    results.append(r)
                    continue
                r.ic_train = t["ic"]
                r.n_bars_train = t["n_bars"]
                if v is not None:
                    r.ic_val = v["ic"]
                    r.hr_val = v["hr"]
                    r.edge_ret_val = v["edge_ret"]
                    r.n_signals_val = v["n_sig"]
                    r.n_bars_val = v["n_bars"]
                    r.pvalue = v["p"]
                results.append(r)

    return results


def report(df):
    ok = df[df["status"] == "ok"].copy()
    h1 = ok[ok["horizon"] == 1]

    print("\n" + "=" * 130)
    print("  CROSS-ASSET IC SCAN v2 — VIX, vol-scaled, macro regime")
    print(f"  {len(df)} measurements | {len(ok)} valid | {len(h1)} at h=1")
    print("=" * 130)

    for direction in ["long", "short"]:
        sub = h1[h1["direction"] == direction]
        if sub.empty:
            continue

        ranking = sub.groupby(["pair_label", "indicator_type"]).agg(
            ic_avg=("ic_val", "mean"),
            ic_best=("ic_val", "max"),
            ic_std=("ic_val", "std"),
            hr=("hr_val", "mean"),
            pct_ic_pos=("ic_val", lambda x: (x > 0).mean()),
            n_configs=("ic_val", "count"),
            edge_ret=("edge_ret_val", "mean"),
        ).sort_values("ic_avg", ascending=False)

        n_conf = ((ranking["ic_avg"] > 0.03) & (ranking["pct_ic_pos"] > 0.5)).sum()
        n_prom = (ranking["ic_avg"] > 0.02).sum()

        print(f"\n  ── {direction.upper()} ({n_conf} confirmed IC>0.03, {n_prom} promising IC>0.02) ──")
        print(f"  {'Pair':<25s} {'Type':<16s} {'IC_avg':>7s} {'IC_best':>8s} {'HR':>6s} "
              f"{'%IC+':>5s} {'Cfgs':>5s} {'EdgeRet':>8s} Status")
        print(f"  {'-'*25} {'-'*16} {'-'*7} {'-'*8} {'-'*6} {'-'*5} {'-'*5} {'-'*8} {'-'*15}")

        for (pair, itype), r in ranking.head(30).iterrows():
            if r["ic_avg"] > 0.03 and r["pct_ic_pos"] > 0.5:
                status = "** CONFIRMED **"
            elif r["ic_avg"] > 0.02:
                status = "promising"
            elif r["ic_avg"] > 0.01:
                status = "weak"
            elif r["ic_avg"] > 0:
                status = "."
            else:
                status = "negative"
            print(f"  {pair:<25s} {itype:<16s} {r['ic_avg']:>7.4f} {r['ic_best']:>8.4f} "
                  f"{r['hr']:>5.1%} {r['pct_ic_pos']:>4.0%} {int(r['n_configs']):>5d} "
                  f"{r['edge_ret']*100:>7.3f}% {status}")

    # Multi-horizon for promising
    promising = h1.groupby(["pair_label", "indicator_type", "direction"]).agg(
        ic_avg=("ic_val", "mean")).reset_index()
    promising = promising[promising["ic_avg"] > 0.015]

    if not promising.empty:
        print(f"\n  ── MULTI-HORIZON DECAY ──")
        for _, row in promising.sort_values("ic_avg", ascending=False).head(10).iterrows():
            pair, itype, d = row["pair_label"], row["indicator_type"], row["direction"]
            sub = ok[(ok["pair_label"] == pair) & (ok["indicator_type"] == itype) & (ok["direction"] == d)]
            print(f"  {pair} [{itype}] {d}:", end="")
            for h in FORWARD_HORIZONS:
                hd = sub[sub["horizon"] == h]
                v = hd["ic_val"].mean() if not hd.empty else 0
                marker = "*" if v > 0.03 else ""
                print(f"  h={h}:{v:+.4f}{marker}", end="")
            print()

    print("\n" + "=" * 130)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--macro-dir", default=str(ROOT / "data" / "raw" / "macro"))
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "research" / "cross_asset_ic_v2"))
    p.add_argument("--timeframes", nargs="+", default=["1d"])
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    macro_dir = Path(args.macro_dir)

    store = ParquetStore(base_dir=Path(args.data_dir))
    resampler = OHLCVResampler()

    ohlcv_cache = {}
    macro_cache = {}

    def get_ohlcv(exchange, symbol, tf):
        key = (exchange, symbol, tf)
        if key not in ohlcv_cache:
            try:
                raw = store.read(exchange, symbol, "1m")
                ohlcv_cache[key] = resampler.resample(raw, tf, base_tf="1m")
            except Exception as e:
                logger.warning("Cannot load {} {} {}: {}", exchange, symbol, tf, e)
                ohlcv_cache[key] = None
        return ohlcv_cache[key]

    def get_macro(filename, col_name):
        if filename not in macro_cache:
            path = macro_dir / filename
            if path.exists():
                macro_cache[filename] = pd.read_parquet(path)
            else:
                macro_cache[filename] = None
        mc = macro_cache[filename]
        if mc is None:
            return None
        if col_name in mc.columns:
            return mc[col_name]
        if len(mc.columns) == 1:
            return mc.iloc[:, 0]
        return None

    all_results = []
    for ref_type, ref_source, ref_col, tgt_ex, tgt_sym, inverse, label, ind_types in PAIRS:
        for tf in args.timeframes:
            # Cross-market: only daily
            if ref_type == "macro" and tf not in ("1d", "1w"):
                continue
            if ref_type == "ohlcv":
                ref_ex, ref_sym = ref_source
                if ref_ex != tgt_ex and tf not in ("1d", "1w"):
                    continue
                ref_ohlcv = get_ohlcv(ref_ex, ref_sym, tf)
                if ref_ohlcv is None:
                    continue
                tgt_ohlcv = get_ohlcv(tgt_ex, tgt_sym, tf)
                if tgt_ohlcv is None:
                    continue
                merged = tgt_ohlcv.copy()
                merged["ref_close"] = ref_ohlcv["close"].reindex(merged.index, method="ffill")
                ref_name = ref_sym
            else:
                # Macro reference
                macro_series = get_macro(ref_source, ref_col)
                if macro_series is None:
                    logger.warning("No macro data for {}", ref_source)
                    continue
                tgt_ohlcv = get_ohlcv(tgt_ex, tgt_sym, tf)
                if tgt_ohlcv is None:
                    continue
                merged = tgt_ohlcv.copy()
                merged["ref_close"] = macro_series.reindex(merged.index, method="ffill")
                ref_name = ref_col

            n_nan = merged["ref_close"].isna().sum()
            if n_nan > len(merged) * 0.5:
                logger.warning("{} {}: >50% NaN ({}/{}), skip", label, tf, n_nan, len(merged))
                continue

            logger.info("Scanning {} {} ({} bars, {:.0f}% ref coverage)...",
                        label, tf, len(merged), (1 - n_nan / len(merged)) * 100)

            pair_results = scan_configs(merged, label, ref_name, tgt_sym, tf, inverse, ind_types)
            all_results.extend(asdict(r) for r in pair_results)

    df = pd.DataFrame(all_results)
    csv_path = output_dir / "cross_asset_ic_v2.csv"
    df.to_csv(csv_path, index=False)
    logger.info("Saved {} measurements to {}", len(df), csv_path)
    report(df)


if __name__ == "__main__":
    main()
