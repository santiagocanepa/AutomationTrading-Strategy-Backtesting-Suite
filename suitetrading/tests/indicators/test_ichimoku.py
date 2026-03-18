"""Tests for Ichimoku TK Cross indicator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.indicators.standard.ichimoku import IchimokuTKCross


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


class TestIchimokuTKCross:
    def test_returns_bool_series(self, ohlcv_df):
        ind = IchimokuTKCross()
        result = ind.compute(ohlcv_df)
        assert result.dtype == bool

    def test_correct_length(self, ohlcv_df):
        ind = IchimokuTKCross()
        result = ind.compute(ohlcv_df)
        assert len(result) == len(ohlcv_df)

    def test_warmup_is_false(self, ohlcv_df):
        ind = IchimokuTKCross()
        result = ind.compute(ohlcv_df, senkou_period=52)
        assert not result.iloc[:52].any()

    def test_bullish_vs_bearish(self, ohlcv_df):
        ind = IchimokuTKCross()
        bull = ind.compute(ohlcv_df, mode="bullish")
        bear = ind.compute(ohlcv_df, mode="bearish")
        assert not bull.equals(bear)

    def test_params_schema(self):
        ind = IchimokuTKCross()
        schema = ind.params_schema()
        assert "tenkan_period" in schema
        assert "kijun_period" in schema
        assert "senkou_period" in schema
        assert "mode" in schema
