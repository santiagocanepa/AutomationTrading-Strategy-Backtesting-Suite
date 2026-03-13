"""Performance benchmarks for the data layer.

Uses pytest-benchmark.  Run with:  pytest tests/data/test_benchmarks.py --benchmark-only
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.data.validator import DataValidator


def _generate_1m_1y() -> pd.DataFrame:
    """~525 600 bars of 1-minute data (365 days)."""
    n = 365 * 1440
    idx = pd.date_range("2024-01-01", periods=n, freq="1min", tz="UTC")
    rng = np.random.default_rng(999)
    price = 42_000.0 + np.cumsum(rng.normal(0, 5, n))
    open_ = price
    close = np.roll(price, -1)
    close[-1] = price[-1]
    high = np.maximum(open_, close) + rng.uniform(1, 50, n)
    low = np.minimum(open_, close) - rng.uniform(1, 50, n)
    volume = rng.uniform(0.1, 100, n)
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


@pytest.fixture(scope="module")
def df_1y() -> pd.DataFrame:
    return _generate_1m_1y()


@pytest.fixture(scope="module")
def populated_store(df_1y: pd.DataFrame, tmp_path_factory) -> tuple[ParquetStore, pd.DataFrame]:
    base = tmp_path_factory.mktemp("bench_store")
    store = ParquetStore(base_dir=base)
    store.write(df_1y, "binance", "BTCUSDT", "1m", source="bench")
    return store, df_1y


# ── Benchmarks ────────────────────────────────────────────────────────────────


@pytest.mark.benchmark
class TestBenchmarks:
    def test_bench_write_1y_1m(self, benchmark, df_1y: pd.DataFrame, tmp_path):
        store = ParquetStore(base_dir=tmp_path / "w")

        def _write():
            store.write(df_1y, "binance", "BTCUSDT", "1m", source="bench")

        result = benchmark.pedantic(_write, rounds=3, warmup_rounds=0)
        # Target: < 3.0s (checked manually)

    def test_bench_read_1y_1m(self, benchmark, populated_store):
        store, _ = populated_store

        def _read():
            return store.read("binance", "BTCUSDT", "1m")

        result = benchmark(_read)
        # Target: < 2.0s

    def test_bench_resample_1y_all_tfs(self, benchmark, df_1y: pd.DataFrame):
        resampler = OHLCVResampler()

        def _resample():
            return resampler.resample_all(df_1y, target_tfs=["5m", "15m", "1h", "4h", "1d"])

        result = benchmark(_resample)

    def test_bench_validate_1y_1m(self, benchmark, df_1y: pd.DataFrame):
        validator = DataValidator()

        def _validate():
            return validator.validate(df_1y, "1m")

        result = benchmark(_validate)

    def test_bench_parquet_size_1y_1m(self, populated_store):
        store, _ = populated_store
        data_dir = store._base_dir / "binance" / "BTCUSDT" / "1m"
        total_bytes = sum(f.stat().st_size for f in data_dir.glob("*.parquet"))
        total_mb = total_bytes / (1024 * 1024)
        # Target: < 30 MB for ~525k rows of synthetic (random) data.
        # Real market data compresses to ~10 MB due to autocorrelation.
        assert total_mb < 30, f"Parquet size too large: {total_mb:.1f} MB"
