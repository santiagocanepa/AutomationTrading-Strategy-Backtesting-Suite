"""Tests for ensemble backtester."""

from __future__ import annotations

import numpy as np
import pytest

from suitetrading.backtesting.ensemble import EnsembleBacktester, EnsembleResult


@pytest.fixture
def equity_curves() -> dict[str, np.ndarray]:
    """3 strategies with 100 bars each."""
    rng = np.random.default_rng(42)
    curves = {}
    for i in range(3):
        returns = rng.normal(0.001, 0.02, size=100)
        curves[f"strat_{i}"] = np.cumprod(1.0 + returns) * 10_000.0
    return curves


@pytest.fixture
def strategy_ids() -> list[str]:
    return ["strat_0", "strat_1", "strat_2"]


@pytest.fixture
def equal_weights() -> np.ndarray:
    return np.array([1 / 3, 1 / 3, 1 / 3])


class TestEnsembleBacktester:
    def test_returns_ensemble_result(self, equity_curves, equal_weights, strategy_ids):
        bt = EnsembleBacktester(initial_capital=100_000.0)
        result = bt.run(equity_curves, equal_weights, strategy_ids)
        assert isinstance(result, EnsembleResult)

    def test_equity_curve_length(self, equity_curves, equal_weights, strategy_ids):
        bt = EnsembleBacktester()
        result = bt.run(equity_curves, equal_weights, strategy_ids)
        # Length should match the equity curves (minus 1 for returns conversion + initial)
        assert len(result.equity_curve) > 0

    def test_metrics_contain_sharpe(self, equity_curves, equal_weights, strategy_ids):
        bt = EnsembleBacktester()
        result = bt.run(equity_curves, equal_weights, strategy_ids)
        assert "sharpe" in result.metrics
        assert "max_drawdown_pct" in result.metrics

    def test_initial_capital_respected(self, equity_curves, equal_weights, strategy_ids):
        bt = EnsembleBacktester(initial_capital=50_000.0)
        result = bt.run(equity_curves, equal_weights, strategy_ids)
        assert result.equity_curve[0] == pytest.approx(50_000.0)

    def test_no_rebalance_mode(self, equity_curves, equal_weights, strategy_ids):
        bt = EnsembleBacktester()
        result = bt.run(equity_curves, equal_weights, strategy_ids, rebalance_freq="none")
        assert result.rebalance_dates is None
