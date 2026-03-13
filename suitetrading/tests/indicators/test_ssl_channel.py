"""Tests for SSL Channel indicator."""

import numpy as np
import pandas as pd
import pytest

from suitetrading.indicators.custom.ssl_channel import (
    SSLChannel,
    SSLChannelLow,
    _ema,
    _ssl_channel_core,
    ssl_channel,
    ssl_cross_signals,
    ssl_level_signals,
)


# ── Fixtures ─────────────────────────────────────────────────────


@pytest.fixture
def sample_ohlcv() -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame with a clear trend reversal."""
    np.random.seed(42)
    n = 200
    # Uptrend → downtrend around bar 100
    trend = np.concatenate([
        np.linspace(100, 150, 100),
        np.linspace(150, 110, 100),
    ])
    noise = np.random.randn(n) * 1.5
    close = trend + noise
    high = close + np.abs(np.random.randn(n)) * 2
    low = close - np.abs(np.random.randn(n)) * 2
    open_ = close + np.random.randn(n) * 0.5
    volume = np.random.randint(1000, 10000, n).astype(float)

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })


# ── EMA tests ────────────────────────────────────────────────────


class TestEMA:
    def test_ema_first_value_equals_input(self):
        data = np.array([10.0, 11.0, 12.0, 11.5, 13.0])
        result = _ema(data, 3)
        assert result[0] == pytest.approx(10.0)

    def test_ema_converges_to_constant(self):
        data = np.full(100, 50.0)
        result = _ema(data, 10)
        assert result[-1] == pytest.approx(50.0, abs=1e-10)

    def test_ema_matches_pandas(self):
        np.random.seed(123)
        data = np.random.randn(100) * 10 + 100
        period = 12
        numba_ema = _ema(data, period)
        pandas_ema = pd.Series(data).ewm(span=period, adjust=False).mean().values
        np.testing.assert_allclose(numba_ema, pandas_ema, rtol=1e-10)


# ── SSL Channel core tests ───────────────────────────────────────


class TestSSLChannelCore:
    def test_output_shapes(self, sample_ohlcv):
        ssl_up, ssl_down = ssl_channel(
            sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"], length=12,
        )
        assert len(ssl_up) == len(sample_ohlcv)
        assert len(ssl_down) == len(sample_ohlcv)

    def test_output_are_series(self, sample_ohlcv):
        ssl_up, ssl_down = ssl_channel(
            sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"],
        )
        assert isinstance(ssl_up, pd.Series)
        assert isinstance(ssl_down, pd.Series)

    def test_ssl_up_and_down_are_not_identical(self, sample_ohlcv):
        ssl_up, ssl_down = ssl_channel(
            sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"],
        )
        # After warmup, they should differ
        assert not np.allclose(ssl_up.values[20:], ssl_down.values[20:])

    def test_hlv_initialization_at_zero(self):
        """Hlv starts at 0, meaning ssl_up = ema_high, ssl_down = ema_low initially."""
        high = np.array([105.0, 106.0, 107.0, 108.0, 109.0])
        low = np.array([95.0, 96.0, 97.0, 98.0, 99.0])
        close = np.array([100.0, 100.5, 100.0, 99.5, 100.0])

        ema_h = _ema(high, 3)
        ema_l = _ema(low, 3)
        ssl_up, ssl_down, hlv = _ssl_channel_core(high, low, close, ema_h, ema_l)

        # Hlv[0] should be 0 (init) → close[0]=100 not > ema_h[0]=105 and not < ema_l[0]=95
        assert hlv[0] == 0.0


# ── Cross signal tests ───────────────────────────────────────────


class TestSSLCrossSignals:
    def test_cross_signals_are_boolean(self, sample_ohlcv):
        ssl_up, ssl_down = ssl_channel(
            sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"],
        )
        buy, sell = ssl_cross_signals(ssl_up, ssl_down)
        assert buy.dtype == bool
        assert sell.dtype == bool

    def test_buy_and_sell_never_both_true(self, sample_ohlcv):
        ssl_up, ssl_down = ssl_channel(
            sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"],
        )
        buy, sell = ssl_cross_signals(ssl_up, ssl_down)
        assert not (buy & sell).any()

    def test_cross_produces_signals_on_trend_reversal(self, sample_ohlcv):
        ssl_up, ssl_down = ssl_channel(
            sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"],
        )
        buy, sell = ssl_cross_signals(ssl_up, ssl_down)
        # With a clear trend reversal, we expect at least 1 buy and 1 sell
        assert buy.sum() >= 1
        assert sell.sum() >= 1


# ── Level signal tests ───────────────────────────────────────────


class TestSSLLevelSignals:
    def test_buy_and_sell_are_complementary(self, sample_ohlcv):
        ssl_up, ssl_down = ssl_channel(
            sample_ohlcv["high"], sample_ohlcv["low"], sample_ohlcv["close"],
        )
        buy, sell = ssl_level_signals(ssl_up, ssl_down)
        # buy OR sell should be True everywhere (or both False if equal)
        assert ((buy | sell) | (ssl_up == ssl_down)).all()


# ── Indicator wrapper tests ──────────────────────────────────────


class TestSSLChannelIndicator:
    def test_compute_returns_boolean_series(self, sample_ohlcv):
        ind = SSLChannel()
        result = ind.compute(sample_ohlcv, length=12, hold_bars=4)
        assert result.dtype == bool
        assert len(result) == len(sample_ohlcv)

    def test_hold_bars_extends_signals(self, sample_ohlcv):
        ind = SSLChannel()
        result_1 = ind.compute(sample_ohlcv, length=12, hold_bars=1)
        result_4 = ind.compute(sample_ohlcv, length=12, hold_bars=4)
        # More hold bars → more True values
        assert result_4.sum() >= result_1.sum()

    def test_params_schema_has_expected_keys(self):
        ind = SSLChannel()
        schema = ind.params_schema()
        assert "length" in schema
        assert "hold_bars" in schema

    def test_missing_columns_raises(self):
        ind = SSLChannel()
        bad_df = pd.DataFrame({"close": [1, 2, 3]})
        with pytest.raises(ValueError, match="missing OHLCV"):
            ind.compute(bad_df)


class TestSSLChannelLowIndicator:
    def test_compute_returns_boolean_series(self, sample_ohlcv):
        ind = SSLChannelLow()
        result = ind.compute(sample_ohlcv, length=12)
        assert result.dtype == bool
        assert len(result) == len(sample_ohlcv)
