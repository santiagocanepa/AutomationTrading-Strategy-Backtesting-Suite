"""Multi-source OHLCV download pipeline.

Three classes compose the download layer:

* ``BinanceVisionDownloader`` — bulk CSV from data.binance.vision
* ``CCXTDownloader``          — any exchange via CCXT async API
* ``DownloadOrchestrator``    — coordinates both + validates + stores
"""

from __future__ import annotations

import asyncio
import io
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

import httpx
import pandas as pd
from loguru import logger

from suitetrading.config.settings import Settings
from suitetrading.data.storage import ParquetStore
from suitetrading.data.timeframes import (
    is_intraday,
    normalize_timeframe,
    tf_to_binance,
    tf_to_ccxt,
)
from suitetrading.data.validator import DataValidator


# ── Binance Vision ───────────────────────────────────────────────────────────


class BinanceVisionDownloader:
    """Download historical klines from Binance Vision bulk data.

    Binance Vision serves pre-generated CSV ZIP files per month at::

        {base_url}/data/spot/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{YYYY-MM}.zip
    """

    def __init__(
        self,
        cache_dir: Path,
        base_url: str = "https://data.binance.vision",
    ) -> None:
        self._cache_dir = Path(cache_dir)
        self._base_url = base_url.rstrip("/")
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    async def download_month(
        self,
        symbol: str,
        interval: str,
        year: int,
        month: int,
    ) -> pd.DataFrame | None:
        """Download a single month.  Returns ``None`` on 404 (pair didn't exist)."""
        url = self._build_url(symbol, interval, year, month)
        zip_name = f"{symbol}-{interval}-{year}-{month:02d}.zip"
        zip_path = self._cache_dir / zip_name

        if zip_path.exists():
            logger.debug("Cache hit: {}", zip_path.name)
            try:
                df = self._parse_zip(zip_path)
                self._validate_month_bounds(df, year, month)
                return df
            except Exception as exc:
                logger.warning("Invalid cached archive {}, re-downloading: {}", zip_path.name, exc)
                zip_path.unlink(missing_ok=True)

        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 404:
                    logger.info("No data (404) for {} {} {}-{:02d}", symbol, interval, year, month)
                    return None
                raise

            tmp_path = zip_path.with_suffix(".tmp")
            tmp_path.write_bytes(resp.content)
            tmp_path.replace(zip_path)

            df = self._parse_zip(zip_path)
            self._validate_month_bounds(df, year, month)
            return df

    async def download_range(
        self,
        symbol: str,
        interval: str,
        start: date,
        end: date,
        *,
        progress: bool = True,
    ) -> pd.DataFrame:
        """Download a date range by iterating months.  Concatenates results."""
        months = _month_range(start, end)
        frames: list[pd.DataFrame] = []

        if progress:
            try:
                from tqdm.asyncio import tqdm as atqdm
                months_iter = atqdm(months, desc=f"{symbol}/{interval}", unit="mo")
            except ImportError:
                months_iter = months
        else:
            months_iter = months

        for year, month in months_iter:
            df = await self.download_month(symbol, interval, year, month)
            if df is not None:
                frames.append(df)

        if not frames:
            raise ValueError(f"No data downloaded for {symbol}/{interval} in range {start}–{end}")

        result = pd.concat(frames).sort_index()
        result = result[~result.index.duplicated(keep="last")]
        return result

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _build_url(self, symbol: str, interval: str, year: int, month: int) -> str:
        fname = f"{symbol}-{interval}-{year}-{month:02d}.zip"
        return f"{self._base_url}/data/spot/monthly/klines/{symbol}/{interval}/{fname}"

    def _parse_zip(self, zip_path: Path) -> pd.DataFrame:
        with zipfile.ZipFile(zip_path) as zf:
            csv_names = [n for n in zf.namelist() if n.endswith(".csv")]
            if not csv_names:
                raise ValueError(f"No CSV found in {zip_path}")
            csv_bytes = zf.read(csv_names[0])
        return self._parse_csv(io.BytesIO(csv_bytes))

    @staticmethod
    def _parse_csv(buf: io.BytesIO) -> pd.DataFrame:
        """Parse Binance Vision CSV (12 columns) → standard 5-column OHLCV."""
        col_names = [
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_vol", "count", "taker_buy_base", "taker_buy_quote", "ignore",
        ]
        df = pd.read_csv(
            buf,
            header=None,
            names=col_names,
            dtype={"open": float, "high": float, "low": float, "close": float, "volume": float},
            usecols=["open_time", "open", "high", "low", "close", "volume"],
        )
        unit = _detect_epoch_unit(df["open_time"])
        df["timestamp"] = pd.to_datetime(df["open_time"], unit=unit, utc=True)
        df = df.drop(columns=["open_time"]).set_index("timestamp").sort_index()
        return df

    @staticmethod
    def _validate_month_bounds(df: pd.DataFrame, year: int, month: int) -> None:
        """Ensure downloaded data stays within the requested calendar month."""
        if df.empty:
            raise ValueError("Downloaded month is empty")

        expected_start = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
        if month == 12:
            expected_end = pd.Timestamp(year=year + 1, month=1, day=1, tz="UTC")
        else:
            expected_end = pd.Timestamp(year=year, month=month + 1, day=1, tz="UTC")

        actual_start = df.index.min()
        actual_end = df.index.max()
        if actual_start < expected_start or actual_end >= expected_end:
            raise ValueError(
                "Downloaded data is outside expected month bounds "
                f"({actual_start.isoformat()} → {actual_end.isoformat()}, expected {year}-{month:02d})"
            )


# ── CCXT ─────────────────────────────────────────────────────────────────────


class CCXTDownloader:
    """Download OHLCV data via CCXT async API with rate limiting and retry."""

    def __init__(
        self,
        exchange_id: str = "binance",
        rate_limit_weight: int = 1200,
        max_retries: int = 3,
        backoff_base: float = 2.0,
    ) -> None:
        self._exchange_id = exchange_id
        self._rate_limit_weight = rate_limit_weight
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._weight_used = 0
        self._weight_reset_ts = 0.0

    async def download_range(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        *,
        progress: bool = True,
    ) -> pd.DataFrame:
        """Download OHLCV with pagination, anti-rate-limit, and retry."""
        import ccxt.async_support as ccxt_async

        exchange = getattr(ccxt_async, self._exchange_id)({"enableRateLimit": False})
        try:
            return await self._paginated_download(exchange, symbol, timeframe, start, end, progress)
        finally:
            await exchange.close()

    async def fetch_latest(self, symbol: str, timeframe: str, bars: int = 500) -> pd.DataFrame:
        """Fetch the most recent N bars."""
        import ccxt.async_support as ccxt_async

        exchange = getattr(ccxt_async, self._exchange_id)({"enableRateLimit": False})
        try:
            raw = await self._fetch_with_retry(exchange, symbol, timeframe, since=None, limit=bars)
            return _normalize_ccxt_ohlcv(raw)
        finally:
            await exchange.close()

    # ── Internals ─────────────────────────────────────────────────────────────

    async def _paginated_download(
        self, exchange, symbol: str, timeframe: str, start: datetime, end: datetime, progress: bool,
    ) -> pd.DataFrame:
        import time

        since_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        all_data: list[list] = []
        limit = 1000

        while since_ms < end_ms:
            raw = await self._fetch_with_retry(exchange, symbol, timeframe, since=since_ms, limit=limit)
            if not raw:
                break
            all_data.extend(raw)
            last_ts = raw[-1][0]
            if last_ts <= since_ms:
                break
            since_ms = last_ts + 1

        if not all_data:
            raise ValueError(f"No data from CCXT for {symbol}/{timeframe}")

        df = _normalize_ccxt_ohlcv(all_data)
        end_ts = pd.Timestamp(end, tz="UTC") if end.tzinfo is None else pd.Timestamp(end)
        return df.loc[df.index <= end_ts]

    async def _fetch_with_retry(
        self, exchange, symbol: str, timeframe: str, since: int | None, limit: int,
    ) -> list:
        import time

        for attempt in range(1, self._max_retries + 1):
            await self._respect_rate_limit()
            try:
                data = await exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=limit)
                self._weight_used += 10  # Binance: each klines request ~10 weight
                return data
            except Exception as exc:
                exc_name = type(exc).__name__
                if "RateLimitExceeded" in exc_name or "429" in str(exc):
                    wait = self._backoff_base ** attempt
                    logger.warning("Rate limited, sleeping {} s (attempt {})", wait, attempt)
                    await asyncio.sleep(wait)
                elif attempt == self._max_retries:
                    raise
                else:
                    wait = self._backoff_base ** attempt
                    logger.warning("{}: {} — retrying in {} s", exc_name, exc, wait)
                    await asyncio.sleep(wait)
        return []

    async def _respect_rate_limit(self) -> None:
        import time

        now = time.monotonic()
        if now - self._weight_reset_ts >= 60:
            self._weight_used = 0
            self._weight_reset_ts = now
        if self._weight_used >= self._rate_limit_weight * 0.9:
            sleep_time = 60 - (now - self._weight_reset_ts)
            if sleep_time > 0:
                logger.info("Rate limit approaching, sleeping {:.1f}s", sleep_time)
                await asyncio.sleep(sleep_time)
                self._weight_used = 0
                self._weight_reset_ts = time.monotonic()


# ── Orchestrator ──────────────────────────────────────────────────────────────


class DownloadOrchestrator:
    """Coordinates downloads from multiple sources with incremental logic."""

    def __init__(self, store: ParquetStore, cache_dir: Path, settings: Settings | None = None) -> None:
        self._store = store
        self._settings = settings or Settings()
        self._bv = BinanceVisionDownloader(
            cache_dir=cache_dir,
            base_url=self._settings.binance_vision_base_url,
        )
        self._ccxt = CCXTDownloader(
            exchange_id=self._settings.default_exchange,
            rate_limit_weight=self._settings.download_rate_limit_weight,
            max_retries=self._settings.download_retry_max,
            backoff_base=self._settings.download_retry_backoff,
        )
        self._validator = DataValidator()
        self._alpaca = self._build_alpaca()

    def _build_alpaca(self):
        """Build an AlpacaDownloader if credentials are configured, else ``None``."""
        key = self._settings.alpaca_api_key
        secret = self._settings.alpaca_secret_key
        if not key or not secret:
            return None
        from suitetrading.data.alpaca import AlpacaDownloader

        return AlpacaDownloader(
            api_key=key,
            secret_key=secret,
            asset_class="stock",
            feed=self._settings.alpaca_feed or None,
        )

    async def sync(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        exchange: str = "binance",
        timeframe: str = "1m",
        force: bool = False,
    ) -> dict:
        """Synchronize data for a symbol/timeframe to the store."""
        if exchange == "alpaca":
            return await self._sync_alpaca(symbol, start, end, timeframe=timeframe, force=force)
        return await self._sync_binance(symbol, start, end, exchange=exchange, timeframe=timeframe, force=force)

    async def _sync_alpaca(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        timeframe: str = "1d",
        force: bool = False,
    ) -> dict:
        """Download from Alpaca and store under exchange='alpaca'."""
        if self._alpaca is None:
            raise RuntimeError(
                "Alpaca credentials not configured. "
                "Set ALPACA_API_KEY and ALPACA_SECRET_KEY environment variables."
            )

        tf = normalize_timeframe(timeframe)

        if force:
            missing = _month_range(start, end)
        else:
            missing = self._identify_missing_periods("alpaca", symbol, tf, start, end)

        if not missing:
            logger.info("All periods cached for alpaca/{}/{}", symbol, tf)
            return {"periods_downloaded": 0, "rows_new": 0, "errors": []}

        rows_new = 0
        errors: list[str] = []

        for year, month in missing:
            try:
                month_start = date(year, month, 1)
                if month == 12:
                    month_end = date(year + 1, 1, 1)
                else:
                    month_end = date(year, month + 1, 1)
                # Clamp to requested range
                period_start = max(start, month_start)
                period_end = min(end, month_end)

                df = self._alpaca.download_range(symbol, tf, period_start, period_end)

                if df.empty:
                    continue

                issues = self._validator.validate(df, tf)
                validation_errors = [i for i in issues if i.severity == "error"]
                if validation_errors:
                    msg = f"{year}-{month:02d}: {len(validation_errors)} validation errors, skipping"
                    logger.warning(msg)
                    errors.append(msg)
                    continue

                self._store.write(df, "alpaca", symbol, tf, source="alpaca")
                rows_new += len(df)

            except Exception as exc:
                msg = f"{year}-{month:02d}: {exc}"
                logger.error("Alpaca download failed: {}", msg)
                errors.append(msg)

        return {
            "periods_downloaded": len(missing),
            "rows_new": rows_new,
            "errors": errors,
        }

    async def _sync_binance(
        self,
        symbol: str,
        start: date,
        end: date,
        *,
        exchange: str = "binance",
        timeframe: str = "1m",
        force: bool = False,
    ) -> dict:
        """Original Binance Vision + CCXT sync logic."""
        tf = normalize_timeframe(timeframe)
        binance_tf = tf_to_binance(tf)

        if force:
            missing = _month_range(start, end)
        else:
            missing = self._identify_missing_periods(exchange, symbol, tf, start, end)

        if not missing:
            logger.info("All months cached for {}/{}/{}", exchange, symbol, tf)
            return {"periods_downloaded": 0, "rows_new": 0, "errors": []}

        today = date.today()
        current_month = (today.year, today.month)
        ccxt_symbol = _to_ccxt_symbol(symbol)
        ccxt_tf = tf_to_ccxt(tf)
        rows_new = 0
        errors: list[str] = []

        for year, month in missing:
            try:
                source = "unknown"
                if (year, month) == current_month or binance_tf is None:
                    # Current month or unsupported BV TF → CCXT
                    month_start = datetime(year, month, 1, tzinfo=timezone.utc)
                    if month == 12:
                        month_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc)
                    else:
                        month_end = datetime(year, month + 1, 1, tzinfo=timezone.utc)
                    df = await self._ccxt.download_range(
                        ccxt_symbol, ccxt_tf or tf, month_start, month_end, progress=False,
                    )
                    source = f"ccxt_{self._settings.default_exchange}"
                else:
                    df = await self._bv.download_month(symbol, binance_tf, year, month)
                    source = "binance_vision"

                if df is None or df.empty:
                    continue

                # Validate
                issues = self._validator.validate(df, tf)
                validation_errors = [i for i in issues if i.severity == "error"]
                if validation_errors:
                    msg = f"{year}-{month:02d}: {len(validation_errors)} validation errors, skipping"
                    logger.warning(msg)
                    errors.append(msg)
                    continue

                self._store.write(df, exchange, symbol, tf, source=source)
                rows_new += len(df)

            except Exception as exc:
                msg = f"{year}-{month:02d}: {exc}"
                logger.error("Download failed: {}", msg)
                errors.append(msg)

        return {
            "periods_downloaded": len(missing),
            "rows_new": rows_new,
            "errors": errors,
        }

    async def sync_all(
        self,
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        *,
        exchange: str = "binance",
    ) -> list[dict]:
        """Sync all configured symbols for the given exchange."""
        if exchange == "alpaca":
            symbols = symbols or self._settings.alpaca_symbols
        else:
            symbols = symbols or self._settings.default_symbols
        start = start or date(2017, 8, 1)
        end = end or date.today()
        results = []
        for sym in symbols:
            report = await self.sync(sym, start, end, exchange=exchange)
            results.append({"symbol": sym, **report})
        return results

    def _identify_missing_periods(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: date,
        end: date,
    ) -> list[tuple[int, int]]:
        """Return ``(year, month)`` tuples for missing periods.

        For intraday TFs checks ``YYYY-MM.parquet`` files;
        for daily+ TFs checks ``YYYY.parquet`` files but still returns
        ``(year, 1)`` tuples so the download loop can work uniformly.
        """
        data_dir = self._store._base_dir / exchange / symbol / timeframe
        existing_files = set()
        if data_dir.exists():
            existing_files = {fp.stem for fp in data_dir.glob("*.parquet")}

        if is_intraday(timeframe):
            all_months = _month_range(start, end)
            return [(y, m) for y, m in all_months if f"{y}-{m:02d}" not in existing_files]

        # daily+ → yearly partitions
        all_years = _year_range(start, end)
        missing_months: list[tuple[int, int]] = []
        for yr in all_years:
            if str(yr) not in existing_files:
                # Expand into months so the download loop processes this year
                yr_start = max(start, date(yr, 1, 1))
                yr_end = min(end, date(yr, 12, 31))
                missing_months.extend(_month_range(yr_start, yr_end))
        return missing_months

    # Keep old name as alias for backward compat in tests
    _identify_missing_months = _identify_missing_periods


# ── Module-level helpers ────────────────────────────────────────────────────


def _normalize_ccxt_ohlcv(raw: list[list]) -> pd.DataFrame:
    """Convert raw CCXT list-of-lists to standard OHLCV DataFrame."""
    df = pd.DataFrame(raw, columns=["timestamp_ms", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    df = df.drop(columns=["timestamp_ms"]).set_index("timestamp").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    return df


def _detect_epoch_unit(values: pd.Series) -> str:
    """Infer epoch unit from magnitude.

    Binance Vision switched some archives from millisecond to microsecond
    timestamps, so parsing must be tolerant to both.
    """
    sample = values.dropna()
    if sample.empty:
        return "ms"

    magnitude = int(abs(int(sample.iloc[0])))
    if magnitude >= 1_000_000_000_000_000_000:
        return "ns"
    if magnitude >= 1_000_000_000_000_000:
        return "us"
    return "ms"


def _to_ccxt_symbol(symbol: str) -> str:
    """Convert exchange symbol like ``BTCUSDT`` to CCXT format ``BTC/USDT``.

    Handles common quote currencies: USDT, BUSD, USDC, BTC, ETH, BNB.
    """
    if "/" in symbol:
        return symbol  # already CCXT format
    for quote in ("USDT", "BUSD", "USDC", "TUSD", "BTC", "ETH", "BNB"):
        if symbol.endswith(quote):
            base = symbol[: -len(quote)]
            if base:
                return f"{base}/{quote}"
    return symbol  # fallback: return as-is


def _year_range(start: date, end: date) -> list[int]:
    """Generate list of years between *start* and *end* inclusive."""
    return list(range(start.year, end.year + 1))


def _month_range(start: date, end: date) -> list[tuple[int, int]]:
    """Generate list of ``(year, month)`` between *start* and *end* inclusive."""
    months: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        months.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return months
