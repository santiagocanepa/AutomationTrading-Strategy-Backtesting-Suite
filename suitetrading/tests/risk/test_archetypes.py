"""Tests for risk archetypes — each archetype builds a valid RiskConfig."""

from __future__ import annotations

import pytest

from suitetrading.config.archetypes import (
    ARCHETYPE_INDICATORS,
    get_combination_mode,
    get_entry_indicators,
)
from suitetrading.risk.archetypes import ARCHETYPE_REGISTRY, get_archetype
from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.archetypes.legacy import LegacyFirestormProfile, fibonacci_weights
from suitetrading.risk.contracts import RiskConfig


# ═══════════════════════════════════════════════════════════════════════════════
# Registry
# ═══════════════════════════════════════════════════════════════════════════════


class TestRegistry:
    def test_all_registered(self):
        expected = {
            "legacy_firestorm", "trend_following", "mean_reversion",
            "mixed", "pyramidal", "grid_dca", "momentum", "breakout",
            "momentum_trend",
            "donchian_simple",
            "roc_simple",
            "ma_cross_simple",
            "adx_simple",
            "roc_adx",
            "roc_ma",
            "roc_ssl",
            "donchian_adx",
            "ma_ssl", "ma_adx", "donchian_ssl",
            "donchian_roc", "triple_momentum", "roc_fire",
            "ssl_roc", "ssl_ma", "fire_roc", "fire_ma", "wt_roc",
            "macd_simple", "macd_roc", "macd_ssl", "macd_adx",
            "ema_simple", "ema_roc", "ema_adx",
            "roc_donch_ssl", "roc_ma_ssl", "macd_roc_adx", "ema_roc_adx",
            "roc_mtf", "ma_cross_mtf", "macd_mtf", "roc_ssl_mtf", "ema_roc_mtf",
            "roc_mtf_longopt", "roc_shortopt", "macd_mtf_longopt", "macd_shortopt", "ma_x_ssl_longopt", "ema_mtf_longopt",
            "rsi_roc", "rsi_mtf", "bband_roc", "wt_filter_roc", "roc_mtf_roc", "macd_roc_mtf",
            "roc_fullrisk", "roc_fullrisk_mtf", "macd_fullrisk", "ma_x_fullrisk", "ema_fullrisk_mtf",
            "donchian_mtf", "donchian_roc_mtf", "ema_adx_mtf", "roc_macd_mtf", "ssl_adx_mtf", "triple_mtf",
            "roc_fullrisk_pyr", "macd_fullrisk_pyr", "ma_x_fullrisk_pyr",
            "roc_fullrisk_pyr_mtf", "roc_fullrisk_time", "roc_fullrisk_all",
            "donchian_fullrisk_pyr", "ema_fullrisk_pyr", "rsi_fullrisk_pyr",
            "roc_macd_fullrisk_pyr", "roc_ema_fullrisk_pyr", "macd_ema_fullrisk_pyr",
            "roc_adx_fullrisk_pyr",
            "macd_fullrisk_pyr_mtf", "roc_adx_fullrisk_pyr_mtf",
            "macd_fullrisk_time", "macd_fullrisk_all",
            "ssl_fullrisk_pyr", "wt_fullrisk_pyr", "bband_fullrisk_pyr",
            "roc_fullrisk_htf_macd", "roc_fullrisk_pyr_htf_macd", "macd_fullrisk_htf_ema",
            # Sprint 8: FTM stop variants
            "roc_fullrisk_pyr_ftm", "macd_fullrisk_pyr_ftm", "ma_x_fullrisk_pyr_ftm",
            "roc_fullrisk_pyr_mtf_ftm", "donchian_fullrisk_pyr_ftm",
            "ema_fullrisk_pyr_ftm", "rsi_fullrisk_pyr_ftm",
            "roc_macd_fullrisk_pyr_ftm", "roc_ema_fullrisk_pyr_ftm", "macd_ema_fullrisk_pyr_ftm",
            # Sprint 8: Trailing policy variants
            "roc_fullrisk_pyr_trail_policy", "macd_fullrisk_pyr_trail_policy",
            "ma_x_fullrisk_pyr_trail_policy", "roc_fullrisk_pyr_mtf_trail_policy",
            "donchian_fullrisk_pyr_trail_policy",
            # Sprint 9: New indicator archetypes
            "squeeze_fullrisk_pyr", "stochrsi_fullrisk_pyr",
            "ichimoku_fullrisk_pyr", "obv_fullrisk_pyr",
            "squeeze_roc_fullrisk_pyr", "ichimoku_macd_fullrisk_pyr",
            "stochrsi_ema_fullrisk_pyr", "squeeze_fullrisk_pyr_mtf",
            "ichimoku_fullrisk_pyr_mtf", "obv_roc_fullrisk_pyr",
            "squeeze_ssl_fullrisk_pyr", "ichimoku_ssl_fullrisk_pyr",
        }
        assert set(ARCHETYPE_REGISTRY.keys()) == expected

    def test_get_archetype_returns_correct_type(self):
        for name, cls in ARCHETYPE_REGISTRY.items():
            instance = get_archetype(name)
            assert isinstance(instance, cls)

    def test_get_archetype_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown archetype"):
            get_archetype("nonexistent")


class TestIndicatorArchetypeConfig:
    """Tests for config/archetypes.py — indicator mapping."""

    def test_all_indicator_archetypes_have_risk_archetype(self):
        for name in ARCHETYPE_INDICATORS:
            assert name in ARCHETYPE_REGISTRY, f"'{name}' lacks a risk archetype"

    def test_mixed_uses_majority(self):
        mode, threshold = get_combination_mode("mixed")
        assert mode == "majority"
        assert threshold == 2

    def test_trend_following_uses_excluyente(self):
        mode, threshold = get_combination_mode("trend_following")
        assert mode == "excluyente"
        assert threshold is None

    def test_momentum_has_three_entry_indicators(self):
        assert len(get_entry_indicators("momentum")) == 3

    def test_breakout_has_three_entry_indicators(self):
        assert len(get_entry_indicators("breakout")) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# Every archetype builds valid RiskConfig
# ═══════════════════════════════════════════════════════════════════════════════


class TestAllArchetypesBuildConfig:
    @pytest.mark.parametrize("name", list(ARCHETYPE_REGISTRY.keys()))
    def test_builds_valid_config(self, name: str):
        arch = get_archetype(name)
        cfg = arch.build_config()
        assert isinstance(cfg, RiskConfig)
        assert cfg.archetype == name

    @pytest.mark.parametrize("name", list(ARCHETYPE_REGISTRY.keys()))
    def test_overrides_apply(self, name: str):
        arch = get_archetype(name)
        cfg = arch.build_config(initial_capital=99_999.0)
        assert cfg.initial_capital == pytest.approx(99_999.0)

    @pytest.mark.parametrize("name", list(ARCHETYPE_REGISTRY.keys()))
    def test_nested_overrides(self, name: str):
        arch = get_archetype(name)
        cfg = arch.build_config(sizing={"risk_pct": 2.5})
        assert cfg.sizing.risk_pct == pytest.approx(2.5)


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy Firestorm specifics
# ═══════════════════════════════════════════════════════════════════════════════


class TestLegacyFirestorm:
    def test_direction_long_only(self):
        cfg = LegacyFirestormProfile().build_config()
        assert cfg.direction == "long"

    def test_sizing_5pct(self):
        cfg = LegacyFirestormProfile().build_config()
        assert cfg.sizing.risk_pct == pytest.approx(5.0)

    def test_be_buffer(self):
        cfg = LegacyFirestormProfile().build_config()
        assert cfg.break_even.buffer == pytest.approx(1.0007)

    def test_partial_tp_35pct(self):
        cfg = LegacyFirestormProfile().build_config()
        assert cfg.partial_tp.close_pct == pytest.approx(35.0)

    def test_pyramid_3_adds_fibonacci(self):
        cfg = LegacyFirestormProfile().build_config()
        assert cfg.pyramid.max_adds == 3
        assert cfg.pyramid.weighting == "fibonacci"

    def test_stop_model_signal(self):
        cfg = LegacyFirestormProfile().build_config()
        assert cfg.stop.model == "signal"

    def test_trailing_model_signal(self):
        cfg = LegacyFirestormProfile().build_config()
        assert cfg.trailing.model == "signal"


# ═══════════════════════════════════════════════════════════════════════════════
# Fibonacci weights helper
# ═══════════════════════════════════════════════════════════════════════════════


class TestFibonacciWeights:
    def test_three_orders(self):
        w = fibonacci_weights(3)
        assert len(w) == 3
        assert w == pytest.approx([0.25, 0.25, 0.50])

    def test_sums_to_one(self):
        for n in range(1, 8):
            w = fibonacci_weights(n)
            assert sum(w) == pytest.approx(1.0)

    def test_zero_returns_empty(self):
        assert fibonacci_weights(0) == []

    def test_one_order(self):
        assert fibonacci_weights(1) == pytest.approx([1.0])


# ═══════════════════════════════════════════════════════════════════════════════
# Archetype-specific values
# ═══════════════════════════════════════════════════════════════════════════════


class TestTrendFollowing:
    def test_risk_pct(self):
        cfg = get_archetype("trend_following").build_config()
        assert cfg.sizing.risk_pct == pytest.approx(0.5)

    def test_pyramid_enabled(self):
        cfg = get_archetype("trend_following").build_config()
        assert cfg.pyramid.enabled is True
        assert cfg.pyramid.max_adds == 3


class TestMeanReversion:
    def test_no_pyramid(self):
        cfg = get_archetype("mean_reversion").build_config()
        assert cfg.pyramid.enabled is False

    def test_time_exit_enabled(self):
        cfg = get_archetype("mean_reversion").build_config()
        assert cfg.time_exit.enabled is True


class TestGridDCA:
    def test_high_pyramid_adds(self):
        cfg = get_archetype("grid_dca").build_config()
        assert cfg.pyramid.max_adds == 8

    def test_full_tp_close(self):
        cfg = get_archetype("grid_dca").build_config()
        assert cfg.partial_tp.close_pct == pytest.approx(100.0)
