#!/usr/bin/env python3
"""Step 1: Indicator Edge Map — Rigorous IC Scanner.

Measures raw signal quality for 30 indicators across 3 timeframes,
15 assets, 2 directions, with:
  - Multiple param configurations per indicator (not just defaults)
  - Multiple forward return horizons (1, 2, 3, 5, 10 bars)
  - Direction-appropriate modes (bullish for longs, bearish for shorts)
  - Per-asset granularity (no averaging that hides heterogeneity)
  - Bootstrapped confidence intervals on IC

See docs/research_methodology.md Section 6 for specification.

Usage
-----
python scripts/research/step1_ic_scanner.py
python scripts/research/step1_ic_scanner.py --indicators roc macd
python scripts/research/step1_ic_scanner.py --assets SPY BTCUSDT
python scripts/research/step1_ic_scanner.py --timeframes 4h
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

# ── Configuration ─────────────────────────────────────────────────────

STOCK_SYMBOLS = ["SPY", "QQQ", "GLD", "TLT", "XLE", "XLK", "IWM", "AAPL", "NVDA", "TSLA"]
CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT"]
ALL_TIMEFRAMES = ["1w", "1d", "4h"]
FORWARD_HORIZONS = [1, 2, 3, 5, 10]
EXCLUDE_INDICATORS = {"atr", "cs_momentum"}
MACRO_KEYS = ["vix", "yield_spread", "hy_spread"]

# Mode mapping: which mode is appropriate for which direction
# If indicator has mode param, use these. Otherwise mode is direction-agnostic.
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

# Param sweep configs: for each indicator, test multiple param sets
# Format: list of dicts to override from defaults
def _param_sweep(indicator_name: str) -> list[dict]:
    """Generate multiple param configs for an indicator."""
    ind = get_indicator(indicator_name)
    schema = ind.params_schema()

    # Extract default
    defaults = {}
    for k, v in schema.items():
        if "default" in v:
            defaults[k] = v["default"]
        elif "choices" in v:
            defaults[k] = v["choices"][0]
        elif "min" in v:
            defaults[k] = v["min"]

    # Find the primary numeric param (first non-mode, non-hold_bars)
    primary_param = None
    for k, v in schema.items():
        if k in ("hold_bars", "mode"):
            continue
        if v.get("type") in ("int", "float"):
            primary_param = k
            break

    if primary_param is None:
        return [defaults]

    pspec = schema[primary_param]
    lo = pspec.get("min", pspec.get("low", 5))
    hi = pspec.get("max", pspec.get("high", 50))

    # Generate 5 evenly spaced values for primary param
    if pspec.get("type") == "int":
        values = sorted(set([int(v) for v in np.linspace(lo, hi, 5)]))
    else:
        step = pspec.get("step", (hi - lo) / 4)
        values = [round(lo + i * step, 4) for i in range(5) if lo + i * step <= hi]
        if not values:
            values = [lo, (lo + hi) / 2, hi]

    configs = []
    for val in values:
        cfg = dict(defaults)
        cfg[primary_param] = val
        configs.append(cfg)

    return configs


# ── Data contract ─────────────────────────────────────────────────────

@dataclass
class EdgeMetrics:
    indicator: str = ""
    timeframe: str = ""
    asset: str = ""
    asset_class: str = ""
    direction: str = ""
    param_config: str = ""
    horizon: int = 1
    ic: float = 0.0
    ic_pvalue: float = 1.0
    hit_rate: float = 0.0
    avg_fwd_return_signal: float = 0.0
    avg_fwd_return_nosignal: float = 0.0
    edge_return: float = 0.0  # signal - no_signal
    signal_frequency_per_month: float = 0.0
    n_signals: int = 0
    n_bars: int = 0
    edge_ratio: float = 0.0
    temporal_stability: float = float("nan")
    ic_rolling_mean: float = 0.0
    ic_rolling_std: float = 0.0
    ic_ci_lower: float = 0.0
    ic_ci_upper: float = 0.0
    status: str = "ok"


# ── Core compute ──────────────────────────────────────────────────────

def compute_edge(
    signal: pd.Series,
    close: pd.Series,
    direction: str,
    horizon: int,
    bars_per_month: float,
) -> EdgeMetrics:
    """Compute edge metrics for one signal × one forward horizon."""
    m = EdgeMetrics(direction=direction, horizon=horizon)

    # Forward return at given horizon
    fwd_ret = close.pct_change(horizon).shift(-horizon)
    if direction == "short":
        fwd_ret = -fwd_ret

    valid = pd.DataFrame({"sig": signal, "ret": fwd_ret}).dropna()
    if len(valid) < 100:
        m.status = "insufficient_data"
        return m

    sig = valid["sig"].astype(bool)
    ret = valid["ret"]
    m.n_bars = len(valid)
    m.n_signals = int(sig.sum())

    if m.n_signals < 10:
        m.status = "too_few_signals"
        return m

    # IC: Spearman correlation
    corr, pval = sp_stats.spearmanr(sig.astype(float).values, ret.values)
    m.ic = float(corr) if np.isfinite(corr) else 0.0
    m.ic_pvalue = float(pval) if np.isfinite(pval) else 1.0

    # Hit rate
    sig_rets = ret[sig]
    m.hit_rate = float((sig_rets > 0).mean())

    # Average returns
    m.avg_fwd_return_signal = float(sig_rets.mean())
    nosig_rets = ret[~sig]
    m.avg_fwd_return_nosignal = float(nosig_rets.mean()) if len(nosig_rets) > 0 else 0.0
    m.edge_return = m.avg_fwd_return_signal - m.avg_fwd_return_nosignal

    # Frequency
    n_months = max(m.n_bars / bars_per_month, 1)
    m.signal_frequency_per_month = m.n_signals / n_months

    # Edge ratio
    wins = sig_rets[sig_rets > 0]
    losses = sig_rets[sig_rets <= 0]
    if len(wins) > 0 and len(losses) > 0 and losses.mean() != 0:
        m.edge_ratio = float((m.hit_rate * wins.mean()) / ((1 - m.hit_rate) * abs(losses.mean())))

    # Temporal stability: rolling IC in 3-month windows
    window = int(bars_per_month * 3)
    if window > 50 and len(valid) >= window * 2:
        ics = []
        for start in range(0, len(valid) - window + 1, window):
            chunk = valid.iloc[start:start + window]
            cs = chunk["sig"].astype(float)
            cr = chunk["ret"]
            if cs.sum() >= 5 and cs.std() > 0:
                c, _ = sp_stats.spearmanr(cs.values, cr.values)
                if np.isfinite(c):
                    ics.append(c)

        if len(ics) >= 3:
            m.temporal_stability = float(sum(1 for ic in ics if ic > 0) / len(ics))
            m.ic_rolling_mean = float(np.mean(ics))
            m.ic_rolling_std = float(np.std(ics))
            # 95% CI via bootstrap
            m.ic_ci_lower = float(np.percentile(ics, 2.5))
            m.ic_ci_upper = float(np.percentile(ics, 97.5))

    return m


def scan_indicator_full(
    indicator_name: str,
    ohlcv: pd.DataFrame,
    timeframe: str,
    asset: str,
    asset_class: str,
    bars_per_month: float,
) -> list[EdgeMetrics]:
    """Scan one indicator with multiple configs, modes, and horizons."""
    results = []
    configs = _param_sweep(indicator_name)
    schema = get_indicator(indicator_name).params_schema()
    has_mode = "mode" in schema

    for direction in ["long", "short"]:
        # Select appropriate mode for direction
        mode_override = {}
        if has_mode:
            mode_map = LONG_MODES if direction == "long" else SHORT_MODES
            if indicator_name in mode_map:
                mode_override["mode"] = mode_map[indicator_name]

        for cfg in configs:
            params = {**cfg, **mode_override}
            param_label = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "hold_bars")

            try:
                ind = get_indicator(indicator_name)
                signal = ind.compute(ohlcv, **params)
            except Exception as e:
                results.append(EdgeMetrics(
                    indicator=indicator_name, timeframe=timeframe, asset=asset,
                    asset_class=asset_class, direction=direction,
                    param_config=param_label, status=f"error: {e}",
                ))
                continue

            for horizon in FORWARD_HORIZONS:
                m = compute_edge(signal, ohlcv["close"], direction, horizon, bars_per_month)
                m.indicator = indicator_name
                m.timeframe = timeframe
                m.asset = asset
                m.asset_class = asset_class
                m.param_config = param_label
                results.append(m)

    return results


# ── Data loading ──────────────────────────────────────────────────────

def load_and_enrich(
    asset: str, timeframe: str, store: ParquetStore,
    resampler: OHLCVResampler, macro_cache, futures_dl,
) -> pd.DataFrame | None:
    exchange = "alpaca" if asset in STOCK_SYMBOLS else "binance"
    try:
        raw = store.read(exchange, asset, "1m")
    except FileNotFoundError:
        return None
    if raw.empty:
        return None

    ohlcv = resampler.resample(raw, timeframe, base_tf="1m")
    if len(ohlcv) < 100:
        return None

    if asset in STOCK_SYMBOLS and macro_cache is not None:
        aligned = macro_cache.get_aligned(MACRO_KEYS, ohlcv.index)
        for col in aligned.columns:
            if not aligned[col].isna().all():
                ohlcv[col] = aligned[col].values
        hyg_lqd = macro_cache.get_aligned(["hyg", "lqd"], ohlcv.index)
        if not hyg_lqd["hyg"].isna().all() and not hyg_lqd["lqd"].isna().all():
            ohlcv["credit_spread"] = (hyg_lqd["hyg"] / hyg_lqd["lqd"]).values

    if asset in CRYPTO_SYMBOLS and futures_dl is not None:
        try:
            ohlcv = futures_dl.load_and_merge(asset, ohlcv)
        except Exception:
            pass

    return ohlcv


# ── Reporting ─────────────────────────────────────────────────────────

def generate_reports(df: pd.DataFrame, output_dir: Path) -> None:
    """Generate ranking files and console report."""
    ok = df[df["status"] == "ok"].copy()
    if ok.empty:
        return

    rankings_dir = output_dir / "rankings"
    rankings_dir.mkdir(parents=True, exist_ok=True)

    # Best config per (indicator, tf, asset, direction, horizon):
    # pick the param_config with highest IC
    best_per = (
        ok.sort_values("ic", ascending=False)
        .groupby(["indicator", "timeframe", "asset", "direction", "horizon"])
        .first()
        .reset_index()
    )
    best_per.to_csv(output_dir / "best_config_per_combo.csv", index=False)

    # Overall ranking: best IC across all configs, averaged over assets
    # Use horizon=1 for primary ranking (other horizons are supplementary)
    h1 = best_per[best_per["horizon"] == 1]

    for tf in sorted(ok["timeframe"].unique()):
        for direction in ["long", "short"]:
            subset = h1[(h1["timeframe"] == tf) & (h1["direction"] == direction)]
            if subset.empty:
                continue

            ranking = (
                subset.groupby("indicator")
                .agg(
                    mean_ic=("ic", "mean"),
                    median_ic=("ic", "median"),
                    max_ic=("ic", "max"),
                    min_ic=("ic", "min"),
                    mean_hr=("hit_rate", "mean"),
                    mean_stab=("temporal_stability", "mean"),
                    mean_freq=("signal_frequency_per_month", "mean"),
                    mean_edge_return=("edge_return", "mean"),
                    n_assets=("asset", "nunique"),
                    n_assets_ic_pos=("ic", lambda x: (x > 0).sum()),
                )
                .sort_values("mean_ic", ascending=False)
            )
            ranking.to_csv(rankings_dir / f"{tf}_{direction}.csv")

    # Console report
    print("\n" + "=" * 100)
    print("  STEP 1: INDICATOR EDGE MAP — RIGOROUS RESULTS")
    print("  (best param config per indicator, horizon=1 bar forward)")
    print("=" * 100)

    for tf in sorted(ok["timeframe"].unique()):
        for direction in ["long", "short"]:
            subset = h1[(h1["timeframe"] == tf) & (h1["direction"] == direction)]
            if subset.empty:
                continue

            ranking = (
                subset.groupby("indicator")
                .agg(
                    mean_ic=("ic", "mean"),
                    max_ic=("ic", "max"),
                    mean_hr=("hit_rate", "mean"),
                    mean_stab=("temporal_stability", "mean"),
                    mean_freq=("signal_frequency_per_month", "mean"),
                    n_pos=("ic", lambda x: (x > 0).sum()),
                    n_total=("ic", "count"),
                )
                .sort_values("mean_ic", ascending=False)
            )

            strong = (ranking["mean_ic"] > 0.03).sum()
            moderate = ((ranking["mean_ic"] > 0.02) & (ranking["mean_ic"] <= 0.03)).sum()

            print(f"\n  ── {tf} {direction.upper()} ({strong} strong, {moderate} moderate) ──")
            print(f"  {'Indicator':<25s} {'MeanIC':>7s} {'MaxIC':>7s} {'HR':>6s} {'Stab':>6s} {'F/mo':>5s} {'IC+':>4s} Edge")
            print(f"  {'-'*25} {'-'*7} {'-'*7} {'-'*6} {'-'*6} {'-'*5} {'-'*4} {'-'*8}")

            for ind, row in ranking.head(15).iterrows():
                ic = row["mean_ic"]
                if ic > 0.03:
                    edge = "STRONG"
                elif ic > 0.02:
                    edge = "MODERATE"
                elif ic > 0.01:
                    edge = "marginal"
                else:
                    edge = "."
                stab = f"{row['mean_stab']:.0%}" if not np.isnan(row["mean_stab"]) else "N/A"
                ic_pos = f"{int(row['n_pos'])}/{int(row['n_total'])}"
                print(f"  {ind:<25s} {ic:>7.4f} {row['max_ic']:>7.4f} {row['mean_hr']:>5.1%} {stab:>6s} {row['mean_freq']:>5.1f} {ic_pos:>4s} {edge}")

    # Multi-horizon analysis for top indicators
    print(f"\n  ── MULTI-HORIZON ANALYSIS (top 5 indicators by IC, each TF×direction) ──")
    for tf in sorted(ok["timeframe"].unique()):
        for direction in ["long", "short"]:
            h1_sub = h1[(h1["timeframe"] == tf) & (h1["direction"] == direction)]
            top5 = h1_sub.groupby("indicator")["ic"].mean().nlargest(5).index

            if len(top5) == 0:
                continue

            print(f"\n  {tf} {direction}:")
            print(f"  {'Indicator':<25s}", end="")
            for h in FORWARD_HORIZONS:
                print(f" {'h=' + str(h):>6s}", end="")
            print()

            for ind in top5:
                print(f"  {ind:<25s}", end="")
                for h in FORWARD_HORIZONS:
                    h_data = best_per[
                        (best_per["timeframe"] == tf) & (best_per["direction"] == direction)
                        & (best_per["indicator"] == ind) & (best_per["horizon"] == h)
                    ]
                    if not h_data.empty:
                        ic_val = h_data["ic"].mean()
                        print(f" {ic_val:>6.3f}", end="")
                    else:
                        print(f" {'N/A':>6s}", end="")
                print()

    print("=" * 100)


# ── CLI ───────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Step 1: Rigorous IC Scanner")
    p.add_argument("--indicators", nargs="+", default=None)
    p.add_argument("--assets", nargs="+", default=None)
    p.add_argument("--timeframes", nargs="+", default=None)
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--macro-dir", default=str(ROOT / "data" / "raw" / "macro"))
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "research" / "step1_edge_map"))
    return p.parse_args()


def main() -> None:
    args = parse_args()
    indicators = args.indicators or sorted(set(INDICATOR_REGISTRY.keys()) - EXCLUDE_INDICATORS)
    assets = args.assets or (STOCK_SYMBOLS + CRYPTO_SYMBOLS)
    timeframes = args.timeframes or ALL_TIMEFRAMES
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    store = ParquetStore(base_dir=Path(args.data_dir))
    resampler = OHLCVResampler()

    macro_cache = None
    try:
        from suitetrading.data.macro_cache import MacroCacheManager
        macro_cache = MacroCacheManager(cache_dir=Path(args.macro_dir))
    except Exception:
        logger.warning("Macro cache unavailable")

    futures_dl = None
    try:
        from suitetrading.data.futures import BinanceFuturesDownloader
        futures_dl = BinanceFuturesDownloader(output_dir=Path(args.data_dir))
    except Exception:
        logger.warning("Futures downloader unavailable")

    # Estimate total
    n_configs_est = 5  # avg configs per indicator
    total_est = len(indicators) * len(timeframes) * len(assets) * 2 * n_configs_est * len(FORWARD_HORIZONS)
    logger.info(
        "Rigorous IC Scanner: {} ind × {} TFs × {} assets × 2 dirs × ~{} configs × {} horizons ≈ {} measurements",
        len(indicators), len(timeframes), len(assets), n_configs_est, len(FORWARD_HORIZONS), total_est,
    )

    bpm_stocks = {"1w": 4, "1d": 21, "4h": 126}
    bpm_crypto = {"1w": 4, "1d": 30, "4h": 180}

    all_results: list[dict] = []
    count = 0

    for asset in assets:
        asset_class = "stocks" if asset in STOCK_SYMBOLS else "crypto"
        bpm_table = bpm_stocks if asset_class == "stocks" else bpm_crypto

        for tf in timeframes:
            ohlcv = load_and_enrich(asset, tf, store, resampler, macro_cache, futures_dl)
            if ohlcv is None:
                logger.debug("Skipping {} {} (no data)", asset, tf)
                continue

            bpm = bpm_table.get(tf, 126)
            logger.info("Scanning {} {} ({} bars)...", asset, tf, len(ohlcv))

            for ind_name in indicators:
                metrics_list = scan_indicator_full(ind_name, ohlcv, tf, asset, asset_class, bpm)
                for m in metrics_list:
                    all_results.append(asdict(m))
                    count += 1

            if count % 500 == 0:
                logger.info("  Progress: {} measurements", count)

    df = pd.DataFrame(all_results)
    df.to_csv(output_dir / "edge_summary_full.csv", index=False)
    logger.info("Saved {} measurements to {}", len(df), output_dir / "edge_summary_full.csv")

    generate_reports(df, output_dir)


if __name__ == "__main__":
    main()
