"""Shared fixtures for data module tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest


@pytest.fixture
def sample_1m_1day() -> pd.DataFrame:
    """1 day of synthetic 1m OHLCV data (1440 bars) with guaranteed valid OHLCV."""
    idx = pd.date_range("2024-01-15", periods=1440, freq="1min", tz="UTC")
    rng = np.random.default_rng(42)
    price = 42_000.0 + rng.standard_normal(1440).cumsum() * 10
    open_ = price + rng.uniform(-5, 5, 1440)
    close = price
    high = np.maximum(open_, close) + np.abs(rng.standard_normal(1440)) * 20
    low = np.minimum(open_, close) - np.abs(rng.standard_normal(1440)) * 20
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.abs(rng.standard_normal(1440)) * 100,
        },
        index=idx,
    )


@pytest.fixture
def sample_1m_1month() -> pd.DataFrame:
    """1 month of synthetic 1m OHLCV data (~44 640 bars) with valid OHLCV."""
    idx = pd.date_range("2024-01-01", "2024-01-31 23:59", freq="1min", tz="UTC")
    rng = np.random.default_rng(42)
    n = len(idx)
    price = 42_000.0 + rng.standard_normal(n).cumsum() * 5
    open_ = price + rng.uniform(-3, 3, n)
    close = price
    high = np.maximum(open_, close) + np.abs(rng.standard_normal(n)) * 15
    low = np.minimum(open_, close) - np.abs(rng.standard_normal(n)) * 15
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.abs(rng.standard_normal(n)) * 50,
        },
        index=idx,
    )


@pytest.fixture
def sample_1m_3months() -> pd.DataFrame:
    """3 months of synthetic 1m OHLCV data (for multi-partition tests), valid OHLCV."""
    idx = pd.date_range("2024-01-01", "2024-03-31 23:59", freq="1min", tz="UTC")
    rng = np.random.default_rng(42)
    n = len(idx)
    price = 42_000.0 + rng.standard_normal(n).cumsum() * 5
    open_ = price + rng.uniform(-3, 3, n)
    close = price
    high = np.maximum(open_, close) + np.abs(rng.standard_normal(n)) * 15
    low = np.minimum(open_, close) - np.abs(rng.standard_normal(n)) * 15
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": np.abs(rng.standard_normal(n)) * 50,
        },
        index=idx,
    )


@pytest.fixture
def tmp_store(tmp_path: Path):
    """ParquetStore backed by a temporary directory."""
    from suitetrading.data.storage import ParquetStore

    return ParquetStore(base_dir=tmp_path / "processed")
