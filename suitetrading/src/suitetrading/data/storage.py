"""Partitioned Parquet storage for OHLCV data.

Layout on disk::

    {base_dir}/{exchange}/{symbol}/{timeframe}/{period}.parquet

Where *period* is ``YYYY-MM`` for intraday TFs or ``YYYY`` for daily+.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger

from suitetrading.data.timeframes import (
    normalize_timeframe,
    partition_scheme as _partition_scheme,
    tf_to_pandas_offset,
)

REQUIRED_COLUMNS = frozenset({"open", "high", "low", "close", "volume"})


class ParquetStore:
    """Read/write OHLCV data as partitioned Parquet files.

    Thread-safe for reads.  Writes are not concurrent-safe (single writer
    assumed — the download pipeline is sequential per symbol/tf).
    """

    def __init__(
        self,
        base_dir: Path,
        compression: str = "zstd",
        compression_level: int = 3,
    ) -> None:
        self._base_dir = Path(base_dir)
        self._compression = compression
        self._compression_level = compression_level

    # ── Public API ───────────────────────────────────────────────────────────

    def write(
        self,
        df: pd.DataFrame,
        exchange: str,
        symbol: str,
        timeframe: str,
        *,
        source: str = "unknown",
    ) -> list[Path]:
        """Write OHLCV DataFrame, auto-partitioned by month/year.

        Validates schema, deduplicates by timestamp (keeps last), sorts
        ascending, splits into partition files, and overwrites existing
        partitions if date ranges overlap.  Returns list of written paths.
        """
        tf = normalize_timeframe(timeframe)
        self._validate_write_schema(df)

        # Deduplicate & sort
        df = df[~df.index.duplicated(keep="last")].sort_index()

        scheme = self._detect_partition_scheme(tf)
        written: list[Path] = []

        if scheme == "monthly":
            groups = df.groupby([df.index.year, df.index.month])
            for (year, month), chunk in groups:
                period = f"{year}-{month:02d}"
                path = self._partition_path(exchange, symbol, tf, period)
                self._write_partition(chunk, path, exchange, symbol, tf, source)
                written.append(path)
        else:
            groups = df.groupby(df.index.year)
            for year, chunk in groups:
                period = str(year)
                path = self._partition_path(exchange, symbol, tf, period)
                self._write_partition(chunk, path, exchange, symbol, tf, source)
                written.append(path)

        logger.info(
            "Wrote {n} partitions for {exchange}/{symbol}/{tf}",
            n=len(written), exchange=exchange, symbol=symbol, tf=tf,
        )
        return written

    def read(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: datetime | None = None,
        end: datetime | None = None,
        columns: list[str] | None = None,
    ) -> pd.DataFrame:
        """Read OHLCV data for a date range.

        Raises ``FileNotFoundError`` if no data exists for the query.
        """
        tf = normalize_timeframe(timeframe)
        data_dir = self._base_dir / exchange / symbol / tf

        if not data_dir.exists():
            raise FileNotFoundError(f"No data directory: {data_dir}")

        files = sorted(data_dir.glob("*.parquet"))
        if not files:
            raise FileNotFoundError(f"No parquet files in {data_dir}")

        read_cols = list(columns) if columns else None
        frames: list[pd.DataFrame] = []

        for fp in files:
            tbl = pq.read_table(fp, columns=read_cols)
            part = tbl.to_pandas()

            # Restore DatetimeIndex from the stored 'timestamp' column or index
            if "timestamp" in part.columns:
                part = part.set_index("timestamp")
            if part.index.tz is None:
                part.index = part.index.tz_localize("UTC")
            part.index.name = None

            frames.append(part)

        df = pd.concat(frames).sort_index()
        df = df[~df.index.duplicated(keep="last")]

        # Apply date range filter
        if start is not None:
            ts_start = pd.Timestamp(start)
            if ts_start.tzinfo is None:
                ts_start = ts_start.tz_localize("UTC")
            df = df.loc[df.index >= ts_start]
        if end is not None:
            ts_end = pd.Timestamp(end)
            if ts_end.tzinfo is None:
                ts_end = ts_end.tz_localize("UTC")
            df = df.loc[df.index <= ts_end]

        if df.empty:
            raise FileNotFoundError(
                f"No data in range {start}–{end} for {exchange}/{symbol}/{tf}"
            )

        return df

    def list_available(self) -> list[dict]:
        """Return inventory of all stored datasets."""
        result: list[dict] = []
        if not self._base_dir.exists():
            return result

        for exchange_dir in sorted(self._base_dir.iterdir()):
            if not exchange_dir.is_dir():
                continue
            for symbol_dir in sorted(exchange_dir.iterdir()):
                if not symbol_dir.is_dir():
                    continue
                for tf_dir in sorted(symbol_dir.iterdir()):
                    if not tf_dir.is_dir():
                        continue
                    files = list(tf_dir.glob("*.parquet"))
                    if not files:
                        continue
                    # Quick peek at first/last file metadata
                    try:
                        info = self._quick_info(files)
                    except Exception:
                        continue
                    result.append({
                        "exchange": exchange_dir.name,
                        "symbol": symbol_dir.name,
                        "timeframe": tf_dir.name,
                        **info,
                    })
        return result

    def info(self, exchange: str, symbol: str, timeframe: str) -> dict:
        """Return metadata for a specific dataset."""
        tf = normalize_timeframe(timeframe)
        data_dir = self._base_dir / exchange / symbol / tf

        if not data_dir.exists():
            raise FileNotFoundError(f"No data directory: {data_dir}")

        files = sorted(data_dir.glob("*.parquet"))
        if not files:
            raise FileNotFoundError(f"No parquet files in {data_dir}")

        total_rows = 0
        date_min: pd.Timestamp | None = None
        date_max: pd.Timestamp | None = None
        total_size = 0
        source = "unknown"

        for fp in files:
            meta = pq.read_metadata(fp)
            total_rows += meta.num_rows
            total_size += fp.stat().st_size

            custom = meta.metadata or {}
            if b"source" in custom:
                source = custom[b"source"].decode()
            if b"date_min" in custom:
                dmin = pd.Timestamp(custom[b"date_min"].decode())
                if date_min is None or dmin < date_min:
                    date_min = dmin
            if b"date_max" in custom:
                dmax = pd.Timestamp(custom[b"date_max"].decode())
                if date_max is None or dmax > date_max:
                    date_max = dmax

        return {
            "date_min": date_min,
            "date_max": date_max,
            "rows": total_rows,
            "size_mb": round(total_size / (1024 * 1024), 3),
            "source": source,
        }

    # ── Private helpers ──────────────────────────────────────────────────────

    def _partition_path(self, exchange: str, symbol: str, timeframe: str, period: str) -> Path:
        return self._base_dir / exchange / symbol / timeframe / f"{period}.parquet"

    @staticmethod
    def _detect_partition_scheme(timeframe: str) -> str:
        return _partition_scheme(timeframe)

    def _write_partition(
        self,
        df: pd.DataFrame,
        path: Path,
        exchange: str,
        symbol: str,
        timeframe: str,
        source: str,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        # Store index as a regular column so Arrow preserves tz metadata
        write_df = df.copy()
        write_df.index.name = "timestamp"
        write_df = write_df.reset_index()

        table = pa.Table.from_pandas(write_df, preserve_index=False)

        # Attach custom metadata
        custom_meta = {
            b"exchange": exchange.encode(),
            b"symbol": symbol.encode(),
            b"timeframe": timeframe.encode(),
            b"source": source.encode(),
            b"download_timestamp": pd.Timestamp.now("UTC").isoformat().encode(),
            b"rows": str(len(df)).encode(),
            b"date_min": df.index.min().isoformat().encode(),
            b"date_max": df.index.max().isoformat().encode(),
        }
        existing_meta = table.schema.metadata or {}
        merged = {**existing_meta, **custom_meta}
        table = table.replace_schema_metadata(merged)

        pq.write_table(
            table,
            path,
            compression=self._compression,
            compression_level=self._compression_level if self._compression == "zstd" else None,
        )

    @staticmethod
    def _validate_write_schema(df: pd.DataFrame) -> None:
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError(f"Index must be DatetimeIndex, got {type(df.index).__name__}")
        if df.index.tz is None:
            raise ValueError("DatetimeIndex must have timezone (expected UTC)")
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")
        for col in REQUIRED_COLUMNS:
            if not pd.api.types.is_float_dtype(df[col]):
                raise ValueError(f"Column '{col}' must be float64, got {df[col].dtype}")

    @staticmethod
    def _quick_info(files: list[Path]) -> dict:
        """Read min/max dates and total rows from a list of parquet files."""
        total_rows = 0
        date_min: pd.Timestamp | None = None
        date_max: pd.Timestamp | None = None

        for fp in files:
            meta = pq.read_metadata(fp)
            total_rows += meta.num_rows
            custom = meta.metadata or {}
            if b"date_min" in custom:
                dmin = pd.Timestamp(custom[b"date_min"].decode())
                if date_min is None or dmin < date_min:
                    date_min = dmin
            if b"date_max" in custom:
                dmax = pd.Timestamp(custom[b"date_max"].decode())
                if date_max is None or dmax > date_max:
                    date_max = dmax

        return {"date_min": date_min, "date_max": date_max, "rows": total_rows}
