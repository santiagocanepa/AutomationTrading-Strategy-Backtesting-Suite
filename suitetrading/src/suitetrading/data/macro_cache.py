"""Local Parquet cache for macro data (FRED + cross-asset).

Provides offline backtesting by caching macro series to disk
with staleness tracking and automatic alignment to OHLCV indices.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from suitetrading.data.cross_asset import CrossAssetDownloader
from suitetrading.data.fred import FREDDownloader

_META_FILE = "_meta.json"


class MacroCacheManager:
    """Local Parquet cache for macro data."""

    def __init__(self, cache_dir: Path | str = Path("data/raw/macro")) -> None:
        self._dir = Path(cache_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── Read ──────────────────────────────────────────────────────────

    def get(
        self, key: str, max_age_days: int = 1
    ) -> pd.Series | pd.DataFrame | None:
        """Read cached data. Returns None if stale or missing."""
        path = self._dir / f"{key}.parquet"
        if not path.exists():
            return None

        age_days = self._age_days(key)
        if age_days is not None and age_days > max_age_days:
            logger.debug("Cache stale for {}: {:.1f}d old (max {}d)", key, age_days, max_age_days)
            return None

        return self._read_parquet(path)

    def get_or_cached(self, key: str) -> pd.Series | pd.DataFrame | None:
        """Read cached data regardless of age. For offline/fallback use."""
        path = self._dir / f"{key}.parquet"
        if not path.exists():
            return None
        return self._read_parquet(path)

    # ── Write ─────────────────────────────────────────────────────────

    def put(self, key: str, data: pd.Series | pd.DataFrame) -> Path:
        """Write data to cache and update metadata."""
        path = self._dir / f"{key}.parquet"
        if isinstance(data, pd.Series):
            df = data.to_frame(name=data.name or key)
        else:
            df = data
        df.to_parquet(path, compression="zstd")
        self._update_meta(key)
        logger.debug("Cached {} → {} ({} rows)", key, path, len(df))
        return path

    # ── Refresh ───────────────────────────────────────────────────────

    def refresh_fred(
        self,
        downloader: FREDDownloader,
        *,
        keys: list[str] | None = None,
        force: bool = False,
        start: str | None = None,
        max_age_days: int = 1,
    ) -> dict[str, Path]:
        """Refresh FRED series. Skips fresh unless force=True."""
        targets = keys or list(FREDDownloader.SERIES.keys())
        paths: dict[str, Path] = {}

        for key in targets:
            if not force and self._is_fresh(key, max_age_days):
                logger.debug("Skipping {} (fresh)", key)
                paths[key] = self._dir / f"{key}.parquet"
                continue
            try:
                series = downloader.download(key, start=start)
                paths[key] = self.put(key, series)
            except Exception:
                logger.warning("Failed to refresh {}; using cached if available", key)
                cached_path = self._dir / f"{key}.parquet"
                if cached_path.exists():
                    paths[key] = cached_path
        return paths

    def refresh_cross_asset(
        self,
        downloader: CrossAssetDownloader,
        *,
        keys: list[str] | None = None,
        force: bool = False,
        start: str | None = None,
        max_age_days: int = 1,
    ) -> dict[str, Path]:
        """Refresh cross-asset ETF data."""
        targets = keys or list(CrossAssetDownloader.TICKERS.keys())
        paths: dict[str, Path] = {}

        for key in targets:
            if not force and self._is_fresh(key, max_age_days):
                logger.debug("Skipping {} (fresh)", key)
                paths[key] = self._dir / f"{key}.parquet"
                continue
            try:
                df = downloader.download(key, start=start)
                paths[key] = self.put(key, df)
            except Exception:
                logger.warning("Failed to refresh {}; using cached if available", key)
                cached_path = self._dir / f"{key}.parquet"
                if cached_path.exists():
                    paths[key] = cached_path
        return paths

    # ── Alignment ─────────────────────────────────────────────────────

    def get_aligned(
        self, keys: list[str], index: pd.DatetimeIndex
    ) -> pd.DataFrame:
        """Read multiple cached series and align to a target DatetimeIndex.

        Daily macro data is forward-filled to match intraday (1h, 4h) indices.
        Missing keys produce NaN columns with a warning.
        """
        result = pd.DataFrame(index=index)

        for key in keys:
            data = self.get_or_cached(key)
            if data is None:
                logger.warning("No cached data for '{}' — column will be NaN", key)
                result[key] = float("nan")
                continue

            if isinstance(data, pd.DataFrame):
                # For OHLCV cross-asset data, use close price
                if "close" in data.columns:
                    series = data["close"]
                else:
                    series = data.iloc[:, 0]
            else:
                series = data

            series.name = key
            # Reindex to target, forward-fill daily values across intraday bars
            aligned = series.reindex(index, method="ffill")
            result[key] = aligned

        return result

    # ── Internal ──────────────────────────────────────────────────────

    def _read_parquet(self, path: Path) -> pd.Series | pd.DataFrame:
        df = pd.read_parquet(path)
        # Single-column DataFrames from Series → return as Series
        if len(df.columns) == 1:
            s = df.iloc[:, 0]
            s.name = df.columns[0]
            return s
        return df

    def _is_fresh(self, key: str, max_age_days: int) -> bool:
        age = self._age_days(key)
        return age is not None and age <= max_age_days

    def _age_days(self, key: str) -> float | None:
        meta = self._read_meta()
        ts = meta.get(key)
        if ts is None:
            return None
        return (time.time() - ts) / 86400

    def _update_meta(self, key: str) -> None:
        meta = self._read_meta()
        meta[key] = time.time()
        meta_path = self._dir / _META_FILE
        meta_path.write_text(json.dumps(meta, indent=2))

    def _read_meta(self) -> dict[str, Any]:
        meta_path = self._dir / _META_FILE
        if not meta_path.exists():
            return {}
        try:
            return json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
