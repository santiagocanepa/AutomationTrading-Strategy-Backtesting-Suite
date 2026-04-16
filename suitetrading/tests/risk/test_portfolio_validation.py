"""Tests for portfolio validation — DSR, alpha decay, clustering, regime, tail risk."""

from __future__ import annotations

import numpy as np
import pytest

from suitetrading.risk.portfolio_validation import PortfolioValidator, ValidationResult


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(42)


@pytest.fixture
def returns_matrix(rng: np.random.Generator) -> np.ndarray:
    """10 strategies × 1000 bars with slight positive drift."""
    return rng.normal(0.0003, 0.01, size=(1000, 10))


@pytest.fixture
def weights() -> np.ndarray:
    return np.ones(10) / 10


@pytest.fixture
def strategy_ids() -> list[str]:
    return [f"strat_{i}" for i in range(10)]


@pytest.fixture
def port_returns(returns_matrix: np.ndarray, weights: np.ndarray) -> np.ndarray:
    return returns_matrix @ weights


class TestDeflatedSharpeRatio:
    def test_returns_required_keys(self, port_returns: np.ndarray):
        v = PortfolioValidator()
        result = v.deflated_sharpe_ratio(port_returns, n_trials=100)
        assert "dsr" in result
        assert "observed_sharpe_per_bar" in result
        assert "expected_max_sharpe" in result
        assert "significant_5pct" in result

    def test_dsr_between_0_and_1(self, port_returns: np.ndarray):
        v = PortfolioValidator()
        result = v.deflated_sharpe_ratio(port_returns, n_trials=100)
        assert 0.0 <= result["dsr"] <= 1.0

    def test_more_trials_lowers_dsr(self, port_returns: np.ndarray):
        v = PortfolioValidator()
        dsr_10 = v.deflated_sharpe_ratio(port_returns, n_trials=10)["dsr"]
        dsr_10000 = v.deflated_sharpe_ratio(port_returns, n_trials=10000)["dsr"]
        assert dsr_10 > dsr_10000

    def test_random_walk_not_significant(self, rng: np.random.Generator):
        v = PortfolioValidator()
        noise = rng.normal(0.0, 0.01, size=1000)
        result = v.deflated_sharpe_ratio(noise, n_trials=1000)
        assert not result["significant_5pct"]

    def test_short_series(self):
        v = PortfolioValidator()
        result = v.deflated_sharpe_ratio(np.array([0.01, -0.01]), n_trials=10)
        assert result["dsr"] == 0.0


class TestAlphaDecay:
    def test_returns_required_keys(self, port_returns: np.ndarray):
        v = PortfolioValidator()
        result = v.alpha_decay_analysis(port_returns, n_windows=5)
        assert "windows" in result
        assert "slope" in result
        assert "status" in result
        assert len(result["windows"]) == 5

    def test_stable_for_iid_returns(self, port_returns: np.ndarray):
        v = PortfolioValidator()
        result = v.alpha_decay_analysis(port_returns, n_windows=5)
        assert result["status"] in ("STABLE", "IMPROVING")

    def test_decaying_signal_detected(self, rng: np.random.Generator):
        v = PortfolioValidator()
        # Strong drift in first half, none in second
        good = rng.normal(0.005, 0.01, size=500)
        bad = rng.normal(-0.001, 0.01, size=500)
        returns = np.concatenate([good, bad])
        result = v.alpha_decay_analysis(returns, n_windows=4)
        assert result["slope"] < 0


class TestStrategyClustering:
    def test_returns_required_keys(self, returns_matrix, strategy_ids):
        v = PortfolioValidator()
        result = v.strategy_clustering(returns_matrix, strategy_ids)
        assert "effective_n" in result
        assert "cluster_analysis" in result
        assert "top_correlated_pairs" in result

    def test_independent_strategies_high_effective_n(self, rng: np.random.Generator):
        v = PortfolioValidator()
        independent = rng.normal(0.0, 0.01, size=(500, 10))
        ids = [f"s_{i}" for i in range(10)]
        result = v.strategy_clustering(independent, ids)
        assert result["effective_n"] > 5  # independent → high eff N

    def test_identical_strategies_low_effective_n(self):
        v = PortfolioValidator()
        base = np.random.default_rng(42).normal(0.0, 0.01, size=(500, 1))
        identical = np.tile(base, (1, 5)) + np.random.default_rng(42).normal(0, 0.0001, size=(500, 5))
        ids = [f"s_{i}" for i in range(5)]
        result = v.strategy_clustering(identical, ids)
        assert result["effective_n"] < 3  # near-identical → low eff N


class TestRegimeConditional:
    def test_returns_required_keys(self, port_returns: np.ndarray):
        v = PortfolioValidator()
        result = v.regime_conditional(port_returns)
        assert "regimes" in result
        assert "all_regimes_positive" in result
        assert "stress_ratio" in result
        assert set(result["regimes"].keys()) == {"low_vol", "normal", "high_vol", "deep_drawdown"}

    def test_regime_bars_sum_to_total(self, port_returns: np.ndarray):
        v = PortfolioValidator()
        result = v.regime_conditional(port_returns, vol_lookback=60)
        total_bars = sum(r["bars"] for r in result["regimes"].values())
        # Should account for most bars (minus warmup)
        assert total_bars >= len(port_returns) * 0.9


class TestTailRisk:
    def test_returns_required_keys(self, port_returns: np.ndarray):
        v = PortfolioValidator()
        result = v.tail_risk(port_returns)
        assert "var_95" in result
        assert "cvar_95" in result
        assert "var_99" in result
        assert "cvar_99" in result
        assert "tail_ratio" in result

    def test_cvar_worse_than_var(self, port_returns: np.ndarray):
        v = PortfolioValidator()
        result = v.tail_risk(port_returns)
        assert result["cvar_95"] <= result["var_95"]
        assert result["cvar_99"] <= result["var_99"]

    def test_var99_worse_than_var95(self, port_returns: np.ndarray):
        v = PortfolioValidator()
        result = v.tail_risk(port_returns)
        assert result["var_99"] <= result["var_95"]


class TestRunAll:
    def test_returns_validation_result(self, returns_matrix, weights, strategy_ids):
        v = PortfolioValidator()
        result = v.run_all(returns_matrix, weights, strategy_ids, n_trials=100)
        assert isinstance(result, ValidationResult)
        assert "overall_pass" in result.summary
        assert result.deflated_sharpe is not None
        assert result.alpha_decay is not None
        assert result.clustering is not None
        assert result.regime_conditional is not None
        assert result.tail_risk is not None

    def test_summary_contains_all_keys(self, returns_matrix, weights, strategy_ids):
        v = PortfolioValidator()
        result = v.run_all(returns_matrix, weights, strategy_ids, n_trials=100)
        expected_keys = {
            "dsr_significant", "dsr_value", "alpha_stable", "alpha_decay_status",
            "effective_strategies", "diversification_pct", "all_regimes_positive",
            "stress_ratio", "cvar_99_pct", "tail_ratio", "overall_pass",
        }
        assert expected_keys.issubset(set(result.summary.keys()))
