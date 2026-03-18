#!/usr/bin/env python3
"""Portfolio Walk-Forward — build portfolio on IS, validate on OOS holdout.

The definitive test: can we construct a profitable portfolio using ONLY
past data, and does it work on unseen future data?

Splits each equity curve into IS (first 70%) and OOS (last 30%).
Builds the portfolio (selection + weights) ONLY on IS data.
Evaluates on OOS data that the portfolio construction never saw.

Usage
-----
python scripts/portfolio_walkforward.py \
    --pool-dir artifacts/slippage_analysis \
    --output-dir artifacts/portfolio_wfo
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.risk.correlation import (
    DiversificationRatio,
    StrategyCorrelationAnalyzer,
    StrategySelector,
)
from suitetrading.risk.portfolio_optimizer import PortfolioOptimizer
from suitetrading.backtesting.ensemble import EnsembleBacktester


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Portfolio walk-forward validation")
    p.add_argument("--pool-dir", default=str(ROOT / "artifacts" / "slippage_analysis"))
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "portfolio_wfo"))
    p.add_argument("--is-fraction", type=float, default=0.70,
                   help="Fraction of data for in-sample (default 70%%)")
    p.add_argument("--target-count", type=int, default=100)
    p.add_argument("--max-avg-corr", type=float, default=0.50)
    p.add_argument("--initial-capital", type=float, default=100_000.0)
    return p.parse_args()


def load_pool(pool_dir: Path) -> tuple[dict[str, np.ndarray], dict[str, dict[str, str]]]:
    """Load equity curves and metadata from pool."""
    curves: dict[str, np.ndarray] = {}
    metadata: dict[str, dict[str, str]] = {}
    for f in sorted(pool_dir.glob("*.json")):
        if "pool_summary" in f.name or "errors" in f.name or "slippage_summary" in f.name:
            continue
        data = json.load(open(f))
        sid = data.get("candidate_id", f.stem)
        if "equity_curve" in data:
            curves[sid] = np.array(data["equity_curve"], dtype=np.float64)
            metadata[sid] = {
                "archetype": data.get("archetype", "unknown"),
                "symbol": data.get("symbol", "unknown"),
                "timeframe": data.get("timeframe", "unknown"),
            }
    return curves, metadata


def split_curves(
    curves: dict[str, np.ndarray],
    is_fraction: float,
) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Split each equity curve into IS and OOS portions."""
    is_curves: dict[str, np.ndarray] = {}
    oos_curves: dict[str, np.ndarray] = {}
    for sid, eq in curves.items():
        split_idx = int(len(eq) * is_fraction)
        if split_idx < 50 or (len(eq) - split_idx) < 20:
            continue  # Too short
        is_curves[sid] = eq[:split_idx]
        oos_curves[sid] = eq[split_idx:]
    return is_curves, oos_curves


def curves_to_returns(curves: dict[str, np.ndarray], ids: list[str]) -> np.ndarray:
    """Convert equity curves to returns matrix, aligned to min length."""
    min_len = min(len(curves[sid]) for sid in ids)
    returns_list = []
    for sid in ids:
        eq = curves[sid][:min_len]
        ret = np.diff(eq) / np.where(eq[:-1] != 0, eq[:-1], 1.0)
        returns_list.append(ret)
    return np.column_stack(returns_list)


def compute_metrics(returns: np.ndarray, label: str) -> dict[str, float]:
    """Compute portfolio-level metrics from a return series."""
    if len(returns) < 2:
        return {}
    equity = np.cumprod(1.0 + returns) * 100_000.0
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / np.where(peak > 0, peak, 1.0) * 100
    std = np.std(returns, ddof=1)
    sharpe = np.mean(returns) / std if std > 1e-12 else 0.0
    ann_factor = np.sqrt(365 * 6)  # 4h assumption
    return {
        f"{label}_sharpe_per_bar": round(float(sharpe), 6),
        f"{label}_sharpe_ann": round(float(sharpe * ann_factor), 2),
        f"{label}_max_dd_pct": round(float(np.max(dd)), 2),
        f"{label}_total_return_pct": round(float((equity[-1] / equity[0] - 1) * 100), 2),
        f"{label}_bars": len(returns),
    }


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load pool
    curves, metadata = load_pool(Path(args.pool_dir))
    logger.info("Loaded {} equity curves", len(curves))

    # Split IS / OOS
    is_curves, oos_curves = split_curves(curves, args.is_fraction)
    common_ids = sorted(set(is_curves) & set(oos_curves))
    logger.info(
        "Split {:.0f}% IS / {:.0f}% OOS: {} strategies with both",
        args.is_fraction * 100, (1 - args.is_fraction) * 100, len(common_ids),
    )

    # ═══════════════════════════════════════════════════════════════
    # STEP 1: Build portfolio using ONLY IS data
    # ═══════════════════════════════════════════════════════════════
    logger.info("Building portfolio on IS data only...")

    # Correlation on IS
    analyzer = StrategyCorrelationAnalyzer()
    is_only = {sid: is_curves[sid] for sid in common_ids}
    corr = analyzer.compute_matrix(is_only)
    logger.info("IS correlation: avg={:.3f}, clusters={}", corr.avg_correlation, len(corr.clusters))

    # Select on IS
    is_metadata = {sid: metadata[sid] for sid in common_ids if sid in metadata}
    selector = StrategySelector(
        target_count=args.target_count,
        max_avg_corr=args.max_avg_corr,
        min_sharpe=0.0,
    )
    selected = selector.select(is_only, is_metadata)
    selected_ids = [s["strategy_id"] for s in selected]
    logger.info("IS selection: {} strategies", len(selected_ids))

    if len(selected_ids) < 3:
        logger.error("Too few strategies selected on IS data")
        sys.exit(1)

    # Optimize weights on IS
    is_returns = curves_to_returns(is_curves, selected_ids)
    optimizer = PortfolioOptimizer()
    pw = optimizer.optimize(is_returns, selected_ids, method="shrinkage_kelly")
    weights = pw.weights
    logger.info("IS optimization: Sharpe={:.4f}, method=shrinkage_kelly", pw.expected_sharpe)

    # ═══════════════════════════════════════════════════════════════
    # STEP 2: Evaluate on OOS data (NEVER SEEN by portfolio construction)
    # ═══════════════════════════════════════════════════════════════
    logger.info("Evaluating on OOS holdout...")

    # OOS returns for selected strategies
    oos_returns = curves_to_returns(oos_curves, selected_ids)

    # Portfolio returns
    is_port_returns = is_returns @ weights
    oos_port_returns = oos_returns @ weights

    # Metrics
    is_metrics = compute_metrics(is_port_returns, "is")
    oos_metrics = compute_metrics(oos_port_returns, "oos")

    # OOS equity curve
    oos_equity = np.cumprod(1.0 + oos_port_returns) * args.initial_capital

    # Degradation
    is_sharpe = is_metrics.get("is_sharpe_per_bar", 0)
    oos_sharpe = oos_metrics.get("oos_sharpe_per_bar", 0)
    degradation = (is_sharpe - oos_sharpe) / abs(is_sharpe) * 100 if abs(is_sharpe) > 1e-8 else 0

    # DR on OOS
    oos_dr = DiversificationRatio.compute(oos_returns, weights)

    # Per-strategy OOS performance
    strategy_oos = {}
    for i, sid in enumerate(selected_ids):
        oos_ret_i = oos_returns[:, i]
        std_i = np.std(oos_ret_i, ddof=1)
        sr_i = np.mean(oos_ret_i) / std_i if std_i > 1e-12 else 0.0
        strategy_oos[sid] = {
            "oos_sharpe": round(float(sr_i), 6),
            "oos_positive": bool(sr_i > 0),
            "weight": round(float(weights[i]), 4),
        }

    oos_positive_count = sum(1 for v in strategy_oos.values() if v["oos_positive"])

    # ═══════════════════════════════════════════════════════════════
    # RESULTS
    # ═══════════════════════════════════════════════════════════════
    results = {
        "is_fraction": args.is_fraction,
        "n_strategies": len(selected_ids),
        "strategy_ids": selected_ids,
        "weights": weights.tolist(),
        **is_metrics,
        **oos_metrics,
        "degradation_pct": round(degradation, 1),
        "oos_dr": round(oos_dr, 3),
        "oos_strategies_positive": oos_positive_count,
        "oos_strategies_total": len(selected_ids),
        "strategy_oos_detail": strategy_oos,
    }

    with open(output_dir / "wfo_results.json", "w") as fp:
        json.dump(results, fp, indent=2, default=str)

    # Save OOS equity curve
    np.save(output_dir / "oos_equity_curve.npy", oos_equity)

    print("\n" + "=" * 70)
    print("  PORTFOLIO WALK-FORWARD VALIDATION")
    print("=" * 70)
    print(f"  Split: {args.is_fraction*100:.0f}% IS / {(1-args.is_fraction)*100:.0f}% OOS")
    print(f"  Strategies selected (on IS): {len(selected_ids)}")
    print()
    print(f"  {'':20s} {'IS':>12s} {'OOS':>12s}")
    print(f"  {'─'*20} {'─'*12} {'─'*12}")
    print(f"  {'Sharpe (per-bar)':20s} {is_metrics.get('is_sharpe_per_bar',0):12.6f} {oos_metrics.get('oos_sharpe_per_bar',0):12.6f}")
    print(f"  {'Sharpe (ann.)':20s} {is_metrics.get('is_sharpe_ann',0):12.2f} {oos_metrics.get('oos_sharpe_ann',0):12.2f}")
    print(f"  {'Max DD':20s} {is_metrics.get('is_max_dd_pct',0):11.2f}% {oos_metrics.get('oos_max_dd_pct',0):11.2f}%")
    print(f"  {'Total Return':20s} {is_metrics.get('is_total_return_pct',0):11.2f}% {oos_metrics.get('oos_total_return_pct',0):11.2f}%")
    print(f"  {'Bars':20s} {is_metrics.get('is_bars',0):12d} {oos_metrics.get('oos_bars',0):12d}")
    print()
    print(f"  Degradation: {degradation:.1f}%")
    print(f"  OOS DR: {oos_dr:.3f}")
    print(f"  OOS strategies with Sharpe > 0: {oos_positive_count}/{len(selected_ids)}")
    print()

    oos_sharpe_ann = oos_metrics.get("oos_sharpe_ann", 0)
    oos_dd = oos_metrics.get("oos_max_dd_pct", 100)
    passed = oos_sharpe_ann > 0 and oos_dd < 15
    print(f"  VERDICT: {'PASS — edge survives OOS' if passed else 'FAIL — edge does not survive OOS'}")
    print("=" * 70)


if __name__ == "__main__":
    main()
