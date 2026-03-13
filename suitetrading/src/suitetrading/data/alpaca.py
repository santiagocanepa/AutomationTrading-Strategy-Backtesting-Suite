"""Alpaca Markets OHLCV downloader for stocks and crypto.

Uses the ``alpaca-py`` SDK to fetch historical bars from Alpaca's data API.
Supports both stock and crypto asset classes via their respective clients.

Requires environment variables ``ALPACA_API_KEY`` and ``ALPACA_SECRET_KEY``.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

import pandas as pd
from loguru import logger

from suitetrading.data.timeframes import normalize_timeframe, tf_to_alpaca


AssetClass = Literal["stock", "crypto"]

# Alpaca free-tier limit: 200 bars per request for historical data.
# Paid plans allow up to 10_000.  We paginate conservatively.
_PAGE_LIMIT = 10_000


class AlpacaDownloader:
    """Download OHLCV bars from Alpaca Markets.

    Parameters
    ----------
    api_key : str
        Alpaca API key (``ALPACA_API_KEY``).
    secret_key : str
        Alpaca secret key (``ALPACA_SECRET_KEY``).
    asset_class : AssetClass
        ``"stock"`` or ``"crypto"``.
    feed : str | None
        Data feed for stocks (``"iex"`` free, ``"sip"`` paid).
        Ignored for crypto.
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        *,
        asset_class: AssetClass = "stock",
        feed: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._secret_key = secret_key
        self._asset_class = asset_class
        self._feed = feed
        self._client = self._build_client()

    def _build_client(self):
        """Lazily import and construct the appropriate Alpaca data client."""
        from alpaca.data.historical.crypto import CryptoHistoricalDataClient
        from alpaca.data.historical.stock import StockHistoricalDataClient

        creds = {"api_key": self._api_key, "secret_key": self._secret_key}

        if self._asset_class == "crypto":
            return CryptoHistoricalDataClient(**creds)
        return StockHistoricalDataClient(**creds)

    # ── Public API ────────────────────────────────────────────────────────────

    def download_range(
        self,
        symbol: str,
        timeframe: str,
        start: date,
        end: date,
    ) -> pd.DataFrame:
        """Download OHLCV bars for *symbol* between *start* and *end*.

        Returns a standard OHLCV DataFrame with UTC DatetimeIndex matching
        the ``ParquetStore`` schema.
        """
        tf_key = normalize_timeframe(timeframe)
        alpaca_tf_str = tf_to_alpaca(tf_key)
        if alpaca_tf_str is None:
            raise ValueError(f"Timeframe {tf_key!r} is not supported by Alpaca")

        alpaca_tf = self._parse_alpaca_timeframe(alpaca_tf_str)

        start_dt = datetime(start.year, start.month, start.day, tzinfo=timezone.utc)
        end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=timezone.utc)

        logger.info(
            "Alpaca {} download: {} {} from {} to {}",
            self._asset_class, symbol, tf_key, start, end,
        )

        if self._asset_class == "crypto":
            df = self._download_crypto(symbol, alpaca_tf, start_dt, end_dt)
        else:
            df = self._download_stock(symbol, alpaca_tf, start_dt, end_dt)

        if df.empty:
            raise ValueError(
                f"No data from Alpaca for {symbol}/{tf_key} in range {start}–{end}"
            )

        logger.info("Alpaca downloaded {} rows for {}/{}", len(df), symbol, tf_key)
        return df

    # ── Internals ─────────────────────────────────────────────────────────────

    def _download_stock(
        self, symbol: str, timeframe, start: datetime, end: datetime,
    ) -> pd.DataFrame:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest

        kwargs: dict = {
            "symbol_or_symbols": symbol,
            "timeframe": timeframe,
            "start": start,
            "end": end,
            "limit": _PAGE_LIMIT,
            "adjustment": Adjustment.ALL,
        }
        if self._feed:
            kwargs["feed"] = DataFeed(self._feed)

        bars = self._client.get_stock_bars(StockBarsRequest(**kwargs))
        return self._barset_to_df(bars)

    def _download_crypto(
        self, symbol: str, timeframe, start: datetime, end: datetime,
    ) -> pd.DataFrame:
        from alpaca.data.requests import CryptoBarsRequest

        bars = self._client.get_crypto_bars(
            CryptoBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                limit=_PAGE_LIMIT,
            ),
        )
        return self._barset_to_df(bars)

    @staticmethod
    def _barset_to_df(barset) -> pd.DataFrame:
        """Convert Alpaca ``BarSet`` → standard OHLCV DataFrame."""
        df = barset.df
        if df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        # BarSet.df has a MultiIndex (symbol, timestamp) — drop symbol level
        if isinstance(df.index, pd.MultiIndex):
            df = df.droplevel(0)

        df.index.name = "timestamp"

        # Ensure UTC
        if df.index.tz is None:
            df = df.tz_localize("UTC")
        else:
            df = df.tz_convert("UTC")

        # Keep only OHLCV columns
        df = df[["open", "high", "low", "close", "volume"]].copy()
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]
        return df

    @staticmethod
    def _parse_alpaca_timeframe(tf_str: str):
        """Parse our string representation into an Alpaca ``TimeFrame`` object."""
        from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

        # tf_str examples: "1Min", "5Min", "1Hour", "4Hour", "1Day", "1Week", "1Month"
        unit_map = {
            "Min": TimeFrameUnit.Minute,
            "Hour": TimeFrameUnit.Hour,
            "Day": TimeFrameUnit.Day,
            "Week": TimeFrameUnit.Week,
            "Month": TimeFrameUnit.Month,
        }
        for suffix, unit in unit_map.items():
            if tf_str.endswith(suffix):
                amount = int(tf_str[: -len(suffix)])
                return TimeFrame(amount, unit)
        raise ValueError(f"Cannot parse Alpaca timeframe: {tf_str!r}")
