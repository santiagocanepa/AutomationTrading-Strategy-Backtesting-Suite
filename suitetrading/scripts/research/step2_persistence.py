#!/usr/bin/env python3
"""Step 2: Signal Persistence — How long does a HTF signal's edge last in lower TFs?

For each indicator with edge in Step 1 (1w, 1d), measures: when the signal
fires on TF_high, what is the cumulative forward return on TF_low at
N bars forward? This reveals the "half-life" of the signal.

A signal with high persistence is usable as an HTF filter: it creates a
WINDOW of bars in the lower TF where entries have positive expected return.

Output: persistence curves and half-life metrics per (indicator, TF_high→TF_low).

Usage
-----
python scripts/research/step2_persistence.py
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
from suitetrading.indicators.registry import get_indicator

warnings.filterwarnings("ignore", category=RuntimeWarning)

# ── Configuration ─────────────────────────────────────────────────────

STOCK_SYMBOLS = ["SPY", "QQQ", "GLD", "TLT", "XLE", "XLK", "IWM", "AAPL", "NVDA", "TSLA"]
CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT"]
MACRO_KEYS = ["vix", "yield_spread", "hy_spread"]

# Indicators with STRONG edge from Step 1 — candidates for HTF filters
# Format: (indicator_name, tf_high, direction, mode_override)
HTF_CANDIDATES = [
    # Weekly LONG (trend signals — IC grows with horizon)
    ("ssl_channel", "1w", "long", {}),
    ("macd", "1w", "long", {"mode": "bullish"}),
    ("momentum_divergence", "1w", "long", {"mode": "bullish"}),
    ("roc", "1w", "long", {"mode": "bullish"}),
    ("hurst", "1w", "long", {"mode": "trending"}),
    # Weekly SHORT
    ("macd", "1w", "short", {"mode": "bearish"}),
    ("momentum_divergence", "1w", "short", {"mode": "bearish"}),
    ("vrp", "1w", "short", {"mode": "risk_off"}),
    ("hurst", "1w", "short", {"mode": "trending"}),
    ("ema", "1w", "short", {"mode": "below"}),
    # Daily LONG
    ("yield_curve", "1d", "long", {"mode": "normal"}),
    ("adx_filter", "1d", "long", {"mode": "strong"}),
    ("ema", "1d", "long", {"mode": "above"}),
    ("volatility_regime", "1d", "long", {"mode": "trending"}),
    # Daily SHORT
    ("vrp", "1d", "short", {"mode": "risk_off"}),
    ("yield_curve", "1d", "short", {"mode": "inverted"}),
    ("hurst", "1d", "short", {"mode": "trending"}),
    ("ichimoku", "1d", "short", {"mode": "bearish"}),
]

# TF cascades to measure persistence into
TF_CASCADES = {
    "1w": ["1d", "4h", "1h"],
    "1d": ["4h", "1h", "15m"],
}

# Forward bars to measure at each lower TF
FORWARD_BARS = [1, 2, 4, 8, 16, 24, 32, 48, 64, 96]


# ── Data contract ─────────────────────────────────────────────────────

@dataclass
class PersistenceMetric:
    indicator: str = ""
    tf_high: str = ""
    tf_low: str = ""
    direction: str = ""
    asset: str = ""
    asset_class: str = ""
    forward_bars: int = 0
    mean_cumret: float = 0.0         # avg cumulative return at N bars
    median_cumret: float = 0.0
    hit_rate: float = 0.0            # % of signals with positive cumret at N bars
    n_signals: int = 0
    pvalue: float = 1.0              # t-test: is mean_cumret != 0?
    baseline_cumret: float = 0.0     # avg cumret at N bars for ALL bars (not just signals)


# ── Core computation ──────────────────────────────────────────────────

def compute_persistence(
    signal_htf: pd.Series,
    close_ltf: pd.Series,
    direction: str,
    forward_bars_list: list[int],
) -> list[PersistenceMetric]:
    """Measure persistence of HTF signal edge in LTF forward returns."""
    # Align: for each bar where signal_htf is True, find the corresponding
    # position in the LTF series and measure forward cumulative return
    signal_times = signal_htf[signal_htf].index
    if len(signal_times) < 5:
        return []

    results = []
    for n_bars in forward_bars_list:
        cum_rets = []
        baseline_rets = []

        for t in signal_times:
            # Find the LTF bar at or after the signal time
            ltf_after = close_ltf.index.searchsorted(t)
            if ltf_after + n_bars >= len(close_ltf):
                continue

            entry_price = close_ltf.iloc[ltf_after]
            exit_price = close_ltf.iloc[ltf_after + n_bars]

            if entry_price <= 0:
                continue

            ret = (exit_price / entry_price - 1)
            if direction == "short":
                ret = -ret
            cum_rets.append(ret)

        # Baseline: random entry at every LTF bar
        step = max(n_bars, 10)
        for i in range(0, len(close_ltf) - n_bars, step):
            entry_p = close_ltf.iloc[i]
            exit_p = close_ltf.iloc[i + n_bars]
            if entry_p > 0:
                r = exit_p / entry_p - 1
                if direction == "short":
                    r = -r
                baseline_rets.append(r)

        if len(cum_rets) < 5:
            continue

        arr = np.array(cum_rets)
        base_arr = np.array(baseline_rets) if baseline_rets else np.array([0.0])
        _, pval = sp_stats.ttest_1samp(arr, 0) if len(arr) >= 5 else (0, 1.0)

        m = PersistenceMetric(
            forward_bars=n_bars,
            mean_cumret=float(np.mean(arr)),
            median_cumret=float(np.median(arr)),
            hit_rate=float((arr > 0).mean()),
            n_signals=len(arr),
            pvalue=float(pval) if np.isfinite(pval) else 1.0,
            baseline_cumret=float(np.mean(base_arr)),
        )
        results.append(m)

    return results


def get_best_params(indicator_name: str, mode_override: dict) -> dict:
    """Get params: use Step 1 best config logic (sweep midpoint + mode override)."""
    ind = get_indicator(indicator_name)
    schema = ind.params_schema()
    params = {}
    for k, v in schema.items():
        if "default" in v:
            params[k] = v["default"]
        elif "choices" in v:
            params[k] = v["choices"][0]
        elif "min" in v:
            params[k] = v["min"]

    # Use midpoint of primary param range (better than min for most indicators)
    for k, v in schema.items():
        if k in ("hold_bars", "mode"):
            continue
        if v.get("type") in ("int", "float") and "min" in v and "max" in v:
            mid = (v["min"] + v["max"]) / 2
            params[k] = int(mid) if v["type"] == "int" else round(mid, 4)
            break

    params.update(mode_override)
    return params


# ── Main ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Step 2: Signal Persistence Analyzer")
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--macro-dir", default=str(ROOT / "data" / "raw" / "macro"))
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "research" / "step2_persistence"))
    return p.parse_args()


def main() -> None:
    args = parse_args()
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

    all_assets = STOCK_SYMBOLS + CRYPTO_SYMBOLS
    total = len(HTF_CANDIDATES) * len(all_assets) * 3  # ~3 LTF per HTF
    logger.info("Step 2: Measuring persistence for {} HTF signals × {} assets", len(HTF_CANDIDATES), len(all_assets))

    all_results: list[dict] = []
    count = 0

    for asset in all_assets:
        asset_class = "stocks" if asset in STOCK_SYMBOLS else "crypto"
        exchange = "alpaca" if asset in STOCK_SYMBOLS else "binance"

        try:
            raw = store.read(exchange, asset, "1m")
        except FileNotFoundError:
            continue
        if raw.empty:
            continue

        # Pre-resample all needed TFs
        ohlcv_cache: dict[str, pd.DataFrame] = {}
        for tf in ["1w", "1d", "4h", "1h", "15m"]:
            try:
                ohlcv_cache[tf] = resampler.resample(raw, tf, base_tf="1m")
            except Exception:
                pass

        # Enrich macro for stocks
        if asset_class == "stocks" and macro_cache is not None:
            for tf in ohlcv_cache:
                df = ohlcv_cache[tf]
                aligned = macro_cache.get_aligned(MACRO_KEYS, df.index)
                for col in aligned.columns:
                    if not aligned[col].isna().all():
                        df[col] = aligned[col].values
                hyg_lqd = macro_cache.get_aligned(["hyg", "lqd"], df.index)
                if not hyg_lqd["hyg"].isna().all() and not hyg_lqd["lqd"].isna().all():
                    df["credit_spread"] = (hyg_lqd["hyg"] / hyg_lqd["lqd"]).values

        # Enrich futures for crypto
        if asset_class == "crypto" and futures_dl is not None:
            for tf in ohlcv_cache:
                try:
                    ohlcv_cache[tf] = futures_dl.load_and_merge(asset, ohlcv_cache[tf])
                except Exception:
                    pass

        for ind_name, tf_high, direction, mode_override in HTF_CANDIDATES:
            if tf_high not in ohlcv_cache:
                continue

            ohlcv_htf = ohlcv_cache[tf_high]
            params = get_best_params(ind_name, mode_override)

            try:
                ind = get_indicator(ind_name)
                signal = ind.compute(ohlcv_htf, **params)
            except Exception as e:
                logger.debug("  {} {} {} {}: compute error: {}", ind_name, tf_high, asset, direction, e)
                continue

            n_signals = signal.sum()
            if n_signals < 5:
                continue

            # Measure persistence into each lower TF
            for tf_low in TF_CASCADES.get(tf_high, []):
                if tf_low not in ohlcv_cache:
                    continue

                close_ltf = ohlcv_cache[tf_low]["close"]
                persistence = compute_persistence(signal, close_ltf, direction, FORWARD_BARS)

                for m in persistence:
                    m.indicator = ind_name
                    m.tf_high = tf_high
                    m.tf_low = tf_low
                    m.direction = direction
                    m.asset = asset
                    m.asset_class = asset_class
                    all_results.append(asdict(m))

                count += 1
                if count % 50 == 0:
                    logger.info("  Progress: {} cascade measurements", count)

    # Save
    df = pd.DataFrame(all_results)
    df.to_csv(output_dir / "persistence_full.csv", index=False)
    logger.info("Saved {} measurements to {}", len(df), output_dir / "persistence_full.csv")

    # Report
    print_persistence_report(df, output_dir)


def print_persistence_report(df: pd.DataFrame, output_dir: Path) -> None:
    """Generate persistence report."""
    if df.empty:
        print("No results.")
        return

    print("\n" + "=" * 110)
    print("  STEP 2: SIGNAL PERSISTENCE — HOW LONG DOES HTF EDGE LAST IN LTF?")
    print("=" * 110)

    # Group by (indicator, tf_high, tf_low, direction)
    grouped = df.groupby(["indicator", "tf_high", "tf_low", "direction"])

    for (ind, tf_h, tf_l, dirn), grp in sorted(grouped, key=lambda x: -x[1].groupby("forward_bars")["mean_cumret"].mean().max()):
        by_bars = grp.groupby("forward_bars").agg(
            mean_ret=("mean_cumret", "mean"),
            mean_hr=("hit_rate", "mean"),
            n_sig=("n_signals", "mean"),
            mean_baseline=("baseline_cumret", "mean"),
            mean_pval=("pvalue", "mean"),
        ).sort_index()

        # Find peak return and half-life
        if by_bars.empty:
            continue

        peak_ret = by_bars["mean_ret"].max()
        peak_bar = by_bars["mean_ret"].idxmax()
        excess = by_bars["mean_ret"] - by_bars["mean_baseline"]
        peak_excess = excess.max()

        if peak_excess <= 0:
            continue

        # Half-life: first bar where excess drops below 50% of peak
        half_bar = "N/A"
        for bars, ex in excess.items():
            if ex < peak_excess * 0.5:
                half_bar = str(bars)
                break

        sig_str = "***" if by_bars["mean_pval"].min() < 0.01 else "**" if by_bars["mean_pval"].min() < 0.05 else "*" if by_bars["mean_pval"].min() < 0.10 else ""

        print(f"\n  {ind} {tf_h}→{tf_l} {dirn} {sig_str}")
        print(f"  {'Bars':>6s} {'AvgRet':>8s} {'Baseline':>9s} {'Excess':>8s} {'HR':>6s} {'p-val':>7s}")
        for bars, row in by_bars.iterrows():
            ex = row["mean_ret"] - row["mean_baseline"]
            pstr = f'{row["mean_pval"]:.3f}' if row["mean_pval"] < 0.1 else "n.s."
            print(f"  {bars:>6d} {row['mean_ret']*100:>7.3f}% {row['mean_baseline']*100:>8.3f}% {ex*100:>7.3f}% {row['mean_hr']:>5.1%} {pstr:>7s}")
        print(f"  Peak: {peak_bar} bars ({peak_ret*100:.3f}%), half-life: {half_bar} bars")

    # Summary: best cascades
    print(f"\n  ── BEST HTF→LTF CASCADES (by peak excess return) ──")
    summary_rows = []
    for (ind, tf_h, tf_l, dirn), grp in grouped:
        by_bars = grp.groupby("forward_bars").agg(
            mean_ret=("mean_cumret", "mean"),
            mean_baseline=("baseline_cumret", "mean"),
            mean_pval=("pvalue", "mean"),
        )
        excess = by_bars["mean_ret"] - by_bars["mean_baseline"]
        if excess.max() > 0:
            peak_bar = excess.idxmax()
            summary_rows.append({
                "indicator": ind, "tf_high": tf_h, "tf_low": tf_l,
                "direction": dirn, "peak_excess": excess.max(),
                "peak_bar": peak_bar, "p_at_peak": by_bars.loc[peak_bar, "mean_pval"],
            })

    summary = pd.DataFrame(summary_rows).sort_values("peak_excess", ascending=False)
    summary.to_csv(output_dir / "persistence_summary.csv", index=False)

    print(f"  {'Indicator':<25s} {'HTF→LTF':<12s} {'Dir':<6s} {'PeakExcess':>10s} {'@Bars':>6s} {'p-val':>7s}")
    for _, r in summary.head(20).iterrows():
        pstr = f'{r["p_at_peak"]:.3f}' if r["p_at_peak"] < 0.1 else "n.s."
        print(f"  {r['indicator']:<25s} {r['tf_high']}→{r['tf_low']:<7s} {r['direction']:<6s} {r['peak_excess']*100:>9.3f}% {int(r['peak_bar']):>6d} {pstr:>7s}")

    print("=" * 110)


if __name__ == "__main__":
    main()
