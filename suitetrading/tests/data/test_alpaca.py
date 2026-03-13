"""Tests for AlpacaDownloader and Alpaca-related orchestrator paths.

All network I/O is mocked — no real Alpaca API calls.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from suitetrading.data.alpaca import AlpacaDownloader
from suitetrading.data.downloader import DownloadOrchestrator
from suitetrading.data.storage import ParquetStore
from suitetrading.data.timeframes import tf_to_alpaca


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _make_alpaca_barset(
    symbol: str = "AAPL",
    rows: int = 50,
    start: str = "2024-01-02 14:30:00",
    freq: str = "1D",
) -> MagicMock:
    """Create a mock Alpaca BarSet with a .df property returning OHLCV."""
    idx = pd.date_range(start, periods=rows, freq=freq, tz="America/New_York")
    multi_idx = pd.MultiIndex.from_arrays(
        [[symbol] * rows, idx],
        names=["symbol", "timestamp"],
    )
    df = pd.DataFrame(
        {
            "open": [150.0 + i for i in range(rows)],
            "high": [155.0 + i for i in range(rows)],
            "low": [148.0 + i for i in range(rows)],
            "close": [152.0 + i for i in range(rows)],
            "volume": [1_000_000.0 + i * 1000 for i in range(rows)],
            "trade_count": [5000.0] * rows,
            "vwap": [151.0 + i for i in range(rows)],
        },
        index=multi_idx,
    )
    barset = MagicMock()
    barset.df = df
    return barset


def _make_empty_barset() -> MagicMock:
    barset = MagicMock()
    barset.df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    return barset


# ═══════════════════════════════════════════════════════════════════════════════
# tf_to_alpaca
# ═══════════════════════════════════════════════════════════════════════════════


class TestTfToAlpaca:
    def test_supported_timeframes(self):
        assert tf_to_alpaca("1m") == "1Min"
        assert tf_to_alpaca("5m") == "5Min"
        assert tf_to_alpaca("15m") == "15Min"
        assert tf_to_alpaca("30m") == "30Min"
        assert tf_to_alpaca("1h") == "1Hour"
        assert tf_to_alpaca("4h") == "4Hour"
        assert tf_to_alpaca("1d") == "1Day"
        assert tf_to_alpaca("1w") == "1Week"
        assert tf_to_alpaca("1M") == "1Month"

    def test_unsupported_timeframes(self):
        assert tf_to_alpaca("3m") is None
        assert tf_to_alpaca("45m") is None


# ═══════════════════════════════════════════════════════════════════════════════
# AlpacaDownloader._parse_alpaca_timeframe
# ═══════════════════════════════════════════════════════════════════════════════


class TestParseAlpacaTimeframe:
    def test_minute(self):
        from alpaca.data.timeframe import TimeFrameUnit

        result = AlpacaDownloader._parse_alpaca_timeframe("1Min")
        assert result.amount == 1
        assert result.unit == TimeFrameUnit.Minute

    def test_multi_minute(self):
        from alpaca.data.timeframe import TimeFrameUnit

        result = AlpacaDownloader._parse_alpaca_timeframe("15Min")
        assert result.amount == 15
        assert result.unit == TimeFrameUnit.Minute

    def test_hour(self):
        from alpaca.data.timeframe import TimeFrameUnit

        result = AlpacaDownloader._parse_alpaca_timeframe("4Hour")
        assert result.amount == 4
        assert result.unit == TimeFrameUnit.Hour

    def test_day(self):
        from alpaca.data.timeframe import TimeFrameUnit

        result = AlpacaDownloader._parse_alpaca_timeframe("1Day")
        assert result.amount == 1
        assert result.unit == TimeFrameUnit.Day

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Cannot parse"):
            AlpacaDownloader._parse_alpaca_timeframe("INVALID")


# ═══════════════════════════════════════════════════════════════════════════════
# AlpacaDownloader._barset_to_df
# ═══════════════════════════════════════════════════════════════════════════════


class TestBarsetToDf:
    def test_standard_conversion(self):
        barset = _make_alpaca_barset(rows=10)
        df = AlpacaDownloader._barset_to_df(barset)

        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df.index.name == "timestamp"
        assert str(df.index.tz) == "UTC"
        assert len(df) == 10

    def test_drops_extra_columns(self):
        barset = _make_alpaca_barset(rows=5)
        df = AlpacaDownloader._barset_to_df(barset)
        assert "trade_count" not in df.columns
        assert "vwap" not in df.columns

    def test_deduplicates(self):
        barset = _make_alpaca_barset(rows=5)
        # Add a duplicate timestamp
        original_df = barset.df
        dup_row = original_df.iloc[[0]].copy()
        dup_row["open"] = 999.0
        combined = pd.concat([original_df, dup_row])
        barset.df = combined

        df = AlpacaDownloader._barset_to_df(barset)
        assert len(df) == 5

    def test_empty_barset(self):
        barset = _make_empty_barset()
        df = AlpacaDownloader._barset_to_df(barset)
        assert df.empty
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]


# ═══════════════════════════════════════════════════════════════════════════════
# AlpacaDownloader.download_range (mocked)
# ═══════════════════════════════════════════════════════════════════════════════


class TestAlpacaDownloaderDownload:
    def _make_downloader(self, mock_client: MagicMock, asset_class: str = "stock") -> AlpacaDownloader:
        """Create an AlpacaDownloader with a mocked client."""
        with patch.object(AlpacaDownloader, "_build_client", return_value=mock_client):
            return AlpacaDownloader(
                api_key="test-key",
                secret_key="test-secret",
                asset_class=asset_class,
            )

    def test_download_stock_returns_ohlcv(self):
        barset = _make_alpaca_barset(symbol="AAPL", rows=20)
        mock_client = MagicMock()
        mock_client.get_stock_bars.return_value = barset

        dl = self._make_downloader(mock_client, "stock")
        df = dl.download_range("AAPL", "1d", date(2024, 1, 1), date(2024, 3, 1))
        assert len(df) == 20
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        mock_client.get_stock_bars.assert_called_once()

    def test_download_crypto_returns_ohlcv(self):
        barset = _make_alpaca_barset(symbol="BTC/USD", rows=15)
        mock_client = MagicMock()
        mock_client.get_crypto_bars.return_value = barset

        dl = self._make_downloader(mock_client, "crypto")
        df = dl.download_range("BTC/USD", "1h", date(2024, 1, 1), date(2024, 2, 1))
        assert len(df) == 15
        mock_client.get_crypto_bars.assert_called_once()

    def test_unsupported_timeframe_raises(self):
        mock_client = MagicMock()
        dl = self._make_downloader(mock_client, "stock")
        with pytest.raises(ValueError, match="not supported by Alpaca"):
            dl.download_range("AAPL", "3m", date(2024, 1, 1), date(2024, 2, 1))

    def test_empty_response_raises(self):
        mock_client = MagicMock()
        mock_client.get_stock_bars.return_value = _make_empty_barset()
        dl = self._make_downloader(mock_client, "stock")
        with pytest.raises(ValueError, match="No data from Alpaca"):
            dl.download_range("AAPL", "1d", date(2024, 1, 1), date(2024, 2, 1))


# ═══════════════════════════════════════════════════════════════════════════════
# DownloadOrchestrator — Alpaca routing
# ═══════════════════════════════════════════════════════════════════════════════


class TestOrchestratorAlpaca:
    def _make_orchestrator(self, tmp_path: Path, *, with_alpaca: bool = True):
        """Create an orchestrator with optional mocked Alpaca credentials."""
        from suitetrading.config.settings import Settings

        settings = Settings(
            alpaca_api_key="test-key" if with_alpaca else "",
            alpaca_secret_key="test-secret" if with_alpaca else "",
            alpaca_feed="iex",
        )
        store = ParquetStore(base_dir=tmp_path / "parquet")
        mock_dl = MagicMock()

        build_return = mock_dl if with_alpaca else None
        with patch.object(
            DownloadOrchestrator, "_build_alpaca", return_value=build_return,
        ):
            orch = DownloadOrchestrator(
                store=store,
                cache_dir=tmp_path / "cache",
                settings=settings,
            )
        return orch, mock_dl

    @pytest.mark.asyncio
    async def test_sync_routes_to_alpaca(self, tmp_path: Path):
        orch, mock_dl = self._make_orchestrator(tmp_path)

        # Mock AlpacaDownloader.download_range to return valid OHLCV
        idx = pd.date_range("2024-01-02", periods=21, freq="B", tz="UTC")
        mock_dl.download_range.return_value = pd.DataFrame(
            {
                "open": [150.0] * 21,
                "high": [155.0] * 21,
                "low": [148.0] * 21,
                "close": [152.0] * 21,
                "volume": [1e6] * 21,
            },
            index=idx,
        )

        result = await orch.sync(
            "AAPL", date(2024, 1, 1), date(2024, 1, 31),
            exchange="alpaca", timeframe="1d",
        )
        assert result["rows_new"] > 0
        assert result["errors"] == []
        mock_dl.download_range.assert_called()

    @pytest.mark.asyncio
    async def test_sync_binance_unchanged(self, tmp_path: Path):
        """Passing exchange='binance' should NOT touch Alpaca."""
        orch, mock_dl = self._make_orchestrator(tmp_path)

        # Mock _identify_missing_periods to return empty
        orch._identify_missing_periods = MagicMock(return_value=[])
        result = await orch.sync(
            "BTCUSDT", date(2024, 1, 1), date(2024, 1, 31),
            exchange="binance",
        )
        assert result["periods_downloaded"] == 0
        mock_dl.download_range.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_alpaca_no_credentials_raises(self, tmp_path: Path):
        orch, _ = self._make_orchestrator(tmp_path, with_alpaca=False)
        with pytest.raises(RuntimeError, match="Alpaca credentials not configured"):
            await orch.sync(
                "AAPL", date(2024, 1, 1), date(2024, 1, 31),
                exchange="alpaca", timeframe="1d",
            )

    @pytest.mark.asyncio
    async def test_sync_alpaca_cached_returns_zero(self, tmp_path: Path):
        orch, mock_dl = self._make_orchestrator(tmp_path)
        orch._identify_missing_periods = MagicMock(return_value=[])

        result = await orch.sync(
            "AAPL", date(2024, 1, 1), date(2024, 1, 31),
            exchange="alpaca", timeframe="1d",
        )
        assert result["periods_downloaded"] == 0
        assert result["rows_new"] == 0
        mock_dl.download_range.assert_not_called()

    @pytest.mark.asyncio
    async def test_sync_alpaca_stores_under_alpaca_exchange(self, tmp_path: Path):
        orch, mock_dl = self._make_orchestrator(tmp_path)

        idx = pd.date_range("2024-01-02", periods=21, freq="B", tz="UTC")
        mock_dl.download_range.return_value = pd.DataFrame(
            {
                "open": [150.0] * 21,
                "high": [155.0] * 21,
                "low": [148.0] * 21,
                "close": [152.0] * 21,
                "volume": [1e6] * 21,
            },
            index=idx,
        )

        await orch.sync(
            "AAPL", date(2024, 1, 1), date(2024, 1, 31),
            exchange="alpaca", timeframe="1d",
        )

        # Verify data stored under alpaca/AAPL/1d/
        stored = orch._store.read("alpaca", "AAPL", "1d")
        assert not stored.empty
        assert list(stored.columns) == ["open", "high", "low", "close", "volume"]

    @pytest.mark.asyncio
    async def test_sync_alpaca_handles_download_error(self, tmp_path: Path):
        orch, mock_dl = self._make_orchestrator(tmp_path)
        mock_dl.download_range.side_effect = ValueError("API error")

        result = await orch.sync(
            "AAPL", date(2024, 1, 1), date(2024, 1, 31),
            exchange="alpaca", timeframe="1d",
        )
        assert result["rows_new"] == 0
        assert len(result["errors"]) > 0
        assert "API error" in result["errors"][0]
