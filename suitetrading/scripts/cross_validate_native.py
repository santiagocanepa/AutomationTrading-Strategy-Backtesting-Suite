"""Cross-validate resampled data against native exchange data.

Usage::

    python -m scripts.cross_validate_native --symbol BTCUSDT --exchange binance

Downloads native 1h and 1d klines via CCXT, compares against
1m→1h and 1m→1d resampled data from the local store.
Outputs results to ``docs/cross_validation_report.md``.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

# Ensure project root is on sys.path for script invocation
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from suitetrading.config.settings import Settings
from suitetrading.data.downloader import CCXTDownloader, _to_ccxt_symbol
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.data.timeframes import tf_to_pandas_offset


def _first_complete_bar_start(window_start: pd.Timestamp, target_tf: str) -> pd.Timestamp:
    """Return the first target timeframe boundary fully covered by the 1m window."""
    aligned_start = pd.Timestamp(window_start)
    if aligned_start.tz is None:
        aligned_start = aligned_start.tz_localize("UTC")

    return aligned_start.ceil(tf_to_pandas_offset(target_tf))


def _trim_to_complete_bars(
    df: pd.DataFrame,
    *,
    window_start: pd.Timestamp,
    target_tf: str,
) -> pd.DataFrame:
    """Drop leading partial bars before validating against native exchange data."""
    comparison_start = _first_complete_bar_start(window_start, target_tf)
    return df.loc[df.index >= comparison_start]


async def cross_validate(
    symbol: str,
    exchange: str,
    store_dir: Path,
    days: int = 30,
) -> dict:
    """Run cross-validation for a symbol.

    1. Read stored 1m data (last *days* days).
    2. Download native 1h and 1d from CCXT for the same period.
    3. Resample 1m → 1h/1d with OHLCVResampler.
    4. Compare resampled vs native using ``validate_against_native()``.
    """
    store = ParquetStore(base_dir=store_dir)
    resampler = OHLCVResampler()
    ccxt = CCXTDownloader(exchange_id=exchange)
    ccxt_symbol = _to_ccxt_symbol(symbol)

    # Read stored 1m data
    df_1m = store.read(exchange, symbol, "1m")
    if df_1m is None or df_1m.empty:
        return {"symbol": symbol, "error": "No 1m data in store"}

    # Use last N days of data
    cutoff = df_1m.index.max() - pd.Timedelta(days=days)
    df_1m = df_1m.loc[df_1m.index >= cutoff]

    start = datetime(
        df_1m.index.min().year,
        df_1m.index.min().month,
        df_1m.index.min().day,
        tzinfo=timezone.utc,
    )
    end = datetime(
        df_1m.index.max().year,
        df_1m.index.max().month,
        df_1m.index.max().day,
        23, 59, 59,
        tzinfo=timezone.utc,
    )

    reports: dict[str, dict] = {}
    window_start = df_1m.index.min()

    for target_tf in ("1h", "1d"):
        # Resample from 1m
        resampled = resampler.resample(df_1m, target_tf, base_tf="1m")
        resampled = _trim_to_complete_bars(resampled, window_start=window_start, target_tf=target_tf)

        comparison_start = _first_complete_bar_start(window_start, target_tf)

        # Download native
        native = await ccxt.download_range(
            ccxt_symbol,
            target_tf,
            comparison_start.to_pydatetime(),
            end,
            progress=False,
        )
        native = native.loc[native.index >= comparison_start]

        # Compare
        report = resampler.validate_against_native(resampled, native)
        report["comparison_start"] = comparison_start.isoformat()
        reports[target_tf] = report

    return {"symbol": symbol, "reports": reports}


def write_report(results: list[dict], output_path: Path) -> None:
    """Write cross-validation results to a markdown report."""
    lines = [
        "# Cross-Validation Report: Resampled vs Native Exchange Data\n",
        f"Generated: {date.today().isoformat()}\n",
        "## Methodology\n",
        "- Download native 1h and 1d klines from exchange via CCXT",
        "- Resample stored 1m data → 1h and 1m → 1d using OHLCVResampler",
        "- Exclude the leading partial bar and compare only fully covered target candles",
        "- Compare OHLC (tolerance ≤ 0.01%) and Volume (absolute diff ≤ 1e-9)\n",
        "## Results\n",
    ]

    for result in results:
        symbol = result["symbol"]
        lines.append(f"### {symbol}\n")

        if "error" in result:
            lines.append(f"**Error**: {result['error']}\n")
            continue

        for tf, report in result["reports"].items():
            status = "PASS" if report["pass"] else "FAIL"
            lines.append(f"#### 1m → {tf}: **{status}**\n")
            lines.append(f"- Comparison start: {report['comparison_start']}")
            lines.append(f"- Bars compared: {report['bars_compared']}")

            for col, info in report.get("columns", {}).items():
                if "max_pct_diff" in info:
                    lines.append(f"- {col}: max diff = {info['max_pct_diff']:.6f}% ({'PASS' if info['pass'] else 'FAIL'})")
                elif "max_abs_diff" in info:
                    lines.append(f"- {col}: max abs diff = {info['max_abs_diff']:.6f} ({'PASS' if info['pass'] else 'FAIL'})")
            lines.append("")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    print(f"Report written to {output_path}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-validate resampled vs native exchange data")
    parser.add_argument("--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--store-dir", type=str, default=None)
    args = parser.parse_args()

    settings = Settings()
    store_dir = Path(args.store_dir) if args.store_dir else Path(settings.raw_data_dir)

    results = []
    for sym in args.symbols:
        print(f"Validating {sym}...")
        result = await cross_validate(sym, args.exchange, store_dir, days=args.days)
        results.append(result)

    output = PROJECT_ROOT / "docs" / "cross_validation_report.md"
    write_report(results, output)


if __name__ == "__main__":
    asyncio.run(main())
