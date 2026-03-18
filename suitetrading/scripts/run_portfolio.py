#!/usr/bin/env python3
"""Portfolio construction pipeline: load finalists → correlate → select → optimize → ensemble.

Usage
-----
python scripts/run_portfolio.py \
    --finalists artifacts/discovery/results/finalists.csv \
    --evidence-dir artifacts/discovery/evidence \
    --output-dir artifacts/portfolio
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
    p = argparse.ArgumentParser(description="Portfolio construction pipeline")
    p.add_argument("--finalists", default=str(ROOT / "artifacts" / "discovery" / "results" / "finalists.csv"))
    p.add_argument("--evidence-dir", default=str(ROOT / "artifacts" / "discovery" / "evidence"))
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "portfolio"))
    p.add_argument("--target-count", type=int, default=100)
    p.add_argument("--max-avg-corr", type=float, default=0.30)
    p.add_argument("--methods", nargs="+",
                   default=["equal", "min_variance", "risk_parity", "kelly", "shrinkage_kelly"])
    p.add_argument("--rebalance", default="none",
                   choices=["none", "daily", "weekly", "monthly"])
    p.add_argument("--initial-capital", type=float, default=100_000.0)
    return p.parse_args()


def load_equity_curves(evidence_dir: Path) -> tuple[dict[str, np.ndarray], dict[str, dict[str, str]]]:
    """Load equity curves and metadata from evidence cards."""
    curves: dict[str, np.ndarray] = {}
    metadata: dict[str, dict[str, str]] = {}

    for f in sorted(evidence_dir.glob("*.json")):
        with open(f) as fp:
            data = json.load(fp)
        sid = data.get("candidate_id", f.stem)
        if "equity_curve" in data:
            curves[sid] = np.array(data["equity_curve"], dtype=np.float64)
            metadata[sid] = {
                "archetype": data.get("archetype", "unknown"),
                "symbol": data.get("symbol", "unknown"),
                "timeframe": data.get("timeframe", "unknown"),
            }

    return curves, metadata


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load data
    evidence_dir = Path(args.evidence_dir)
    equity_curves, metadata = load_equity_curves(evidence_dir)
    logger.info("Loaded {} equity curves", len(equity_curves))

    if len(equity_curves) < 10:
        logger.error("Need ≥10 equity curves, found {}", len(equity_curves))
        sys.exit(1)

    # ── Step 1: Correlation analysis ──
    logger.info("Computing correlation matrix...")
    analyzer = StrategyCorrelationAnalyzer()
    corr_matrix = analyzer.compute_matrix(equity_curves)
    logger.info(
        "Avg correlation: {:.3f}, clusters: {}",
        corr_matrix.avg_correlation, len(corr_matrix.clusters),
    )

    # ── Step 2: Strategy selection ──
    logger.info("Selecting {} strategies...", args.target_count)
    selector = StrategySelector(
        target_count=args.target_count,
        max_avg_corr=args.max_avg_corr,
        min_sharpe=0.0,  # Only select strategies with positive Sharpe
    )
    selected = selector.select(equity_curves, metadata)
    logger.info("Selected {} strategies", len(selected))

    selected_ids = [s["strategy_id"] for s in selected]

    # ── Step 3: Build returns matrix for selected ──
    selected_curves = {sid: equity_curves[sid] for sid in selected_ids}
    min_len = min(len(c) for c in selected_curves.values())
    returns_matrix = np.column_stack([
        np.diff(c[:min_len]) / np.maximum(c[:min_len - 1], 1e-12)
        for c in [selected_curves[sid] for sid in selected_ids]
    ])

    # ── Step 4: Optimize weights with multiple methods ──
    optimizer = PortfolioOptimizer()
    results: dict[str, Any] = {}

    for method in args.methods:
        logger.info("Optimizing with method: {}", method)
        pw = optimizer.optimize(returns_matrix, selected_ids, method=method)
        results[method] = {
            "weights": pw.weights.tolist(),
            "expected_return": pw.expected_return,
            "expected_volatility": pw.expected_volatility,
            "expected_sharpe": pw.expected_sharpe,
            "method": pw.method,
            "metrics": pw.metrics,
        }
        logger.info(
            "  {} → Sharpe: {:.4f}, Vol: {:.6f}",
            method, pw.expected_sharpe, pw.expected_volatility,
        )

    # Select best method by Sharpe
    best_method = max(results, key=lambda m: results[m]["expected_sharpe"])
    best_weights = np.array(results[best_method]["weights"])
    logger.info("Best method: {} (Sharpe {:.4f})", best_method, results[best_method]["expected_sharpe"])

    # ── Step 5: Ensemble backtest ──
    logger.info("Running ensemble backtest...")
    ensemble = EnsembleBacktester(initial_capital=args.initial_capital)
    ensemble_result = ensemble.run(
        equity_curves={sid: selected_curves[sid][:min_len] for sid in selected_ids},
        weights=best_weights,
        strategy_ids=selected_ids,
        rebalance_freq=args.rebalance,
    )

    # ── Step 6: Diversification ratio ──
    dr = DiversificationRatio.compute(returns_matrix, best_weights)
    logger.info("Diversification Ratio: {:.3f}", dr)

    # ── Save results ──
    with open(output_dir / "weights.json", "w") as fp:
        json.dump({
            "strategy_ids": selected_ids,
            "weights": best_weights.tolist(),
            "method": best_method,
        }, fp, indent=2)

    with open(output_dir / "optimization_results.json", "w") as fp:
        json.dump(results, fp, indent=2, default=str)

    with open(output_dir / "selection.json", "w") as fp:
        json.dump(selected, fp, indent=2, default=str)

    # Save ensemble metrics
    with open(output_dir / "ensemble_metrics.json", "w") as fp:
        json.dump(ensemble_result.metrics, fp, indent=2, default=str)

    print("\n" + "=" * 60)
    print("  PORTFOLIO CONSTRUCTION COMPLETE")
    print("=" * 60)
    print(f"  Strategies selected: {len(selected_ids)}")
    print(f"  Best method: {best_method}")
    print(f"  Portfolio Sharpe: {results[best_method]['expected_sharpe']:.4f}")
    print(f"  Diversification Ratio: {dr:.3f}")
    print(f"  Ensemble Max DD: {ensemble_result.metrics.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Results: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
