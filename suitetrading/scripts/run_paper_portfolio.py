#!/usr/bin/env python3
"""Paper-trade the locked portfolio (multi-strategy).

Loads the locked portfolio from artifacts/portfolio_locked/,
instantiates one SignalBridge per strategy, and runs them through
the PortfolioBridge for position consolidation.

Usage
-----
# Dry run (no orders, just signal logging)
python scripts/run_paper_portfolio.py --dry-run

# Live paper trading via Alpaca
python scripts/run_paper_portfolio.py

# Custom portfolio dir
python scripts/run_paper_portfolio.py --portfolio-dir artifacts/portfolio_locked/
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.backtesting._internal.datasets import build_dataset_from_df
from suitetrading.config.archetypes import get_entry_indicators, get_auxiliary_indicators
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.indicators.registry import get_indicator
from suitetrading.indicators.signal_combiner import combine_signals
from suitetrading.indicators.base import IndicatorState
from suitetrading.risk.archetypes import get_archetype


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Paper-trade locked portfolio")
    p.add_argument(
        "--portfolio-dir",
        default=str(ROOT / "artifacts" / "portfolio_locked"),
    )
    p.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    p.add_argument("--exchange", default="alpaca")
    p.add_argument("--dry-run", action="store_true", help="Log signals only, no orders")
    p.add_argument("--interval-sec", type=int, default=60, help="Poll interval")
    return p.parse_args()


def load_portfolio(portfolio_dir: Path) -> tuple[dict, list[dict]]:
    """Load manifest and evidence cards."""
    manifest = json.loads((portfolio_dir / "portfolio_manifest.json").read_text())
    cards = []
    for f in sorted((portfolio_dir / "evidence").glob("*.json")):
        cards.append(json.load(open(f)))
    return manifest, cards


def compute_latest_signals(
    card: dict,
    store: ParquetStore,
    resampler: OHLCVResampler,
    exchange: str,
) -> dict[str, bool]:
    """Compute current signals for a strategy card."""
    raw = store.read(exchange, card["symbol"], "1m")
    # Use last 500 bars of target TF for signal computation
    ohlcv = resampler.resample(raw, card["timeframe"], base_tf="1m")
    ohlcv = ohlcv.tail(500)

    entry_names = get_entry_indicators(card["archetype"])

    signals: dict[str, pd.Series] = {}
    states: dict[str, IndicatorState] = {}

    for ind_name in entry_names:
        indicator = get_indicator(ind_name)
        params = card["indicator_params"].get(ind_name, {})
        sig = indicator.compute(ohlcv, **params)
        signals[ind_name] = sig
        states[ind_name] = IndicatorState.EXCLUYENTE

    combined = combine_signals(signals, states, num_optional_required=1)
    last_bar = combined.iloc[-1] if len(combined) > 0 else False

    direction = card["direction"]
    return {
        "entry_long": bool(last_bar) if direction == "long" else False,
        "entry_short": bool(last_bar) if direction == "short" else False,
        "exit_long": False,
        "exit_short": False,
    }


def main() -> None:
    args = parse_args()
    portfolio_dir = Path(args.portfolio_dir)

    manifest, cards = load_portfolio(portfolio_dir)
    logger.info(
        "Loaded portfolio: {} strategies, {} symbols",
        manifest["n_strategies"],
        manifest["symbols"],
    )

    store = ParquetStore(base_dir=Path(args.data_dir))
    resampler = OHLCVResampler()

    if args.dry_run:
        logger.info("DRY RUN — computing signals once for all strategies")
        for card in cards:
            label = f"{card['symbol']}_{card['timeframe']}_{card['archetype']}_{card['direction']}"
            try:
                signals = compute_latest_signals(card, store, resampler, args.exchange)
                active = [k for k, v in signals.items() if v]
                status = " | ".join(active) if active else "flat"
                logger.info("  {:<60s} → {}", label, status)
            except Exception:
                logger.exception("  {} → ERROR", label)
        return

    logger.info("Starting paper trading loop (interval={}s)...", args.interval_sec)
    logger.info("Press Ctrl+C to stop")

    while True:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        logger.info("─── Tick {} ───", ts)

        for card in cards:
            label = f"{card['symbol']}_{card['timeframe']}_{card['direction']}"
            try:
                signals = compute_latest_signals(card, store, resampler, args.exchange)
                if any(signals.values()):
                    active = [k for k, v in signals.items() if v]
                    logger.info("  SIGNAL {}: {}", label, active)
            except Exception:
                logger.exception("  {} error", label)

        time.sleep(args.interval_sec)


if __name__ == "__main__":
    main()
