"""Tests for risk contracts — Pydantic models, enums, dataclasses."""

from __future__ import annotations

import pytest

from suitetrading.risk.contracts import (
    BreakEvenConfig,
    PartialTPConfig,
    PortfolioLimits,
    PositionSnapshot,
    PositionState,
    PyramidConfig,
    RiskConfig,
    SizingConfig,
    StopConfig,
    TrailingConfig,
    TransitionEvent,
    TransitionResult,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════


class TestPositionState:
    def test_all_states_exist(self):
        states = {s.name for s in PositionState}
        expected = {"FLAT", "OPEN_INITIAL", "OPEN_BREAKEVEN", "OPEN_TRAILING",
                    "OPEN_PYRAMIDED", "PARTIALLY_CLOSED", "CLOSED"}
        assert states == expected


class TestTransitionEvent:
    def test_string_values(self):
        assert TransitionEvent.ENTRY_FILLED == "entry_filled"
        assert TransitionEvent.STOP_LOSS_HIT == "stop_loss_hit"
        assert TransitionEvent.KILL_SWITCH_TRIGGERED == "kill_switch_triggered"


# ═══════════════════════════════════════════════════════════════════════════════
# Dataclasses
# ═══════════════════════════════════════════════════════════════════════════════


class TestPositionSnapshot:
    def test_defaults(self):
        snap = PositionSnapshot()
        assert snap.state == PositionState.FLAT
        assert snap.direction == "flat"
        assert snap.quantity == 0.0
        assert snap.tp1_hit is False

    def test_custom_values(self):
        snap = PositionSnapshot(state=PositionState.OPEN_INITIAL, direction="long", quantity=5.0)
        assert snap.quantity == 5.0
        assert snap.direction == "long"


class TestTransitionResult:
    def test_defaults(self):
        snap = PositionSnapshot()
        result = TransitionResult(snapshot=snap)
        assert result.event is None
        assert result.reason is None
        assert result.orders == []
        assert result.state_changed is False


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic configs
# ═══════════════════════════════════════════════════════════════════════════════


class TestSizingConfig:
    def test_defaults(self):
        cfg = SizingConfig()
        assert cfg.model == "fixed_fractional"
        assert cfg.risk_pct == 1.0

    def test_validation_rejects_zero_risk(self):
        with pytest.raises(Exception):
            SizingConfig(risk_pct=0.0)

    def test_validation_rejects_negative_leverage(self):
        with pytest.raises(Exception):
            SizingConfig(max_leverage=0.5)


class TestRiskConfig:
    def test_defaults(self):
        cfg = RiskConfig()
        assert cfg.archetype == "mixed"
        assert cfg.direction == "both"
        assert isinstance(cfg.sizing, SizingConfig)
        assert isinstance(cfg.portfolio, PortfolioLimits)

    def test_pyramid_risk_validator(self):
        """max_adds × max_risk_per_trade must not exceed 100%."""
        with pytest.raises(ValueError, match="pyramid"):
            RiskConfig(
                pyramid=PyramidConfig(enabled=True, max_adds=20),
                sizing=SizingConfig(max_risk_per_trade=10.0),
            )

    def test_valid_config_passes(self):
        cfg = RiskConfig(
            sizing=SizingConfig(risk_pct=1.0, max_risk_per_trade=5.0),
            pyramid=PyramidConfig(max_adds=3),
        )
        assert cfg.pyramid.max_adds == 3


class TestPartialTPConfig:
    def test_close_pct_bounds(self):
        with pytest.raises(Exception):
            PartialTPConfig(close_pct=0.5)  # below ge=1.0

    def test_valid(self):
        cfg = PartialTPConfig(close_pct=50.0, trigger="r_multiple")
        assert cfg.trigger == "r_multiple"


class TestPortfolioLimits:
    def test_defaults(self):
        lim = PortfolioLimits()
        assert lim.max_portfolio_heat == 15.0
        assert lim.kill_switch_drawdown == 25.0
