"""Tests for OBV Trend indicator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.indicators.standard.obv import OBVTrend


@pytest.fixture
def ohlcv_df() -> pd.DataFrame:
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


class TestOBVTrend:
    def test_returns_bool_series(self, ohlcv_df):
        ind = OBVTrend()
        result = ind.compute(ohlcv_df)
        assert result.dtype == bool

    def test_correct_length(self, ohlcv_df):
        ind = OBVTrend()
        result = ind.compute(ohlcv_df)
        assert len(result) == len(ohlcv_df)

    def test_warmup_is_false(self, ohlcv_df):
        ind = OBVTrend()
        result = ind.compute(ohlcv_df, ma_period=20)
        assert not result.iloc[:20].any()

    def test_bullish_vs_bearish(self, ohlcv_df):
        ind = OBVTrend()
        bull = ind.compute(ohlcv_df, mode="bullish")
        bear = ind.compute(ohlcv_df, mode="bearish")
        assert not bull.equals(bear)

    def test_params_schema(self):
        ind = OBVTrend()
        schema = ind.params_schema()
        assert "ma_period" in schema
        assert "mode" in schema
        assert schema["mode"]["choices"] == ["bullish", "bearish"]
