"""Tests for WaveTrend indicator."""

import numpy as np
import pandas as pd
import pytest

from suitetrading.indicators.custom.wavetrend import (
    WaveTrendDivergence,
    WaveTrendReversal,
    _ema,
    _pivot_high,
    _pivot_low,
    _sma,
    wavetrend,
    wavetrend_reversal,
)


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Synthetic data with oscillating price for divergence/reversal detection."""
    np.random.seed(42)
    n = 500
    # Create oscillating price with varying amplitude
    t = np.arange(n)
    base = 100 + 10 * np.sin(2 * np.pi * t / 80)
    trend = np.linspace(0, 20, n)
    noise = np.random.randn(n) * 2
    close = base + trend + noise
    high = close + np.abs(np.random.randn(n)) * 3
    low = close - np.abs(np.random.randn(n)) * 3
    open_ = close + np.random.randn(n) * 0.5
    volume = np.random.randint(1000, 10000, n).astype(float)

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


class TestEMA:
    def test_matches_pandas_ewm(self):
        np.random.seed(7)
        data = np.random.randn(100) * 10 + 50
        period = 9
        result = _ema(data, period)
        expected = pd.Series(data).ewm(span=period, adjust=False).mean().values
        np.testing.assert_allclose(result, expected, rtol=1e-10)


class TestSMA:
    def test_matches_pandas_rolling_mean(self):
        np.random.seed(7)
        data = np.random.randn(50) * 10 + 50
        period = 3
        result = _sma(data, period)
        expected = pd.Series(data).rolling(period).mean().values
        # First period-1 values are NaN
        for i in range(period - 1):
            assert np.isnan(result[i])
        np.testing.assert_allclose(result[period - 1:], expected[period - 1:], rtol=1e-10)


class TestPivots:
    def test_pivot_high_detects_peak(self):
        data = np.array([1, 2, 3, 4, 5, 4, 3, 2, 1, 2, 3], dtype=np.float64)
        result = _pivot_high(data, 3, 3)
        # Peak at index 4 (value=5) with left=3, right=3
        assert result[4] == pytest.approx(5.0)

    def test_pivot_low_detects_trough(self):
        data = np.array([5, 4, 3, 2, 1, 2, 3, 4, 5, 4, 3], dtype=np.float64)
        result = _pivot_low(data, 3, 3)
        # Trough at index 4 (value=1)
        assert result[4] == pytest.approx(1.0)

    def test_no_pivot_in_monotonic(self):
        data = np.arange(20, dtype=np.float64)
        highs = _pivot_high(data, 3, 3)
        lows = _pivot_low(data, 3, 3)
        # Monotonically increasing → no pivots
        assert np.all(np.isnan(highs))
        assert np.all(np.isnan(lows))


class TestWaveTrendOscillator:
    def test_output_shapes(self, sample_ohlcv):
        wt1, wt2 = wavetrend(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        assert len(wt1) == len(sample_ohlcv)
        assert len(wt2) == len(sample_ohlcv)

    def test_wt2_is_smoothed_wt1(self, sample_ohlcv):
        """wt2 = SMA(wt1, 3), so it should be smoother."""
        wt1, wt2 = wavetrend(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        # After warmup, wt2 std should be <= wt1 std (smoothing reduces variance)
        assert wt2.iloc[50:].std() <= wt1.iloc[50:].std() * 1.1  # small tolerance

    def test_oscillator_crosses_zero(self, sample_ohlcv):
        """With oscillating data, WT should cross zero."""
        wt1, _ = wavetrend(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        has_positive = (wt1 > 0).any()
        has_negative = (wt1 < 0).any()
        assert has_positive and has_negative


class TestWaveTrendReversal:
    def test_reversal_signals_are_boolean(self, sample_ohlcv):
        wt1, wt2 = wavetrend(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        buy, sell = wavetrend_reversal(wt1, wt2)
        assert buy.dtype == bool
        assert sell.dtype == bool

    def test_buy_only_in_oversold(self, sample_ohlcv):
        wt1, wt2 = wavetrend(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        buy, _ = wavetrend_reversal(wt1, wt2, os_level=-60)
        # Buy signals should only fire when wt2 <= -60
        if buy.any():
            assert (wt2[buy] <= -60).all()

    def test_sell_only_in_overbought(self, sample_ohlcv):
        wt1, wt2 = wavetrend(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        _, sell = wavetrend_reversal(wt1, wt2, ob_level=60)
        if sell.any():
            assert (wt2[sell] >= 60).all()

    def test_buy_and_sell_never_simultaneous(self, sample_ohlcv):
        wt1, wt2 = wavetrend(sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"])
        buy, sell = wavetrend_reversal(wt1, wt2)
        assert not (buy & sell).any()


class TestWaveTrendReversalIndicator:
    def test_compute_returns_boolean(self, sample_ohlcv):
        ind = WaveTrendReversal()
        result = ind.compute(sample_ohlcv)
        assert result.dtype == bool
        assert len(result) == len(sample_ohlcv)

    def test_hold_bars_extends_signal(self, sample_ohlcv):
        ind = WaveTrendReversal()
        r1 = ind.compute(sample_ohlcv, hold_bars=1)
        r5 = ind.compute(sample_ohlcv, hold_bars=5)
        assert r5.sum() >= r1.sum()

    def test_params_schema(self):
        ind = WaveTrendReversal()
        schema = ind.params_schema()
        assert "channel_len" in schema
        assert "ob_level" in schema
        assert "os_level" in schema
        assert "hold_bars" in schema


class TestWaveTrendDivergenceIndicator:
    def test_compute_returns_boolean(self, sample_ohlcv):
        ind = WaveTrendDivergence()
        result = ind.compute(sample_ohlcv)
        assert result.dtype == bool
        assert len(result) == len(sample_ohlcv)

    def test_params_schema(self):
        ind = WaveTrendDivergence()
        schema = ind.params_schema()
        assert "lookback_left" in schema
        assert "divergence_length" in schema
