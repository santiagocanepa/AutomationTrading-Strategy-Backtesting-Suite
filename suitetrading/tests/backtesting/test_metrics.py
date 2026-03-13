"""Tests for metrics.py — performance metrics computation."""

import numpy as np
import pandas as pd
import pytest

from suitetrading.backtesting.metrics import MetricsEngine, _annualisation_factor


class TestMetricsEngine:
    @pytest.fixture
    def engine(self):
        return MetricsEngine()

    def test_empty_equity_curve(self, engine):
        result = engine.compute(equity_curve=np.array([]))
        assert result["net_profit"] == 0.0
        assert result["total_trades"] == 0

    def test_flat_equity(self, engine):
        eq = np.full(100, 10_000.0)
        result = engine.compute(equity_curve=eq, initial_capital=10_000.0)
        assert result["net_profit"] == 0.0
        assert result["total_return_pct"] == 0.0
        assert result["max_drawdown_pct"] == 0.0

    def test_profitable_run(self, engine):
        eq = np.linspace(10_000, 12_000, 500)
        result = engine.compute(equity_curve=eq, initial_capital=10_000.0)
        assert result["net_profit"] == pytest.approx(2000.0, abs=1)
        assert result["total_return_pct"] == pytest.approx(20.0, abs=0.1)
        assert result["sharpe"] > 0
        assert result["max_drawdown_pct"] == pytest.approx(0.0, abs=0.1)

    def test_losing_run(self, engine):
        eq = np.linspace(10_000, 8_000, 500)
        result = engine.compute(equity_curve=eq, initial_capital=10_000.0)
        assert result["net_profit"] < 0
        assert result["total_return_pct"] < 0
        assert result["max_drawdown_pct"] > 0

    def test_drawdown_calculation(self, engine):
        eq = np.array([100, 110, 105, 120, 90, 95, 100])
        result = engine.compute(equity_curve=eq, initial_capital=100.0)
        # Peak 120, trough 90 → DD = 30/120 = 25%
        assert result["max_drawdown_pct"] == pytest.approx(25.0, abs=0.1)

    def test_trade_metrics_winning(self, engine):
        trades = pd.DataFrame({"pnl": [100, 50, -30, 80, -20]})
        result = engine.compute(
            equity_curve=np.full(10, 10_000.0),
            trades=trades,
            initial_capital=10_000.0,
        )
        assert result["total_trades"] == 5
        assert result["win_rate"] == pytest.approx(60.0, abs=0.1)
        assert result["profit_factor"] > 1.0
        assert result["average_trade"] == pytest.approx(36.0, abs=0.1)

    def test_all_winning_trades(self, engine):
        trades = pd.DataFrame({"pnl": [100, 200, 50]})
        result = engine.compute(
            equity_curve=np.full(10, 10_000.0),
            trades=trades,
            initial_capital=10_000.0,
        )
        assert result["win_rate"] == 100.0
        assert result["profit_factor"] == 999.99  # capped inf
        assert result["max_consecutive_losses"] == 0

    def test_all_losing_trades(self, engine):
        trades = pd.DataFrame({"pnl": [-100, -200, -50]})
        result = engine.compute(
            equity_curve=np.full(10, 10_000.0),
            trades=trades,
            initial_capital=10_000.0,
        )
        assert result["win_rate"] == 0.0
        assert result["profit_factor"] == 0.0
        assert result["max_consecutive_losses"] == 3

    def test_max_consecutive_losses(self, engine):
        trades = pd.DataFrame({"pnl": [100, -10, -20, -30, 50, -5, -15]})
        result = engine.compute(
            equity_curve=np.full(10, 10_000.0),
            trades=trades,
            initial_capital=10_000.0,
        )
        assert result["max_consecutive_losses"] == 3

    def test_no_trades(self, engine):
        result = engine.compute(
            equity_curve=np.full(10, 10_000.0),
            trades=pd.DataFrame(),
            initial_capital=10_000.0,
        )
        assert result["total_trades"] == 0
        assert result["win_rate"] == 0.0

    def test_sortino_all_positive(self, engine):
        eq = np.linspace(10_000, 11_000, 100)
        result = engine.compute(equity_curve=eq, initial_capital=10_000.0)
        # No downside (<2 losses) → sortino is NaN (statistically undefined)
        assert np.isnan(result["sortino"])

    def test_calmar_ratio(self, engine):
        eq = np.array([1000, 1100, 1050, 1200])
        result = engine.compute(equity_curve=eq, initial_capital=1000.0)
        # return = 20%, max_dd ≈ 4.55% (50 from 1100) → calmar ≈ 4.4
        expected_calmar = 20.0 / (50.0 / 1100.0 * 100.0)
        assert result["calmar"] == pytest.approx(expected_calmar, rel=0.01)


class TestAnnualisation:
    """Verify timeframe-aware annualisation factors."""

    @pytest.mark.parametrize("tf,expected_bpy", [
        ("15m", 365 * 24 * 4),
        ("1h", 365 * 24),
        ("4h", 365 * 6),
        ("1d", 365),
    ])
    def test_annualisation_factor_known_timeframes(self, tf, expected_bpy):
        result = _annualisation_factor(tf)
        assert result == pytest.approx(np.sqrt(expected_bpy))

    def test_annualisation_factor_unknown_falls_back(self):
        result = _annualisation_factor("3m")
        assert result == pytest.approx(np.sqrt(365 * 24))

    def test_annualisation_factor_none_falls_back(self):
        result = _annualisation_factor(None)
        assert result == pytest.approx(np.sqrt(365 * 24))

    def test_context_changes_sharpe(self):
        engine = MetricsEngine()
        eq = np.linspace(10_000, 12_000, 500)

        result_1h = engine.compute(
            equity_curve=eq, initial_capital=10_000.0,
            context={"timeframe": "1h"},
        )
        result_1d = engine.compute(
            equity_curve=eq, initial_capital=10_000.0,
            context={"timeframe": "1d"},
        )
        # 1h has more bars per year → larger annualisation → larger sharpe
        assert abs(result_1h["sharpe"]) > abs(result_1d["sharpe"])
