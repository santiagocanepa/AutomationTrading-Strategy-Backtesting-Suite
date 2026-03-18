#!/usr/bin/env python3
"""Stress testing pipeline for the strategy portfolio.

Usage
-----
python scripts/run_stress_tests.py \
    --portfolio-weights artifacts/portfolio/weights.json \
    --evidence-dir artifacts/discovery/evidence \
    --output-dir artifacts/stress_tests
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

from suitetrading.risk.stress_testing import PortfolioStressTester


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Portfolio stress testing")
    p.add_argument("--portfolio-weights", default=str(ROOT / "artifacts" / "portfolio" / "weights.json"))
    p.add_argument("--evidence-dir", default=str(ROOT / "artifacts" / "discovery" / "evidence"))
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "stress_tests"))
    p.add_argument("--monte-carlo-sims", type=int, default=10_000)
    p.add_argument("--block-size", type=int, default=20)
    p.add_argument("--perturbation-pct", type=float, default=10.0)
    p.add_argument("--target-corr-shift", type=float, default=0.8)
    p.add_argument("--seed", type=int, default=42)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load weights
    with open(args.portfolio_weights) as fp:
        weights_data = json.load(fp)
    strategy_ids = weights_data["strategy_ids"]
    weights = np.array(weights_data["weights"])

    # Load equity curves
    evidence_dir = Path(args.evidence_dir)
    equity_curves: dict[str, np.ndarray] = {}
    for f in sorted(evidence_dir.glob("*.json")):
        with open(f) as fp:
            data = json.load(fp)
        sid = data.get("candidate_id", f.stem)
        if "equity_curve" in data and sid in strategy_ids:
            equity_curves[sid] = np.array(data["equity_curve"], dtype=np.float64)

    available_ids = [sid for sid in strategy_ids if sid in equity_curves]
    if len(available_ids) < 2:
        logger.error("Need ≥2 equity curves, found {}", len(available_ids))
        sys.exit(1)

    # Build returns matrix
    curves_list = [equity_curves[sid] for sid in available_ids]
    min_len = min(len(c) for c in curves_list)
    returns_matrix = np.column_stack([
        np.diff(c[:min_len]) / np.maximum(c[:min_len - 1], 1e-12)
        for c in curves_list
    ])
    available_weights = np.array([
        weights[strategy_ids.index(sid)] for sid in available_ids
    ])
    available_weights /= available_weights.sum()

    # Run stress tests
    tester = PortfolioStressTester()
    logger.info("Running stress tests on {} strategies...", len(available_ids))

    result = tester.run_all(
        returns_matrix=returns_matrix,
        weights=available_weights,
        strategy_ids=available_ids,
        n_monte_carlo=args.monte_carlo_sims,
        block_size=args.block_size,
        seed=args.seed,
    )

    # Save results
    output = {
        "monte_carlo": result.monte_carlo,
        "weight_perturbation": result.weight_perturbation,
        "correlation_shift": result.correlation_shift,
        "overall_pass": result.overall_pass,
    }
    with open(output_dir / "stress_test_results.json", "w") as fp:
        json.dump(output, fp, indent=2, default=str)

    # Summary
    mc = result.monte_carlo or {}
    wp = result.weight_perturbation or {}
    cs = result.correlation_shift or {}

    print("\n" + "=" * 60)
    print("  STRESS TEST RESULTS")
    print("=" * 60)
    print(f"  Monte Carlo ({args.monte_carlo_sims} sims, block={args.block_size}):")
    print(f"    Max DD P50: {mc.get('max_dd_p50', 0):.2f}%")
    print(f"    Max DD P95: {mc.get('max_dd_p95', 0):.2f}%")
    print(f"    Max DD P99: {mc.get('max_dd_p99', 0):.2f}%")
    print(f"    P(ruin):    {mc.get('prob_ruin', 0):.6f}")
    print(f"  Weight Perturbation (±{args.perturbation_pct}%):")
    print(f"    Sharpe CV:  {wp.get('sharpe_cv', 0):.4f}")
    print(f"    Sharpe range: [{wp.get('sharpe_min', 0):.4f}, {wp.get('sharpe_max', 0):.4f}]")
    print(f"  Correlation Shift (→ {args.target_corr_shift}):")
    print(f"    Max DD shift: {cs.get('max_dd_shift', 0):.2f}%")
    print(f"  Overall: {'PASS' if result.overall_pass else 'FAIL'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
