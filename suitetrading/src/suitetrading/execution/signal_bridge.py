"""Signal-to-order bridge for paper/live trading.

Translates backtest-style indicator signals into execution commands
via ``AlpacaExecutor``.  Tracks position state and prevents duplicate
entries.

V1 Scope
--------
- Long-only, single position at a time
- Market entry + ATR-based SL/TP (matching the backtester)
- State: FLAT → OPEN → FLAT
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from loguru import logger

from suitetrading.risk.contracts import RiskConfig


class Executor(Protocol):
    """Minimal executor interface used by SignalBridge."""

    @property
    def paper(self) -> bool: ...

    def get_account(self) -> Any: ...
    def get_position(self, symbol: str) -> Any: ...
    def submit_market_order(self, symbol: str, qty: float, side: str) -> Any: ...
    def close_position(self, symbol: str) -> Any: ...


@dataclass
class BridgeState:
    """Internal state tracked by the bridge."""

    position: str = "flat"  # "flat" | "long"
    entry_price: float = 0.0
    entry_bar_idx: int = -1
    stop_loss: float = 0.0
    take_profit: float = 0.0
    qty: float = 0.0
    entry_order_id: str = ""
    bars_in_trade: int = 0


@dataclass
class TradeLog:
    """Record of a single trade for analysis."""

    symbol: str
    side: str
    entry_time: str
    entry_price: float
    exit_time: str | None = None
    exit_price: float | None = None
    exit_reason: str | None = None
    pnl: float | None = None
    bars_held: int = 0


class SignalBridge:
    """Translates backtest signals to Alpaca execution commands.

    Uses the **same ATR-based SL/TP logic** as the backtesting runners
    so that paper-trading behaviour matches optimised backtest results.

    Parameters
    ----------
    executor
        Object implementing the :class:`Executor` protocol.
    risk_config
        Risk configuration (for SL/TP calculations).
    symbol
        Trading symbol (e.g. ``"BTC/USD"``).
    log_dir
        Directory to write trade logs (optional).
    atr_period
        ATR lookback period (must match backtester, default 14).
    """

    def __init__(
        self,
        executor: Executor,
        risk_config: RiskConfig,
        symbol: str,
        log_dir: Path | None = None,
        atr_period: int = 14,
    ) -> None:
        self._executor = executor
        self._risk = risk_config
        self._symbol = symbol
        self._state = BridgeState()
        self._trades: list[TradeLog] = []
        self._log_dir = log_dir
        self._bar_idx = 0
        self._atr_period = atr_period
        # Rolling window for ATR computation
        self._highs: list[float] = []
        self._lows: list[float] = []
        self._closes: list[float] = []

    @property
    def state(self) -> BridgeState:
        return self._state

    @property
    def trades(self) -> list[TradeLog]:
        return list(self._trades)

    def on_bar(
        self,
        bar: dict[str, float],
        signals: dict[str, bool],
    ) -> str | None:
        """Process a new bar and execute orders if needed.

        Parameters
        ----------
        bar
            Dict with keys: ``open``, ``high``, ``low``, ``close``, ``volume``,
            ``timestamp`` (ISO string or epoch).
        signals
            Dict with boolean signal flags: ``entry_long``, ``exit_long``.

        Returns
        -------
        Action taken: ``"entry"``, ``"exit_signal"``, ``"exit_sl"``,
        ``"exit_tp"``, ``"exit_time"``, ``"skip"`` or ``None``.
        """
        self._bar_idx += 1
        action = None

        close = bar["close"]
        high = bar.get("high", close)
        low = bar.get("low", close)
        ts = bar.get("timestamp", datetime.now(timezone.utc).isoformat())

        # Update price history for ATR
        self._highs.append(high)
        self._lows.append(low)
        self._closes.append(close)

        if self._state.position == "flat":
            if signals.get("entry_long", False):
                action = self._enter_long(close, ts)

        elif self._state.position == "long":
            self._state.bars_in_trade += 1

            # Check SL hit
            if self._state.stop_loss > 0 and low <= self._state.stop_loss:
                action = self._exit("exit_sl", self._state.stop_loss, ts)
            # Check TP hit
            elif self._state.take_profit > 0 and high >= self._state.take_profit:
                action = self._exit("exit_tp", self._state.take_profit, ts)
            # Check signal exit
            elif signals.get("exit_long", False):
                action = self._exit("exit_signal", close, ts)
            # Check time exit
            elif (
                self._risk.time_exit.enabled
                and self._state.bars_in_trade >= self._risk.time_exit.max_bars
            ):
                action = self._exit("exit_time", close, ts)

        return action

    # ── ATR computation (matching backtester runners.py) ──────────────

    def _current_atr(self) -> float:
        """Compute ATR using Wilder smoothing on the rolling window.

        Replicates ``_compute_atr`` from backtesting runners.
        """
        period = self._atr_period
        n = len(self._highs)
        if n < period:
            return 0.0

        highs = self._highs
        lows = self._lows
        closes = self._closes

        # True Range for each bar
        tr = [highs[0] - lows[0]]
        for i in range(1, n):
            tr.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))

        # Wilder smoothing
        atr = sum(tr[:period]) / period
        for i in range(period, n):
            atr = (atr * (period - 1) + tr[i]) / period

        return atr

    def _enter_long(self, price: float, timestamp: str) -> str:
        """Submit market buy and set ATR-based SL/TP levels."""
        account = self._executor.get_account()
        risk_pct = self._risk.sizing.risk_pct / 100.0
        capital = account.equity * risk_pct

        # ATR-based stop distance (same as backtester)
        atr_val = self._current_atr()
        if atr_val > 0:
            stop_dist = atr_val * self._risk.stop.atr_multiple
        else:
            stop_dist = price * self._risk.stop.fixed_pct / 100.0

        if stop_dist <= 0:
            logger.warning("Stop distance <= 0, skipping entry")
            return "skip"

        stop_loss = price - stop_dist
        take_profit = price + stop_dist * self._risk.stop.atr_multiple

        # Position size: risk capital / SL distance
        qty = capital / stop_dist
        if qty <= 0:
            logger.warning("Computed qty <= 0, skipping entry")
            return "skip"

        result = self._executor.submit_market_order(
            symbol=self._symbol, qty=qty, side="buy",
        )

        self._state = BridgeState(
            position="long",
            entry_price=price,
            entry_bar_idx=self._bar_idx,
            stop_loss=stop_loss,
            take_profit=take_profit,
            qty=qty,
            entry_order_id=result.order_id,
            bars_in_trade=0,
        )

        self._trades.append(TradeLog(
            symbol=self._symbol,
            side="long",
            entry_time=timestamp,
            entry_price=price,
        ))

        logger.info(
            "ENTRY LONG {} qty={:.6f} @ {:.2f} SL={:.2f} TP={:.2f} ATR={:.2f}",
            self._symbol, qty, price, stop_loss, take_profit, atr_val,
        )
        return "entry"

    def _exit(self, reason: str, price: float, timestamp: str) -> str:
        """Close the current position."""
        self._executor.close_position(self._symbol)

        raw_pnl = (price - self._state.entry_price) * self._state.qty
        # Apply commission + slippage to approximate real costs
        notional_entry = self._state.entry_price * self._state.qty
        notional_exit = price * self._state.qty
        commission = (notional_entry + notional_exit) * (self._risk.commission_pct / 100.0)
        slippage = (notional_entry + notional_exit) * (self._risk.slippage_pct / 100.0)
        net_pnl = raw_pnl - commission - slippage

        # Update last trade log
        if self._trades:
            trade = self._trades[-1]
            trade.exit_time = timestamp
            trade.exit_price = price
            trade.exit_reason = reason
            trade.pnl = net_pnl
            trade.bars_held = self._state.bars_in_trade

        logger.info(
            "EXIT {} {} @ {:.2f} reason={} bars={} gross={:.2f} net={:.2f}",
            self._symbol, reason, price, reason,
            self._state.bars_in_trade, raw_pnl, net_pnl,
        )

        self._state = BridgeState()  # reset to flat
        self._save_log()
        return reason

    def reconcile(self) -> None:
        """Sync internal state with actual Alpaca positions."""
        pos = self._executor.get_position(self._symbol)
        if pos is None and self._state.position == "long":
            logger.warning("Position lost — resetting to flat")
            self._state = BridgeState()
        elif pos is not None and self._state.position == "flat":
            logger.warning(
                "Unexpected position found: {} qty={}",
                pos.symbol, pos.qty,
            )

    def _save_log(self) -> None:
        """Persist trade log to disk."""
        if not self._log_dir:
            return
        self._log_dir.mkdir(parents=True, exist_ok=True)
        log_path = self._log_dir / f"trades_{self._symbol.replace('/', '_')}.jsonl"
        if self._trades:
            trade = self._trades[-1]
            with open(log_path, "a") as f:
                f.write(json.dumps({
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "entry_time": trade.entry_time,
                    "entry_price": trade.entry_price,
                    "exit_time": trade.exit_time,
                    "exit_price": trade.exit_price,
                    "exit_reason": trade.exit_reason,
                    "pnl": trade.pnl,
                    "bars_held": trade.bars_held,
                }) + "\n")
