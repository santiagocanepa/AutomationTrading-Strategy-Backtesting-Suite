"""Tests for Squeeze Momentum indicator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.indicators.standard.squeeze import SqueezeMomentum


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
    """Generate synthetic OHLCV data with a squeeze-release pattern."""
    rng = np.random.default_rng(42)
    n = 300
    close = 100.0 + np.cumsum(rng.normal(0, 1, n))
    high = close + rng.uniform(0.5, 2.0, n)
    low = close - rng.uniform(0.5, 2.0, n)
    return pd.DataFrame({
        "open": close + rng.normal(0, 0.3, n),
        "high": high,
        "low": low,
        "close": close,
        "volume": rng.uniform(1000, 5000, n),
    })


class TestSqueezeMomentum:
    def test_returns_bool_series(self, ohlcv_df):
        ind = SqueezeMomentum()
        result = ind.compute(ohlcv_df)
        assert result.dtype == bool

    def test_correct_length(self, ohlcv_df):
        ind = SqueezeMomentum()
        result = ind.compute(ohlcv_df)
        assert len(result) == len(ohlcv_df)

    def test_warmup_is_false(self, ohlcv_df):
        ind = SqueezeMomentum()
        result = ind.compute(ohlcv_df, bb_period=20, kc_period=20)
        assert not result.iloc[:20].any()

    def test_bearish_mode(self, ohlcv_df):
        ind = SqueezeMomentum()
        bull = ind.compute(ohlcv_df, mode="bullish")
        bear = ind.compute(ohlcv_df, mode="bearish")
        # Should not be identical
        assert not bull.equals(bear)

    def test_params_schema(self):
        ind = SqueezeMomentum()
        schema = ind.params_schema()
        assert "bb_period" in schema
        assert "kc_period" in schema
        assert "mode" in schema
        assert schema["mode"]["choices"] == ["bullish", "bearish"]
