"""Tests for WarmupCalculator."""

from __future__ import annotations

from datetime import timedelta

import pytest

from suitetrading.data.warmup import (
    DEFAULT_WARMUP_BARS,
    INDICATOR_WARMUP,
    WarmupCalculator,
    _tf_to_timedelta,
)


@pytest.fixture
def calc() -> WarmupCalculator:
    return WarmupCalculator()


# ═══════════════════════════════════════════════════════════════════════════════
# _tf_to_timedelta
# ═══════════════════════════════════════════════════════════════════════════════


class TestTfToTimedelta:
    def test_1m_100_bars(self):
        assert _tf_to_timedelta("1m", 100) == timedelta(minutes=100)

    def test_1h_50_bars(self):
        assert _tf_to_timedelta("1h", 50) == timedelta(hours=50)

    def test_1d_10_bars(self):
        assert _tf_to_timedelta("1d", 10) == timedelta(days=10)

    def test_1M_monthly_approx(self):
        td = _tf_to_timedelta("1M", 3)
        assert td == timedelta(days=90)


# ═══════════════════════════════════════════════════════════════════════════════
# WarmupCalculator.calculate
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalculate:
    def test_single_ema_1h(self, calc: WarmupCalculator):
        indicators = [{"key": "ema_21", "timeframe": "1h"}]
        result = calc.calculate(indicators)
        expected = timedelta(hours=INDICATOR_WARMUP["ema_21"])  # 100h
        assert result == expected

    def test_multi_indicator_takes_max(self, calc: WarmupCalculator):
        indicators = [
            {"key": "rsi_14", "timeframe": "1m"},   # 100 × 60s = 6000s
            {"key": "ema_200", "timeframe": "1h"},   # 600 × 3600s = 2_160_000s
        ]
        result = calc.calculate(indicators)
        expected_max = timedelta(seconds=600 * 3600)
        assert result == expected_max

    def test_unknown_indicator_uses_default(self, calc: WarmupCalculator):
        indicators = [{"key": "unknown_indicator", "timeframe": "5m"}]
        result = calc.calculate(indicators)
        expected = timedelta(seconds=DEFAULT_WARMUP_BARS * 300)
        assert result == expected

    def test_empty_indicators_returns_zero(self, calc: WarmupCalculator):
        assert calc.calculate([]) == timedelta(0)

    def test_squeeze_weekly(self, calc: WarmupCalculator):
        indicators = [{"key": "squeeze", "timeframe": "1w"}]
        result = calc.calculate(indicators)
        expected = timedelta(seconds=INDICATOR_WARMUP["squeeze"] * 604800)
        assert result == expected


# ═══════════════════════════════════════════════════════════════════════════════
# WarmupCalculator.calculate_from_config
# ═══════════════════════════════════════════════════════════════════════════════


class TestCalculateFromConfig:
    def test_config_with_indicators(self, calc: WarmupCalculator):
        config = {
            "base_timeframe": "1m",
            "indicators": [
                {"key": "ema_50", "timeframe": "15m"},
            ],
        }
        result = calc.calculate_from_config(config)
        assert result == timedelta(seconds=INDICATOR_WARMUP["ema_50"] * 900)

    def test_config_empty(self, calc: WarmupCalculator):
        assert calc.calculate_from_config({}) == timedelta(0)
