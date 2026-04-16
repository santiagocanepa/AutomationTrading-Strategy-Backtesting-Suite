# Data Module

## Overview
- Download, validate, store, and resample OHLCV data from crypto (Binance Vision, CCXT) and stocks (Alpaca), plus macro overlays (FRED, cross-asset ETFs, Binance Futures).
- All data persists as partitioned Parquet files under `data/raw/{exchange}/{symbol}/{timeframe}/{period}.parquet`.
- Single source of truth for timeframe representations: `timeframes.py` maps between internal keys, Binance, CCXT, Alpaca, pandas, and Pine Script.

---

## Files

| File | Responsibility | LOC |
|------|---------------|-----|
| `downloader.py` | `BinanceVisionDownloader`, `CCXTDownloader`, `DownloadOrchestrator` — bulk CSV + async API download | 614 |
| `alpaca.py` | `AlpacaDownloader` — stock/crypto bars via alpaca-py SDK | 191 |
| `storage.py` | `ParquetStore` — read/write/list OHLCV as partitioned Parquet | 311 |
| `resampler.py` | `OHLCVResampler` — resample 1m base to any higher TF | 161 |
| `validator.py` | `DataValidator` — schema, gap, OHLCV logic, outlier checks | 308 |
| `warmup.py` | `WarmupCalculator` — compute indicator warmup as `timedelta` | 87 |
| `timeframes.py` | `TIMEFRAME_MAP`, `normalize_timeframe`, conversion helpers | 115 |
| `cross_asset.py` | `CrossAssetDownloader` — macro ETFs (HYG, LQD, UUP, IEF) via yfinance | 73 |
| `fred.py` | `FREDDownloader` — VIX, yield curve, credit spreads via FRED API | 97 |
| `futures.py` | `BinanceFuturesDownloader` — funding rate, open interest, L/S ratio | 322 |
| `macro_cache.py` | `MacroCacheManager` — local Parquet cache + staleness tracking for macro data | 197 |
| `__init__.py` | Public re-exports | 32 |

---

## Key Classes

```python
class DownloadOrchestrator:
    def __init__(self, store: ParquetStore, cache_dir: Path, settings: Settings | None = None)
    async def sync(self, symbol: str, start: date, end: date, *, exchange: str = "binance", timeframe: str = "1m", force: bool = False) -> dict
    async def sync_all(self, symbols: list[str] | None, start: date | None, end: date | None, *, exchange: str = "binance") -> list[dict]

class ParquetStore:
    def __init__(self, base_dir: Path, compression: str = "zstd", compression_level: int = 3)
    def write(self, df: pd.DataFrame, exchange: str, symbol: str, timeframe: str, *, source: str = "unknown") -> list[Path]
    def read(self, exchange: str, symbol: str, timeframe: str, start: datetime | None, end: datetime | None, columns: list[str] | None) -> pd.DataFrame
    def list_available(self) -> list[dict]
    def info(self, exchange: str, symbol: str, timeframe: str) -> dict

class DataValidator:
    def validate(self, df: pd.DataFrame, expected_tf: str) -> list[ValidationIssue]
    def detect_gaps(self, df: pd.DataFrame, expected_tf: str, *, ignore_weekends: bool = False) -> pd.DataFrame
    def fill_gaps(self, df: pd.DataFrame, expected_tf: str, method: str = "ffill") -> tuple[pd.DataFrame, int]
    def generate_report(self, exchange: str, symbol: str, timeframe: str, df: pd.DataFrame) -> dict

class OHLCVResampler:
    def resample(self, df_base: pd.DataFrame, target_tf: str, *, base_tf: str = "1m") -> pd.DataFrame
    def resample_all(self, df_1m: pd.DataFrame, target_tfs: list[str] | None = None, *, base_tf: str = "1m") -> dict[str, pd.DataFrame]
    @staticmethod
    def validate_against_native(resampled: pd.DataFrame, native: pd.DataFrame, tolerance_pct: float = 0.01) -> dict

class MacroCacheManager:
    def __init__(self, cache_dir: Path | str = Path("data/raw/macro"))
    def get(self, key: str, max_age_days: int = 1) -> pd.Series | pd.DataFrame | None
    def put(self, key: str, data: pd.Series | pd.DataFrame) -> Path
    def refresh_fred(self, downloader: FREDDownloader, *, keys: list[str] | None, force: bool, start: str | None, max_age_days: int) -> dict[str, Path]
    def get_aligned(self, keys: list[str], index: pd.DatetimeIndex) -> pd.DataFrame
```

---

## Data Sources

| Source | Class | Assets | Symbols / Series | Format |
|--------|-------|--------|-----------------|--------|
| Binance Vision bulk CSV | `BinanceVisionDownloader` | Crypto spot | Any USDT/BUSD/BTC pair | ZIP→CSV, 12 cols → OHLCV |
| Binance CCXT API | `CCXTDownloader` | Crypto (any CCXT exchange) | Any pair, auto-paginates | JSON list-of-lists |
| Alpaca Markets | `AlpacaDownloader` | Stocks + crypto | Configured via `ALPACA_SYMBOLS` | alpaca-py BarSet |
| Binance Futures API | `BinanceFuturesDownloader` | Crypto derivatives | BTCUSDT, ETHUSDT, … | REST JSON (no key needed) |
| FRED | `FREDDownloader` | Macro | VIX, DGS10, DGS2, T10Y2Y, T10Y3M, BAMLH0A0HYM2, BAMLC0A0CM, DTWEXBGS | fredapi Series |
| yfinance | `CrossAssetDownloader` | ETFs | HYG, LQD, UUP, IEF | yfinance OHLCV |

---

## Storage

`ParquetStore` layout:
```
data/raw/
└── {exchange}/          # "binance", "alpaca"
    └── {symbol}/        # "BTCUSDT", "AAPL"
        └── {timeframe}/ # "1m", "1h", "1d"
            ├── 2023-01.parquet   # intraday TFs (≤4h) → monthly partitions
            ├── 2023-02.parquet
            └── 2023.parquet      # daily+ TFs → yearly partitions
```

- **Partition scheme**: `monthly` for TFs ≤ 4h; `yearly` for 1d/1w/1M.
- **Compression**: zstd level 3 (configurable).
- **Index**: `timestamp` column stored as Arrow TimestampType (UTC), restored as `DatetimeIndex` on read.
- **Metadata** per file: `exchange`, `symbol`, `timeframe`, `source`, `download_timestamp`, `rows`, `date_min`, `date_max`.
- **Write**: deduplicates on timestamp (keeps last), sorts ascending, overwrites existing partition if overlap.
- **Read**: glob all `.parquet` in dir, concat + deduplicate, filter by `start`/`end`.
- **Schema contract**: `open`, `high`, `low`, `close`, `volume` must be `float64`; index must be UTC `DatetimeIndex`.

---

## Tests

```bash
# From suitetrading/
pytest tests/data/ -v

# Single file
pytest tests/data/test_storage.py -v
pytest tests/data/test_validator.py -v
pytest tests/data/test_downloader.py -v
```

Test files: `test_downloader.py`, `test_storage.py`, `test_validator.py`, `test_resampler.py`, `test_alpaca.py`, `test_warmup.py`, `test_timeframes.py`, `test_fred.py`, `test_cross_asset.py`, `test_macro_cache.py`, `test_integration.py`, `test_benchmarks.py`, `test_cross_validate_native.py`.
