"""Execution runners — bar-loop simulation with FSM integration.

Provides two execution paths:

- ``run_fsm_backtest``: full FSM-based bar loop with position sizing,
  trailing, partial TP, pyramiding.  Suitable for all archetypes.
- ``run_simple_backtest``: lightweight bar loop (no pyramiding, no
  partial TP) for high-throughput screening of A/B archetypes.

Both paths are deterministic: same inputs → same outputs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from suitetrading.backtesting._internal.schemas import BacktestDataset, StrategySignals
from suitetrading.risk.contracts import PositionState, RiskConfig
from suitetrading.risk.portfolio import PortfolioRiskManager
from suitetrading.risk.position_sizing import create_sizer
from suitetrading.risk.state_machine import PositionStateMachine
from suitetrading.risk.trailing import create_exit_policy


@dataclass
class TradeRecord:
    """Record of a single completed trade."""

    entry_bar: int
    exit_bar: int
    direction: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float  # GROSS PnL (price-only, no commission)
    exit_reason: str
    commission: float = 0.0  # Total commission paid (entry + exit)


@dataclass
class BacktestResult:
    """Complete output of a single backtest run."""

    equity_curve: np.ndarray
    trades: list[TradeRecord] = field(default_factory=list)
    final_equity: float = 0.0
    total_return_pct: float = 0.0
    mode: str = "fsm"


def run_fsm_backtest(
    *,
    dataset: BacktestDataset,
    signals: StrategySignals,
    risk_config: RiskConfig,
    direction: str = "long",
) -> BacktestResult:
    """Full FSM bar-loop backtest using PositionStateMachine.

    Processes every bar through the state machine, handling entries,
    exits, stop-loss, partial TP, break-even, trailing and pyramiding
    as configured in *risk_config*.
    """
    ohlcv = dataset.ohlcv
    n = len(ohlcv)
    if n == 0:
        return BacktestResult(equity_curve=np.array([]), final_equity=0.0)

    fsm = PositionStateMachine(risk_config)
    sizer = create_sizer(risk_config.sizing)
    snapshot = fsm.initial_snapshot()

    # Portfolio risk manager (feature-flagged)
    portfolio_mgr = None
    if risk_config.portfolio.enabled:
        portfolio_mgr = PortfolioRiskManager(risk_config.portfolio)

    # Trailing policy mode: "signal" (default) or "policy" (ExitPolicy objects)
    trailing_policy = None
    use_trailing_policy = risk_config.trailing.trailing_mode == "policy"
    if use_trailing_policy:
        trailing_policy = create_exit_policy(
            risk_config.trailing.model,
            atr_multiple=risk_config.trailing.atr_multiple,
        )

    equity = risk_config.initial_capital
    equity_curve = np.full(n, equity)
    trades: list[TradeRecord] = []
    commission_pct = risk_config.commission_pct

    # Pre-extract arrays for speed
    opens = ohlcv["open"].values
    highs = ohlcv["high"].values
    lows = ohlcv["low"].values
    closes = ohlcv["close"].values

    entry_long = signals.entry_long.values if signals.entry_long is not None else np.zeros(n, dtype=bool)
    entry_short = signals.entry_short.values if signals.entry_short is not None else np.zeros(n, dtype=bool)
    exit_long = signals.exit_long.values if signals.exit_long is not None else np.zeros(n, dtype=bool)
    exit_short = signals.exit_short.values if signals.exit_short is not None else np.zeros(n, dtype=bool)
    trailing_long = signals.trailing_long.values if signals.trailing_long is not None else np.zeros(n, dtype=bool)
    trailing_short = signals.trailing_short.values if signals.trailing_short is not None else np.zeros(n, dtype=bool)

    # ATR for position sizing (pre-compute using simple true range)
    atr_values = _compute_atr(highs, lows, closes, period=14)

    # Pre-extract Firestorm TM bands from indicators_payload (if available)
    _ftm_up = signals.indicators_payload.get("firestorm_tm_up")
    _ftm_dn = signals.indicators_payload.get("firestorm_tm_dn")
    if _ftm_up is not None:
        _ftm_up = np.asarray(_ftm_up, dtype=np.float64)
    if _ftm_dn is not None:
        _ftm_dn = np.asarray(_ftm_dn, dtype=np.float64)

    # Track entry bar for trade records
    current_entry_bar = 0
    current_entry_price = 0.0
    current_entry_qty = 0.0  # Accumulated quantity for current trade
    trade_commission = 0.0  # Accumulated commission for current trade

    for i in range(n):
        bar = {
            "open": float(opens[i]),
            "high": float(highs[i]),
            "low": float(lows[i]),
            "close": float(closes[i]),
        }

        # Determine direction-aware signals
        if direction in ("long", "both"):
            entry_sig = bool(entry_long[i])
            exit_sig = bool(exit_long[i])
            trail_sig = bool(trailing_long[i])
            entry_dir = "long"
        else:
            entry_sig = bool(entry_short[i])
            exit_sig = bool(exit_short[i])
            trail_sig = bool(trailing_short[i])
            entry_dir = "short"

        # Both directions: alternate or use the active signal
        if direction == "both":
            if snapshot.direction == "short":
                entry_sig = bool(entry_short[i])
                exit_sig = bool(exit_short[i])
                trail_sig = bool(trailing_short[i])
                entry_dir = "short"
            elif snapshot.state == PositionState.FLAT and bool(entry_short[i]) and not bool(entry_long[i]):
                entry_sig = True
                entry_dir = "short"

        # Position sizing
        entry_size = 0.0
        stop_override = None
        if entry_sig and snapshot.state in (PositionState.FLAT, PositionState.CLOSED):
            atr_val = float(atr_values[i]) if atr_values[i] > 0 else None
            stop_model = risk_config.stop.model

            if stop_model == "firestorm_tm" and _ftm_up is not None:
                # Dynamic stop from Firestorm TM bands
                if entry_dir == "long":
                    stop_override = float(_ftm_up[i])
                else:
                    stop_override = float(_ftm_dn[i])
                stop_dist = abs(closes[i] - stop_override)
            elif stop_model == "fixed_pct":
                stop_dist = closes[i] * risk_config.stop.fixed_pct / 100.0
                if entry_dir == "long":
                    stop_override = closes[i] - stop_dist
                else:
                    stop_override = closes[i] + stop_dist
            else:
                # Default: ATR-based stop
                stop_dist = (
                    atr_val * risk_config.stop.atr_multiple
                    if atr_val
                    else closes[i] * risk_config.stop.fixed_pct / 100.0
                )
                if entry_dir == "long":
                    stop_override = closes[i] - stop_dist
                else:
                    stop_override = closes[i] + stop_dist

            entry_size = sizer.size(
                equity=equity,
                entry_price=closes[i],
                stop_price=stop_override,
                volatility_value=atr_val,
                strategy_stats=None,
                portfolio_state=None,
            )

            # Portfolio risk gate (if enabled)
            if portfolio_mgr is not None:
                proposed_risk = entry_size * stop_dist if stop_dist > 0 else 0.0
                portfolio_mgr.update(equity=equity, open_positions=[])
                approved, _reason = portfolio_mgr.approve_new_risk(
                    proposed_risk=proposed_risk,
                    proposed_notional=entry_size * closes[i],
                    proposed_direction=entry_dir,
                )
                if not approved:
                    entry_sig = False
                    entry_size = 0.0

        # Trailing policy evaluation: override trailing_signal if policy mode
        if use_trailing_policy and trailing_policy is not None:
            if snapshot.state not in (PositionState.FLAT, PositionState.CLOSED):
                policy_exit, _new_stop, _exit_reason = trailing_policy.evaluate(
                    snapshot=snapshot,
                    bar=bar,
                    indicators={"atr": float(atr_values[i]) if i < len(atr_values) else None},
                    bar_index=i,
                )
                if policy_exit:
                    trail_sig = True
                if _new_stop is not None and snapshot.stop_price is not None:
                    # Policy can tighten the stop but never loosen it
                    if snapshot.direction == "long":
                        if _new_stop > snapshot.stop_price:
                            snapshot.stop_price = _new_stop
                    else:
                        if _new_stop < snapshot.stop_price:
                            snapshot.stop_price = _new_stop

        result = fsm.evaluate_bar(
            snapshot,
            bar,
            bar_index=i,
            entry_signal=entry_sig,
            entry_direction=entry_dir,
            exit_signal=exit_sig,
            trailing_signal=trail_sig,
            entry_size=entry_size,
            atr_value=float(atr_values[i]) if i < len(atr_values) else None,
            stop_override=stop_override,
        )

        prev_state = snapshot.state
        snapshot = result.snapshot

        # Process orders for trade tracking and equity
        for order in result.orders:
            action = order.get("action", "")
            filled_qty = order.get("filled_qty", 0.0)
            price = order.get("price", 0.0)

            if action == "entry":
                current_entry_bar = i
                current_entry_price = price
                current_entry_qty = filled_qty
                # Commission on entry
                comm = abs(filled_qty * price) * commission_pct / 100.0
                equity -= comm
                trade_commission = comm  # Reset: new trade starts

            elif action in ("close_all", "close_partial"):
                pnl = order.get("pnl", 0.0)
                if pnl == 0.0 and snapshot.direction != "flat":
                    # Calculate from snapshot
                    pnl = snapshot.realized_pnl - sum(t.pnl for t in trades)

                # Commission on exit
                comm = abs(filled_qty * price) * commission_pct / 100.0
                equity -= comm
                trade_commission += comm

            elif action == "pyramid_add":
                comm = abs(filled_qty * price) * commission_pct / 100.0
                equity -= comm
                trade_commission += comm
                current_entry_qty += filled_qty

        # Record trade when position closes
        if prev_state not in (PositionState.FLAT, PositionState.CLOSED) and snapshot.state == PositionState.CLOSED:
            trade_pnl = snapshot.realized_pnl
            # Net of any previous trades' PnL
            prior_pnl = sum(t.pnl for t in trades)
            net_pnl = trade_pnl - prior_pnl
            equity += net_pnl

            trades.append(TradeRecord(
                entry_bar=current_entry_bar,
                exit_bar=i,
                direction=snapshot.direction,
                entry_price=current_entry_price,
                exit_price=closes[i],
                quantity=current_entry_qty,
                pnl=net_pnl,
                exit_reason=result.reason or "",
                commission=trade_commission,
            ))
            trade_commission = 0.0  # Reset for next trade
            current_entry_qty = 0.0
            # Reset snapshot to FLAT for next trade
            snapshot = fsm.reset(snapshot)

        equity_curve[i] = equity

    return BacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        final_equity=equity,
        total_return_pct=(equity / risk_config.initial_capital - 1.0) * 100.0,
        mode="fsm",
    )


def run_simple_backtest(
    *,
    dataset: BacktestDataset,
    signals: StrategySignals,
    risk_config: RiskConfig,
) -> BacktestResult:
    """Lightweight single-position backtest (no pyramiding, no partial TP).

    Faster than FSM for high-throughput screening of archetypes A/B.
    Uses vectorised numpy where possible with a thin bar loop for
    stop-loss tracking.
    """
    ohlcv = dataset.ohlcv
    n = len(ohlcv)
    if n == 0:
        return BacktestResult(equity_curve=np.array([]), final_equity=0.0)

    opens = ohlcv["open"].values
    closes = ohlcv["close"].values
    highs = ohlcv["high"].values
    lows = ohlcv["low"].values
    entries = signals.entry_long.values if signals.entry_long is not None else np.zeros(n, dtype=bool)
    exits = signals.exit_long.values if signals.exit_long is not None else np.zeros(n, dtype=bool)

    atr = _compute_atr(highs, lows, closes, period=14)
    slip = risk_config.slippage_pct
    risk_pct = risk_config.sizing.risk_pct
    atr_mult = risk_config.stop.atr_multiple
    fixed_pct = risk_config.stop.fixed_pct
    commission = risk_config.commission_pct

    equity = risk_config.initial_capital
    equity_curve = np.full(n, equity)
    trades: list[TradeRecord] = []

    in_position = False
    entry_price = 0.0
    stop_price = 0.0
    qty = 0.0
    entry_bar = 0
    entry_comm = 0.0  # Commission paid on entry

    for i in range(n):
        equity_curve[i] = equity

        if in_position:
            # Gap-aware stop
            if closes[i] <= stop_price or lows[i] <= stop_price:
                fill = min(stop_price, opens[i])
                if slip:
                    fill *= (1 - slip / 100.0)
                pnl = (fill - entry_price) * qty
                equity += pnl
                exit_comm = abs(qty * fill) * commission / 100.0
                equity -= exit_comm
                trades.append(TradeRecord(
                    entry_bar=entry_bar, exit_bar=i, direction="long",
                    entry_price=entry_price, exit_price=fill,
                    quantity=qty, pnl=pnl, exit_reason="SL",
                    commission=entry_comm + exit_comm,
                ))
                in_position = False
            elif exits[i]:
                fill = closes[i]
                if slip:
                    fill *= (1 - slip / 100.0)
                pnl = (fill - entry_price) * qty
                equity += pnl
                exit_comm = abs(qty * fill) * commission / 100.0
                equity -= exit_comm
                trades.append(TradeRecord(
                    entry_bar=entry_bar, exit_bar=i, direction="long",
                    entry_price=entry_price, exit_price=fill,
                    quantity=qty, pnl=pnl, exit_reason="signal",
                    commission=entry_comm + exit_comm,
                ))
                in_position = False

            equity_curve[i] = equity

        if not in_position and entries[i]:
            entry_price = closes[i]
            if atr[i] > 0:
                stop_dist = atr[i] * atr_mult
            else:
                stop_dist = entry_price * fixed_pct / 100.0
            stop_price = entry_price - stop_dist
            risk_amount = equity * risk_pct / 100.0
            qty = risk_amount / stop_dist if stop_dist > 0 else 0.0
            if qty > 0:
                in_position = True
                entry_bar = i
                entry_comm = abs(qty * entry_price) * commission / 100.0
                equity -= entry_comm
                equity_curve[i] = equity

    return BacktestResult(
        equity_curve=equity_curve,
        trades=trades,
        final_equity=equity,
        total_return_pct=(equity / risk_config.initial_capital - 1.0) * 100.0,
        mode="simple",
    )


def _compute_atr(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    period: int = 14,
) -> np.ndarray:
    """Compute ATR using Wilder's smoothing (no TA-Lib dependency)."""
    n = len(high)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
    atr = np.empty(n)
    atr[:period] = 0.0
    if n >= period:
        atr[period - 1] = np.mean(tr[:period])
        for i in range(period, n):
            atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr
