#!/usr/bin/env python3
"""Step 1 v3: Deep param sweep IC Scanner.

Improvements over v2:
  - Multi-param grid (all numeric params, not just primary)
  - Grid capped at 20 configs via Latin Hypercube Sampling for large spaces
  - More forward horizons: [1, 2, 3, 5, 8, 10, 15, 20]
  - Reports: avg IC, % configs IC+OOS, best config IC OOS (flagged as upper bound)
  - Train 60% / Validation 40% split
  - FDR correction (Benjamini-Hochberg)

Usage: python scripts/research/step1_ic_scanner_v3.py
"""

from __future__ import annotations

import argparse
import itertools
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
ALL_TIMEFRAMES_FULL = ["1w", "1d", "4h", "1h", "15m"]
ALL_TIMEFRAMES = ALL_TIMEFRAMES_FULL  # default: all TFs including 1h/15m
FORWARD_HORIZONS = [1, 2, 3, 5, 8, 10, 15, 20]
EXCLUDE = {"atr", "cs_momentum"}
# Macro indicators require stock-only data columns (VIX, yield_spread, etc.)
# They produce no_valid_configs for crypto — skip them when scanning crypto-only
MACRO_INDICATORS = {"vrp", "yield_curve", "credit_spread", "hurst"}
MACRO_KEYS = ["vix", "yield_spread", "hy_spread"]
TRAIN_RATIO = 0.60
MAX_CONFIGS = 20  # Cap per indicator
SEED = 42

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


def _multi_param_grid(indicator_name: str, max_configs: int = MAX_CONFIGS) -> list[dict]:
    """Generate multi-param grid, capped via LHS if too large."""
    ind = get_indicator(indicator_name)
    schema = ind.params_schema()
    rng = np.random.default_rng(SEED)

    # Extract defaults
    defaults = {}
    for k, v in schema.items():
        if "default" in v:
            defaults[k] = v["default"]
        elif "choices" in v:
            defaults[k] = v["choices"][0]
        elif "min" in v:
            defaults[k] = v["min"]

    # Build value grids for numeric params
    param_grids: dict[str, list] = {}
    for k, v in schema.items():
        if k in ("hold_bars", "mode"):
            continue
        if v.get("type") not in ("int", "float") or "min" not in v or "max" not in v:
            continue
        lo, hi = v["min"], v["max"]
        n_vals = 5
        if v["type"] == "int":
            vals = sorted(set(int(x) for x in np.linspace(lo, hi, n_vals)))
        else:
            vals = [round(lo + i * (hi - lo) / (n_vals - 1), 4) for i in range(n_vals)]
        param_grids[k] = vals

    if not param_grids:
        return [defaults]

    # Full grid size
    grid_size = 1
    for vals in param_grids.values():
        grid_size *= len(vals)

    if grid_size <= max_configs:
        # Full grid is small enough — use it
        keys = list(param_grids.keys())
        configs = []
        for combo in itertools.product(*[param_grids[k] for k in keys]):
            cfg = dict(defaults)
            for k, v in zip(keys, combo):
                cfg[k] = v
            configs.append(cfg)
        return configs
    else:
        # Latin Hypercube Sampling
        keys = list(param_grids.keys())
        configs = []
        for _ in range(max_configs):
            cfg = dict(defaults)
            for k in keys:
                cfg[k] = rng.choice(param_grids[k])
            configs.append(cfg)
        # Ensure defaults are included
        configs[0] = dict(defaults)
        return configs


# ── Core ──────────────────────────────────────────────────────────────

@dataclass
class ICResult:
    indicator: str = ""
    timeframe: str = ""
    asset: str = ""
    asset_class: str = ""
    direction: str = ""
    horizon: int = 1
    # Config-AVERAGED metrics (unbiased)
    ic_train_avg: float = 0.0
    ic_val_avg: float = 0.0
    hr_train_avg: float = 0.0
    hr_val_avg: float = 0.0
    edge_return_val_avg: float = 0.0
    # Robustness: what % of configs have IC > 0 in OOS?
    pct_configs_ic_pos_val: float = 0.0
    # Best single config (upper bound, flagged as such)
    ic_val_best_config: float = 0.0
    ic_train_of_best_val: float = 0.0
    best_config_label: str = ""
    # Stats
    n_configs_valid: int = 0
    ic_configs_std: float = 0.0
    n_signals_avg: int = 0
    n_bars_train: int = 0
    n_bars_val: int = 0
    # Significance
    ic_train_pvalue: float = 1.0
    ic_val_pvalue: float = 1.0
    fdr_significant: bool = False
    low_confidence: bool = False
    status: str = "ok"


def compute_ic_split(signal, close, direction, horizon, split_idx):
    fwd = close.pct_change(horizon).shift(-horizon)
    if direction == "short":
        fwd = -fwd
    df = pd.DataFrame({"sig": signal, "ret": fwd}).dropna()
    train, val = df.iloc[:split_idx], df.iloc[split_idx:]

    def _ic(chunk):
        if len(chunk) < 30 or chunk["sig"].sum() < 3 or chunk["sig"].std() == 0:
            return None
        sig, ret = chunk["sig"].astype(float).values, chunk["ret"].values
        corr, pval = sp_stats.spearmanr(sig, ret)
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


def scan_indicator(ind_name, ohlcv, tf, asset, ac):
    configs = _multi_param_grid(ind_name)
    schema = get_indicator(ind_name).params_schema()
    has_mode = "mode" in schema
    split_idx = int(len(ohlcv) * TRAIN_RATIO)
    results = []

    for direction in ["long", "short"]:
        mode_ov = {}
        if has_mode:
            m = LONG_MODES if direction == "long" else SHORT_MODES
            if ind_name in m:
                mode_ov["mode"] = m[ind_name]

        for horizon in FORWARD_HORIZONS:
            train_ics, val_ics, val_hrs, val_edges, val_nsigs = [], [], [], [], []
            best_val_ic, best_train_ic, best_label = -999, 0, ""

            for cfg in configs:
                params = {**cfg, **mode_ov}
                label = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if k not in ("hold_bars", "mode"))
                try:
                    sig = get_indicator(ind_name).compute(ohlcv, **params)
                except Exception:
                    continue

                t, v = compute_ic_split(sig, ohlcv["close"], direction, horizon, split_idx)
                if t is None:
                    continue

                train_ics.append(t["ic"])
                if v is not None:
                    val_ics.append(v["ic"])
                    val_hrs.append(v["hr"])
                    val_edges.append(v["edge_ret"])
                    val_nsigs.append(v["n_sig"])
                    if v["ic"] > best_val_ic:
                        best_val_ic = v["ic"]
                        best_train_ic = t["ic"]
                        best_label = label

            if not train_ics:
                results.append(ICResult(
                    indicator=ind_name, timeframe=tf, asset=asset, asset_class=ac,
                    direction=direction, horizon=horizon, status="no_valid_configs",
                ))
                continue

            # P-values via t-test on config IC distributions
            train_p = sp_stats.ttest_1samp(train_ics, 0).pvalue if len(train_ics) >= 3 else 1.0
            val_p = sp_stats.ttest_1samp(val_ics, 0).pvalue if len(val_ics) >= 3 else 1.0

            r = ICResult(
                indicator=ind_name, timeframe=tf, asset=asset, asset_class=ac,
                direction=direction, horizon=horizon,
                ic_train_avg=float(np.mean(train_ics)),
                ic_val_avg=float(np.mean(val_ics)) if val_ics else 0.0,
                hr_train_avg=0.0,  # not tracked per-config in v3
                hr_val_avg=float(np.mean(val_hrs)) if val_hrs else 0.0,
                edge_return_val_avg=float(np.mean(val_edges)) if val_edges else 0.0,
                pct_configs_ic_pos_val=float(np.mean([ic > 0 for ic in val_ics])) if val_ics else 0.0,
                ic_val_best_config=best_val_ic if best_val_ic > -999 else 0.0,
                ic_train_of_best_val=best_train_ic,
                best_config_label=best_label,
                n_configs_valid=len(train_ics),
                ic_configs_std=float(np.std(val_ics)) if len(val_ics) > 1 else 0.0,
                n_signals_avg=int(np.mean(val_nsigs)) if val_nsigs else 0,
                n_bars_train=split_idx,
                n_bars_val=len(ohlcv) - split_idx,
                ic_train_pvalue=float(train_p) if np.isfinite(train_p) else 1.0,
                ic_val_pvalue=float(val_p) if np.isfinite(val_p) else 1.0,
                low_confidence=(tf == "1w"),
            )
            results.append(r)

    return results


# ── Data loading (same as v2) ─────────────────────────────────────────

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


# ── FDR ───────────────────────────────────────────────────────────────

def apply_fdr(pvals, alpha=0.05):
    n = len(pvals)
    idx = np.argsort(pvals)
    sorted_p = pvals[idx]
    bh = np.arange(1, n + 1) / n * alpha
    sig = np.zeros(n, dtype=bool)
    max_k = -1
    for k in range(n):
        if sorted_p[k] <= bh[k]:
            max_k = k
    if max_k >= 0:
        sig[idx[:max_k + 1]] = True
    return sig


# ── Report ────────────────────────────────────────────────────────────

def report(df):
    ok = df[df["status"] == "ok"].copy()
    if ok.empty:
        return

    ok["fdr_sig"] = apply_fdr(ok["ic_val_pvalue"].values)
    h1 = ok[ok["horizon"] == 1]

    print("\n" + "=" * 130)
    print("  STEP 1 v3: DEEP PARAM SWEEP — Multi-param grid (up to 20 configs), Train/Val 60/40, FDR")
    print(f"  Horizons: {FORWARD_HORIZONS}")
    print("  IC_avg = average across ALL configs (unbiased). IC_best = best single config (upper bound).")
    print("  %IC+ = what fraction of configs have IC > 0 in OOS (param robustness).")
    print("=" * 130)

    report_tfs = sorted(ok["timeframe"].unique(), key=lambda t: {"1w": 0, "1d": 1, "4h": 2, "1h": 3, "15m": 4, "5m": 5}.get(t, 9))
    for tf in report_tfs:
        if tf == "1w":
            continue  # weekly reported separately (low confidence)
        for direction in ["long", "short"]:
            sub = h1[(h1["timeframe"] == tf) & (h1["direction"] == direction)]
            if sub.empty:
                continue

            ranking = sub.groupby("indicator").agg(
                ic_avg=("ic_val_avg", "mean"),
                ic_best=("ic_val_best_config", "mean"),
                hr=("hr_val_avg", "mean"),
                pct_ic_pos=("pct_configs_ic_pos_val", "mean"),
                fdr_n=("fdr_sig", "sum"),
                n_assets=("asset", "nunique"),
                n_pos_assets=("ic_val_avg", lambda x: (x > 0).sum()),
                cfg_std=("ic_configs_std", "mean"),
                n_cfgs=("n_configs_valid", "mean"),
                edge_ret=("edge_return_val_avg", "mean"),
            ).sort_values("ic_avg", ascending=False)

            confirmed = ((ranking["ic_avg"] > 0.003) & (ranking["pct_ic_pos"] > 0.5) & (ranking["fdr_n"] > 0)).sum()

            print(f"\n  ── {tf} {direction.upper()} ({confirmed} confirmed) ──")
            print(f"  {'Indicator':<25s} {'IC_avg':>7s} {'IC_best':>8s} {'HR':>6s} {'%IC+':>5s} {'FDR+':>5s} {'A+':>4s} {'Cfgs':>5s} {'EdgeRet':>8s} Status")
            print(f"  {'-'*25} {'-'*7} {'-'*8} {'-'*6} {'-'*5} {'-'*5} {'-'*4} {'-'*5} {'-'*8} {'-'*12}")

            for ind, r in ranking.head(20).iterrows():
                fdr_str = f"{int(r['fdr_n'])}/{int(r['n_assets'])}"
                apos = f"{int(r['n_pos_assets'])}/{int(r['n_assets'])}"

                if r["ic_avg"] > 0.003 and r["pct_ic_pos"] > 0.5 and r["fdr_n"] > 0:
                    status = "CONFIRMED"
                elif r["ic_avg"] > 0.003 and r["pct_ic_pos"] > 0.5:
                    status = "robust"
                elif r["ic_avg"] > 0.003:
                    status = "promising"
                elif r["ic_avg"] > 0:
                    status = "weak"
                else:
                    status = "."

                print(f"  {ind:<25s} {r['ic_avg']:>7.4f} {r['ic_best']:>8.4f} {r['hr']:>5.1%} {r['pct_ic_pos']:>4.0%} {fdr_str:>5s} {apos:>4s} {r['n_cfgs']:>5.0f} {r['edge_ret']*100:>7.3f}% {status}")

    # Multi-horizon for confirmed
    print(f"\n  ── MULTI-HORIZON (IC_avg OOS) ──")
    for tf in report_tfs:
        if tf == "1w":
            continue
        for direction in ["long", "short"]:
            sub = ok[(ok["timeframe"] == tf) & (ok["direction"] == direction)]
            h1_sub = sub[sub["horizon"] == 1]
            ranking = h1_sub.groupby("indicator").agg(
                ic_avg=("ic_val_avg", "mean"), pct_pos=("pct_configs_ic_pos_val", "mean"),
                fdr=("fdr_sig", "sum"),
            )
            good = ranking[(ranking["ic_avg"] > 0.003) & (ranking["pct_pos"] > 0.45)]
            if good.empty:
                continue
            print(f"\n  {tf} {direction}:")
            print(f"  {'Indicator':<25s}", end="")
            for h in FORWARD_HORIZONS:
                print(f" {'h='+str(h):>7s}", end="")
            print(" best_h")
            for ind in good.sort_values("ic_avg", ascending=False).index:
                print(f"  {ind:<25s}", end="")
                best_ic, best_h = -1, 1
                for h in FORWARD_HORIZONS:
                    hd = sub[(sub["indicator"] == ind) & (sub["horizon"] == h)]
                    v = hd["ic_val_avg"].mean() if not hd.empty else 0
                    print(f" {v:>7.4f}", end="")
                    if v > best_ic:
                        best_ic, best_h = v, h
                print(f"   h={best_h}")

    # Weekly (low confidence)
    print(f"\n  ── WEEKLY (descriptive only — low n) ──")
    w1 = h1[h1["timeframe"] == "1w"]
    for direction in ["long", "short"]:
        ws = w1[w1["direction"] == direction]
        if ws.empty:
            continue
        r = ws.groupby("indicator").agg(ic_avg=("ic_val_avg", "mean"), pct_pos=("pct_configs_ic_pos_val", "mean")).sort_values("ic_avg", ascending=False).head(5)
        inds = ", ".join(f"{ind}(IC={row['ic_avg']:.3f}, {row['pct_pos']:.0%}IC+)" for ind, row in r.iterrows())
        print(f"  1w {direction}: {inds}")

    # Final summary
    all_confirmed = []
    for tf in report_tfs:
        if tf == "1w":
            continue
        for direction in ["long", "short"]:
            sub = h1[(h1["timeframe"] == tf) & (h1["direction"] == direction)]
            for ind in sub["indicator"].unique():
                d = sub[sub["indicator"] == ind]
                ic = d["ic_val_avg"].mean()
                pct = d["pct_configs_ic_pos_val"].mean()
                fdr = d["fdr_sig"].sum()
                n_a = d["asset"].nunique()
                if ic > 0.003 and pct > 0.5 and fdr > 0:
                    all_confirmed.append({"ind": ind, "tf": tf, "dir": direction,
                                          "ic_avg": ic, "pct_ic+": pct, "fdr": f"{int(fdr)}/{n_a}"})

    print(f"\n  ── FINAL: {len(all_confirmed)} CONFIRMED (IC_avg > 0.003, >50% configs IC+, FDR significant) ──")
    for c in sorted(all_confirmed, key=lambda x: -x["ic_avg"]):
        print(f"  {c['ind']:<25s} {c['tf']} {c['dir']:<6s} IC_avg={c['ic_avg']:.4f} %IC+={c['pct_ic+']:.0%} FDR={c['fdr']}")

    print("=" * 130)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    args_p = argparse.ArgumentParser()
    args_p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    args_p.add_argument("--macro-dir", default=str(ROOT / "data" / "raw" / "macro"))
    args_p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "research" / "step1_v3"))
    args_p.add_argument("--symbols", nargs="+", default=None,
                        help="Override symbols (default: all stocks + crypto)")
    args_p.add_argument("--timeframes", nargs="+", default=None,
                        help="Override timeframes (default: 1w 1d 4h 1h 15m)")
    args_p.add_argument("--crypto-only", action="store_true",
                        help="Only scan crypto symbols")
    args_p.add_argument("--stocks-only", action="store_true",
                        help="Only scan stock symbols")
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

    # Resolve symbols
    if args.symbols:
        assets = args.symbols
    elif args.crypto_only:
        assets = CRYPTO_SYMBOLS
    elif args.stocks_only:
        assets = STOCK_SYMBOLS
    else:
        assets = STOCK_SYMBOLS + CRYPTO_SYMBOLS

    # Resolve timeframes
    timeframes = args.timeframes if args.timeframes else ALL_TIMEFRAMES

    indicators = sorted(set(INDICATOR_REGISTRY.keys()) - EXCLUDE)
    logger.info("Step 1 v3: {} ind × {} TFs × {} assets × 2 dirs × up to {} configs × {} horizons",
                len(indicators), len(timeframes), len(assets), MAX_CONFIGS, len(FORWARD_HORIZONS))

    all_results = []
    count = 0
    for asset in assets:
        ac = "stocks" if asset in STOCK_SYMBOLS else "crypto"
        for tf in timeframes:
            ohlcv = load_and_enrich(asset, tf, store, resampler, macro_cache, futures_dl)
            if ohlcv is None:
                continue
            logger.info("Scanning {} {} ({} bars)...", asset, tf, len(ohlcv))
            for ind in indicators:
                # Skip macro indicators for crypto (no data columns available)
                if ac == "crypto" and ind in MACRO_INDICATORS:
                    continue
                for r in scan_indicator(ind, ohlcv, tf, asset, ac):
                    all_results.append(asdict(r))
                    count += 1
            if count % 1000 == 0:
                logger.info("  {} measurements", count)

    df = pd.DataFrame(all_results)
    df.to_csv(output_dir / "edge_summary_v3.csv", index=False)
    logger.info("Saved {} measurements", len(df))
    report(df)


if __name__ == "__main__":
    main()
