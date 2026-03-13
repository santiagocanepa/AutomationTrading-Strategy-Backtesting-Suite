"""Smoke tests for the 6 standard TA-Lib indicator wrappers.

Each test verifies that compute() produces a boolean Series with
correct shape and no NaN values outside the expected warm-up period.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from suitetrading.indicators.standard.indicators import (
    ATR,
    EMA,
    MACD,
    RSI,
    VWAP,
    BollingerBands,
)


@pytest.fixture()
def ohlcv_500() -> pd.DataFrame:
    """Synthetic 500-bar OHLCV data with realistic price structure."""
    rng = np.random.default_rng(42)
    n = 500
    base = 50000.0
    returns = rng.normal(0.0002, 0.01, n)
    close = base * np.cumprod(1 + returns)
    high = close * (1 + rng.uniform(0.001, 0.015, n))
    low = close * (1 - rng.uniform(0.001, 0.015, n))
    opn = close * (1 + rng.uniform(-0.005, 0.005, n))
    volume = rng.uniform(100, 10000, n)
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    return pd.DataFrame(
        {"open": opn, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


class TestRSI:
    def test_smoke_oversold(self, ohlcv_500: pd.DataFrame) -> None:
        sig = RSI().compute(ohlcv_500, period=14, threshold=30.0, mode="oversold")
        assert isinstance(sig, pd.Series)
        assert sig.dtype == bool
        assert len(sig) == len(ohlcv_500)
        assert not sig.isna().any()

    def test_smoke_overbought(self, ohlcv_500: pd.DataFrame) -> None:
        sig = RSI().compute(ohlcv_500, period=14, threshold=70.0, mode="overbought")
        assert sig.dtype == bool
        assert len(sig) == len(ohlcv_500)


class TestEMA:
    def test_smoke_crossover_above(self, ohlcv_500: pd.DataFrame) -> None:
        sig = EMA().compute(ohlcv_500, period=21, mode="above")
        assert isinstance(sig, pd.Series)
        assert sig.dtype == bool
        assert len(sig) == len(ohlcv_500)
        assert not sig.iat[0]  # first bar never signals

    def test_smoke_crossover_below(self, ohlcv_500: pd.DataFrame) -> None:
        sig = EMA().compute(ohlcv_500, period=21, mode="below")
        assert sig.dtype == bool


class TestMACD:
    def test_smoke_bullish(self, ohlcv_500: pd.DataFrame) -> None:
        sig = MACD().compute(ohlcv_500, fast=12, slow=26, signal=9, mode="bullish")
        assert isinstance(sig, pd.Series)
        assert sig.dtype == bool
        assert len(sig) == len(ohlcv_500)

    def test_smoke_bearish(self, ohlcv_500: pd.DataFrame) -> None:
        sig = MACD().compute(ohlcv_500, fast=12, slow=26, signal=9, mode="bearish")
        assert sig.dtype == bool


class TestATR:
    def test_smoke_breakout(self, ohlcv_500: pd.DataFrame) -> None:
        sig = ATR().compute(ohlcv_500, period=14, ma_period=50, multiplier=1.5)
        assert isinstance(sig, pd.Series)
        assert sig.dtype == bool
        assert len(sig) == len(ohlcv_500)


class TestVWAP:
    def test_smoke_above(self, ohlcv_500: pd.DataFrame) -> None:
        sig = VWAP().compute(ohlcv_500, mode="above")
        assert isinstance(sig, pd.Series)
        assert sig.dtype == bool
        assert len(sig) == len(ohlcv_500)

    def test_smoke_below(self, ohlcv_500: pd.DataFrame) -> None:
        sig = VWAP().compute(ohlcv_500, mode="below")
        assert sig.dtype == bool


class TestBollingerBands:
    def test_smoke_lower(self, ohlcv_500: pd.DataFrame) -> None:
        sig = BollingerBands().compute(ohlcv_500, period=20, nbdev=2.0, mode="lower")
        assert isinstance(sig, pd.Series)
        assert sig.dtype == bool
        assert len(sig) == len(ohlcv_500)

    def test_smoke_upper(self, ohlcv_500: pd.DataFrame) -> None:
        sig = BollingerBands().compute(ohlcv_500, period=20, nbdev=2.0, mode="upper")
        assert sig.dtype == bool


class TestParamsSchema:
    """Verify all 6 indicators expose a valid params_schema."""

    @pytest.mark.parametrize("cls", [RSI, EMA, MACD, ATR, VWAP, BollingerBands])
    def test_schema_keys(self, cls: type) -> None:
        schema = cls().params_schema()
        assert isinstance(schema, dict)
        assert len(schema) > 0
        for name, spec in schema.items():
            assert "type" in spec, f"{cls.__name__}.{name} missing 'type'"
