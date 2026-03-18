"""Download historical klines for all configured symbols.

Usage::

    python -m scripts.download_data [--symbols BTCUSDT ETHUSDT] [--start 2017-08-01]

Downloads 1m base data from BinanceVision + CCXT (current month),
then stores in partitioned Parquet.
"""

from __future__ import annotations

import argparse
import asyncio
import fcntl
import sys
from datetime import date
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from suitetrading.config.settings import Settings
from suitetrading.data.downloader import DownloadOrchestrator
from suitetrading.data.storage import ParquetStore


SYMBOL_START_DATES: dict[str, date] = {
    "BTCUSDT": date(2017, 8, 17),
    "ETHUSDT": date(2017, 8, 17),
    "SOLUSDT": date(2020, 8, 11),
    "BNBUSDT": date(2017, 11, 6),
    "AVAXUSDT": date(2020, 9, 22),
    "LINKUSDT": date(2019, 1, 16),
    "DOTUSDT": date(2020, 8, 18),
    "MATICUSDT": date(2019, 4, 26),
    "ADAUSDT": date(2018, 4, 17),
    "DOGEUSDT": date(2019, 7, 5),
    "XRPUSDT": date(2018, 5, 4),
    # Alpaca stocks — default to 5 years of history
    "AAPL": date(2019, 1, 1),
    "SPY": date(2019, 1, 1),
    "QQQ": date(2019, 1, 1),
    "MSFT": date(2019, 1, 1),
    "AMZN": date(2019, 1, 1),
}


class DownloadLock:
    """Simple non-blocking filesystem lock for long-running downloads."""

    def __init__(self, lock_path: Path) -> None:
        self._lock_path = lock_path
        self._handle = None

    def __enter__(self) -> "DownloadLock":
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self._lock_path.open("w")
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"Another download is already running ({self._lock_path})") from exc
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._handle is None:
            return
        fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        self._handle.close()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Download OHLCV data to local store")
    parser.add_argument("--symbols", nargs="+", default=None, help="Symbols to download (default: from config)")
    parser.add_argument("--start", type=str, default=None, help="Start date YYYY-MM-DD (default: per symbol)")
    parser.add_argument("--end", type=str, default=None, help="End date YYYY-MM-DD (default: today)")
    parser.add_argument("--timeframe", default="1m", help="Timeframe to download (default: 1m)")
    parser.add_argument("--exchange", default="binance", help="Exchange: binance or alpaca (default: binance)")
    parser.add_argument("--force", action="store_true", help="Force re-download all periods")
    args = parser.parse_args()

    settings = Settings()
    store_dir = Path(settings.raw_data_dir)
    cache_dir = Path(settings.data_dir) / "cache" / "binance_vision"
    lock_path = Path(settings.data_dir) / "download.lock"

    with DownloadLock(lock_path):
        store = ParquetStore(base_dir=store_dir)
        orch = DownloadOrchestrator(store=store, cache_dir=cache_dir, settings=settings)

        if args.exchange == "alpaca":
            symbols = args.symbols or settings.alpaca_symbols
        else:
            symbols = args.symbols or settings.default_symbols
        end = date.fromisoformat(args.end) if args.end else date.today()

        for sym in symbols:
            if args.start:
                start = date.fromisoformat(args.start)
            else:
                start = SYMBOL_START_DATES.get(sym, date(2020, 1, 1))

            print(f"\n{'='*60}")
            print(f"Downloading {sym} {args.timeframe} from {start} to {end}")
            print(f"{'='*60}")

            result = await orch.sync(
                sym,
                start,
                end,
                exchange=args.exchange,
                timeframe=args.timeframe,
                force=args.force,
            )

            print(f"  Periods: {result['periods_downloaded']}")
            print(f"  New rows: {result['rows_new']:,}")
            if result["errors"]:
                print(f"  Errors ({len(result['errors'])}):")
                for err in result["errors"][:5]:
                    print(f"    - {err}")

        print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
