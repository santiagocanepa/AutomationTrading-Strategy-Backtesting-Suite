# Sprint 1 — Data Infrastructure: Technical Specification

> Contratos de API, schemas de datos, algoritmos de resampling, y reglas de
> validación. Este documento es la referencia para implementación — cada función
> pública debe coincidir con la firma aquí definida.

---

## 1. Data Schema: OHLCV Parquet

### 1.1 Columnas y Tipos

| Column | Arrow Type | Pandas Type | Nullable | Description |
|--------|-----------|-------------|----------|-------------|
| `timestamp` | `timestamp[ms, tz=UTC]` | `DatetimeIndex` | No | Apertura de la barra (inclusive) |
| `open` | `float64` | `float64` | No | Precio de apertura |
| `high` | `float64` | `float64` | No | Precio máximo |
| `low` | `float64` | `float64` | No | Precio mínimo |
| `close` | `float64` | `float64` | No | Precio de cierre |
| `volume` | `float64` | `float64` | No | Volumen base asset |

### 1.2 Metadata del Parquet

Cada archivo Parquet incluye metadata custom en el footer:

```python
metadata = {
    b"exchange": b"binance",
    b"symbol": b"BTCUSDT",
    b"timeframe": b"1m",
    b"source": b"binance_vision",        # o "ccxt"
    b"download_timestamp": b"2026-03-15T10:00:00Z",
    b"rows": b"525600",
    b"date_min": b"2024-01-01T00:00:00Z",
    b"date_max": b"2024-12-31T23:59:00Z",
}
```

### 1.3 Convenciones de Timestamp

- **Todo en UTC**. Sin excepciones.
- Timestamp = **apertura** de la barra (convención Binance y la mayoría de exchanges)
- Para 1m: `2024-01-15 14:30:00 UTC` = barra de 14:30:00 a 14:30:59.999
- Para 1H: `2024-01-15 14:00:00 UTC` = barra de 14:00 a 14:59:59.999
- Para 1D: `2024-01-15 00:00:00 UTC` = barra del día 15 completo
- Para 1W: lunes 00:00:00 UTC del inicio de la semana

### 1.4 Particionado en Disco

```
{processed_data_dir}/
  binance/
    BTCUSDT/
      1m/
        2024-01.parquet    # Enero 2024 completo
        2024-02.parquet
        ...
      3m/
        2024-01.parquet    # Generado por resampling
        ...
      1h/
        2024-01.parquet
      1d/
        2024.parquet       # Para D/W/M: particionado anual (pocos rows)
    ETHUSDT/
      ...
    SOLUSDT/
      ...
```

**Regla de particionado**:
- 1m → 5m: mensual (`YYYY-MM.parquet`)
- 15m → 4h: mensual (`YYYY-MM.parquet`)
- 1d → 1M: anual (`YYYY.parquet`)

---

## 2. Module API: `storage.py`

### 2.1 ParquetStore

```python
from pathlib import Path
from datetime import datetime

import pandas as pd


class ParquetStore:
    """Read/write OHLCV data as partitioned Parquet files.

    Thread-safe for reads. Writes are not concurrent-safe (single writer
    assumed — the download pipeline is sequential per symbol/tf).
    """

    def __init__(self, base_dir: Path, compression: str = "zstd", compression_level: int = 3):
        """
        Parameters
        ----------
        base_dir : Path
            Root directory for partitioned data (e.g. ./data/processed).
        compression : str
            Parquet compression codec: "zstd", "snappy", "lz4", "none".
        compression_level : int
            Compression level (only for zstd, 1-22).
        """

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

        - Validates schema before writing (raises ValueError if invalid)
        - Deduplicates by timestamp (keeps last)
        - Sorts by timestamp ascending
        - Splits into partition files automatically
        - Overwrites existing partition files if date ranges overlap

        Returns list of written file paths.
        """

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

        - Returns DataFrame with DatetimeIndex (UTC)
        - If start/end are None, reads all available data
        - Supports column projection (e.g. only ["close", "volume"])
        - Raises FileNotFoundError if no data exists for the query
        """

    def list_available(self) -> list[dict]:
        """Return inventory of all stored datasets.

        Returns list of dicts:
            [{"exchange": "binance", "symbol": "BTCUSDT", "timeframe": "1m",
              "date_min": datetime, "date_max": datetime, "rows": int}, ...]
        """

    def info(self, exchange: str, symbol: str, timeframe: str) -> dict:
        """Return metadata for a specific dataset.

        Returns:
            {"date_min": datetime, "date_max": datetime, "rows": int,
             "size_mb": float, "gaps": list[tuple[datetime, datetime]],
             "source": str}
        """

    def _partition_path(self, exchange: str, symbol: str, timeframe: str, period: str) -> Path:
        """Resolve file path for a partition period (e.g. '2024-01' or '2024')."""

    def _detect_partition_scheme(self, timeframe: str) -> str:
        """Return 'monthly' for intraday TFs, 'yearly' for daily+."""
```

---

## 3. Module API: `downloader.py`

### 3.1 Binance Vision Downloader

```python
from pathlib import Path
from datetime import date

import pandas as pd


class BinanceVisionDownloader:
    """Download historical klines from Binance Vision bulk data.

    Binance Vision serves pre-generated CSV files per month:
    https://data.binance.vision/data/spot/monthly/klines/{symbol}/{interval}/{symbol}-{interval}-{YYYY-MM}.zip

    Each ZIP contains a single CSV with columns:
    [open_time, open, high, low, close, volume, close_time,
     quote_volume, count, taker_buy_base, taker_buy_quote, ignore]
    """

    def __init__(self, cache_dir: Path, base_url: str = "https://data.binance.vision"):
        """
        Parameters
        ----------
        cache_dir : Path
            Directory to cache downloaded ZIP files (avoid re-downloads).
        base_url : str
            Binance Vision base URL.
        """

    async def download_month(
        self,
        symbol: str,
        interval: str,
        year: int,
        month: int,
    ) -> pd.DataFrame | None:
        """Download a single month of kline data.

        - Downloads ZIP, extracts CSV, parses to DataFrame
        - Caches ZIP locally (skip if already cached)
        - Returns None if the file doesn't exist (pair didn't exist yet)
        - Normalizes columns to standard OHLCV schema
        - Converts timestamps to UTC datetime
        """

    async def download_range(
        self,
        symbol: str,
        interval: str,
        start: date,
        end: date,
        *,
        progress: bool = True,
    ) -> pd.DataFrame:
        """Download a date range by iterating over months.

        - Skips months already in cache
        - Concatenates all months into a single DataFrame
        - Validates: no gaps between months, no duplicates
        - Shows progress bar if progress=True
        """

    def _build_url(self, symbol: str, interval: str, year: int, month: int) -> str:
        """Build download URL for a specific month."""

    def _parse_csv(self, csv_path: Path) -> pd.DataFrame:
        """Parse Binance Vision CSV to standard OHLCV DataFrame."""
```

### 3.2 CCXT Downloader

```python
import ccxt.async_support as ccxt_async


class CCXTDownloader:
    """Download OHLCV data via CCXT async API.

    Handles rate limiting, pagination, and normalization across exchanges.
    """

    def __init__(
        self,
        exchange_id: str = "binance",
        rate_limit_weight: int = 1200,
        max_retries: int = 3,
        backoff_base: float = 2.0,
    ):
        """
        Parameters
        ----------
        exchange_id : str
            CCXT exchange ID (e.g. "binance", "bybit", "okx").
        rate_limit_weight : int
            Max API weight per minute (Binance default: 1200).
        max_retries : int
            Max retry attempts for transient errors.
        backoff_base : float
            Exponential backoff multiplier.
        """

    async def download_range(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        *,
        progress: bool = True,
    ) -> pd.DataFrame:
        """Download OHLCV data for a date range with pagination.

        - Uses `fetch_ohlcv(symbol, timeframe, since, limit)` in a loop
        - Handles pagination via `since` parameter (last timestamp + 1ms)
        - Respects rate limits with weight tracking + sleep
        - Retries transient errors with exponential backoff
        - Returns standard OHLCV DataFrame with DatetimeIndex (UTC)
        """

    async def fetch_latest(self, symbol: str, timeframe: str, bars: int = 500) -> pd.DataFrame:
        """Fetch the most recent N bars (for incremental updates)."""

    async def _fetch_with_retry(self, symbol: str, timeframe: str, since: int, limit: int) -> list:
        """Single fetch with retry logic and rate limit tracking."""
```

### 3.3 Download Orchestrator

```python
class DownloadOrchestrator:
    """Coordinates downloads from multiple sources with incremental logic.

    Strategy:
    1. Check what's already in ParquetStore
    2. For missing historical months: use BinanceVisionDownloader
    3. For recent data (current month) or gaps: use CCXTDownloader
    4. Validate and store results
    """

    def __init__(self, store: ParquetStore, cache_dir: Path, settings: Settings): ...

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
        """Synchronize data for a symbol/timeframe to the store.

        Returns dict with sync report:
            {"months_downloaded": 5, "months_cached": 31, "rows_new": 2_500_000,
             "gaps_found": 2, "duration_seconds": 45.2}
        """

    async def sync_all(
        self,
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> list[dict]:
        """Sync all configured symbols. Uses settings.default_symbols if None."""

    def _identify_missing_months(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        start: date,
        end: date,
    ) -> list[tuple[int, int]]:
        """Return list of (year, month) tuples not yet in store."""
```

---

## 4. Module API: `resampler.py`

### 4.1 OHLCV Resampler

```python
class OHLCVResampler:
    """Resample 1m OHLCV data to higher timeframes.

    Replaces the stub and extends the existing mtf.py with data-layer
    awareness (loading from store, caching, validation).
    """

    # Canonical mapping: timeframe string → pandas offset alias
    TF_TO_OFFSET: ClassVar[dict[str, str]] = {
        "1m": "1min",    "3m": "3min",   "5m": "5min",
        "15m": "15min",  "30m": "30min", "45m": "45min",
        "1h": "1h",      "4h": "4h",
        "1d": "1D",      "1w": "1W-MON", "1M": "1ME",
    }

    def resample(self, df_base: pd.DataFrame, target_tf: str) -> pd.DataFrame:
        """Resample a base-TF DataFrame to target_tf.

        Parameters
        ----------
        df_base : pd.DataFrame
            OHLCV with DatetimeIndex at base TF (must be sorted ascending).
        target_tf : str
            Target timeframe key (e.g. "4h", "1d").

        Returns
        -------
        pd.DataFrame
            Resampled OHLCV. Incomplete trailing bars are dropped.

        Raises
        ------
        ValueError
            If target_tf is lower than or equal to base TF.
            If df_base has gaps that would corrupt aggregation.
        """

    def resample_all(
        self,
        df_1m: pd.DataFrame,
        target_tfs: list[str] | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Resample 1m data to all target timeframes.

        Returns dict: {"3m": df_3m, "5m": df_5m, ...}
        Default target_tfs = all TFs except "1m".
        """

    def validate_against_native(
        self,
        resampled: pd.DataFrame,
        native: pd.DataFrame,
        tolerance_pct: float = 0.01,
    ) -> dict:
        """Compare resampled data against native exchange data.

        Returns:
            {
                "rows_compared": 8760,
                "ohlc_max_diff_pct": 0.002,
                "volume_exact_match": True,
                "mismatches": [  # only if any
                    {"timestamp": ..., "column": "high",
                     "resampled": 45123.5, "native": 45123.4, "diff_pct": 0.0002},
                ],
                "passed": True,
            }
        """

    @staticmethod
    def _agg_rules() -> dict[str, str]:
        """Return standard OHLCV aggregation rules."""
        return {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
```

### 4.2 WarmupCalculator

```python
from datetime import timedelta


class WarmupCalculator:
    """Calculate minimum warmup period for a set of indicators.

    The warmup is the number of bars (at each indicator's operating TF)
    before the backtest start where data must be available for indicator
    values to be stable.
    """

    # Known indicator warmup requirements (bars at their operating TF)
    INDICATOR_WARMUP: ClassVar[dict[str, int]] = {
        "ema_200": 250,
        "sma_600": 700,
        "rsi_14": 20,
        "macd_26_9": 40,
        "bollinger_50": 60,
        "atr_14": 20,
        "firestorm_50": 60,
        "wavetrend_30_12_3": 60,
        "squeeze_20": 50,
        "ssl_channel_50": 60,
        "vwap": 50,
    }

    def calculate(
        self,
        indicators: list[dict],
        base_tf: str,
    ) -> timedelta:
        """Calculate total warmup as timedelta from backtest start.

        Parameters
        ----------
        indicators : list[dict]
            Each dict: {"name": str, "params": dict, "timeframe": str}
            Example: {"name": "ema", "params": {"period": 200}, "timeframe": "4h"}
        base_tf : str
            The chart's base timeframe (e.g. "1h").

        Returns
        -------
        timedelta
            How far back from backtest_start we need data.
            This accounts for both the indicator period AND the TF conversion.
        """

    @staticmethod
    def _tf_to_timedelta(tf: str, bars: int) -> timedelta:
        """Convert N bars of a timeframe to a timedelta."""
```

---

## 5. Module API: `validator.py`

### 5.1 DataValidator

```python
from dataclasses import dataclass


@dataclass
class ValidationIssue:
    """A single data quality issue found during validation."""
    severity: str              # "error", "warning", "info"
    issue_type: str            # "gap", "duplicate", "ohlcv_invalid", "volume_zero", ...
    timestamp: datetime | None # Where the issue occurs (None for global issues)
    description: str           # Human-readable description
    affected_rows: int         # Number of rows affected


class DataValidator:
    """Validate OHLCV data quality and generate reports."""

    def validate(self, df: pd.DataFrame, expected_tf: str) -> list[ValidationIssue]:
        """Run all validation checks on an OHLCV DataFrame.

        Checks (in order):
        1. Schema: required columns present, correct dtypes
        2. Timestamps: sorted, UTC, no duplicates
        3. Gaps: missing bars based on expected_tf interval
        4. OHLCV logic: high >= max(open, close), low <= min(open, close)
        5. Volume: non-negative, not all zeros
        6. Outliers: price changes > 50% in a single bar (warning)

        Returns list of ValidationIssue sorted by severity.
        """

    def detect_gaps(
        self,
        df: pd.DataFrame,
        expected_tf: str,
        *,
        ignore_weekends: bool = False,
    ) -> pd.DataFrame:
        """Detect gaps in the time series.

        Returns DataFrame with columns:
            gap_start, gap_end, duration, missing_bars

        For crypto (24/7): ignore_weekends=False (default).
        """

    def fill_gaps(
        self,
        df: pd.DataFrame,
        expected_tf: str,
        method: str = "ffill",
    ) -> tuple[pd.DataFrame, int]:
        """Fill detected gaps in OHLCV data.

        Methods:
        - "ffill": Forward-fill OHLC from last known bar, volume=0
        - "mark": Insert rows with NaN values (for downstream filtering)

        Returns (filled_df, num_bars_filled).
        """

    def generate_report(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
    ) -> dict:
        """Generate a comprehensive quality report.

        Returns:
            {
                "exchange": "binance", "symbol": "BTCUSDT", "timeframe": "1m",
                "date_range": {"start": ..., "end": ...},
                "total_rows": 1_576_800,
                "expected_rows": 1_576_800,
                "completeness_pct": 99.97,
                "gaps": [{"start": ..., "end": ..., "bars": 42}],
                "issues": [...],
                "ohlcv_valid_pct": 100.0,
                "volume_zero_pct": 0.02,
            }
        """
```

---

## 6. Algoritmo de Resampling: Especificación Exacta

### 6.1 Reglas de Agregación

```
Para cada barra del TF superior que contiene N barras del TF base:

open  = df_base["open"].iloc[0]       # Primera barra del grupo
high  = df_base["high"].max()         # Máximo de todas las barras
low   = df_base["low"].min()          # Mínimo de todas las barras
close = df_base["close"].iloc[-1]     # Última barra del grupo
volume = df_base["volume"].sum()      # Suma total
```

### 6.2 Alineación Temporal

```
Timeframe    Alineación de barras
─────────    ────────────────────
3m           00:00, 00:03, 00:06, ...    (múltiplos de 3 desde midnight UTC)
5m           00:00, 00:05, 00:10, ...
15m          00:00, 00:15, 00:30, 00:45
30m          00:00, 00:30
45m          00:00, 00:45, 01:30, ...    (NOTA: no alineado a hora completa)
1h           00:00, 01:00, 02:00, ...
4h           00:00, 04:00, 08:00, 12:00, 16:00, 20:00
1d           00:00 UTC (midnight to midnight)
1w           Lunes 00:00 UTC
1M           Día 1 00:00 UTC
```

### 6.3 Barras Incompletas

- La **última barra** del dataset puede estar incompleta (mes actual, hora actual)
- Regla: **drop** barras incompletas en el resampling
- Detección: si el número de barras base en el grupo < esperado, es incompleta
- Excepción: 1M siempre tiene barras de diferente longitud (28-31 días)

### 6.4 Caso Especial: 45m

45 minutos **no es divisor de 60**, lo que causa alineación no-estándar:

```
00:00 → 00:45 → 01:30 → 02:15 → 03:00 → 03:45 → ...
```

- Binance no ofrece 45m nativo
- TradingView sí lo soporta
- Implementación: `pd.DataFrame.resample("45min")` con `origin="epoch"`
- Validación: no hay dato nativo contra el cual comparar — confiar en pandas

### 6.5 Forward-Fill para MTF Signals

Cuando un indicador opera en TF superior y necesita alinearse al TF base:

```python
# Ejemplo: SMA(close, 50) en 4H, base TF = 1m
sma_4h = compute_sma(df_4h["close"], 50)      # Series con index cada 4H

# Alinear a 1m:
sma_1m = sma_4h.reindex(df_1m.index, method="ffill")

# Resultado: cada barra de 1m tiene el valor del SMA del último 4H bar cerrado
# Barra 1m 14:37 → usa el SMA del 4H bar 12:00 (no 16:00 = no look-ahead)
```

**Crítico**: `method="ffill"` garantiza no forward-looking. El valor de un HTF
bar solo se propaga **después** de que ese bar cierra.

---

## 7. Binance Vision: Formato de CSV

### 7.1 Columnas del CSV

```
open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_base,taker_buy_quote,ignore
1704067200000,42283.88000000,42295.74000000,42277.16000000,42293.72000000,33.48767000,1704067259999,1416298.17891180,1298,20.47651000,866050.13990580,0
```

| # | Column | Type | Uso |
|---|--------|------|-----|
| 0 | `open_time` | int (ms epoch) | → `timestamp` (DatetimeIndex) |
| 1 | `open` | string (float) | → `open` |
| 2 | `high` | string (float) | → `high` |
| 3 | `low` | string (float) | → `low` |
| 4 | `close` | string (float) | → `close` |
| 5 | `volume` | string (float) | → `volume` (base asset) |
| 6 | `close_time` | int (ms epoch) | Descartado (redundante) |
| 7 | `quote_volume` | string (float) | Descartado (no usado por indicadores) |
| 8 | `count` | int | Descartado |
| 9 | `taker_buy_base` | string (float) | Descartado |
| 10 | `taker_buy_quote` | string (float) | Descartado |
| 11 | `ignore` | int | Descartado |

### 7.2 Parsing

```python
def parse_binance_vision_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(
        path,
        header=None,
        names=["open_time","open","high","low","close","volume",
               "close_time","quote_vol","count","taker_buy_base","taker_buy_quote","ignore"],
        dtype={"open": float, "high": float, "low": float, "close": float, "volume": float},
        usecols=["open_time", "open", "high", "low", "close", "volume"],
    )
    df["timestamp"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.drop(columns=["open_time"]).set_index("timestamp").sort_index()
    return df
```

---

## 8. CCXT: Normalización

### 8.1 Formato de Respuesta

```python
# ccxt.fetch_ohlcv() devuelve:
[
    [1704067200000, 42283.88, 42295.74, 42277.16, 42293.72, 33.48767],
    # [timestamp_ms, open, high, low, close, volume]
]
```

### 8.2 Normalización

```python
def normalize_ccxt_ohlcv(raw: list[list], symbol: str) -> pd.DataFrame:
    df = pd.DataFrame(raw, columns=["timestamp_ms", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)
    df = df.drop(columns=["timestamp_ms"]).set_index("timestamp").sort_index()
    df = df.drop_duplicates()  # CCXT puede devolver dupes en boundaries de página
    return df
```

### 8.3 Paginación

```python
# CCXT limit per request: típicamente 1000 (Binance) o 500 (Bybit)
# Para 1m, 1000 bars = ~16.6 horas
# Para 1 mes de 1m: ~44,640 bars → ~45 requests
# Para 1 año de 1m: ~525,600 bars → ~526 requests

# Paginación:
since = start_timestamp_ms
while since < end_timestamp_ms:
    ohlcv = await exchange.fetch_ohlcv(symbol, timeframe, since=since, limit=1000)
    if not ohlcv:
        break
    since = ohlcv[-1][0] + 1  # +1ms para evitar duplicado del último bar
    all_data.extend(ohlcv)
```

---

## 9. Intervalos y Mapeo de Timeframes

### 9.1 Mapeo Unificado

El proyecto usa múltiples convenciones de TF. Esta tabla es la **fuente de verdad**:

| Internal Key | Pine Script | Binance API | CCXT | Pandas Offset | Seconds |
|-------------|-------------|-------------|------|---------------|---------|
| `1m` | `"1"` | `1m` | `1m` | `1min` | 60 |
| `3m` | `"3"` | `3m` | `3m` | `3min` | 180 |
| `5m` | `"5"` | `5m` | `5m` | `5min` | 300 |
| `15m` | `"15"` | `15m` | `15m` | `15min` | 900 |
| `30m` | `"30"` | `30m` | `30m` | `30min` | 1800 |
| `45m` | `"45"` | N/A | N/A | `45min` | 2700 |
| `1h` | `"60"` | `1h` | `1h` | `1h` | 3600 |
| `4h` | `"240"` | `4h` | `4h` | `4h` | 14400 |
| `1d` | `"D"` | `1d` | `1d` | `1D` | 86400 |
| `1w` | `"W"` | `1w` | `1w` | `1W-MON` | 604800 |
| `1M` | `"M"` | `1M` | `1M` | `1ME` | variable |

### 9.2 Función de Conversión

```python
def normalize_timeframe(tf: str) -> str:
    """Convert any TF representation to internal key.

    Examples: "60" → "1h", "240" → "4h", "D" → "1d", "W" → "1w"
    """
    ALIASES = {
        "1": "1m", "3": "3m", "5": "5m", "15": "15m", "30": "30m",
        "45": "45m", "60": "1h", "240": "4h",
        "D": "1d", "W": "1w", "M": "1M",
    }
    return ALIASES.get(tf, tf)
```

---

## 10. Validación: Reglas Completas

### 10.1 Schema Validation

```python
REQUIRED_COLUMNS = {"open", "high", "low", "close", "volume"}
REQUIRED_DTYPES = {
    "open": "float64", "high": "float64", "low": "float64",
    "close": "float64", "volume": "float64",
}
# Index must be DatetimeIndex with tz=UTC
```

### 10.2 Timestamp Validation

```python
# 1. Sorted ascending (no exception)
assert df.index.is_monotonic_increasing

# 2. No duplicates
assert not df.index.duplicated().any()

# 3. Timezone = UTC
assert str(df.index.tz) == "UTC"

# 4. No future timestamps
assert df.index.max() <= pd.Timestamp.now("UTC")
```

### 10.3 OHLCV Logic Validation

```python
# Per row:
assert (df["high"] >= df["open"]).all()
assert (df["high"] >= df["close"]).all()
assert (df["high"] >= df["low"]).all()
assert (df["low"] <= df["open"]).all()
assert (df["low"] <= df["close"]).all()
assert (df["volume"] >= 0).all()

# Warn if:
# - volume == 0 for more than 1% of rows
# - price change > 50% in a single bar (likely error or extreme event)
```

### 10.4 Gap Detection

```python
expected_interval = pd.Timedelta(TF_TO_OFFSET[timeframe])
actual_gaps = df.index.to_series().diff()
gaps = actual_gaps[actual_gaps > expected_interval * 1.5]  # 1.5x tolerance
# Report: timestamp, duration, missing_bars count
```

### 10.5 Cross-Source Validation (Resampling Check)

```python
# Compare resampled vs native:
merged = resampled.join(native, lsuffix="_res", rsuffix="_nat")

for col in ["open", "high", "low", "close"]:
    diff_pct = abs(merged[f"{col}_res"] - merged[f"{col}_nat"]) / merged[f"{col}_nat"] * 100
    assert diff_pct.max() < 0.01, f"{col}: max diff {diff_pct.max():.4f}%"

# Volume must match exactly (sum is deterministic)
assert (merged["volume_res"] == merged["volume_nat"]).all()
```

---

## 11. Error Handling

### 11.1 Download Errors

| Error | Handling | Retry? |
|-------|----------|--------|
| HTTP 404 (file not found) | Log + return None (pair didn't exist) | No |
| HTTP 429 (rate limit) | Sleep exponential backoff, retry | Yes (max 3) |
| HTTP 500/502/503 | Log + backoff + retry | Yes (max 3) |
| Connection timeout | Backoff + retry | Yes (max 3) |
| Corrupt ZIP/CSV | Log error, skip month, report in sync result | No |
| Disk full | Raise immediately (critical) | No |

### 11.2 Storage Errors

| Error | Handling |
|-------|----------|
| Schema mismatch on write | Raise `ValueError` with details |
| File locked (concurrent write) | Raise `IOError` — single writer assumed |
| Corrupt Parquet on read | Log warning, attempt recovery from cache |
| Missing partition files | Return partial data + log warning |

### 11.3 Validation Errors

| Severity | Action |
|----------|--------|
| `error` (schema fail, OHLCV invalid) | Raise exception — data is unusable |
| `warning` (gaps, zero volume, outliers) | Log + include in report — data is usable with caution |
| `info` (minor: timezone mismatch fixed) | Log only |
