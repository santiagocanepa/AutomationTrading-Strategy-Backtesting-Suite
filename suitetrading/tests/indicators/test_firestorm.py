"""Tests for Firestorm indicator."""

import numpy as np
import pandas as pd
import pytest

from suitetrading.indicators.custom.firestorm import (
    Firestorm,
    FirestormTM,
    _ema,
    _firestorm_core,
    _true_range,
    firestorm,
)


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame with trend + reversal."""
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


class TestTrueRange:
    def test_first_bar_is_high_minus_low(self):
        h = np.array([110.0, 112.0])
        lo = np.array([100.0, 98.0])
        c = np.array([105.0, 109.0])
        tr = _true_range(h, lo, c)
        assert tr[0] == pytest.approx(10.0)

    def test_gap_up_increases_tr(self):
        h = np.array([100.0, 120.0])
        lo = np.array([90.0, 115.0])
        c = np.array([95.0, 118.0])
        tr = _true_range(h, lo, c)
        # TR[1] = max(120-115=5, |120-95|=25, |115-95|=20) = 25
        assert tr[1] == pytest.approx(25.0)

    def test_output_length_matches_input(self):
        n = 50
        tr = _true_range(np.ones(n) * 110, np.ones(n) * 100, np.ones(n) * 105)
        assert len(tr) == n


class TestFirestormCore:
    def test_output_shapes(self, sample_ohlcv):
        result = firestorm(
            sample_ohlcv["open"], sample_ohlcv["high"],
            sample_ohlcv["low"], sample_ohlcv["close"],
        )
        for key in ("up", "dn", "trend", "buy", "sell"):
            assert key in result
            assert len(result[key]) == len(sample_ohlcv)

    def test_returns_series(self, sample_ohlcv):
        result = firestorm(
            sample_ohlcv["open"], sample_ohlcv["high"],
            sample_ohlcv["low"], sample_ohlcv["close"],
        )
        assert isinstance(result["up"], pd.Series)
        assert isinstance(result["trend"], pd.Series)

    def test_up_band_below_close_in_uptrend(self, sample_ohlcv):
        """In a clear uptrend, up band should be below close most of the time."""
        result = firestorm(
            sample_ohlcv["open"], sample_ohlcv["high"],
            sample_ohlcv["low"], sample_ohlcv["close"],
        )
        uptrend_mask = result["trend"] == 1
        if uptrend_mask.sum() > 10:
            close_arr = sample_ohlcv["close"][uptrend_mask]
            up_arr = result["up"][uptrend_mask]
            pct_above = (close_arr > up_arr).mean()
            # Should be above up band most of the time
            assert pct_above > 0.7

    def test_trend_values_are_1_or_minus1(self, sample_ohlcv):
        result = firestorm(
            sample_ohlcv["open"], sample_ohlcv["high"],
            sample_ohlcv["low"], sample_ohlcv["close"],
        )
        unique = set(result["trend"].unique())
        assert unique <= {1, -1}

    def test_buy_sell_only_on_trend_change(self, sample_ohlcv):
        result = firestorm(
            sample_ohlcv["open"], sample_ohlcv["high"],
            sample_ohlcv["low"], sample_ohlcv["close"],
        )
        buy = result["buy"]
        sell = result["sell"]
        trend = result["trend"]
        # Buy should only occur where trend changes from -1 to 1
        for i in range(1, len(trend)):
            if buy.iloc[i]:
                assert trend.iloc[i] == 1 and trend.iloc[i - 1] == -1
            if sell.iloc[i]:
                assert trend.iloc[i] == -1 and trend.iloc[i - 1] == 1

    def test_buy_and_sell_never_both_true(self, sample_ohlcv):
        result = firestorm(
            sample_ohlcv["open"], sample_ohlcv["high"],
            sample_ohlcv["low"], sample_ohlcv["close"],
        )
        assert not (result["buy"] & result["sell"]).any()


class TestRatchetLogic:
    def test_up_band_only_increases_in_uptrend(self):
        """In a sustained uptrend, up band should be non-decreasing."""
        n = 100
        close = np.linspace(100, 200, n)  # pure uptrend
        high = close + 2
        low = close - 2
        open_ = close - 0.5
        ohlc4 = (open_ + high + low + close) / 4
        tr = _true_range(high, low, close)
        atr = _ema(tr, 10)

        up, dn, trend, _, _ = _firestorm_core(ohlc4, close, atr, 1.8)

        # After warmup (first 20 bars), in uptrend segments, up should be non-decreasing
        for i in range(21, n):
            if trend[i] == 1 and trend[i - 1] == 1:
                assert up[i] >= up[i - 1] - 1e-10  # allow floating point tolerance


class TestFirestormIndicator:
    def test_compute_returns_boolean(self, sample_ohlcv):
        ind = Firestorm()
        result = ind.compute(sample_ohlcv)
        assert result.dtype == bool

    def test_hold_bars_extends_signal(self, sample_ohlcv):
        ind = Firestorm()
        r1 = ind.compute(sample_ohlcv, hold_bars=1)
        r5 = ind.compute(sample_ohlcv, hold_bars=5)
        assert r5.sum() >= r1.sum()

    def test_sells_with_direction_short(self, sample_ohlcv):
        ind = Firestorm()
        buy = ind.compute(sample_ohlcv, direction="long")
        sell = ind.compute(sample_ohlcv, direction="short")
        # Not necessarily complementary, but both should produce some signals
        assert buy.sum() > 0 or sell.sum() > 0

    def test_params_schema(self):
        ind = Firestorm()
        schema = ind.params_schema()
        assert "period" in schema
        assert "multiplier" in schema
        assert "hold_bars" in schema


class TestFirestormTMIndicator:
    def test_compute_returns_numeric(self, sample_ohlcv):
        ind = FirestormTM()
        result = ind.compute(sample_ohlcv)
        assert result.dtype in (np.float64, float)
        assert len(result) == len(sample_ohlcv)

    def test_long_returns_up_band(self, sample_ohlcv):
        ind = FirestormTM()
        up_band = ind.compute(sample_ohlcv, direction="long", period=9, multiplier=0.9)
        result = firestorm(
            sample_ohlcv["open"], sample_ohlcv["high"],
            sample_ohlcv["low"], sample_ohlcv["close"],
            period=9, multiplier=0.9,
        )
        pd.testing.assert_series_equal(up_band, result["up"], check_names=False)
