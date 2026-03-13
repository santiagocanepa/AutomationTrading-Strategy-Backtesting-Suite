"""Tests for position sizing models."""

from __future__ import annotations

import warnings

import pytest

from suitetrading.risk.contracts import SizingConfig
from suitetrading.risk.position_sizing import (
    ATRSizer,
    FixedFractionalSizer,
    KellySizer,
    OptimalFSizer,
    PositionSizer,
    create_sizer,
)


# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def default_cfg() -> SizingConfig:
    return SizingConfig(risk_pct=1.0, max_risk_per_trade=5.0, max_leverage=1.0)


@pytest.fixture
def base_kwargs() -> dict:
    return {"equity": 10_000.0, "entry_price": 100.0, "stop_price": 95.0}


# ═══════════════════════════════════════════════════════════════════════════════
# FixedFractionalSizer
# ═══════════════════════════════════════════════════════════════════════════════


class TestFixedFractionalSizer:
    def test_basic_calculation(self, default_cfg: SizingConfig):
        sizer = FixedFractionalSizer(default_cfg)
        # risk_amount = 10000 * 1% = 100; stop_dist = |100-95| = 5; size = 100/5 = 20
        size = sizer.size(equity=10_000, entry_price=100.0, stop_price=95.0)
        assert size == pytest.approx(20.0)

    def test_short_direction(self, default_cfg: SizingConfig):
        sizer = FixedFractionalSizer(default_cfg)
        # stop above entry for short: stop_dist = |90 - 95| = 5
        size = sizer.size(equity=10_000, entry_price=90.0, stop_price=95.0)
        assert size == pytest.approx(20.0)

    def test_returns_zero_without_stop(self, default_cfg: SizingConfig):
        sizer = FixedFractionalSizer(default_cfg)
        assert sizer.size(equity=10_000, entry_price=100.0) == 0.0

    def test_returns_zero_when_stop_equals_entry(self, default_cfg: SizingConfig):
        sizer = FixedFractionalSizer(default_cfg)
        assert sizer.size(equity=10_000, entry_price=100.0, stop_price=100.0) == 0.0

    def test_max_risk_per_trade_caps(self):
        cfg = SizingConfig(risk_pct=50.0, max_risk_per_trade=2.0, max_leverage=100.0)
        sizer = FixedFractionalSizer(cfg)
        # risk capped at 2% = 200; stop_dist = 5; raw = 40
        size = sizer.size(equity=10_000, entry_price=100.0, stop_price=95.0)
        assert size == pytest.approx(40.0)

    def test_leverage_cap(self):
        cfg = SizingConfig(risk_pct=10.0, max_risk_per_trade=10.0, max_leverage=1.0)
        sizer = FixedFractionalSizer(cfg)
        # risk = 1000; stop_dist=1; raw=1000 but leverage cap: 10000*1/100=100
        size = sizer.size(equity=10_000, entry_price=100.0, stop_price=99.0)
        assert size == pytest.approx(100.0)

    def test_min_position_filter(self):
        cfg = SizingConfig(risk_pct=0.01, min_position_size=5.0)
        sizer = FixedFractionalSizer(cfg)
        # risk = 10000*0.01% = 1; stop_dist=5; raw=0.2 < min 5.0 → 0
        assert sizer.size(equity=10_000, entry_price=100.0, stop_price=95.0) == 0.0


# ═══════════════════════════════════════════════════════════════════════════════
# ATRSizer
# ═══════════════════════════════════════════════════════════════════════════════


class TestATRSizer:
    def test_basic_calculation(self, default_cfg: SizingConfig):
        sizer = ATRSizer(default_cfg)
        # risk = 100; denom = 2.0 * 2.0 = 4; raw = 25
        size = sizer.size(equity=10_000, entry_price=100.0, volatility_value=2.0)
        assert size == pytest.approx(25.0)

    def test_returns_zero_without_atr(self, default_cfg: SizingConfig):
        sizer = ATRSizer(default_cfg)
        assert sizer.size(equity=10_000, entry_price=100.0) == 0.0

    def test_returns_zero_for_negative_atr(self, default_cfg: SizingConfig):
        sizer = ATRSizer(default_cfg)
        assert sizer.size(equity=10_000, entry_price=100.0, volatility_value=-1.0) == 0.0

    def test_higher_atr_smaller_position(self, default_cfg: SizingConfig):
        sizer = ATRSizer(default_cfg)
        s1 = sizer.size(equity=10_000, entry_price=100.0, volatility_value=2.0)
        s2 = sizer.size(equity=10_000, entry_price=100.0, volatility_value=4.0)
        assert s2 < s1


# ═══════════════════════════════════════════════════════════════════════════════
# KellySizer
# ═══════════════════════════════════════════════════════════════════════════════


class TestKellySizer:
    def test_positive_edge(self, default_cfg: SizingConfig):
        sizer = KellySizer(default_cfg)
        stats = {"win_rate": 0.6, "payoff_ratio": 2.0}
        size = sizer.size(
            equity=10_000, entry_price=100.0, stop_price=95.0,
            strategy_stats=stats,
        )
        # Kelly = 0.6 - 0.4/2.0 = 0.4; fractional = 0.4*0.5 = 0.2
        # risk = 10000 * 0.2 = 2000; stop_dist = 5; raw = 400
        # BUT capped by leverage: 10000*1/100 = 100
        assert size > 0

    def test_no_edge_returns_zero(self, default_cfg: SizingConfig):
        sizer = KellySizer(default_cfg)
        # K = 0.3 - 0.7/0.3 = 0.3 - 2.33 = -2.03 → negative → 0
        stats = {"win_rate": 0.3, "payoff_ratio": 0.3}
        assert sizer.size(
            equity=10_000, entry_price=100.0, stop_price=95.0,
            strategy_stats=stats,
        ) == 0.0

    def test_missing_stats_returns_zero(self, default_cfg: SizingConfig):
        sizer = KellySizer(default_cfg)
        assert sizer.size(equity=10_000, entry_price=100.0) == 0.0

    def test_edge_win_rate_boundary(self, default_cfg: SizingConfig):
        sizer = KellySizer(default_cfg)
        # win_rate=1.0 → returns 0 (ge 1.0 check)
        assert sizer.size(
            equity=10_000, entry_price=100.0,
            strategy_stats={"win_rate": 1.0, "payoff_ratio": 2.0},
        ) == 0.0

    def test_without_stop_uses_entry_price(self):
        cfg = SizingConfig(risk_pct=1.0, max_leverage=10.0)
        sizer = KellySizer(cfg)
        stats = {"win_rate": 0.6, "payoff_ratio": 2.0}
        size = sizer.size(equity=10_000, entry_price=100.0, strategy_stats=stats)
        assert size > 0


# ═══════════════════════════════════════════════════════════════════════════════
# OptimalFSizer
# ═══════════════════════════════════════════════════════════════════════════════


class TestOptimalFSizer:
    def test_emits_warning(self, default_cfg: SizingConfig):
        sizer = OptimalFSizer(default_cfg)
        trades = [0.02, -0.01, 0.03, 0.01, -0.005, 0.015, -0.02, 0.01, 0.005, -0.01, 0.02, -0.005]
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            sizer.size(
                equity=10_000, entry_price=100.0, stop_price=95.0,
                strategy_stats={"trades": trades},
            )
            assert any("experimental" in str(x.message).lower() for x in w)

    def test_returns_zero_with_few_trades(self, default_cfg: SizingConfig):
        sizer = OptimalFSizer(default_cfg)
        assert sizer.size(
            equity=10_000, entry_price=100.0,
            strategy_stats={"trades": [0.01, -0.01]},
        ) == 0.0

    def test_returns_positive_with_profitable_trades(self):
        cfg = SizingConfig(risk_pct=1.0, max_leverage=10.0)
        sizer = OptimalFSizer(cfg)
        trades = [0.05, 0.03, -0.01, 0.04, 0.02, -0.02, 0.06, 0.01, -0.005, 0.03, 0.02, -0.01]
        size = sizer.size(
            equity=10_000, entry_price=100.0, stop_price=95.0,
            strategy_stats={"trades": trades},
        )
        assert size > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateSizer:
    def test_creates_fixed_fractional(self):
        cfg = SizingConfig(model="fixed_fractional")
        assert isinstance(create_sizer(cfg), FixedFractionalSizer)

    def test_creates_atr(self):
        cfg = SizingConfig(model="atr")
        assert isinstance(create_sizer(cfg), ATRSizer)

    def test_creates_kelly(self):
        cfg = SizingConfig(model="kelly")
        assert isinstance(create_sizer(cfg), KellySizer)

    def test_creates_optimal_f(self):
        cfg = SizingConfig(model="optimal_f")
        assert isinstance(create_sizer(cfg), OptimalFSizer)

    def test_unknown_model_raises(self):
        cfg = SizingConfig(model="unknown_sizer")
        with pytest.raises(ValueError, match="Unknown sizing model"):
            create_sizer(cfg)


# ═══════════════════════════════════════════════════════════════════════════════
# Clamp edge cases
# ═══════════════════════════════════════════════════════════════════════════════


class TestClampEdgeCases:
    def test_clamp_negative_size(self):
        cfg = SizingConfig()
        assert PositionSizer._clamp(-10.0, cfg, 10_000, 100.0) == 0.0

    def test_clamp_nan_size(self):
        cfg = SizingConfig()
        assert PositionSizer._clamp(float("nan"), cfg, 10_000, 100.0) == 0.0

    def test_clamp_inf_size(self):
        cfg = SizingConfig()
        assert PositionSizer._clamp(float("inf"), cfg, 10_000, 100.0) == 0.0

    def test_clamp_zero_entry_price(self):
        cfg = SizingConfig()
        assert PositionSizer._clamp(10.0, cfg, 10_000, 0.0) == 0.0
