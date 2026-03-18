"""Tests for portfolio weight optimization."""

from __future__ import annotations

import numpy as np
import pytest

from suitetrading.risk.portfolio_optimizer import PortfolioOptimizer, PortfolioWeights


@pytest.fixture
def returns_matrix() -> np.ndarray:
    """5 strategies × 500 bars of random returns."""
    rng = np.random.default_rng(42)
    return rng.normal(0.0002, 0.01, size=(500, 5))


@pytest.fixture
def strategy_ids() -> list[str]:
    return [f"strat_{i}" for i in range(5)]


class TestEqualWeight:
    def test_weights_sum_to_one(self, returns_matrix, strategy_ids):
        opt = PortfolioOptimizer()
        result = opt.optimize(returns_matrix, strategy_ids, method="equal")
        assert abs(result.weights.sum() - 1.0) < 1e-10

    def test_all_weights_equal(self, returns_matrix, strategy_ids):
        opt = PortfolioOptimizer()
        result = opt.optimize(returns_matrix, strategy_ids, method="equal")
        expected = 1.0 / len(strategy_ids)
        np.testing.assert_array_almost_equal(result.weights, expected)

    def test_method_name(self, returns_matrix, strategy_ids):
        opt = PortfolioOptimizer()
        result = opt.optimize(returns_matrix, strategy_ids, method="equal")
        assert result.method == "equal"


class TestMinVariance:
    def test_weights_sum_to_one(self, returns_matrix, strategy_ids):
        opt = PortfolioOptimizer()
        result = opt.optimize(returns_matrix, strategy_ids, method="min_variance")
        assert abs(result.weights.sum() - 1.0) < 1e-6

    def test_all_weights_non_negative(self, returns_matrix, strategy_ids):
        opt = PortfolioOptimizer()
        result = opt.optimize(returns_matrix, strategy_ids, method="min_variance")
        assert np.all(result.weights >= -1e-10)

    def test_returns_portfolio_weights(self, returns_matrix, strategy_ids):
        opt = PortfolioOptimizer()
        result = opt.optimize(returns_matrix, strategy_ids, method="min_variance")
        assert isinstance(result, PortfolioWeights)
        assert len(result.weights) == len(strategy_ids)


class TestRiskParity:
    def test_weights_sum_to_one(self, returns_matrix, strategy_ids):
        opt = PortfolioOptimizer()
        result = opt.optimize(returns_matrix, strategy_ids, method="risk_parity")
        assert abs(result.weights.sum() - 1.0) < 1e-6

    def test_all_weights_non_negative(self, returns_matrix, strategy_ids):
        opt = PortfolioOptimizer()
        result = opt.optimize(returns_matrix, strategy_ids, method="risk_parity")
        assert np.all(result.weights >= -1e-10)


class TestKelly:
    def test_weights_sum_to_one(self, returns_matrix, strategy_ids):
        opt = PortfolioOptimizer()
        result = opt.optimize(returns_matrix, strategy_ids, method="kelly", kelly_fraction=0.5)
        assert abs(result.weights.sum() - 1.0) < 1e-6

    def test_half_kelly_smaller_than_full(self, returns_matrix, strategy_ids):
        opt = PortfolioOptimizer()
        half = opt.optimize(returns_matrix, strategy_ids, method="kelly", kelly_fraction=0.5)
        full = opt.optimize(returns_matrix, strategy_ids, method="kelly", kelly_fraction=1.0)
        # Half Kelly should have less extreme weights
        assert np.max(np.abs(half.weights)) <= np.max(np.abs(full.weights)) + 0.1


class TestUnknownMethod:
    def test_raises(self, returns_matrix, strategy_ids):
        opt = PortfolioOptimizer()
        with pytest.raises(ValueError, match="Unknown method"):
            opt.optimize(returns_matrix, strategy_ids, method="invalid")
