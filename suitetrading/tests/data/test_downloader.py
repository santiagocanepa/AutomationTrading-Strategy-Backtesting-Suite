"""Tests for the download pipeline (BinanceVision + CCXT + Orchestrator).

All network I/O is mocked — no real HTTP or exchange calls.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pandas as pd
import pytest

from suitetrading.data.downloader import (
    BinanceVisionDownloader,
    CCXTDownloader,
    DownloadOrchestrator,
    _month_range,
    _normalize_ccxt_ohlcv,
    _to_ccxt_symbol,
    _year_range,
)
from suitetrading.data.storage import ParquetStore


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _make_binance_csv_zip(
    rows: int = 100,
    start: str = "2024-01-01",
    csv_name: str = "BTCUSDT-1m-2024-01.csv",
    timestamp_scale: str = "ms",
) -> bytes:
    """Create an in-memory ZIP containing a Binance-format CSV."""
    ts_start = int(pd.Timestamp(start, tz="UTC").timestamp() * 1000)
    lines = []
    for i in range(rows):
        ot = ts_start + i * 60_000
        ct = ot + 59_999
        if timestamp_scale == "us":
            ot *= 1000
            ct *= 1000
        o, h, l, c, v = 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 10.0 + i
        lines.append(f"{ot},{o},{h},{l},{c},{v},{ct},0,0,0,0,0")

    csv_bytes = "\n".join(lines).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(csv_name, csv_bytes)
    return buf.getvalue()


def _make_ccxt_ohlcv(rows: int = 100, start_ts: int | None = None) -> list[list]:
    ts = start_ts or int(pd.Timestamp("2024-06-01", tz="UTC").timestamp() * 1000)
    data = []
    for i in range(rows):
        data.append([ts + i * 60_000, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 10.0 + i])
    return data


# ═══════════════════════════════════════════════════════════════════════════════
# _month_range
# ═══════════════════════════════════════════════════════════════════════════════


class TestMonthRange:
    def test_single_month(self):
        assert _month_range(date(2024, 3, 15), date(2024, 3, 20)) == [(2024, 3)]

    def test_cross_year(self):
        r = _month_range(date(2023, 11, 1), date(2024, 2, 1))
        assert r == [(2023, 11), (2023, 12), (2024, 1), (2024, 2)]

    def test_same_day(self):
        assert _month_range(date(2024, 1, 1), date(2024, 1, 1)) == [(2024, 1)]


# ═══════════════════════════════════════════════════════════════════════════════
# _normalize_ccxt_ohlcv
# ═══════════════════════════════════════════════════════════════════════════════


class TestNormalizeCCXT:
    def test_columns_and_index(self):
        raw = _make_ccxt_ohlcv(10)
        df = _normalize_ccxt_ohlcv(raw)
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df.index.name == "timestamp"
        assert df.index.tz is not None

    def test_dedup_keeps_last(self):
        raw = _make_ccxt_ohlcv(5)
        raw.append(raw[0].copy())
        raw[-1][1] = 999.0  # different open price for duplicate ts
        df = _normalize_ccxt_ohlcv(raw)
        assert len(df) == 5
        assert df.iloc[0]["open"] == 999.0


# ═══════════════════════════════════════════════════════════════════════════════
# BinanceVisionDownloader
# ═══════════════════════════════════════════════════════════════════════════════


class TestBinanceVision:
    def test_build_url(self, tmp_path: Path):
        bv = BinanceVisionDownloader(cache_dir=tmp_path)
        url = bv._build_url("BTCUSDT", "1m", 2024, 1)
        assert "data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip" in url

    def test_parse_csv_columns(self, tmp_path: Path):
        bv = BinanceVisionDownloader(cache_dir=tmp_path)
        zip_bytes = _make_binance_csv_zip(50)
        zip_path = tmp_path / "test.zip"
        zip_path.write_bytes(zip_bytes)
        df = bv._parse_zip(zip_path)
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert len(df) == 50
        assert df.index.tz is not None

    def test_parse_csv_microsecond_timestamps(self, tmp_path: Path):
        bv = BinanceVisionDownloader(cache_dir=tmp_path)
        zip_bytes = _make_binance_csv_zip(
            10,
            start="2025-01-01",
            csv_name="BTCUSDT-1m-2025-01.csv",
            timestamp_scale="us",
        )
        zip_path = tmp_path / "test_us.zip"
        zip_path.write_bytes(zip_bytes)

        df = bv._parse_zip(zip_path)
        assert df.index[0] == pd.Timestamp("2025-01-01 00:00:00+00:00")
        assert df.index[1] == pd.Timestamp("2025-01-01 00:01:00+00:00")

    @pytest.mark.asyncio
    async def test_download_month_cache_hit(self, tmp_path: Path):
        bv = BinanceVisionDownloader(cache_dir=tmp_path)
        zip_path = tmp_path / "BTCUSDT-1m-2024-01.zip"
        zip_path.write_bytes(_make_binance_csv_zip(10))

        df = await bv.download_month("BTCUSDT", "1m", 2024, 1)
        assert df is not None
        assert len(df) == 10

    @pytest.mark.asyncio
    async def test_download_month_404_returns_none(self, tmp_path: Path):
        bv = BinanceVisionDownloader(cache_dir=tmp_path, base_url="https://fake.test")

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=MagicMock(), response=mock_resp,
        )

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("suitetrading.data.downloader.httpx.AsyncClient", return_value=mock_client):
            result = await bv.download_month("BTCUSDT", "1m", 2099, 1)

        assert result is None

    @pytest.mark.asyncio
    async def test_download_range_concat(self, tmp_path: Path):
        bv = BinanceVisionDownloader(cache_dir=tmp_path)
        # Pre-populate cache for 2 months with distinct timestamps
        (tmp_path / "BTCUSDT-1m-2024-01.zip").write_bytes(
            _make_binance_csv_zip(10, start="2024-01-01", csv_name="BTCUSDT-1m-2024-01.csv"),
        )
        (tmp_path / "BTCUSDT-1m-2024-02.zip").write_bytes(
            _make_binance_csv_zip(10, start="2024-02-01", csv_name="BTCUSDT-1m-2024-02.csv"),
        )

        df = await bv.download_range("BTCUSDT", "1m", date(2024, 1, 1), date(2024, 2, 28), progress=False)
        assert len(df) == 20
        assert df.index.is_monotonic_increasing


# ═══════════════════════════════════════════════════════════════════════════════
# CCXTDownloader
# ═══════════════════════════════════════════════════════════════════════════════


class TestCCXTDownloader:
    @pytest.mark.asyncio
    async def test_fetch_latest(self):
        ccxt_dl = CCXTDownloader(exchange_id="binance")
        mock_exchange = AsyncMock()
        mock_exchange.fetch_ohlcv.return_value = _make_ccxt_ohlcv(50)
        mock_exchange.close = AsyncMock()

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            df = await ccxt_dl.fetch_latest("BTC/USDT", "1m", bars=50)

        assert len(df) == 50
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]

    @pytest.mark.asyncio
    async def test_paginated_stops_on_empty(self):
        ccxt_dl = CCXTDownloader(exchange_id="binance")
        mock_exchange = AsyncMock()
        # First call returns data, second returns empty → pagination stops
        mock_exchange.fetch_ohlcv.side_effect = [_make_ccxt_ohlcv(10), []]
        mock_exchange.close = AsyncMock()

        start = datetime(2024, 6, 1, tzinfo=timezone.utc)
        end = datetime(2024, 6, 30, tzinfo=timezone.utc)

        with patch("ccxt.async_support.binance", return_value=mock_exchange):
            df = await ccxt_dl.download_range("BTC/USDT", "1m", start, end)

        assert len(df) == 10


# ═══════════════════════════════════════════════════════════════════════════════
# DownloadOrchestrator
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestrator:
    def test_identify_missing_months_empty_store(self, tmp_path: Path):
        store = ParquetStore(base_dir=tmp_path / "parquet")
        orch = DownloadOrchestrator(store=store, cache_dir=tmp_path / "cache")
        missing = orch._identify_missing_months("binance", "BTCUSDT", "1m", date(2024, 1, 1), date(2024, 3, 31))
        assert missing == [(2024, 1), (2024, 2), (2024, 3)]

    def test_identify_missing_months_partial(self, tmp_path: Path):
        store = ParquetStore(base_dir=tmp_path / "parquet")
        orch = DownloadOrchestrator(store=store, cache_dir=tmp_path / "cache")

        # Simulate existing parquet files for Jan
        month_dir = tmp_path / "parquet" / "binance" / "BTCUSDT" / "1m"
        month_dir.mkdir(parents=True)
        (month_dir / "2024-01.parquet").touch()

        missing = orch._identify_missing_months("binance", "BTCUSDT", "1m", date(2024, 1, 1), date(2024, 3, 31))
        assert missing == [(2024, 2), (2024, 3)]

    @pytest.mark.asyncio
    async def test_sync_all_cached_returns_zero(self, tmp_path: Path):
        store = ParquetStore(base_dir=tmp_path / "parquet")
        orch = DownloadOrchestrator(store=store, cache_dir=tmp_path / "cache")

        # Mock _identify_missing_periods to return empty
        orch._identify_missing_periods = MagicMock(return_value=[])
        result = await orch.sync("BTCUSDT", date(2024, 1, 1), date(2024, 1, 31))
        assert result["periods_downloaded"] == 0
        assert result["rows_new"] == 0

    def test_identify_missing_periods_yearly_empty_store(self, tmp_path: Path):
        """Daily TF should look for YYYY.parquet files, not YYYY-MM."""
        store = ParquetStore(base_dir=tmp_path / "parquet")
        orch = DownloadOrchestrator(store=store, cache_dir=tmp_path / "cache")
        missing = orch._identify_missing_periods("binance", "BTCUSDT", "1d", date(2024, 1, 1), date(2024, 3, 31))
        # Should expand year 2024 into months Jan–Mar
        assert missing == [(2024, 1), (2024, 2), (2024, 3)]

    def test_identify_missing_periods_yearly_partial(self, tmp_path: Path):
        """Year with existing YYYY.parquet should be skipped entirely."""
        store = ParquetStore(base_dir=tmp_path / "parquet")
        orch = DownloadOrchestrator(store=store, cache_dir=tmp_path / "cache")

        # Create yearly partition for 2023
        data_dir = tmp_path / "parquet" / "binance" / "BTCUSDT" / "1d"
        data_dir.mkdir(parents=True)
        (data_dir / "2023.parquet").touch()

        missing = orch._identify_missing_periods("binance", "BTCUSDT", "1d", date(2023, 6, 1), date(2024, 3, 31))
        # 2023 has a file → skip. 2024 missing → expand to months
        assert all(y == 2024 for y, m in missing)
        assert missing == [(2024, 1), (2024, 2), (2024, 3)]

    def test_identify_missing_periods_monthly_still_works(self, tmp_path: Path):
        """Intraday TFs should still use YYYY-MM pattern."""
        store = ParquetStore(base_dir=tmp_path / "parquet")
        orch = DownloadOrchestrator(store=store, cache_dir=tmp_path / "cache")

        data_dir = tmp_path / "parquet" / "binance" / "BTCUSDT" / "1h"
        data_dir.mkdir(parents=True)
        (data_dir / "2024-01.parquet").touch()

        missing = orch._identify_missing_periods("binance", "BTCUSDT", "1h", date(2024, 1, 1), date(2024, 3, 31))
        assert missing == [(2024, 2), (2024, 3)]


# ═══════════════════════════════════════════════════════════════════════════════
# _to_ccxt_symbol
# ═══════════════════════════════════════════════════════════════════════════════


class TestToCCXTSymbol:
    def test_usdt_pair(self):
        assert _to_ccxt_symbol("BTCUSDT") == "BTC/USDT"

    def test_eth_base(self):
        assert _to_ccxt_symbol("ETHUSDT") == "ETH/USDT"

    def test_sol_usdt(self):
        assert _to_ccxt_symbol("SOLUSDT") == "SOL/USDT"

    def test_busd_pair(self):
        assert _to_ccxt_symbol("ETHBUSD") == "ETH/BUSD"

    def test_already_ccxt_format(self):
        assert _to_ccxt_symbol("BTC/USDT") == "BTC/USDT"

    def test_fallback_unknown(self):
        assert _to_ccxt_symbol("XYZABC") == "XYZABC"


# ═══════════════════════════════════════════════════════════════════════════════
# _year_range
# ═══════════════════════════════════════════════════════════════════════════════


class TestYearRange:
    def test_single_year(self):
        assert _year_range(date(2024, 3, 1), date(2024, 11, 1)) == [2024]

    def test_multi_year(self):
        assert _year_range(date(2022, 1, 1), date(2024, 6, 1)) == [2022, 2023, 2024]

    def test_same_date(self):
        assert _year_range(date(2024, 1, 1), date(2024, 1, 1)) == [2024]
