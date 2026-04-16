#!/usr/bin/env python3
"""Parallel IC scanner wrapper.

Launches one step1_ic_scanner_v3.py process per (asset, timeframe) pair,
using all available cores. Merges results at the end.

Usage:
    python scripts/research/run_ic_scan_parallel.py --crypto-only --timeframes 4h 1h 15m
    python scripts/research/run_ic_scan_parallel.py --symbols BTCUSDT ETHUSDT --timeframes 4h
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent.parent
SCANNER = ROOT / "scripts" / "research" / "step1_ic_scanner_v3.py"
PYTHON = sys.executable

STOCK_SYMBOLS = ["SPY", "QQQ", "GLD", "TLT", "XLE", "XLK", "IWM", "AAPL", "NVDA", "TSLA"]
CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "AVAXUSDT"]


def run_one(symbol: str, tf: str, output_dir: Path, data_dir: str, macro_dir: str) -> Path | None:
    """Run scanner for a single (symbol, tf) pair."""
    sub_dir = output_dir / f"{symbol}_{tf}"
    sub_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        PYTHON, str(SCANNER),
        "--symbols", symbol,
        "--timeframes", tf,
        "--data-dir", data_dir,
        "--macro-dir", macro_dir,
        "--output-dir", str(sub_dir),
    ]

    if symbol in CRYPTO_SYMBOLS:
        cmd.append("--crypto-only")

    logger.info("Launching: {} {}", symbol, tf)
    result = subprocess.run(
        cmd, capture_output=True, text=True, cwd=str(ROOT),
    )

    csv_path = sub_dir / "edge_summary_v3.csv"
    if csv_path.exists():
        df = pd.read_csv(csv_path)
        logger.info("Done: {} {} -> {} measurements", symbol, tf, len(df))
        return csv_path
    else:
        logger.warning("FAILED: {} {} | stderr: {}", symbol, tf,
                        result.stderr[-500:] if result.stderr else "no stderr")
        return None


def main():
    p = argparse.ArgumentParser(description="Parallel IC scan across assets and timeframes")
    p.add_argument("--symbols", nargs="+", default=None)
    p.add_argument("--timeframes", nargs="+", default=["4h", "1h", "15m"])
    p.add_argument("--crypto-only", action="store_true")
    p.add_argument("--stocks-only", action="store_true")
    p.add_argument("--max-workers", type=int, default=10,
                   help="Max parallel processes (default: 10)")
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--macro-dir", default=str(ROOT / "data" / "raw" / "macro"))
    p.add_argument("--output-dir", default=str(ROOT / "artifacts" / "research" / "ic_scan_parallel"))
    args = p.parse_args()

    # Resolve symbols
    if args.symbols:
        symbols = args.symbols
    elif args.crypto_only:
        symbols = CRYPTO_SYMBOLS
    elif args.stocks_only:
        symbols = STOCK_SYMBOLS
    else:
        symbols = STOCK_SYMBOLS + CRYPTO_SYMBOLS

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Build task list: (symbol, tf) pairs
    tasks = [(sym, tf) for sym in symbols for tf in args.timeframes]
    logger.info("Launching {} tasks across {} workers", len(tasks), args.max_workers)

    csv_paths: list[Path] = []
    with ProcessPoolExecutor(max_workers=args.max_workers) as pool:
        futures = {
            pool.submit(run_one, sym, tf, output_dir, args.data_dir, args.macro_dir): (sym, tf)
            for sym, tf in tasks
        }
        for future in as_completed(futures):
            sym, tf = futures[future]
            try:
                path = future.result()
                if path:
                    csv_paths.append(path)
            except Exception as e:
                logger.error("Exception for {} {}: {}", sym, tf, e)

    # Merge all CSVs
    if csv_paths:
        dfs = [pd.read_csv(p) for p in csv_paths]
        merged = pd.concat(dfs, ignore_index=True)
        merged_path = output_dir / "edge_summary_v3_merged.csv"
        merged.to_csv(merged_path, index=False)
        logger.info("Merged {} measurements -> {}", len(merged), merged_path)

        # Print summary
        ok = merged[merged["status"] == "ok"]
        h1 = ok[ok["horizon"] == 1]
        for tf in sorted(h1["timeframe"].unique()):
            for d in ["long", "short"]:
                sub = h1[(h1["timeframe"] == tf) & (h1["direction"] == d)]
                if sub.empty:
                    continue
                ic_pos = sub[sub["ic_val_avg"] > 0.02]
                logger.info("{} {} -> {} total, {} with IC_OOS > 0.02",
                            tf, d, len(sub), len(ic_pos))
    else:
        logger.error("No results collected!")


if __name__ == "__main__":
    main()
