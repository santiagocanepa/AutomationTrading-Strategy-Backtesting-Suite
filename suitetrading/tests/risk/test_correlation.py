"""Tests for strategy correlation analysis and selection."""

from __future__ import annotations

import numpy as np
import pytest

from suitetrading.risk.correlation import (
    CorrelationMatrix,
    DiversificationRatio,
    StrategyCorrelationAnalyzer,
    StrategySelector,
)


@pytest.fixture
def random_equity_curves() -> dict[str, np.ndarray]:
    """Generate 10 random equity curves."""
    rng = np.random.default_rng(42)
    curves = {}
    for i in range(10):
        returns = rng.normal(0.0002, 0.01, size=1000)
        equity = np.cumprod(1.0 + returns) * 10_000.0
        curves[f"strat_{i}"] = equity
    return curves


@pytest.fixture
def metadata() -> dict[str, dict[str, str]]:
    return {
        f"strat_{i}": {
            "archetype": f"arch_{i % 3}",
            "symbol": f"SYM_{i % 2}",
            "timeframe": "1h",
        }
        for i in range(10)
    }


class TestCorrelationAnalyzer:
    def test_compute_matrix_shape(self, random_equity_curves):
        analyzer = StrategyCorrelationAnalyzer()
        result = analyzer.compute_matrix(random_equity_curves)
        n = len(random_equity_curves)
        assert result.pearson.shape == (n, n)
        assert result.spearman.shape == (n, n)
        assert result.drawdown_corr.shape == (n, n)

    def test_diagonal_is_one(self, random_equity_curves):
        analyzer = StrategyCorrelationAnalyzer()
        result = analyzer.compute_matrix(random_equity_curves)
        np.testing.assert_array_almost_equal(np.diag(result.pearson), 1.0, decimal=5)

    def test_symmetric(self, random_equity_curves):
        analyzer = StrategyCorrelationAnalyzer()
        result = analyzer.compute_matrix(random_equity_curves)
        np.testing.assert_array_almost_equal(result.pearson, result.pearson.T, decimal=10)

    def test_avg_correlation_bounded(self, random_equity_curves):
        analyzer = StrategyCorrelationAnalyzer()
        result = analyzer.compute_matrix(random_equity_curves)
        assert -1.0 <= result.avg_correlation <= 1.0

    def test_clusters_non_empty(self, random_equity_curves):
        analyzer = StrategyCorrelationAnalyzer()
        result = analyzer.compute_matrix(random_equity_curves)
        assert len(result.clusters) >= 1


class TestDiversificationRatio:
    def test_equal_weight_dr(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0, 0.01, size=(500, 5))
        dr = DiversificationRatio.compute(returns)
        assert dr >= 1.0  # DR ≥ 1 for uncorrelated assets

    def test_perfectly_correlated_dr_near_one(self):
        rng = np.random.default_rng(42)
        base = rng.normal(0.0, 0.01, size=500)
        returns = np.column_stack([base + rng.normal(0, 0.0001, 500) for _ in range(5)])
        dr = DiversificationRatio.compute(returns)
        assert dr < 1.5  # Nearly correlated → DR close to 1

    def test_custom_weights(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.0, 0.01, size=(500, 3))
        weights = np.array([0.5, 0.3, 0.2])
        dr = DiversificationRatio.compute(returns, weights)
        assert dr > 0


class TestStrategySelector:
    def test_selects_up_to_target(self, random_equity_curves, metadata):
        selector = StrategySelector(target_count=5, max_avg_corr=0.90)
        selected = selector.select(random_equity_curves, metadata)
        assert len(selected) <= 5

    def test_returns_strategy_ids(self, random_equity_curves, metadata):
        selector = StrategySelector(target_count=5, max_avg_corr=0.90)
        selected = selector.select(random_equity_curves, metadata)
        for s in selected:
            assert "strategy_id" in s
            assert s["strategy_id"] in random_equity_curves

    def test_respects_max_per_archetype(self, random_equity_curves, metadata):
        selector = StrategySelector(target_count=10, max_avg_corr=0.90, max_per_archetype=1)
        selected = selector.select(random_equity_curves, metadata)
        archetypes = [metadata[s["strategy_id"]]["archetype"] for s in selected]
        from collections import Counter
        counts = Counter(archetypes)
        for arch, count in counts.items():
            assert count <= 1
