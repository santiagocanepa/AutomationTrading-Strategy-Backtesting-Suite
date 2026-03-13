"""Tests for suitetrading.data.storage — Parquet read/write with partitioning."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pytest

from suitetrading.data.storage import ParquetStore


# ── Write / Read roundtrip ───────────────────────────────────────────────────


class TestWriteRead:
    def test_write_read_roundtrip(self, tmp_store: ParquetStore, sample_1m_1day: pd.DataFrame) -> None:
        tmp_store.write(sample_1m_1day, "binance", "BTCUSDT", "1m", source="test")
        result = tmp_store.read("binance", "BTCUSDT", "1m")
        pd.testing.assert_frame_equal(sample_1m_1day, result, check_freq=False)

    def test_write_creates_partitions(self, tmp_store: ParquetStore, sample_1m_3months: pd.DataFrame) -> None:
        paths = tmp_store.write(sample_1m_3months, "binance", "BTCUSDT", "1m")
        assert len(paths) == 3  # Jan, Feb, Mar

    def test_write_deduplicates(self, tmp_store: ParquetStore, sample_1m_1day: pd.DataFrame) -> None:
        df = pd.concat([sample_1m_1day, sample_1m_1day.iloc[:100]])
        tmp_store.write(df, "binance", "BTCUSDT", "1m")
        result = tmp_store.read("binance", "BTCUSDT", "1m")
        assert not result.index.duplicated().any()
        assert len(result) == len(sample_1m_1day)

    def test_write_sorts_timestamps(self, tmp_store: ParquetStore, sample_1m_1day: pd.DataFrame) -> None:
        df = sample_1m_1day.iloc[::-1]  # Reversed
        tmp_store.write(df, "binance", "BTCUSDT", "1m")
        result = tmp_store.read("binance", "BTCUSDT", "1m")
        assert result.index.is_monotonic_increasing


# ── Read filters ─────────────────────────────────────────────────────────────


class TestReadFilters:
    def test_read_date_range(self, tmp_store: ParquetStore, sample_1m_1day: pd.DataFrame) -> None:
        tmp_store.write(sample_1m_1day, "binance", "BTCUSDT", "1m")
        start = datetime(2024, 1, 15, 6, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 15, 12, 0, tzinfo=timezone.utc)
        result = tmp_store.read("binance", "BTCUSDT", "1m", start=start, end=end)
        assert result.index.min() >= pd.Timestamp(start)
        assert result.index.max() <= pd.Timestamp(end)

    def test_read_column_projection(self, tmp_store: ParquetStore, sample_1m_1day: pd.DataFrame) -> None:
        tmp_store.write(sample_1m_1day, "binance", "BTCUSDT", "1m")
        result = tmp_store.read("binance", "BTCUSDT", "1m", columns=["timestamp", "close"])
        assert "close" in result.columns
        assert "open" not in result.columns

    def test_read_nonexistent_raises(self, tmp_store: ParquetStore) -> None:
        with pytest.raises(FileNotFoundError):
            tmp_store.read("binance", "NONEXIST", "1m")


# ── Metadata & listing ───────────────────────────────────────────────────────


class TestMetadata:
    def test_list_available(self, tmp_store: ParquetStore, sample_1m_1day: pd.DataFrame) -> None:
        tmp_store.write(sample_1m_1day, "binance", "BTCUSDT", "1m")
        tmp_store.write(sample_1m_1day, "binance", "ETHUSDT", "1m")
        available = tmp_store.list_available()
        symbols = {d["symbol"] for d in available}
        assert "BTCUSDT" in symbols
        assert "ETHUSDT" in symbols

    def test_info_metadata(self, tmp_store: ParquetStore, sample_1m_1day: pd.DataFrame) -> None:
        tmp_store.write(sample_1m_1day, "binance", "BTCUSDT", "1m", source="test_source")
        info = tmp_store.info("binance", "BTCUSDT", "1m")
        assert info["rows"] == len(sample_1m_1day)
        assert info["date_min"] is not None
        assert info["date_max"] is not None
        assert info["source"] == "test_source"
        assert info["size_mb"] > 0


# ── Partitioning schemes ────────────────────────────────────────────────────


class TestPartitioning:
    def test_yearly_partitions(self, tmp_store: ParquetStore) -> None:
        idx = pd.date_range("2023-01-01", periods=365, freq="1D", tz="UTC")
        rng = np.random.default_rng(42)
        n = len(idx)
        df = pd.DataFrame(
            {
                "open": rng.uniform(40000, 50000, n),
                "high": rng.uniform(50000, 55000, n),
                "low": rng.uniform(35000, 40000, n),
                "close": rng.uniform(40000, 50000, n),
                "volume": rng.uniform(0, 1000, n),
            },
            index=idx,
        )
        paths = tmp_store.write(df, "binance", "BTCUSDT", "1d")
        assert len(paths) == 1  # All 2023
        assert "2023.parquet" in paths[0].name

    def test_overwrite_partition(self, tmp_store: ParquetStore, sample_1m_1day: pd.DataFrame) -> None:
        tmp_store.write(sample_1m_1day, "binance", "BTCUSDT", "1m")
        # Write again with slightly modified data
        df2 = sample_1m_1day.copy()
        df2["close"] = df2["close"] + 1.0
        tmp_store.write(df2, "binance", "BTCUSDT", "1m")
        result = tmp_store.read("binance", "BTCUSDT", "1m")
        # Should have the updated values
        pd.testing.assert_series_equal(result["close"], df2["close"], check_names=False, check_freq=False)


# ── Compression ──────────────────────────────────────────────────────────────


class TestCompression:
    def test_compression_zstd(self, tmp_store: ParquetStore, sample_1m_1day: pd.DataFrame) -> None:
        paths = tmp_store.write(sample_1m_1day, "binance", "BTCUSDT", "1m")
        meta = pq.read_metadata(paths[0])
        # Check that at least one row group column is ZSTD compressed
        rg = meta.row_group(0)
        compressions = {rg.column(i).compression for i in range(rg.num_columns)}
        assert "ZSTD" in compressions


# ── Validation on write ──────────────────────────────────────────────────────


class TestWriteValidation:
    def test_write_no_tz_raises(self, tmp_store: ParquetStore) -> None:
        idx = pd.date_range("2024-01-01", periods=10, freq="1min")  # No tz
        df = pd.DataFrame(
            {"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 10.0},
            index=idx,
        )
        with pytest.raises(ValueError, match="timezone"):
            tmp_store.write(df, "binance", "BTCUSDT", "1m")

    def test_write_missing_column_raises(self, tmp_store: ParquetStore) -> None:
        idx = pd.date_range("2024-01-01", periods=10, freq="1min", tz="UTC")
        df = pd.DataFrame({"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5}, index=idx)
        with pytest.raises(ValueError, match="volume"):
            tmp_store.write(df, "binance", "BTCUSDT", "1m")
