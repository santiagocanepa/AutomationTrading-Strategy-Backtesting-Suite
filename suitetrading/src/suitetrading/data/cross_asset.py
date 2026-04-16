"""Cross-asset ETF downloader for macro signals.

Downloads daily OHLCV for ETFs used in cross-asset correlation
and regime detection (HYG, LQD, UUP, etc.) via yfinance.
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf
from loguru import logger


class CrossAssetDownloader:
    """Download cross-asset ETF data for macro signals."""

    TICKERS: dict[str, str] = {
        "hyg": "HYG",
        "lqd": "LQD",
        "uup": "UUP",
        "ief": "IEF",
    }

    def download(
        self,
        ticker: str,
        start: str | None = None,
        period: str = "10y",
    ) -> pd.DataFrame:
        """Download daily OHLCV for a ticker.

        Returns DataFrame with UTC DatetimeIndex and lowercase columns.
        """
        yf_ticker = self.TICKERS.get(ticker.lower(), ticker.upper())

        kwargs: dict = {}
        if start:
            kwargs["start"] = start
        else:
            kwargs["period"] = period

        raw = yf.download(yf_ticker, progress=False, auto_adjust=True, **kwargs)

        if raw is None or raw.empty:
            raise ValueError(f"No data returned for {yf_ticker}")

        # Flatten MultiIndex columns if present (yfinance >= 0.2.36)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)

        df = raw.rename(columns=str.lower)[["open", "high", "low", "close", "volume"]]
        df.index = pd.DatetimeIndex(df.index, tz="UTC")
        df = df.sort_index()

        logger.info(
            "Downloaded {}: {} bars ({} → {})",
            yf_ticker, len(df),
            str(df.index[0].date()), str(df.index[-1].date()),
        )
        return df

    def download_all(
        self, start: str | None = None
    ) -> dict[str, pd.DataFrame]:
        """Download all configured tickers."""
        results: dict[str, pd.DataFrame] = {}
        for key in self.TICKERS:
            try:
                results[key] = self.download(key, start=start)
            except Exception:
                logger.exception("Failed to download cross-asset: {}", key)
        return results
