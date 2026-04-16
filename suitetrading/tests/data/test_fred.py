"""Tests for FRED API downloader."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from suitetrading.data.fred import FREDDownloader


# ── Fixtures ──────────────────────────────────────────────────────────

def _mock_fred_series(n: int = 100, name: str = "VIXCLS") -> pd.Series:
    """Synthetic FRED-like series (daily, no tz)."""
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(42)
    values = 15.0 + rng.normal(0, 2, n)
    return pd.Series(values, index=idx, name=name)


@pytest.fixture
def mock_fred(monkeypatch):
    """Patch fredapi.Fred so no real API calls are made."""
    instance = MagicMock()
    instance.get_series.return_value = _mock_fred_series()
    mock_cls = MagicMock(return_value=instance)
    monkeypatch.setattr("suitetrading.data.fred.Fred", mock_cls)
    return instance


@pytest.fixture
def downloader(mock_fred, monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test_key_123")
    return FREDDownloader()


# ── Tests ─────────────────────────────────────────────────────────────

class TestFREDDownloader:
    def test_download_single_series(self, downloader, mock_fred):
        result = downloader.download("vix")
        assert isinstance(result, pd.Series)
        assert len(result) == 100
        assert result.name == "vix"
        mock_fred.get_series.assert_called_once()

    def test_download_with_env_key(self, monkeypatch):
        monkeypatch.setenv("FRED_API_KEY", "env_key_456")
        mock_cls = MagicMock()
        mock_cls.return_value.get_series.return_value = _mock_fred_series()
        monkeypatch.setattr("suitetrading.data.fred.Fred", mock_cls)
        FREDDownloader()
        mock_cls.assert_called_once_with(api_key="env_key_456")

    def test_no_api_key_raises(self, monkeypatch):
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        with pytest.raises(ValueError, match="FRED API key required"):
            FREDDownloader()

    def test_retry_on_error(self, downloader, mock_fred):
        mock_fred.get_series.side_effect = [
            ConnectionError("timeout"),
            _mock_fred_series(),
        ]
        result = downloader.download("vix")
        assert len(result) == 100
        assert mock_fred.get_series.call_count == 2

    def test_max_retries_exhausted_raises(self, downloader, mock_fred):
        mock_fred.get_series.side_effect = ConnectionError("persistent failure")
        with pytest.raises(RuntimeError, match="Failed to download"):
            downloader.download("vix")
        assert mock_fred.get_series.call_count == 3

    def test_forward_fill_drops_nan(self, downloader, mock_fred):
        series = _mock_fred_series(50)
        series.iloc[10:15] = np.nan
        mock_fred.get_series.return_value = series
        result = downloader.download("vix")
        assert not result.isna().any()
        assert len(result) == 45  # 50 - 5 NaN rows dropped

    def test_returns_utc_datetime_index(self, downloader):
        result = downloader.download("vix")
        assert result.index.tz is not None
        assert str(result.index.tz) == "UTC"

    def test_all_configured_series_are_valid_keys(self):
        expected = {"vix", "yield_10y", "yield_2y", "yield_spread",
                    "yield_3m10y", "hy_spread", "ig_spread", "dollar_index"}
        assert set(FREDDownloader.SERIES.keys()) == expected

    def test_download_all(self, downloader, mock_fred):
        results = downloader.download_all()
        assert len(results) == len(FREDDownloader.SERIES)
        for key, series in results.items():
            assert isinstance(series, pd.Series)
