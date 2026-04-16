#!/usr/bin/env python3
"""Step 1 v2: Rigorous IC Scanner with OOS validation + FDR correction.

Fixes from v1 audit:
  1. Reports IC AVERAGE across param configs (not best-of-5)
  2. Temporal split: train on first 60%, validate on last 40%
  3. FDR correction (Benjamini-Hochberg) on all p-values
  4. Weekly flagged as low-confidence (n too small)
  5. Direction-appropriate modes for each indicator
  6. No selection bias: all configs contribute equally

Usage: python scripts/research/step1_ic_scanner_v2.py
"""

from __future__ import annotations

import argparse
import sys
import warnings
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
from suitetrading.indicators.registry import INDICATOR_REGISTRY, get_indicator

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ── Config ────────────────────────────────────────────────────────────

STOCK_SYMBOLS = ["SPY", "QQQ", "GLD", "TLT", "XLE", "XLK", "IWM", "AAPL", "NVDA", "TSLA"]
CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT"]
ALL_TIMEFRAMES = ["1w", "1d", "4h"]
FORWARD_HORIZONS = [1, 3, 5, 10]
EXCLUDE = {"atr", "cs_momentum"}
MACRO_KEYS = ["vix", "yield_spread", "hy_spread"]
TRAIN_RATIO = 0.60  # First 60% for discovery, last 40% for validation

LONG_MODES = {
    "roc": "bullish", "macd": "bullish", "rsi": "oversold", "ema": "above",
    "bollinger_bands": "lower", "donchian": "upper", "ma_crossover": "bullish",
    "momentum_divergence": "bullish", "obv": "bullish", "stoch_rsi": "oversold",
    "ichimoku": "bullish", "squeeze": "bullish", "volume_spike": "bullish",
    "adx_filter": "strong", "volatility_regime": "trending",
    "vrp": "risk_on", "yield_curve": "normal", "credit_spread": "risk_on",
    "hurst": "trending", "vwap": "above",
    "funding_rate": "reversal_long", "basis": "reversal_long",
    "taker_volume": "buy_pressure", "oi_divergence": "bullish",
    "long_short_ratio": "contrarian_long",
}
SHORT_MODES = {
    "roc": "bearish", "macd": "bearish", "rsi": "overbought", "ema": "below",
    "bollinger_bands": "upper", "donchian": "lower", "ma_crossover": "bearish",
    "momentum_divergence": "bearish", "obv": "bearish", "stoch_rsi": "overbought",
    "ichimoku": "bearish", "squeeze": "bearish", "volume_spike": "bearish",
    "adx_filter": "strong", "volatility_regime": "trending",
    "vrp": "risk_off", "yield_curve": "inverted", "credit_spread": "risk_off",
    "hurst": "trending", "vwap": "below",
    "funding_rate": "reversal_short", "basis": "reversal_short",
    "taker_volume": "sell_pressure", "oi_divergence": "bearish",
    "long_short_ratio": "contrarian_short",
}


def _param_sweep(indicator_name: str) -> list[dict]:
    """Generate 5 param configs."""
    ind = get_indicator(indicator_name)
    schema = ind.params_schema()
    defaults = {}
    for k, v in schema.items():
        if "default" in v:
            defaults[k] = v["default"]
        elif "choices" in v:
            defaults[k] = v["choices"][0]
        elif "min" in v:
            defaults[k] = v["min"]

    primary = None
    for k, v in schema.items():
        if k in ("hold_bars", "mode") or v.get("type") not in ("int", "float"):
            continue
        primary = k
        break

    if primary is None:
        return [defaults]

    pspec = schema[primary]
    lo, hi = pspec.get("min", 5), pspec.get("max", 50)
    if pspec.get("type") == "int":
        values = sorted(set(int(v) for v in np.linspace(lo, hi, 5)))
    else:
        values = [round(lo + i * (hi - lo) / 4, 4) for i in range(5)]

    return [{**defaults, primary: v} for v in values]


# ── Core ──────────────────────────────────────────────────────────────

@dataclass
class ICResult:
    indicator: str = ""
    timeframe: str = ""
    asset: str = ""
    asset_class: str = ""
    direction: str = ""
    horizon: int = 1
    # TRAIN (in-sample) metrics — averaged across ALL configs
    ic_train: float = 0.0
    ic_train_pvalue: float = 1.0
    hr_train: float = 0.0
    n_signals_train: int = 0
    n_bars_train: int = 0
    edge_return_train: float = 0.0
    # VALIDATION (out-of-sample) metrics — averaged across ALL configs
    ic_val: float = 0.0
    ic_val_pvalue: float = 1.0
    hr_val: float = 0.0
    n_signals_val: int = 0
    n_bars_val: int = 0
    edge_return_val: float = 0.0
    # Cross-config metrics
    n_configs: int = 0
    ic_configs_std: float = 0.0  # std of IC across configs (lower = more robust)
    # FDR-corrected (filled in post-processing)
    ic_train_fdr_significant: bool = False
    ic_val_fdr_significant: bool = False
    # Flags
    low_confidence: bool = False  # True for weekly (small n)
    status: str = "ok"


def compute_ic_on_split(
    signal: pd.Series, close: pd.Series, direction: str,
    horizon: int, split_idx: int,
) -> tuple[dict, dict]:
    """Compute IC on train and validation splits separately."""
    fwd = close.pct_change(horizon).shift(-horizon)
    if direction == "short":
        fwd = -fwd

    df = pd.DataFrame({"sig": signal, "ret": fwd}).dropna()
    train = df.iloc[:split_idx]
    val = df.iloc[split_idx:]

    def _ic(chunk):
        if len(chunk) < 30 or chunk["sig"].sum() < 5 or chunk["sig"].std() == 0:
            return {"ic": np.nan, "p": 1.0, "hr": np.nan, "n_sig": 0,
                    "n_bars": len(chunk), "edge_ret": 0.0}
        sig = chunk["sig"].astype(bool)
        ret = chunk["ret"]
        corr, pval = sp_stats.spearmanr(sig.astype(float).values, ret.values)
        sig_rets = ret[sig]
        nosig_rets = ret[~sig]
        return {
            "ic": float(corr) if np.isfinite(corr) else 0.0,
            "p": float(pval) if np.isfinite(pval) else 1.0,
            "hr": float((sig_rets > 0).mean()),
            "n_sig": int(sig.sum()),
            "n_bars": len(chunk),
            "edge_ret": float(sig_rets.mean() - nosig_rets.mean()) if len(nosig_rets) > 0 else 0.0,
        }

    return _ic(train), _ic(val)


def scan_indicator(
    indicator_name: str, ohlcv: pd.DataFrame, timeframe: str,
    asset: str, asset_class: str,
) -> list[ICResult]:
    """Scan one indicator: all configs averaged, train/val split, both directions."""
    configs = _param_sweep(indicator_name)
    schema = get_indicator(indicator_name).params_schema()
    has_mode = "mode" in schema
    split_idx = int(len(ohlcv) * TRAIN_RATIO)
    results = []

    for direction in ["long", "short"]:
        mode_override = {}
        if has_mode:
            m = LONG_MODES if direction == "long" else SHORT_MODES
            if indicator_name in m:
                mode_override["mode"] = m[indicator_name]

        for horizon in FORWARD_HORIZONS:
            train_ics = []
            val_ics = []
            train_hrs = []
            val_hrs = []
            train_edges = []
            val_edges = []
            train_nsigs = []
            val_nsigs = []

            for cfg in configs:
                params = {**cfg, **mode_override}
                try:
                    ind = get_indicator(indicator_name)
                    signal = ind.compute(ohlcv, **params)
                except Exception:
                    continue

                t, v = compute_ic_on_split(signal, ohlcv["close"], direction, horizon, split_idx)

                if not np.isnan(t["ic"]):
                    train_ics.append(t["ic"])
                    train_hrs.append(t["hr"])
                    train_edges.append(t["edge_ret"])
                    train_nsigs.append(t["n_sig"])
                if not np.isnan(v["ic"]):
                    val_ics.append(v["ic"])
                    val_hrs.append(v["hr"])
                    val_edges.append(v["edge_ret"])
                    val_nsigs.append(v["n_sig"])

            if not train_ics:
                results.append(ICResult(
                    indicator=indicator_name, timeframe=timeframe, asset=asset,
                    asset_class=asset_class, direction=direction, horizon=horizon,
                    status="no_valid_configs",
                ))
                continue

            # Average across configs (NO selection bias)
            avg_train_ic = np.mean(train_ics)
            avg_val_ic = np.mean(val_ics) if val_ics else np.nan

            # p-value: t-test on config ICs (is the mean IC != 0?)
            if len(train_ics) >= 3:
                _, train_p = sp_stats.ttest_1samp(train_ics, 0)
            else:
                train_p = sp_stats.norm.sf(abs(avg_train_ic) / max(np.std(train_ics, ddof=1), 1e-10)) * 2 if train_ics else 1.0

            if len(val_ics) >= 3:
                _, val_p = sp_stats.ttest_1samp(val_ics, 0)
            else:
                val_p = 1.0

            r = ICResult(
                indicator=indicator_name, timeframe=timeframe, asset=asset,
                asset_class=asset_class, direction=direction, horizon=horizon,
                ic_train=float(avg_train_ic),
                ic_train_pvalue=float(train_p) if np.isfinite(train_p) else 1.0,
                hr_train=float(np.mean(train_hrs)) if train_hrs else 0.0,
                n_signals_train=int(np.mean(train_nsigs)) if train_nsigs else 0,
                n_bars_train=split_idx,
                edge_return_train=float(np.mean(train_edges)) if train_edges else 0.0,
                ic_val=float(avg_val_ic) if np.isfinite(avg_val_ic) else 0.0,
                ic_val_pvalue=float(val_p) if np.isfinite(val_p) else 1.0,
                hr_val=float(np.mean(val_hrs)) if val_hrs else 0.0,
                n_signals_val=int(np.mean(val_nsigs)) if val_nsigs else 0,
                n_bars_val=len(ohlcv) - split_idx,
                edge_return_val=float(np.mean(val_edges)) if val_edges else 0.0,
                n_configs=len(train_ics),
                ic_configs_std=float(np.std(train_ics)) if len(train_ics) > 1 else 0.0,
                low_confidence=(timeframe == "1w"),
            )
            results.append(r)

    return results


# ── Data loading ──────────────────────────────────────────────────────

def load_and_enrich(asset, tf, store, resampler, macro_cache, futures_dl):
    exchange = "alpaca" if asset in STOCK_SYMBOLS else "binance"
    try:
        raw = store.read(exchange, asset, "1m")
    except FileNotFoundError:
        return None
    if raw.empty:
        return None
    ohlcv = resampler.resample(raw, tf, base_tf="1m")
    if len(ohlcv) < 200:
        return None

    if asset in STOCK_SYMBOLS and macro_cache:
        aligned = macro_cache.get_aligned(MACRO_KEYS, ohlcv.index)
        for col in aligned.columns:
            if not aligned[col].isna().all():
                ohlcv[col] = aligned[col].values
        hyg_lqd = macro_cache.get_aligned(["hyg", "lqd"], ohlcv.index)
        if not hyg_lqd["hyg"].isna().all() and not hyg_lqd["lqd"].isna().all():
            ohlcv["credit_spread"] = (hyg_lqd["hyg"] / hyg_lqd["lqd"]).values

    if asset in CRYPTO_SYMBOLS and futures_dl:
        try:
            ohlcv = futures_dl.load_and_merge(asset, ohlcv)
        except Exception:
            pass
    return ohlcv


# ── FDR correction ────────────────────────────────────────────────────

def apply_fdr(df: pd.DataFrame, col: str, alpha: float = 0.05) -> pd.Series:
    """Benjamini-Hochberg FDR correction. Returns boolean Series."""
    pvals = df[col].values
    n = len(pvals)
    sorted_idx = np.argsort(pvals)
    sorted_pvals = pvals[sorted_idx]
    bh_critical = np.arange(1, n + 1) / n * alpha

    # Find largest k where p[k] <= bh_critical[k]
    significant = np.zeros(n, dtype=bool)
    max_k = 0
    for k in range(n):
        if sorted_pvals[k] <= bh_critical[k]:
            max_k = k

    significant[sorted_idx[:max_k + 1]] = True
    return pd.Series(significant, index=df.index)


# ── Reporting ─────────────────────────────────────────────────────────

def report(df: pd.DataFrame) -> None:
    ok = df[df["status"] == "ok"].copy()
    if ok.empty:
        return

    # Apply FDR
    ok["fdr_train"] = apply_fdr(ok, "ic_train_pvalue")
    ok["fdr_val"] = apply_fdr(ok, "ic_val_pvalue")

    h1 = ok[ok["horizon"] == 1]

    print("\n" + "=" * 115)
    print("  STEP 1 v2: RIGOROUS IC MAP — Train/Val split + FDR correction + Config-averaged IC")
    print("  IC = AVERAGE across 5 param configs (no selection bias)")
    print(f"  Train: first {TRAIN_RATIO:.0%} of data | Validation: last {1-TRAIN_RATIO:.0%}")
    print("=" * 115)

    for tf in ["1d", "4h"]:  # Skip 1w in main report (low confidence)
        for direction in ["long", "short"]:
            sub = h1[(h1["timeframe"] == tf) & (h1["direction"] == direction)]
            if sub.empty:
                continue

            ranking = (
                sub.groupby("indicator")
                .agg(
                    ic_train=("ic_train", "mean"),
                    ic_val=("ic_val", "mean"),
                    hr_train=("hr_train", "mean"),
                    hr_val=("hr_val", "mean"),
                    fdr_train_n=("fdr_train", "sum"),
                    fdr_val_n=("fdr_val", "sum"),
                    n_total=("ic_train", "count"),
                    n_pos_val=("ic_val", lambda x: (x > 0).sum()),
                    edge_ret_val=("edge_return_val", "mean"),
                    configs_std=("ic_configs_std", "mean"),
                )
                .sort_values("ic_val", ascending=False)  # Sort by OOS, not in-sample
            )

            n_confirmed = ((ranking["ic_train"] > 0.005) & (ranking["ic_val"] > 0.005) & (ranking["fdr_val_n"] > 0)).sum()

            print(f"\n  ── {tf} {direction.upper()} ({n_confirmed} OOS-confirmed) ──")
            print(f"  {'Indicator':<25s} {'IC_train':>8s} {'IC_val':>8s} {'HR_val':>7s} {'FDR+':>5s} {'IC+oos':>6s} {'EdgeRet':>8s} {'CfgStd':>7s} Status")
            print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*7} {'-'*5} {'-'*6} {'-'*8} {'-'*7} {'-'*12}")

            for ind, r in ranking.head(20).iterrows():
                fdr_str = f"{int(r['fdr_val_n'])}/{int(r['n_total'])}"
                pos_str = f"{int(r['n_pos_val'])}/{int(r['n_total'])}"
                edge_str = f"{r['edge_ret_val']*100:.3f}%"

                if r["ic_train"] > 0.005 and r["ic_val"] > 0.005 and r["fdr_val_n"] > 0:
                    status = "CONFIRMED"
                elif r["ic_train"] > 0.005 and r["ic_val"] > 0:
                    status = "promising"
                elif r["ic_train"] > 0.005:
                    status = "train-only"
                else:
                    status = "."

                print(f"  {ind:<25s} {r['ic_train']:>8.4f} {r['ic_val']:>8.4f} {r['hr_val']:>6.1%} {fdr_str:>5s} {pos_str:>6s} {edge_str:>8s} {r['configs_std']:>7.4f} {status}")

    # Weekly (low confidence, descriptive only)
    print(f"\n  ── WEEKLY (descriptive only — low statistical power, n≈277 bars) ──")
    w1 = h1[h1["timeframe"] == "1w"]
    if not w1.empty:
        for direction in ["long", "short"]:
            ws = w1[w1["direction"] == direction]
            ranking = ws.groupby("indicator").agg(
                ic_train=("ic_train", "mean"), ic_val=("ic_val", "mean"),
            ).sort_values("ic_val", ascending=False).head(5)
            inds = ", ".join(f"{ind}(t={r['ic_train']:.3f}/v={r['ic_val']:.3f})" for ind, r in ranking.iterrows())
            print(f"  1w {direction}: {inds}")

    # Multi-horizon for confirmed indicators
    print(f"\n  ── MULTI-HORIZON (OOS IC, confirmed indicators only) ──")
    for tf in ["1d", "4h"]:
        for direction in ["long", "short"]:
            sub = ok[(ok["timeframe"] == tf) & (ok["direction"] == direction)]
            h1_sub = sub[sub["horizon"] == 1]
            confirmed = h1_sub.groupby("indicator").agg(
                ic_val=("ic_val", "mean"), fdr=("fdr_val", "sum")
            )
            confirmed = confirmed[(confirmed["ic_val"] > 0.005) & (confirmed["fdr"] > 0)]
            if confirmed.empty:
                continue

            print(f"\n  {tf} {direction}:")
            print(f"  {'Indicator':<25s}", end="")
            for h in FORWARD_HORIZONS:
                print(f" {'h='+str(h):>7s}", end="")
            print()

            for ind in confirmed.index:
                print(f"  {ind:<25s}", end="")
                for h in FORWARD_HORIZONS:
                    h_data = sub[(sub["indicator"] == ind) & (sub["horizon"] == h)]
                    val = h_data["ic_val"].mean() if not h_data.empty else 0
                    print(f" {val:>7.4f}", end="")
                print()

    # Final summary
    all_confirmed = []
    for tf in ["1d", "4h"]:
        for direction in ["long", "short"]:
            sub = h1[(h1["timeframe"] == tf) & (h1["direction"] == direction)]
            for ind in sub["indicator"].unique():
                ind_data = sub[sub["indicator"] == ind]
                ic_t = ind_data["ic_train"].mean()
                ic_v = ind_data["ic_val"].mean()
                fdr_n = ind_data["fdr_val"].sum()
                if ic_t > 0.005 and ic_v > 0.005 and fdr_n > 0:
                    all_confirmed.append({"indicator": ind, "tf": tf, "dir": direction,
                                          "ic_train": ic_t, "ic_val": ic_v})

    print(f"\n  ── FINAL: {len(all_confirmed)} CONFIRMED indicator×TF×direction combinations ──")
    for c in sorted(all_confirmed, key=lambda x: -x["ic_val"]):
        print(f"  {c['indicator']:<25s} {c['tf']} {c['dir']:<6s} IC_train={c['ic_train']:.4f} IC_val={c['ic_val']:.4f}")

    print("=" * 115)


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    args_p = argparse.ArgumentParser()
    args_p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    args_p.add_argument("--macro-dir", default=str(ROOT / "data" / "raw" / "macro"))
    args_p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "research" / "step1_v2"))
    args = args_p.parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    store = ParquetStore(base_dir=Path(args.data_dir))
    resampler = OHLCVResampler()
    macro_cache = None
    try:
        from suitetrading.data.macro_cache import MacroCacheManager
        macro_cache = MacroCacheManager(cache_dir=Path(args.macro_dir))
    except Exception:
        pass
    futures_dl = None
    try:
        from suitetrading.data.futures import BinanceFuturesDownloader
        futures_dl = BinanceFuturesDownloader(output_dir=Path(args.data_dir))
    except Exception:
        pass

    indicators = sorted(set(INDICATOR_REGISTRY.keys()) - EXCLUDE)
    assets = STOCK_SYMBOLS + CRYPTO_SYMBOLS
    logger.info("Step 1 v2: {} ind × {} TFs × {} assets × 2 dirs × 5 configs × {} horizons",
                len(indicators), len(ALL_TIMEFRAMES), len(assets), len(FORWARD_HORIZONS))
    logger.info("Train/Val split: {:.0%}/{:.0%}", TRAIN_RATIO, 1 - TRAIN_RATIO)

    all_results: list[dict] = []
    count = 0

    for asset in assets:
        ac = "stocks" if asset in STOCK_SYMBOLS else "crypto"
        for tf in ALL_TIMEFRAMES:
            ohlcv = load_and_enrich(asset, tf, store, resampler, macro_cache, futures_dl)
            if ohlcv is None:
                continue
            logger.info("Scanning {} {} ({} bars, split at {})...",
                        asset, tf, len(ohlcv), int(len(ohlcv) * TRAIN_RATIO))

            for ind in indicators:
                for r in scan_indicator(ind, ohlcv, tf, asset, ac):
                    all_results.append(asdict(r))
                    count += 1
            if count % 500 == 0:
                logger.info("  {} measurements", count)

    df = pd.DataFrame(all_results)
    df.to_csv(output_dir / "edge_summary_v2.csv", index=False)
    logger.info("Saved {} measurements", len(df))
    report(df)


if __name__ == "__main__":
    main()
