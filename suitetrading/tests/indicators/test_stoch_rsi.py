"""Tests for Stochastic RSI indicator."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.indicators.standard.stoch_rsi import StochRSI as StochasticRSI


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


class TestStochasticRSI:
    def test_returns_bool_series(self, ohlcv_df):
        ind = StochasticRSI()
        result = ind.compute(ohlcv_df)
        assert result.dtype == bool

    def test_correct_length(self, ohlcv_df):
        ind = StochasticRSI()
        result = ind.compute(ohlcv_df)
        assert len(result) == len(ohlcv_df)

    def test_warmup_is_false(self, ohlcv_df):
        ind = StochasticRSI()
        result = ind.compute(ohlcv_df, rsi_period=14, stoch_period=14)
        assert not result.iloc[:30].any()

    def test_oversold_vs_overbought(self, ohlcv_df):
        ind = StochasticRSI()
        oversold = ind.compute(ohlcv_df, mode="oversold")
        overbought = ind.compute(ohlcv_df, mode="overbought")
        assert not oversold.equals(overbought)

    def test_params_schema(self):
        ind = StochasticRSI()
        schema = ind.params_schema()
        assert "rsi_period" in schema
        assert "stoch_period" in schema
        assert "mode" in schema
        assert schema["mode"]["choices"] == ["oversold", "overbought"]
