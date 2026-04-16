#!/usr/bin/env python3
"""Download macro data (FRED + cross-asset ETFs) to local cache.

Usage
-----
python scripts/download_macro_data.py                          # All series
python scripts/download_macro_data.py --series vix yield_spread # Specific
python scripts/download_macro_data.py --force                   # Force refresh
python scripts/download_macro_data.py --start 2015-01-01        # Custom start
python scripts/download_macro_data.py --cross-asset-only        # Only ETFs
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.data.cross_asset import CrossAssetDownloader
from suitetrading.data.fred import FREDDownloader
from suitetrading.data.macro_cache import MacroCacheManager


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Download macro data to local cache")
    p.add_argument("--series", nargs="+", default=None, help="FRED series keys to download")
    p.add_argument("--start", default="2015-01-01", help="Start date")
    p.add_argument("--force", action="store_true", help="Force refresh even if fresh")
    p.add_argument("--cache-dir", default=str(ROOT / "data" / "raw" / "macro"))
    p.add_argument("--cross-asset-only", action="store_true", help="Only download ETFs")
    p.add_argument("--fred-only", action="store_true", help="Only download FRED series")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cache = MacroCacheManager(cache_dir=Path(args.cache_dir))

    if not args.cross_asset_only:
        logger.info("Downloading FRED macro series...")
        try:
            fred = FREDDownloader()
            paths = cache.refresh_fred(
                fred, keys=args.series, force=args.force, start=args.start,
            )
            logger.info("FRED: {} series cached", len(paths))
            for key, path in paths.items():
                logger.info("  {} → {}", key, path)
        except ValueError as e:
            logger.error("FRED download failed: {}. Set FRED_API_KEY env var.", e)

    if not args.fred_only:
        logger.info("Downloading cross-asset ETFs...")
        ca = CrossAssetDownloader()
        paths = cache.refresh_cross_asset(
            ca, force=args.force, start=args.start,
        )
        logger.info("Cross-asset: {} ETFs cached", len(paths))
        for key, path in paths.items():
            logger.info("  {} → {}", key, path)


if __name__ == "__main__":
    main()
