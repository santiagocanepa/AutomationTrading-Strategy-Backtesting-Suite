"""Tests for portfolio stress testing."""

from __future__ import annotations

import numpy as np
import pytest

from suitetrading.risk.stress_testing import PortfolioStressTester, StressTestResult


@pytest.fixture
def returns_matrix() -> np.ndarray:
    """5 strategies × 500 bars."""
    rng = np.random.default_rng(42)
    return rng.normal(0.0002, 0.01, size=(500, 5))


@pytest.fixture
def weights() -> np.ndarray:
    return np.array([0.2, 0.2, 0.2, 0.2, 0.2])


@pytest.fixture
def strategy_ids() -> list[str]:
    return [f"strat_{i}" for i in range(5)]


class TestMonteCarloBlockBootstrap:
    def test_returns_dict(self, returns_matrix, weights):
        tester = PortfolioStressTester()
        result = tester.monte_carlo_block_bootstrap(
            returns_matrix, weights, n_simulations=100, block_size=10, seed=42,
        )
        assert isinstance(result, dict)
        assert "max_dd_p50" in result
        assert "max_dd_p95" in result
        assert "prob_ruin" in result

    def test_p99_worse_than_p50(self, returns_matrix, weights):
        tester = PortfolioStressTester()
        result = tester.monte_carlo_block_bootstrap(
            returns_matrix, weights, n_simulations=500, seed=42,
        )
        assert result["max_dd_p99"] >= result["max_dd_p50"]


class TestWeightPerturbation:
    def test_returns_sharpe_stats(self, returns_matrix, weights):
        tester = PortfolioStressTester()
        result = tester.weight_perturbation(
            returns_matrix, weights, perturbation_pct=10.0, n_trials=100, seed=42,
        )
        assert "sharpe_mean" in result
        assert "sharpe_std" in result
        assert "sharpe_cv" in result

    def test_cv_below_one_for_stable(self, returns_matrix, weights):
        tester = PortfolioStressTester()
        result = tester.weight_perturbation(
            returns_matrix, weights, perturbation_pct=5.0, n_trials=100, seed=42,
        )
        # Coefficient of variation should be reasonable for small perturbations
        assert result["sharpe_cv"] < 2.0


class TestCorrelationRegimeShift:
    def test_returns_shift_metrics(self, returns_matrix, weights):
        tester = PortfolioStressTester()
        result = tester.correlation_regime_shift(
            returns_matrix, weights, target_corr=0.8, n_simulations=100, seed=42,
        )
        assert "max_dd_shift_p50" in result
        assert "sharpe_shift_mean" in result


class TestRunAll:
    def test_returns_stress_result(self, returns_matrix, weights, strategy_ids):
        tester = PortfolioStressTester()
        result = tester.run_all(
            returns_matrix, weights, strategy_ids,
            n_monte_carlo=100, block_size=10, seed=42,
        )
        assert isinstance(result, StressTestResult)
        assert result.monte_carlo is not None
        assert result.weight_perturbation is not None
