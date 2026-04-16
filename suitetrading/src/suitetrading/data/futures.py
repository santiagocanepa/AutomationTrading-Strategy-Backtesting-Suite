"""Binance Futures data downloader — funding rate, open interest, long/short ratio.

Downloads historical derivatives data from Binance Futures API and stores
as parquet files.  Data is merged into the OHLCV DataFrame at load time
to enrich the BacktestDataset with columns the futures indicators need.

API Endpoints
-------------
- Funding Rate:      GET /fapi/v1/fundingRate          (8h updates, limit=1000)
- Open Interest:     GET /futures/data/openInterestHist (5m-1d, limit=500)
- Long/Short Ratio:  GET /futures/data/globalLongShortAccountRatio (5m-1d, limit=500)

Production notes:
    - Funding rate: poll once per settlement (every 8h)
    - OI + L/S ratio: poll every 5m for real-time strategies
    - All endpoints are unauthenticated (no API key needed)
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd
from loguru import logger

BASE_URL = "https://fapi.binance.com"

# Rate limit: 2400 req/min for Binance Futures. Stay well below.
_REQUEST_DELAY = 0.15  # seconds between requests


class BinanceFuturesDownloader:
    """Download and store historical futures data from Binance.

    Parameters
    ----------
    output_dir
        Base directory for parquet storage.
        Files are saved as ``{output_dir}/binance/{symbol}/futures/{type}.parquet``.
    """

    def __init__(self, output_dir: Path | str = Path("data/raw")) -> None:
        self._output_dir = Path(output_dir)
        self._client = httpx.Client(timeout=30.0, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> BinanceFuturesDownloader:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ── Funding Rate ─────────────────────────────────────────────────

    def download_funding_rate(
        self,
        symbol: str,
        start: datetime | str | None = None,
        end: datetime | str | None = None,
    ) -> pd.DataFrame:
        """Download funding rate history for a symbol.

        Returns DataFrame with DatetimeIndex and ``funding_rate`` column.
        """
        url = f"{BASE_URL}/fapi/v1/fundingRate"
        start_ms = self._to_ms(start) if start else None
        end_ms = self._to_ms(end) if end else None

        all_rows: list[dict[str, Any]] = []
        current_start = start_ms

        while True:
            params: dict[str, Any] = {"symbol": symbol, "limit": 1000}
            if current_start:
                params["startTime"] = current_start
            if end_ms:
                params["endTime"] = end_ms

            data = self._get(url, params)
            if not data:
                break

            all_rows.extend(data)
            logger.debug("Funding rate {}: fetched {} records", symbol, len(data))

            if len(data) < 1000:
                break

            # Advance to after the last record
            current_start = data[-1]["fundingTime"] + 1
            time.sleep(_REQUEST_DELAY)

        if not all_rows:
            logger.warning("No funding rate data for {}", symbol)
            return pd.DataFrame()

        df = pd.DataFrame(all_rows)
        df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
        df["funding_rate"] = df["fundingRate"].astype(float)
        df = df.set_index("timestamp").sort_index()
        df = df[["funding_rate"]].drop_duplicates()

        self._save(df, symbol, "funding_rate")
        logger.info("Funding rate {}: {} records ({} to {})",
                     symbol, len(df), df.index[0], df.index[-1])
        return df

    # ── Open Interest ────────────────────────────────────────────────

    def download_open_interest(
        self,
        symbol: str,
        period: str = "1h",
        start: datetime | str | None = None,
        end: datetime | str | None = None,
    ) -> pd.DataFrame:
        """Download open interest history.

        Parameters
        ----------
        period
            Data resolution: ``"5m"``, ``"15m"``, ``"30m"``, ``"1h"``,
            ``"2h"``, ``"4h"``, ``"6h"``, ``"12h"``, ``"1d"``.
        """
        url = f"{BASE_URL}/futures/data/openInterestHist"
        start_ms = self._to_ms(start) if start else None
        end_ms = self._to_ms(end) if end else None

        all_rows: list[dict[str, Any]] = []
        current_start = start_ms

        while True:
            params: dict[str, Any] = {
                "symbol": symbol, "period": period, "limit": 500,
            }
            if current_start:
                params["startTime"] = current_start
            if end_ms:
                params["endTime"] = end_ms

            data = self._get(url, params)
            if not data:
                break

            all_rows.extend(data)
            logger.debug("OI {}: fetched {} records", symbol, len(data))

            if len(data) < 500:
                break

            current_start = data[-1]["timestamp"] + 1
            time.sleep(_REQUEST_DELAY)

        if not all_rows:
            logger.warning("No OI data for {}", symbol)
            return pd.DataFrame()

        df = pd.DataFrame(all_rows)
        df["ts"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["open_interest"] = df["sumOpenInterest"].astype(float)
        df["open_interest_value"] = df["sumOpenInterestValue"].astype(float)
        df = df.set_index("ts").sort_index()
        df = df[["open_interest", "open_interest_value"]].drop_duplicates()

        self._save(df, symbol, f"open_interest_{period}")
        logger.info("OI {}: {} records ({} to {})",
                     symbol, len(df), df.index[0], df.index[-1])
        return df

    # ── Long/Short Ratio ─────────────────────────────────────────────

    def download_long_short_ratio(
        self,
        symbol: str,
        period: str = "1h",
        start: datetime | str | None = None,
        end: datetime | str | None = None,
    ) -> pd.DataFrame:
        """Download global long/short account ratio history."""
        url = f"{BASE_URL}/futures/data/globalLongShortAccountRatio"
        start_ms = self._to_ms(start) if start else None
        end_ms = self._to_ms(end) if end else None

        all_rows: list[dict[str, Any]] = []
        current_start = start_ms

        while True:
            params: dict[str, Any] = {
                "symbol": symbol, "period": period, "limit": 500,
            }
            if current_start:
                params["startTime"] = current_start
            if end_ms:
                params["endTime"] = end_ms

            data = self._get(url, params)
            if not data:
                break

            all_rows.extend(data)
            logger.debug("L/S ratio {}: fetched {} records", symbol, len(data))

            if len(data) < 500:
                break

            current_start = data[-1]["timestamp"] + 1
            time.sleep(_REQUEST_DELAY)

        if not all_rows:
            logger.warning("No L/S ratio data for {}", symbol)
            return pd.DataFrame()

        df = pd.DataFrame(all_rows)
        df["ts"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["long_short_ratio"] = df["longShortRatio"].astype(float)
        df["long_account"] = df["longAccount"].astype(float)
        df["short_account"] = df["shortAccount"].astype(float)
        df = df.set_index("ts").sort_index()
        df = df[["long_short_ratio", "long_account", "short_account"]].drop_duplicates()

        self._save(df, symbol, f"long_short_ratio_{period}")
        logger.info("L/S ratio {}: {} records ({} to {})",
                     symbol, len(df), df.index[0], df.index[-1])
        return df

    # ── Download all ─────────────────────────────────────────────────

    def download_all(
        self,
        symbol: str,
        period: str = "1h",
        start: datetime | str | None = None,
        end: datetime | str | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Download all futures data types for a symbol."""
        results = {}
        results["funding_rate"] = self.download_funding_rate(symbol, start, end)
        results["open_interest"] = self.download_open_interest(symbol, period, start, end)
        results["long_short_ratio"] = self.download_long_short_ratio(symbol, period, start, end)
        return results

    # ── Load & merge ─────────────────────────────────────────────────

    def load_and_merge(
        self,
        symbol: str,
        ohlcv: pd.DataFrame,
        period: str = "1h",
    ) -> pd.DataFrame:
        """Load stored futures data and merge into OHLCV DataFrame.

        Forward-fills lower-frequency data (funding rate is 8h) to match
        the OHLCV index.  Returns the enriched DataFrame.
        """
        enriched = ohlcv.copy()

        # Funding rate
        fr_path = self._parquet_path(symbol, "funding_rate")
        if fr_path.exists():
            fr = pd.read_parquet(fr_path)
            enriched = enriched.join(fr[["funding_rate"]], how="left")
            enriched["funding_rate"] = enriched["funding_rate"].ffill()

        # Open interest
        oi_path = self._parquet_path(symbol, f"open_interest_{period}")
        if oi_path.exists():
            oi = pd.read_parquet(oi_path)
            enriched = enriched.join(oi[["open_interest"]], how="left")
            enriched["open_interest"] = enriched["open_interest"].ffill()

        # Long/Short ratio
        ls_path = self._parquet_path(symbol, f"long_short_ratio_{period}")
        if ls_path.exists():
            ls = pd.read_parquet(ls_path)
            enriched = enriched.join(ls[["long_short_ratio"]], how="left")
            enriched["long_short_ratio"] = enriched["long_short_ratio"].ffill()

        added = [c for c in ["funding_rate", "open_interest", "long_short_ratio"]
                 if c in enriched.columns]
        if added:
            logger.info("Enriched {} OHLCV with: {}", symbol, added)

        return enriched

    # ── Private helpers ──────────────────────────────────────────────

    def _get(self, url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """GET request with error handling."""
        try:
            resp = self._client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.warning("API error {}: {}", e.response.status_code, e.response.text[:200])
            return []
        except httpx.RequestError as e:
            logger.warning("Request failed: {}", e)
            return []

    def _save(self, df: pd.DataFrame, symbol: str, data_type: str) -> Path:
        """Save DataFrame as parquet."""
        path = self._parquet_path(symbol, data_type)
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path, compression="zstd")
        return path

    def _parquet_path(self, symbol: str, data_type: str) -> Path:
        return self._output_dir / "binance" / symbol / "futures" / f"{data_type}.parquet"

    @staticmethod
    def _to_ms(dt: datetime | str) -> int:
        if isinstance(dt, str):
            dt = pd.Timestamp(dt, tz="UTC").to_pydatetime()
        return int(dt.timestamp() * 1000)
