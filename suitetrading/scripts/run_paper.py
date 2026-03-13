#!/usr/bin/env python3
"""Paper-trading runner — polls Alpaca bars, computes signals, executes via SignalBridge.

Loads a finalist config (JSON evidence card from run_discovery.py), computes
indicator signals on live bars, and routes entry/exit decisions through
``AlpacaExecutor`` + ``SignalBridge``.

Requirements
------------
- ``APCA_API_KEY_ID`` and ``APCA_API_SECRET_KEY`` env vars (or flags)
- A finalist JSON card with ``indicator_params``, ``risk_overrides``, etc.

Usage
-----
# Paper trade the #1 finalist on BTC/USD, polling every 60s
python scripts/run_paper.py \
    --config artifacts/discovery/evidence/finalist_001_BTCUSDT_4h_trend_following.json \
    --symbol BTC/USD \
    --timeframe 1h \
    --poll-interval 60

# Dry run (no orders, just log signals)
python scripts/run_paper.py \
    --config artifacts/discovery/evidence/finalist_001_BTCUSDT_4h_trend_following.json \
    --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.config.archetypes import get_auxiliary_indicators
from suitetrading.execution.alpaca_executor import AlpacaExecutor
from suitetrading.execution.signal_bridge import SignalBridge
from suitetrading.indicators.base import IndicatorState
from suitetrading.indicators.registry import get_indicator
from suitetrading.indicators.signal_combiner import combine_signals
from suitetrading.risk.archetypes import get_archetype

# Graceful shutdown flag
_RUNNING = True


def _handle_signal(signum: int, frame: Any) -> None:
    global _RUNNING
    logger.info("Shutdown signal received ({}), finishing current cycle…", signum)
    _RUNNING = False


signal.signal(signal.SIGINT, _handle_signal)
signal.signal(signal.SIGTERM, _handle_signal)


# ── CLI ───────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Paper trading runner")
    p.add_argument(
        "--config", required=True,
        help="Path to finalist JSON evidence card",
    )
    p.add_argument(
        "--symbol", default=None,
        help="Alpaca trading symbol (e.g. BTC/USD). Defaults to card's symbol.",
    )
    p.add_argument(
        "--timeframe", default=None,
        help="Bar timeframe (e.g. 1h, 4h). Defaults to card's timeframe.",
    )
    p.add_argument(
        "--poll-interval", type=int, default=60,
        help="Seconds between bar poll cycles",
    )
    p.add_argument(
        "--lookback-bars", type=int, default=500,
        help="Bars to fetch for indicator warmup",
    )
    p.add_argument(
        "--api-key", default=os.environ.get("APCA_API_KEY_ID", ""),
    )
    p.add_argument(
        "--secret-key", default=os.environ.get("APCA_API_SECRET_KEY", ""),
    )
    p.add_argument(
        "--paper", action="store_true", default=True,
        help="Use paper trading (default: True)",
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Compute signals but do NOT send orders",
    )
    p.add_argument(
        "--log-dir", default=str(ROOT / "artifacts" / "paper_trading"),
    )
    return p.parse_args()


# ── Config Loading ────────────────────────────────────────────────────


def load_config(config_path: str) -> dict[str, Any]:
    """Load and validate finalist JSON card."""
    with open(config_path) as f:
        card = json.load(f)

    required = ("indicator_params", "risk_overrides", "archetype")
    for key in required:
        if key not in card:
            raise ValueError(f"Finalist card missing required key: {key!r}")

    return card


# ── Bar Fetching ──────────────────────────────────────────────────────


ALPACA_SYMBOL_MAP: dict[str, str] = {
    "BTCUSDT": "BTC/USD",
    "ETHUSDT": "ETH/USD",
    "SOLUSDT": "SOL/USD",
}


def resolve_symbol(card_symbol: str, cli_symbol: str | None) -> str:
    """Resolve trading symbol: CLI override > mapped > card value."""
    if cli_symbol:
        return cli_symbol
    return ALPACA_SYMBOL_MAP.get(card_symbol, card_symbol)


def fetch_recent_bars(
    api_key: str,
    secret_key: str,
    symbol: str,
    timeframe: str,
    lookback_bars: int,
) -> pd.DataFrame:
    """Fetch recent bars from Alpaca crypto historical API."""
    from suitetrading.data.alpaca import AlpacaDownloader

    downloader = AlpacaDownloader(
        api_key=api_key,
        secret_key=secret_key,
        asset_class="crypto",
    )

    # Estimate how many days we need for the lookback
    tf_minutes = _tf_to_minutes(timeframe)
    days_needed = max(1, (lookback_bars * tf_minutes) // (24 * 60) + 2)
    end_date = date.today()
    start_date = end_date - timedelta(days=days_needed)

    df = downloader.download_range(symbol, timeframe, start_date, end_date)

    # Return only the last N bars
    if len(df) > lookback_bars:
        df = df.iloc[-lookback_bars:]

    return df


def _generate_synthetic_bars(n: int) -> pd.DataFrame:
    """Generate synthetic OHLCV bars for dry-run mode (no API needed)."""
    import numpy as np

    rng = np.random.default_rng(42)
    base = 50_000.0
    returns = rng.normal(0.0, 0.005, size=n)
    closes = base * np.cumprod(1 + returns)
    highs = closes * (1 + rng.uniform(0.001, 0.01, size=n))
    lows = closes * (1 - rng.uniform(0.001, 0.01, size=n))
    opens = closes * (1 + rng.uniform(-0.005, 0.005, size=n))
    volumes = rng.uniform(100, 5000, size=n)

    idx = pd.date_range(end=datetime.now(timezone.utc), periods=n, freq="1h")
    return pd.DataFrame(
        {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes},
        index=idx,
    )


def _tf_to_minutes(tf: str) -> int:
    """Convert timeframe string to minutes."""
    mapping = {
        "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "4h": 240, "1d": 1440,
    }
    return mapping.get(tf, 60)


# ── Signal Computation ────────────────────────────────────────────────


def compute_signals(
    df: pd.DataFrame,
    indicator_params: dict[str, dict[str, Any]],
    auxiliary_indicators: set[str] | None = None,
) -> dict[str, bool]:
    """Compute indicator signals on current bar data.

    Returns signal dict for the LAST bar only.
    """
    auxiliary = auxiliary_indicators or set()
    signals: dict[str, pd.Series] = {}
    states: dict[str, IndicatorState] = {}

    for ind_name, params in indicator_params.items():
        if ind_name in auxiliary:
            continue
        indicator = get_indicator(ind_name)
        sig = indicator.compute(df, **params)
        signals[ind_name] = sig
        states[ind_name] = IndicatorState.EXCLUYENTE

    if not signals:
        return {"entry_long": False, "exit_long": False}

    entry = combine_signals(signals, states)

    # Last bar's signal values
    last_entry = bool(entry.iloc[-1]) if len(entry) > 0 else False

    # Exit signal: inverse of entry (simplified v1)
    # A more sophisticated exit could check for signal reversal
    prev_entry = bool(entry.iloc[-2]) if len(entry) > 1 else False
    exit_long = prev_entry and not last_entry

    return {
        "entry_long": last_entry,
        "exit_long": exit_long,
    }


# ── Dry-Run Executor ─────────────────────────────────────────────────


class DryRunExecutor:
    """Mock executor that logs but does not submit orders."""

    def __init__(self) -> None:
        self._paper = True

    @property
    def paper(self) -> bool:
        return True

    def get_account(self):
        from suitetrading.execution.alpaca_executor import AccountInfo
        return AccountInfo(equity=10_000.0, cash=10_000.0, buying_power=10_000.0, currency="USD")

    def get_positions(self) -> list:
        return []

    def get_position(self, symbol: str):
        return None

    def submit_market_order(self, symbol: str, qty: float, side: str):
        from suitetrading.execution.alpaca_executor import OrderResult
        logger.info("[DRY RUN] {} {} {} qty={:.6f}", side.upper(), "MARKET", symbol, qty)
        return OrderResult(order_id="dry-run", symbol=symbol, side=side, qty=qty, status="dry_run")

    def close_position(self, symbol: str):
        from suitetrading.execution.alpaca_executor import OrderResult
        logger.info("[DRY RUN] CLOSE {}", symbol)
        return OrderResult(order_id="dry-run", symbol=symbol, side="sell", qty=0, status="dry_run")


# ── Main Loop ─────────────────────────────────────────────────────────


def main() -> None:
    args = parse_args()

    # Load config
    card = load_config(args.config)
    indicator_params = card["indicator_params"]
    risk_overrides = card.get("risk_overrides", {})
    archetype = card["archetype"]
    card_symbol = card.get("symbol", "BTCUSDT")
    card_tf = card.get("timeframe", "1h")

    symbol = resolve_symbol(card_symbol, args.symbol)
    timeframe = args.timeframe or card_tf
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Paper Trading Config:")
    logger.info("  Symbol: {} (card: {})", symbol, card_symbol)
    logger.info("  Timeframe: {}", timeframe)
    logger.info("  Archetype: {}", archetype)
    logger.info("  Indicators: {}", list(indicator_params.keys()))
    logger.info("  Dry run: {}", args.dry_run)

    # Resolve auxiliary indicators (not used in entry signal combination)
    auxiliary = set(get_auxiliary_indicators(archetype))

    # Build risk config
    risk_config = get_archetype(archetype).build_config(**risk_overrides)

    # Initialize executor
    if args.dry_run:
        executor = DryRunExecutor()
    else:
        if not args.api_key or not args.secret_key:
            logger.error("Alpaca API keys required. Set APCA_API_KEY_ID and APCA_API_SECRET_KEY.")
            sys.exit(1)
        executor = AlpacaExecutor(
            api_key=args.api_key,
            secret_key=args.secret_key,
            paper=args.paper,
        )

    bridge = SignalBridge(
        executor=executor,
        risk_config=risk_config,
        symbol=symbol,
        log_dir=log_dir,
    )

    # Save session config
    session_log = {
        "start_time": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol,
        "timeframe": timeframe,
        "archetype": archetype,
        "indicator_params": indicator_params,
        "risk_overrides": risk_overrides,
        "dry_run": args.dry_run,
        "poll_interval": args.poll_interval,
    }
    with open(log_dir / f"session_{symbol.replace('/', '_')}.json", "w") as f:
        json.dump(session_log, f, indent=2, default=str)

    last_bar_ts: str | None = None
    cycle = 0

    logger.info("Starting paper trading loop (poll every {}s)…", args.poll_interval)
    print("Press Ctrl+C to stop gracefully.\n")

    while _RUNNING:
        cycle += 1
        try:
            # Fetch recent bars for indicator warmup
            if args.dry_run:
                df = _generate_synthetic_bars(args.lookback_bars)
            else:
                df = fetch_recent_bars(
                    api_key=args.api_key,
                    secret_key=args.secret_key,
                    symbol=symbol,
                    timeframe=timeframe,
                    lookback_bars=args.lookback_bars,
                )

            if df.empty:
                logger.warning("No bars returned, retrying in {}s", args.poll_interval)
                time.sleep(args.poll_interval)
                continue

            current_ts = str(df.index[-1])

            # Only process if we have a NEW bar
            if current_ts == last_bar_ts:
                time.sleep(args.poll_interval)
                continue

            last_bar_ts = current_ts
            last_row = df.iloc[-1]

            bar = {
                "open": float(last_row["open"]),
                "high": float(last_row["high"]),
                "low": float(last_row["low"]),
                "close": float(last_row["close"]),
                "volume": float(last_row["volume"]),
                "timestamp": current_ts,
            }

            # Compute signals on full lookback window
            signals = compute_signals(df, indicator_params, auxiliary)

            logger.info(
                "Cycle {} | {} | close={:.2f} | entry={} exit={} | state={}",
                cycle, current_ts, bar["close"],
                signals["entry_long"], signals["exit_long"],
                bridge.state.position,
            )

            # Execute through bridge
            action = bridge.on_bar(bar, signals)
            if action:
                logger.info("ACTION: {}", action)

            # Periodic reconciliation (every 10 cycles)
            if cycle % 10 == 0 and not args.dry_run:
                bridge.reconcile()

        except KeyboardInterrupt:
            break
        except Exception as exc:
            logger.error("Error in cycle {}: {}", cycle, exc)

        time.sleep(args.poll_interval)

    # Shutdown
    logger.info("Shutting down paper trading…")
    logger.info("Total cycles: {}", cycle)
    logger.info("Trades executed: {}", len(bridge.trades))
    logger.info("Final state: {}", bridge.state.position)

    # Save final trade log summary
    if bridge.trades:
        trades_summary = []
        for t in bridge.trades:
            trades_summary.append({
                "symbol": t.symbol,
                "side": t.side,
                "entry_time": t.entry_time,
                "entry_price": t.entry_price,
                "exit_time": t.exit_time,
                "exit_price": t.exit_price,
                "exit_reason": t.exit_reason,
                "pnl": t.pnl,
                "bars_held": t.bars_held,
            })
        summary_path = log_dir / f"summary_{symbol.replace('/', '_')}.json"
        with open(summary_path, "w") as f:
            json.dump(trades_summary, f, indent=2, default=str)
        logger.info("Trade summary → {}", summary_path)

    print("\n" + "=" * 60)
    print("  PAPER TRADING SESSION ENDED")
    print("=" * 60)
    print(f"  Cycles: {cycle}")
    print(f"  Trades: {len(bridge.trades)}")
    if bridge.trades:
        total_pnl = sum(t.pnl or 0.0 for t in bridge.trades)
        print(f"  Total PnL: {total_pnl:.2f}")
    print(f"  Logs: {log_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
