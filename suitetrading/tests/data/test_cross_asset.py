"""Tests for cross-asset ETF downloader."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from suitetrading.data.cross_asset import CrossAssetDownloader


def _mock_yf_download(n: int = 200) -> pd.DataFrame:
    """Synthetic yfinance-like DataFrame."""
    idx = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    return pd.DataFrame(
        {
            "Open": close + rng.normal(0, 0.2, n),
            "High": close + np.abs(rng.normal(0.3, 0.2, n)),
            "Low": close - np.abs(rng.normal(0.3, 0.2, n)),
            "Close": close,
            "Volume": rng.integers(1_000_000, 10_000_000, n).astype(float),
        },
        index=idx,
    )


@pytest.fixture
def mock_yf(monkeypatch):
    mock = MagicMock()
    mock.download.return_value = _mock_yf_download()
    monkeypatch.setattr("suitetrading.data.cross_asset.yf", mock)
    return mock


class TestCrossAssetDownloader:
    def test_download_returns_ohlcv_columns(self, mock_yf):
        dl = CrossAssetDownloader()
        df = dl.download("hyg")
        assert set(df.columns) == {"open", "high", "low", "close", "volume"}

    def test_download_returns_utc_index(self, mock_yf):
        dl = CrossAssetDownloader()
        df = dl.download("lqd")
        assert df.index.tz is not None
        assert str(df.index.tz) == "UTC"

    def test_handles_missing_ticker(self, mock_yf):
        mock_yf.download.return_value = pd.DataFrame()
        dl = CrossAssetDownloader()
        with pytest.raises(ValueError, match="No data returned"):
            dl.download("NONEXISTENT")

    def test_download_all(self, mock_yf):
        dl = CrossAssetDownloader()
        results = dl.download_all()
        assert len(results) == len(CrossAssetDownloader.TICKERS)
        for key, df in results.items():
            assert "close" in df.columns
