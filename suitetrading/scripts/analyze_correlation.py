#!/usr/bin/env python3
"""Correlation analysis and strategy selection script.

Usage
-----
python scripts/analyze_correlation.py \
    --evidence-dir artifacts/discovery/evidence \
    --output-dir artifacts/correlation
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.risk.correlation import (
    DiversificationRatio,
    StrategyCorrelationAnalyzer,
    StrategySelector,
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Correlation analysis")
    p.add_argument("--evidence-dir", default=str(ROOT / "artifacts" / "discovery" / "evidence"))
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "correlation"))
    p.add_argument("--target-count", type=int, default=100)
    p.add_argument("--max-avg-corr", type=float, default=0.30)
    p.add_argument("--max-per-archetype", type=int, default=3)
    p.add_argument("--max-per-asset-tf", type=int, default=2)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load equity curves
    evidence_dir = Path(args.evidence_dir)
    equity_curves: dict[str, np.ndarray] = {}
    metadata: dict[str, dict[str, str]] = {}

    for f in sorted(evidence_dir.glob("*.json")):
        with open(f) as fp:
            data = json.load(fp)
        sid = data.get("candidate_id", f.stem)
        if "equity_curve" in data:
            equity_curves[sid] = np.array(data["equity_curve"], dtype=np.float64)
            metadata[sid] = {
                "archetype": data.get("archetype", "unknown"),
                "symbol": data.get("symbol", "unknown"),
                "timeframe": data.get("timeframe", "unknown"),
            }

    logger.info("Loaded {} equity curves", len(equity_curves))

    if len(equity_curves) < 2:
        logger.error("Need ≥2 equity curves")
        sys.exit(1)

    # Correlation analysis
    analyzer = StrategyCorrelationAnalyzer()
    corr_result = analyzer.compute_matrix(equity_curves)

    logger.info("Avg Pearson correlation: {:.3f}", corr_result.avg_correlation)
    logger.info("Clusters: {}", len(corr_result.clusters))

    # Save correlation matrix
    np.save(output_dir / "pearson_matrix.npy", corr_result.pearson)
    np.save(output_dir / "spearman_matrix.npy", corr_result.spearman)

    with open(output_dir / "correlation_summary.json", "w") as fp:
        json.dump({
            "avg_correlation": corr_result.avg_correlation,
            "n_strategies": len(corr_result.strategy_ids),
            "n_clusters": len(corr_result.clusters),
            "strategy_ids": corr_result.strategy_ids,
        }, fp, indent=2)

    # Strategy selection
    selector = StrategySelector(
        target_count=args.target_count,
        max_avg_corr=args.max_avg_corr,
        max_per_archetype=args.max_per_archetype,
        max_per_asset_tf=args.max_per_asset_tf,
    )
    selected = selector.select(equity_curves, metadata)

    # Diversification ratio
    selected_ids = [s["strategy_id"] for s in selected]
    if len(selected_ids) >= 2:
        selected_curves = [equity_curves[sid] for sid in selected_ids]
        min_len = min(len(c) for c in selected_curves)
        returns_matrix = np.column_stack([
            np.diff(c[:min_len]) / np.maximum(c[:min_len - 1], 1e-12)
            for c in selected_curves
        ])
        dr = DiversificationRatio.compute(returns_matrix)
    else:
        dr = 1.0

    with open(output_dir / "selection.json", "w") as fp:
        json.dump({
            "selected": selected,
            "diversification_ratio": dr,
            "count": len(selected),
        }, fp, indent=2, default=str)

    print("\n" + "=" * 60)
    print("  CORRELATION ANALYSIS")
    print("=" * 60)
    print(f"  Candidates: {len(equity_curves)}")
    print(f"  Avg correlation: {corr_result.avg_correlation:.3f}")
    print(f"  Clusters: {len(corr_result.clusters)}")
    print(f"  Selected: {len(selected)}")
    print(f"  Diversification Ratio: {dr:.3f}")
    print(f"  Results: {output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
