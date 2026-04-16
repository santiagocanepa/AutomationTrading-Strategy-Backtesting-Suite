#!/usr/bin/env python3
"""Cross-asset momentum IC scanner.

Measures IC of reference asset returns as predictor of target asset direction.
Tests all defined pairs across multiple lookback windows and timeframes.

Usage:
    python scripts/research/step1_ic_cross_asset.py
    python scripts/research/step1_ic_cross_asset.py --timeframes 1d 4h 1h
"""

from __future__ import annotations

import argparse
import itertools
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
)

# ── Config ─────────────────────────────────────────────────────────

FORWARD_HORIZONS = [1, 2, 3, 5, 8, 10, 15, 20]
LOOKBACKS = [3, 6, 12, 24, 48]
HOLD_BARS_OPTIONS = [1, 3, 5]
TRAIN_RATIO = 0.60
SEED = 42

# Pairs: (reference_exchange, reference_symbol, target_exchange, target_symbol, inverse, label)
PAIRS = [
    # Crypto leader-follower (same market, 24/7, no alignment issues)
    ("binance", "BTCUSDT", "binance", "ETHUSDT", False, "BTC→ETH"),
    ("binance", "BTCUSDT", "binance", "SOLUSDT", False, "BTC→SOL"),
    ("binance", "BTCUSDT", "binance", "BNBUSDT", False, "BTC→BNB"),
    ("binance", "BTCUSDT", "binance", "AVAXUSDT", False, "BTC→AVAX"),
    ("binance", "ETHUSDT", "binance", "SOLUSDT", False, "ETH→SOL"),
    ("binance", "ETHUSDT", "binance", "AVAXUSDT", False, "ETH→AVAX"),
    # Cross-market (use daily TF to avoid alignment issues)
    ("alpaca", "SPY", "binance", "BTCUSDT", False, "SPY→BTC"),
    ("alpaca", "SPY", "binance", "ETHUSDT", False, "SPY→ETH"),
    ("alpaca", "QQQ", "binance", "BTCUSDT", False, "QQQ→BTC"),
    ("alpaca", "QQQ", "binance", "SOLUSDT", False, "QQQ→SOL"),
    # Inverse cross-market (risk-off)
    ("alpaca", "TLT", "binance", "BTCUSDT", True, "TLT→BTC(inv)"),
    ("alpaca", "TLT", "alpaca", "SPY", True, "TLT→SPY(inv)"),
    ("alpaca", "GLD", "alpaca", "SPY", True, "GLD→SPY(inv)"),
    # Stock leader-follower
    ("alpaca", "SPY", "alpaca", "QQQ", False, "SPY→QQQ"),
    ("alpaca", "SPY", "alpaca", "IWM", False, "SPY→IWM"),
    ("alpaca", "QQQ", "alpaca", "AAPL", False, "QQQ→AAPL"),
    ("alpaca", "QQQ", "alpaca", "NVDA", False, "QQQ→NVDA"),
    ("alpaca", "QQQ", "alpaca", "TSLA", False, "QQQ→TSLA"),
    ("alpaca", "SPY", "alpaca", "XLE", False, "SPY→XLE"),
]


@dataclass
class CrossAssetICResult:
    pair_label: str = ""
    reference: str = ""
    target: str = ""
    inverse: bool = False
    timeframe: str = ""
    direction: str = ""
    lookback: int = 0
    hold_bars: int = 0
    horizon: int = 1
    ic_train: float = 0.0
    ic_val: float = 0.0
    hr_val: float = 0.0
    edge_ret_val: float = 0.0
    n_signals_val: int = 0
    n_bars_train: int = 0
    n_bars_val: int = 0
    ic_val_pvalue: float = 1.0
    status: str = "ok"


def compute_ic(signal: pd.Series, close: pd.Series, direction: str,
               horizon: int, split_idx: int):
    """Compute IC on train/val split."""
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
            "ic": float(corr),
            "p": float(pval) if np.isfinite(pval) else 1.0,
            "hr": float((sig_rets > 0).mean()) if len(sig_rets) > 0 else 0.5,
            "n_sig": int(sig_b.sum()),
            "n_bars": len(chunk),
            "edge_ret": float(sig_rets.mean() - nosig_rets.mean()) if len(nosig_rets) > 0 else 0.0,
        }

    return _ic(train), _ic(val)


def scan_pair(ref_ohlcv, target_ohlcv, pair_label, ref_sym, target_sym,
              inverse, tf):
    """Scan all lookback × hold_bars × direction × horizon for one pair."""
    indicator = CrossAssetMomentumInverse() if inverse else CrossAssetMomentum()

    # Merge reference close into target
    merged = target_ohlcv.copy()
    merged["ref_close"] = ref_ohlcv["close"].reindex(merged.index, method="ffill")

    # Drop rows where ref is NaN (cross-market alignment)
    valid_mask = merged["ref_close"].notna()
    n_nan = (~valid_mask).sum()
    if n_nan > len(merged) * 0.5:
        logger.warning("Pair {}: >50% NaN in reference ({}/{}), skipping",
                        pair_label, n_nan, len(merged))
        return []

    split_idx = int(valid_mask.sum() * TRAIN_RATIO)
    results = []

    for direction in ["long", "short"]:
        mode = "bullish" if direction == "long" else "bearish"

        for lookback in LOOKBACKS:
            for hold_bars in HOLD_BARS_OPTIONS:
                sig = indicator.compute(
                    merged,
                    reference_col="ref_close",
                    lookback=lookback,
                    hold_bars=hold_bars,
                    mode=mode,
                )

                for horizon in FORWARD_HORIZONS:
                    t, v = compute_ic(sig, merged["close"], direction, horizon, split_idx)

                    r = CrossAssetICResult(
                        pair_label=pair_label,
                        reference=ref_sym,
                        target=target_sym,
                        inverse=inverse,
                        timeframe=tf,
                        direction=direction,
                        lookback=lookback,
                        hold_bars=hold_bars,
                        horizon=horizon,
                    )

                    if t is None:
                        r.status = "insufficient_data"
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
                        r.ic_val_pvalue = v["p"]
                    else:
                        r.status = "no_val_data"

                    results.append(r)

    return results


def report(df: pd.DataFrame):
    """Print summary report."""
    ok = df[df["status"] == "ok"].copy()
    h1 = ok[ok["horizon"] == 1]

    print("\n" + "=" * 120)
    print("  CROSS-ASSET MOMENTUM IC SCAN")
    print(f"  {len(df)} total measurements | {len(ok)} valid | {len(h1)} at h=1")
    print("=" * 120)

    for direction in ["long", "short"]:
        sub = h1[h1["direction"] == direction]
        if sub.empty:
            continue

        # Average IC across configs (lookback × hold_bars) per pair × TF
        ranking = sub.groupby(["pair_label", "timeframe"]).agg(
            ic_avg=("ic_val", "mean"),
            ic_best=("ic_val", "max"),
            ic_std=("ic_val", "std"),
            hr=("hr_val", "mean"),
            pct_ic_pos=("ic_val", lambda x: (x > 0).mean()),
            n_configs=("ic_val", "count"),
            edge_ret=("edge_ret_val", "mean"),
            best_lookback=("lookback", lambda x: x.iloc[sub.loc[x.index, "ic_val"].argmax()] if len(x) > 0 else 0),
        ).sort_values("ic_avg", ascending=False)

        n_confirmed = (ranking["ic_avg"] > 0.03).sum()
        n_promising = (ranking["ic_avg"] > 0.02).sum()

        print(f"\n  ── {direction.upper()} ({n_confirmed} confirmed IC>0.03, {n_promising} promising IC>0.02) ──")
        print(f"  {'Pair':<25s} {'TF':<5s} {'IC_avg':>7s} {'IC_best':>8s} {'HR':>6s} "
              f"{'%IC+':>5s} {'Cfgs':>5s} {'EdgeRet':>8s} Status")
        print(f"  {'-'*25} {'-'*5} {'-'*7} {'-'*8} {'-'*6} {'-'*5} {'-'*5} {'-'*8} {'-'*15}")

        for (pair, tf), r in ranking.head(25).iterrows():
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

            print(f"  {pair:<25s} {tf:<5s} {r['ic_avg']:>7.4f} {r['ic_best']:>8.4f} "
                  f"{r['hr']:>5.1%} {r['pct_ic_pos']:>4.0%} {int(r['n_configs']):>5d} "
                  f"{r['edge_ret']*100:>7.3f}% {status}")

    # Multi-horizon for confirmed pairs
    confirmed = h1.groupby(["pair_label", "timeframe", "direction"]).agg(
        ic_avg=("ic_val", "mean")).reset_index()
    confirmed = confirmed[confirmed["ic_avg"] > 0.02]

    if not confirmed.empty:
        print(f"\n  ── MULTI-HORIZON (confirmed pairs) ──")
        for _, row in confirmed.iterrows():
            pair, tf, d = row["pair_label"], row["timeframe"], row["direction"]
            sub = ok[(ok["pair_label"] == pair) & (ok["timeframe"] == tf) & (ok["direction"] == d)]
            print(f"\n  {pair} {tf} {d}:", end="")
            for h in FORWARD_HORIZONS:
                hd = sub[sub["horizon"] == h]
                v = hd["ic_val"].mean() if not hd.empty else 0
                marker = "*" if v > 0.03 else ""
                print(f"  h={h}:{v:+.4f}{marker}", end="")
            print()

    print("\n" + "=" * 120)


def main():
    p = argparse.ArgumentParser(description="Cross-asset momentum IC scanner")
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "research" / "cross_asset_ic"))
    p.add_argument("--timeframes", nargs="+", default=["1d", "4h", "1h"])
    args = p.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    store = ParquetStore(base_dir=Path(args.data_dir))
    resampler = OHLCVResampler()

    # Cache resampled data
    cache: dict[tuple[str, str, str], pd.DataFrame | None] = {}

    def get_ohlcv(exchange, symbol, tf):
        key = (exchange, symbol, tf)
        if key not in cache:
            try:
                raw = store.read(exchange, symbol, "1m")
                cache[key] = resampler.resample(raw, tf, base_tf="1m")
            except Exception as e:
                logger.warning("Cannot load {} {} {}: {}", exchange, symbol, tf, e)
                cache[key] = None
        return cache[key]

    timeframes = args.timeframes
    n_pairs = len(PAIRS)
    n_tfs = len(timeframes)
    n_configs = len(LOOKBACKS) * len(HOLD_BARS_OPTIONS)
    total_est = n_pairs * n_tfs * n_configs * 2 * len(FORWARD_HORIZONS)
    logger.info("Cross-asset IC scan: {} pairs × {} TFs × {} configs × 2 dirs × {} horizons = ~{} measurements",
                n_pairs, n_tfs, n_configs, len(FORWARD_HORIZONS), total_est)

    all_results = []
    for ref_ex, ref_sym, tgt_ex, tgt_sym, inverse, label in PAIRS:
        for tf in timeframes:
            # Cross-market pairs: force daily TF to avoid alignment issues
            if ref_ex != tgt_ex and tf not in ("1d", "1w"):
                logger.debug("Skipping cross-market pair {} at {}", label, tf)
                continue

            ref = get_ohlcv(ref_ex, ref_sym, tf)
            tgt = get_ohlcv(tgt_ex, tgt_sym, tf)

            if ref is None or tgt is None or len(ref) < 200 or len(tgt) < 200:
                logger.warning("Insufficient data for {} at {}", label, tf)
                continue

            logger.info("Scanning {} {} ({}/{} bars)...", label, tf, len(ref), len(tgt))
            pair_results = scan_pair(ref, tgt, label, ref_sym, tgt_sym, inverse, tf)
            all_results.extend(asdict(r) for r in pair_results)

    df = pd.DataFrame(all_results)
    csv_path = output_dir / "cross_asset_ic.csv"
    df.to_csv(csv_path, index=False)
    logger.info("Saved {} measurements to {}", len(df), csv_path)

    report(df)


if __name__ == "__main__":
    main()
