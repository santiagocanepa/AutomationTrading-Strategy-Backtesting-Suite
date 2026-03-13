#!/usr/bin/env python3
"""Post-discovery analysis: re-run finalists, generate evidence cards.

Reads the JSON evidence cards produced by ``run_discovery.py``, re-runs
each finalist with ``BacktestObjective.run_single()`` to obtain full
equity curves and trades, then produces:

  1. ``finalists_detailed.csv`` — all metrics + OOS stats
  2. Individual evidence cards (JSON) with equity curve & trade log
  3. ``discovery_report.md`` — markdown summary
  4. Optional equity-curve PNGs (if matplotlib available)

Usage
-----
# Analyze all finalists from the default discovery directory
python scripts/analyze_discovery.py

# Analyze with a specific artifacts dir
python scripts/analyze_discovery.py --artifacts-dir artifacts/discovery

# Only top-20 finalists
python scripts/analyze_discovery.py --top 20
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.backtesting._internal.datasets import build_dataset_from_df
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.config.archetypes import (
    get_all_indicators,
    get_auxiliary_indicators,
)
from suitetrading.optimization._internal.objective import BacktestObjective

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _MPL = True
except ImportError:
    _MPL = False


# ── CLI ───────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Analyze discovery finalists")
    p.add_argument(
        "--artifacts-dir",
        default=str(ROOT / "artifacts" / "discovery"),
        help="Root directory of discovery artifacts",
    )
    p.add_argument(
        "--exchange", default="binance",
    )
    p.add_argument(
        "--data-dir", default=str(ROOT / "data" / "raw"),
    )
    p.add_argument(
        "--months", type=int, default=12,
        help="Months of data for full backtest",
    )
    p.add_argument(
        "--top", type=int, default=0,
        help="Analyze only top N finalists (0 = all)",
    )
    p.add_argument(
        "--mode", default="fsm", choices=["fsm", "simple", "auto"],
    )
    p.add_argument(
        "--no-plots", action="store_true",
        help="Skip equity-curve plot generation",
    )
    return p.parse_args()


# ── Helpers ───────────────────────────────────────────────────────────


def load_ohlcv_cached(
    cache: dict[str, pd.DataFrame],
    exchange: str,
    symbol: str,
    timeframe: str,
    months: int,
    data_dir: Path,
) -> pd.DataFrame:
    """Load and cache OHLCV data (avoids re-reading for same symbol+tf)."""
    key = f"{symbol}_{timeframe}"
    if key not in cache:
        store = ParquetStore(base_dir=data_dir)
        df_1m = store.read(exchange, symbol, "1m")
        cutoff = df_1m.index.max() - pd.DateOffset(months=months)
        df_1m = df_1m.loc[df_1m.index >= cutoff]
        if timeframe == "1m":
            cache[key] = df_1m
        else:
            cache[key] = OHLCVResampler().resample(df_1m, timeframe, base_tf="1m")
    return cache[key]


def load_finalists(evidence_dir: Path) -> list[dict[str, Any]]:
    """Load all finalist JSON cards from the evidence directory."""
    files = sorted(evidence_dir.glob("finalist_*.json"))
    finalists = []
    for fp in files:
        with open(fp) as f:
            finalists.append(json.load(f))
    return finalists


def flatten_params(
    indicator_params: dict[str, dict[str, Any]],
    risk_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Reconstruct flat Optuna-style params for BacktestObjective.run_single()."""
    flat: dict[str, Any] = {}
    for ind_name, params in indicator_params.items():
        for param_name, value in params.items():
            flat[f"{ind_name}__{param_name}"] = value
    flat.update(risk_overrides)
    return flat


def plot_equity_curve(
    equity: list[float] | np.ndarray,
    title: str,
    output_path: Path,
) -> None:
    """Save equity curve plot to PNG."""
    if not _MPL:
        return
    fig, axes = plt.subplots(2, 1, figsize=(12, 6), height_ratios=[3, 1])

    eq = np.asarray(equity, dtype=float)
    axes[0].plot(eq, linewidth=0.8)
    axes[0].set_title(title)
    axes[0].set_ylabel("Equity")
    axes[0].grid(True, alpha=0.3)

    # Drawdown
    peak = np.maximum.accumulate(eq)
    dd = (eq - peak) / np.where(peak > 0, peak, 1.0)
    axes[1].fill_between(range(len(dd)), dd, 0, alpha=0.4, color="red")
    axes[1].set_ylabel("Drawdown")
    axes[1].set_xlabel("Bar")
    axes[1].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path, dpi=100)
    plt.close(fig)


# ── Core Analysis ─────────────────────────────────────────────────────


def analyze_finalist(
    finalist: dict[str, Any],
    ohlcv_cache: dict[str, pd.DataFrame],
    args: argparse.Namespace,
) -> dict[str, Any]:
    """Re-run a finalist and collect detailed metrics."""
    symbol = finalist["symbol"]
    tf = finalist["timeframe"]
    archetype = finalist["archetype"]
    indicators = get_all_indicators(archetype)
    auxiliary = get_auxiliary_indicators(archetype)

    ohlcv = load_ohlcv_cached(
        ohlcv_cache, args.exchange, symbol, tf, args.months, Path(args.data_dir),
    )
    dataset = build_dataset_from_df(
        ohlcv, exchange=args.exchange, symbol=symbol, base_timeframe=tf,
    )

    flat_params = flatten_params(
        finalist.get("indicator_params", {}),
        finalist.get("risk_overrides", {}),
    )

    objective = BacktestObjective(
        dataset=dataset,
        indicator_names=indicators,
        auxiliary_indicators=auxiliary,
        archetype=archetype,
        metric="sharpe",
        mode=args.mode,
    )

    result = objective.run_single(flat_params)

    trades_df = result.get("trades")
    n_trades = 0
    avg_trade_pnl = 0.0
    if trades_df is not None and len(trades_df) > 0:
        if isinstance(trades_df, pd.DataFrame):
            n_trades = len(trades_df)
            if "pnl" in trades_df.columns:
                avg_trade_pnl = float(trades_df["pnl"].mean())
        elif isinstance(trades_df, list):
            n_trades = len(trades_df)

    eq = result["equity_curve"]
    eq_arr = np.asarray(eq, dtype=float)

    # Returns stats
    rets = np.diff(eq_arr) / np.maximum(eq_arr[:-1], 1e-10)
    rets = rets[np.isfinite(rets)]

    return {
        "rank": finalist.get("rank", 0),
        "study": finalist.get("study", ""),
        "symbol": symbol,
        "timeframe": tf,
        "archetype": archetype,
        "indicators": indicators,
        "flat_params": flat_params,
        # Discovery-stage metrics
        "oos_sharpe": finalist.get("observed_sharpe", 0.0),
        "pbo": finalist.get("pbo", 1.0),
        "dsr": finalist.get("dsr", 0.0),
        "degradation": finalist.get("degradation", float("inf")),
        # Full backtest metrics
        **{f"full_{k}": v for k, v in result["metrics"].items()},
        "n_trades": n_trades,
        "avg_trade_pnl": avg_trade_pnl,
        # Distribution stats
        "returns_skew": float(pd.Series(rets).skew()) if len(rets) > 2 else 0.0,
        "returns_kurtosis": float(pd.Series(rets).kurtosis()) if len(rets) > 3 else 0.0,
        # Raw curve for plotting
        "_equity_curve": eq,
    }


# ── Report Generation ─────────────────────────────────────────────────


def generate_report(
    detailed: list[dict[str, Any]],
    output_dir: Path,
) -> None:
    """Generate a markdown summary report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Discovery Analysis Report",
        f"Generated: {now}",
        "",
        "## Summary",
        f"- **Finalists analyzed**: {len(detailed)}",
    ]

    if detailed:
        best = detailed[0]
        lines.extend([
            f"- **Best full-backtest Sharpe**: {best.get('full_sharpe', 0):.4f}",
            f"- **Best study**: {best.get('study', 'N/A')}",
            "",
            "## Top 10 Finalists",
            "",
            "| Rank | Study | OOS Sharpe | Full Sharpe | PBO | DSR | Max DD% | Trades |",
            "|------|-------|-----------|-------------|-----|-----|---------|--------|",
        ])
        for d in detailed[:10]:
            lines.append(
                f"| {d['rank']} "
                f"| {d['study']} "
                f"| {d['oos_sharpe']:.3f} "
                f"| {d.get('full_sharpe', 0):.3f} "
                f"| {d['pbo']:.3f} "
                f"| {d['dsr']:.3f} "
                f"| {d.get('full_max_drawdown_pct', 0):.1f}% "
                f"| {d['n_trades']} |"
            )

        # Archetype breakdown
        arch_counts: dict[str, list[float]] = {}
        for d in detailed:
            arch = d["archetype"]
            arch_counts.setdefault(arch, []).append(d.get("full_sharpe", 0.0))

        lines.extend(["", "## By Archetype", ""])
        for arch, sharpes in sorted(arch_counts.items()):
            avg_s = np.mean(sharpes) if sharpes else 0.0
            lines.append(f"- **{arch}**: {len(sharpes)} finalists, avg Sharpe = {avg_s:.3f}")

        # Symbol breakdown
        sym_counts: dict[str, list[float]] = {}
        for d in detailed:
            sym = d["symbol"]
            sym_counts.setdefault(sym, []).append(d.get("full_sharpe", 0.0))

        lines.extend(["", "## By Symbol", ""])
        for sym, sharpes in sorted(sym_counts.items()):
            avg_s = np.mean(sharpes) if sharpes else 0.0
            lines.append(f"- **{sym}**: {len(sharpes)} finalists, avg Sharpe = {avg_s:.3f}")

        # TF breakdown
        tf_counts: dict[str, list[float]] = {}
        for d in detailed:
            tf = d["timeframe"]
            tf_counts.setdefault(tf, []).append(d.get("full_sharpe", 0.0))

        lines.extend(["", "## By Timeframe", ""])
        for tf, sharpes in sorted(tf_counts.items()):
            avg_s = np.mean(sharpes) if sharpes else 0.0
            lines.append(f"- **{tf}**: {len(sharpes)} finalists, avg Sharpe = {avg_s:.3f}")

    report_path = output_dir / "discovery_report.md"
    report_path.write_text("\n".join(lines) + "\n")
    logger.info("Report written to {}", report_path)


# ── Main ──────────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()
    artifacts_dir = Path(args.artifacts_dir)
    evidence_dir = artifacts_dir / "evidence"
    results_dir = artifacts_dir / "results"
    plots_dir = artifacts_dir / "plots"

    if not evidence_dir.exists():
        logger.error("No evidence directory at {} — run discovery first", evidence_dir)
        sys.exit(1)

    finalists = load_finalists(evidence_dir)
    if not finalists:
        logger.error("No finalist cards found in {}", evidence_dir)
        sys.exit(1)

    if args.top > 0:
        finalists = finalists[: args.top]

    logger.info("Analyzing {} finalists…", len(finalists))
    ohlcv_cache: dict[str, pd.DataFrame] = {}
    detailed: list[dict[str, Any]] = []

    for i, finalist in enumerate(finalists):
        logger.info(
            "[{}/{}] {} — rank {}",
            i + 1, len(finalists), finalist.get("study", "?"), finalist.get("rank", "?"),
        )
        try:
            result = analyze_finalist(finalist, ohlcv_cache, args)
            detailed.append(result)

            # Plot equity curve
            if not args.no_plots and _MPL:
                plots_dir.mkdir(parents=True, exist_ok=True)
                rank = result["rank"]
                study = result["study"]
                plot_equity_curve(
                    result["_equity_curve"],
                    title=f"#{rank} {study}  Sharpe={result.get('full_sharpe', 0):.3f}",
                    output_path=plots_dir / f"equity_{rank:03d}_{study}.png",
                )
        except Exception as exc:
            logger.error("Failed to analyze finalist {}: {}", finalist.get("study"), exc)

    if not detailed:
        logger.error("No finalists could be analyzed")
        sys.exit(1)

    # Sort by full-backtest Sharpe descending
    detailed.sort(key=lambda d: d.get("full_sharpe", 0.0), reverse=True)

    # Export detailed CSV (exclude raw equity curve)
    csv_rows = [{k: v for k, v in d.items() if not k.startswith("_")} for d in detailed]
    df = pd.DataFrame(csv_rows)
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / "finalists_detailed.csv"
    df.to_csv(csv_path, index=False)
    logger.info("Detailed CSV → {} ({} rows)", csv_path, len(df))

    # Save enriched evidence cards
    enriched_dir = artifacts_dir / "evidence_enriched"
    enriched_dir.mkdir(parents=True, exist_ok=True)
    for d in detailed:
        card = {k: v for k, v in d.items() if not k.startswith("_")}
        fp = enriched_dir / f"finalist_{d['rank']:03d}_{d['study']}.json"
        with open(fp, "w") as f:
            json.dump(card, f, indent=2, default=str)

    # Generate report
    generate_report(detailed, results_dir)

    # Print summary
    print("\n" + "=" * 60)
    print("  ANALYSIS COMPLETE")
    print("=" * 60)
    print(f"  Finalists analyzed: {len(detailed)}")
    if detailed:
        print(f"  Best full Sharpe: {detailed[0].get('full_sharpe', 0):.4f} ({detailed[0]['study']})")
        positive = sum(1 for d in detailed if d.get("full_sharpe", 0) > 0)
        print(f"  Positive Sharpe: {positive}/{len(detailed)}")
    print(f"  Detailed CSV: {csv_path}")
    print(f"  Report: {results_dir / 'discovery_report.md'}")
    if not args.no_plots and _MPL:
        print(f"  Plots: {plots_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
