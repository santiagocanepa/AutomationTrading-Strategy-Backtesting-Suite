"""Tests for ASH (Absolute Strength Histogram) indicator."""

import numpy as np
import pandas as pd
import pytest

from suitetrading.indicators.custom.ash import ASH, ash_compute


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Synthetic OHLCV with trend + reversal."""
    np.random.seed(42)
    n = 300
    trend = np.concatenate([
        np.linspace(100, 160, 150),
        np.linspace(160, 105, 150),
    ])
    noise = np.random.randn(n) * 2
    close = trend + noise
    high = close + np.abs(np.random.randn(n)) * 3
    low = close - np.abs(np.random.randn(n)) * 3
    open_ = close + np.random.randn(n) * 1
    volume = np.random.randint(1000, 10000, n).astype(float)
    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


class TestASHCompute:
    def test_output_has_expected_keys(self, sample_ohlcv):
        result = ash_compute(sample_ohlcv["close"], sample_ohlcv["high"], sample_ohlcv["low"])
        assert set(result.keys()) == {"sm_bulls", "sm_bears", "diff", "bullish", "bearish"}

    def test_output_length_matches_input(self, sample_ohlcv):
        result = ash_compute(sample_ohlcv["close"], sample_ohlcv["high"], sample_ohlcv["low"])
        for key, series in result.items():
            assert len(series) == len(sample_ohlcv), f"{key} length mismatch"

    def test_diff_is_non_negative(self, sample_ohlcv):
        result = ash_compute(sample_ohlcv["close"], sample_ohlcv["high"], sample_ohlcv["low"])
        assert (result["diff"] >= -1e-10).all()

    @pytest.mark.parametrize("mode", ["rsi", "stochastic", "adx"])
    def test_mode_does_not_crash(self, sample_ohlcv, mode):
        result = ash_compute(
            sample_ohlcv["close"], sample_ohlcv["high"], sample_ohlcv["low"],
            mode=mode,
        )
        assert len(result["bullish"]) == len(sample_ohlcv)
        assert result["bullish"].dtype == bool

    @pytest.mark.parametrize("ma_type", ["ema", "sma", "wma"])
    def test_ma_type_does_not_crash(self, sample_ohlcv, ma_type):
        result = ash_compute(
            sample_ohlcv["close"], sample_ohlcv["high"], sample_ohlcv["low"],
            ma_type=ma_type,
        )
        assert len(result["diff"]) == len(sample_ohlcv)


class TestASHIndicator:
    def test_compute_returns_bool_series(self, sample_ohlcv):
        ind = ASH()
        result = ind.compute(sample_ohlcv)
        assert isinstance(result, pd.Series)
        assert result.dtype == bool
        assert len(result) == len(sample_ohlcv)

    @pytest.mark.parametrize("mode", ["rsi", "stochastic", "adx"])
    def test_all_modes_produce_signals(self, sample_ohlcv, mode):
        ind = ASH()
        result = ind.compute(sample_ohlcv, mode=mode)
        assert result.dtype == bool
        assert len(result) == len(sample_ohlcv)

    def test_bullish_and_bearish_differ(self, sample_ohlcv):
        """Bullish and bearish signals should not be identical."""
        ind = ASH()
        bull = ind.compute(sample_ohlcv, signal_mode="bullish")
        bear = ind.compute(sample_ohlcv, signal_mode="bearish")
        assert not bull.equals(bear), "bullish and bearish signals are identical"

    def test_bullish_and_bearish_not_both_true(self, sample_ohlcv):
        """At any bar, bullish and bearish should not both be True."""
        ind = ASH()
        bull = ind.compute(sample_ohlcv, signal_mode="bullish")
        bear = ind.compute(sample_ohlcv, signal_mode="bearish")
        overlap = (bull & bear).sum()
        assert overlap == 0, f"{overlap} bars have both bullish and bearish True"

    def test_params_schema_valid(self):
        ind = ASH()
        schema = ind.params_schema()
        assert "length" in schema
        assert "smooth" in schema
        assert "mode" in schema
        assert "ma_type" in schema
        assert "signal_mode" in schema
        # Check types and ranges
        assert schema["length"]["type"] == "int"
        assert schema["length"]["min"] == 3
        assert schema["length"]["max"] == 30
        assert schema["mode"]["type"] == "str"
        assert "rsi" in schema["mode"]["choices"]
        assert "stochastic" in schema["mode"]["choices"]
        assert "adx" in schema["mode"]["choices"]

    def test_schema_defaults_are_valid(self, sample_ohlcv):
        """Compute with all defaults should work without errors."""
        ind = ASH()
        schema = ind.params_schema()
        defaults = {k: v["default"] for k, v in schema.items()}
        result = ind.compute(sample_ohlcv, **defaults)
        assert result.dtype == bool
