"""Tests for PortfolioRiskManager — drawdown, heat, kill switch, Monte Carlo."""

from __future__ import annotations

import numpy as np
import pytest

from suitetrading.risk.contracts import PortfolioLimits
from suitetrading.risk.portfolio import PortfolioRiskManager, PortfolioState


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def default_limits() -> PortfolioLimits:
    return PortfolioLimits(
        max_portfolio_heat=15.0,
        max_drawdown_pct=20.0,
        max_gross_exposure=1.0,
        kill_switch_drawdown=25.0,
    )


@pytest.fixture
def mgr(default_limits: PortfolioLimits) -> PortfolioRiskManager:
    return PortfolioRiskManager(default_limits)


# ═══════════════════════════════════════════════════════════════════════════════
# Update / drawdown tracking
# ═══════════════════════════════════════════════════════════════════════════════


class TestUpdate:
    def test_peak_tracks_highest(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        assert mgr.state.peak_equity == 10_000
        mgr.update(equity=12_000)
        assert mgr.state.peak_equity == 12_000
        mgr.update(equity=11_000)
        assert mgr.state.peak_equity == 12_000

    def test_drawdown_pct_calculated(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        mgr.update(equity=8_000)
        assert mgr.state.drawdown_pct == pytest.approx(20.0)

    def test_zero_equity(self, mgr: PortfolioRiskManager):
        state = mgr.update(equity=0.0)
        assert state.drawdown_pct == 0.0

    def test_exposure_calculations(self, mgr: PortfolioRiskManager):
        positions = [
            {"direction": "long", "quantity": 10.0, "entry_price": 100.0,
             "current_price": 105.0, "stop_price": 95.0},
        ]
        mgr.update(equity=10_000, open_positions=positions)
        # gross = 10*105 = 1050; exposure = 1050/10000 = 0.105
        assert mgr.state.gross_exposure == pytest.approx(0.105)
        assert mgr.state.active_positions == 1
        # risk = 10 * |105-95| = 100
        assert mgr.state.open_risk == pytest.approx(100.0)


# ═══════════════════════════════════════════════════════════════════════════════
# Kill switch
# ═══════════════════════════════════════════════════════════════════════════════


class TestKillSwitch:
    def test_kill_switch_triggers(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        mgr.update(equity=7_000)  # 30% DD → ≥ 25% threshold
        assert mgr.state.killed is True
        assert mgr.state.kill_reason is not None

    def test_kill_switch_stays_killed(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        mgr.update(equity=7_000)
        mgr.update(equity=11_000)  # recovery
        assert mgr.state.killed is True  # once killed, stays killed


# ═══════════════════════════════════════════════════════════════════════════════
# Approve new risk
# ═══════════════════════════════════════════════════════════════════════════════


class TestApproveNewRisk:
    def test_approved_when_healthy(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        ok, reason = mgr.approve_new_risk(proposed_risk=100.0)
        assert ok is True
        assert reason == "approved"

    def test_rejected_when_killed(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        mgr.update(equity=7_000)  # triggers kill
        ok, reason = mgr.approve_new_risk(proposed_risk=10.0)
        assert ok is False
        assert "Kill switch" in reason

    def test_rejected_on_drawdown_limit(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        mgr.update(equity=8_000)  # 20% DD = limit
        ok, reason = mgr.approve_new_risk(proposed_risk=10.0)
        assert ok is False
        assert "Drawdown" in reason

    def test_rejected_on_heat_limit(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        # open_risk already at  1400 (14%) + 200 proposed = 1600 (16%) > 15% heat
        mgr.state.open_risk = 1400.0
        ok, reason = mgr.approve_new_risk(proposed_risk=200.0)
        assert ok is False
        assert "heat" in reason.lower()

    def test_rejected_on_gross_exposure(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        mgr.state.gross_exposure = 0.95
        ok, reason = mgr.approve_new_risk(proposed_risk=50.0, proposed_notional=1000.0)
        assert ok is False
        assert "exposure" in reason.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# Evaluate portfolio
# ═══════════════════════════════════════════════════════════════════════════════


class TestEvaluatePortfolio:
    def test_report_keys(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        report = mgr.evaluate_portfolio()
        assert "equity" in report
        assert "drawdown_pct" in report
        assert "action" in report
        assert "killed" in report

    def test_action_approve(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        report = mgr.evaluate_portfolio()
        assert report["action"] == "approve"

    def test_action_reduce(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        mgr.update(equity=8_400)  # 16% dd → 80% of 20% limit → reduce
        report = mgr.evaluate_portfolio()
        assert report["action"] == "reduce"

    def test_action_halt(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        mgr.update(equity=7_000)  # killed
        report = mgr.evaluate_portfolio()
        assert report["action"] == "halt"


# ═══════════════════════════════════════════════════════════════════════════════
# Monte Carlo
# ═══════════════════════════════════════════════════════════════════════════════


class TestMonteCarlo:
    def test_output_shape(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.001, 0.02, 200)
        result = PortfolioRiskManager.monte_carlo(returns, n_simulations=500, seed=42)
        assert "max_dd_p50" in result
        assert "max_dd_p95" in result
        assert "terminal_p50" in result
        assert "prob_ruin" in result
        assert result["n_simulations"] == 500

    def test_reproducible_with_seed(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(0.001, 0.02, 100)
        r1 = PortfolioRiskManager.monte_carlo(returns, seed=123)
        r2 = PortfolioRiskManager.monte_carlo(returns, seed=123)
        assert r1["max_dd_p50"] == r2["max_dd_p50"]
        assert r1["terminal_p50"] == r2["terminal_p50"]

    def test_empty_returns(self):
        result = PortfolioRiskManager.monte_carlo(np.array([]))
        assert "error" in result

    def test_prob_ruin_between_0_and_1(self):
        rng = np.random.default_rng(42)
        returns = rng.normal(-0.01, 0.05, 300)  # slightly negative
        result = PortfolioRiskManager.monte_carlo(returns, seed=42)
        assert 0.0 <= result["prob_ruin"] <= 1.0


# ═══════════════════════════════════════════════════════════════════════════════
# Reset
# ═══════════════════════════════════════════════════════════════════════════════


class TestPortfolioReset:
    def test_reset_clears_state(self, mgr: PortfolioRiskManager):
        mgr.update(equity=10_000)
        mgr.update(equity=7_000)
        assert mgr.state.killed is True
        mgr.reset()
        assert mgr.state.killed is False
        assert mgr.state.equity == 0.0
