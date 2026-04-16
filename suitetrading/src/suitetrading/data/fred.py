"""FRED API downloader for macro economic series.

Downloads VIX, yield curve, credit spreads and other macro indicators
from the Federal Reserve Economic Data (FRED) API.
"""

from __future__ import annotations

import os
import time

import pandas as pd
from fredapi import Fred
from loguru import logger


class FREDDownloader:
    """Download macro series from FRED API."""

    SERIES: dict[str, str] = {
        "vix": "VIXCLS",
        "yield_10y": "DGS10",
        "yield_2y": "DGS2",
        "yield_spread": "T10Y2Y",
        "yield_3m10y": "T10Y3M",
        "hy_spread": "BAMLH0A0HYM2",
        "ig_spread": "BAMLC0A0CM",
        "dollar_index": "DTWEXBGS",
    }

    def __init__(self, api_key: str | None = None, max_retries: int = 3) -> None:
        key = api_key or os.environ.get("FRED_API_KEY")
        if not key:
            raise ValueError(
                "FRED API key required. Set FRED_API_KEY env var or pass api_key."
            )
        self._fred = Fred(api_key=key)
        self._max_retries = max_retries

    def download(
        self,
        series_id: str,
        start: str | None = None,
        end: str | None = None,
    ) -> pd.Series:
        """Download a single FRED series with retry logic.

        Returns a forward-filled Series with DatetimeIndex (UTC).
        """
        fred_id = self.SERIES.get(series_id, series_id)

        for attempt in range(1, self._max_retries + 1):
            try:
                data = self._fred.get_series(
                    fred_id,
                    observation_start=start,
                    observation_end=end,
                )
                break
            except Exception as exc:
                if attempt == self._max_retries:
                    raise RuntimeError(
                        f"Failed to download {fred_id} after {self._max_retries} attempts"
                    ) from exc
                wait = 2.0**attempt
                logger.warning(
                    "FRED download {} failed (attempt {}/{}): {}. Retrying in {:.0f}s",
                    fred_id, attempt, self._max_retries, exc, wait,
                )
                time.sleep(wait)

        if data is None or data.empty:
            raise ValueError(f"No data returned for FRED series {fred_id}")

        data = data.dropna()
        data.index = pd.DatetimeIndex(data.index, tz="UTC")
        data.name = series_id
        result = data.astype(float)
        logger.info(
            "Downloaded FRED {}: {} points ({} → {})",
            fred_id, len(result),
            str(result.index[0].date()), str(result.index[-1].date()),
        )
        return result

    def download_all(
        self, start: str | None = None
    ) -> dict[str, pd.Series]:
        """Download all pre-configured series."""
        results: dict[str, pd.Series] = {}
        for key in self.SERIES:
            try:
                results[key] = self.download(key, start=start)
            except Exception:
                logger.exception("Failed to download FRED series: {}", key)
        return results
