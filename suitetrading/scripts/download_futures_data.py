#!/usr/bin/env python3
"""Download Binance Futures data — funding rate, open interest, long/short ratio.

Usage
-----
# All symbols, all data types
python scripts/download_futures_data.py

# Specific symbols
python scripts/download_futures_data.py --symbols BTCUSDT ETHUSDT SOLUSDT

# Custom date range and resolution
python scripts/download_futures_data.py --start 2020-01-01 --period 4h
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.data.futures import BinanceFuturesDownloader

DEFAULT_SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT",
    "LINKUSDT", "DOTUSDT", "ADAUSDT", "DOGEUSDT", "XRPUSDT",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Download Binance Futures historical data",
    )
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--start", default="2020-01-01",
                   help="Start date (default: 2020-01-01)")
    p.add_argument("--end", default=None,
                   help="End date (default: now)")
    p.add_argument("--period", default="1h",
                   choices=["5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"],
                   help="Resolution for OI and L/S ratio (default: 1h)")
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--skip-funding", action="store_true")
    p.add_argument("--skip-oi", action="store_true")
    p.add_argument("--skip-lsratio", action="store_true")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    with BinanceFuturesDownloader(output_dir=Path(args.data_dir)) as dl:
        for symbol in args.symbols:
            logger.info("Downloading futures data for {}", symbol)

            if not args.skip_funding:
                dl.download_funding_rate(symbol, start=args.start, end=args.end)

            if not args.skip_oi:
                dl.download_open_interest(
                    symbol, period=args.period, start=args.start, end=args.end,
                )

            if not args.skip_lsratio:
                dl.download_long_short_ratio(
                    symbol, period=args.period, start=args.start, end=args.end,
                )

    logger.info("Done. Data stored in {}", args.data_dir)


if __name__ == "__main__":
    main()
