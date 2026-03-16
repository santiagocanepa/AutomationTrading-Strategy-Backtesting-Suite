"""Position lifecycle state machine.

Implements a deterministic, bar-based FSM that processes OHLCV bars and
risk signals to manage the full position lifecycle: entry, pyramiding,
partial take-profit, break-even, trailing and exit.

Evaluation priority per bar (immutable contract):
    1. Stop-loss
    2. Partial TP (TP1)
    3. Break-even
    4. Trailing exit
    5. New entry / pyramid add
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from typing import Any

from suitetrading.risk.contracts import (
    PositionSnapshot,
    PositionState,
    RiskConfig,
    TransitionEvent,
    TransitionResult,
)

# Re-export for backward compatibility
__all__ = [
    "PositionState",
    "PositionStateMachine",
]


class PositionStateMachine:
    """Deterministic position lifecycle state machine.

    The FSM is *pure* — ``evaluate_bar`` returns a new ``TransitionResult``
    without mutating external state, which makes it suitable for both
    sequential and vectorised simulation modes.
    """

    def __init__(self, config: RiskConfig) -> None:
        self._cfg = config

    # ── Public API ────────────────────────────────────────────────────

    def initial_snapshot(self) -> PositionSnapshot:
        """Return a fresh FLAT snapshot."""
        return PositionSnapshot()

    def evaluate_bar(
        self,
        snapshot: PositionSnapshot,
        bar: dict[str, float],
        bar_index: int,
        *,
        entry_signal: bool = False,
        entry_direction: str = "long",
        exit_signal: bool = False,
        trailing_signal: bool = False,
        entry_size: float = 0.0,
        atr_value: float | None = None,
        stop_override: float | None = None,
        indicators: dict[str, Any] | None = None,
    ) -> TransitionResult:
        """Evaluate one bar against the position snapshot.

        Applies the fixed-priority evaluation order and returns the
        resulting *TransitionResult*.  The input *snapshot* is **not**
        mutated.
        """
        snap = deepcopy(snapshot)
        orders: list[dict[str, Any]] = []
        event: TransitionEvent | None = None
        reason: str | None = None
        state_changed = False

        if snap.state not in (PositionState.FLAT, PositionState.CLOSED):
            snap.bars_in_position += 1
            snap.unrealized_pnl = self._calc_unrealized(snap, bar["close"])

        # Priority 1: Stop-loss
        if self._should_stop_loss(snap, bar):
            snap, event, reason, fill, qty = self._apply_stop_loss(snap, bar)
            orders.append(self._close_order(snap, reason, fill, qty))
            state_changed = True
            return TransitionResult(snap, event, reason, orders, state_changed)

        # Priority 2: Partial TP1
        if self._should_take_profit_1(snap, bar, exit_signal):
            snap, event, reason, tp_order = self._apply_take_profit_1(snap, bar, bar_index)
            orders.append(tp_order)
            state_changed = True
            # continue evaluation (BE may activate same bar)

        # Priority 3: Break-even
        if self._should_break_even(snap, bar):
            snap, be_event, be_reason, be_fill, be_qty = self._apply_break_even(snap, bar)
            if be_event is not None:
                orders.append(self._close_order(snap, be_reason, be_fill, be_qty))
                return TransitionResult(snap, be_event, be_reason, orders, True)
            # BE price updated but not hit — continue

        # Priority 4: Trailing exit
        if self._should_trailing_exit(snap, bar, trailing_signal, bar_index):
            snap, event, reason, fill, qty = self._apply_trailing_exit(snap, bar)
            orders.append(self._close_order(snap, reason, fill, qty))
            state_changed = True
            return TransitionResult(snap, event, reason, orders, state_changed)

        # Priority 5: Time exit
        if self._should_time_exit(snap):
            snap, event, reason, fill, qty = self._apply_time_exit(snap, bar)
            orders.append(self._close_order(snap, reason, fill, qty))
            return TransitionResult(snap, event, reason, orders, True)

        # Priority 6: Entry / Pyramid
        if entry_signal and self._can_enter(snap, bar, bar_index, entry_direction):
            snap, event, reason, entry_order = self._apply_entry(
                snap, bar, bar_index, entry_direction, entry_size, stop_override,
            )
            orders.append(entry_order)
            state_changed = True

        return TransitionResult(snap, event, reason, orders, state_changed)

    # ── Stop-loss ─────────────────────────────────────────────────────

    def _should_stop_loss(self, snap: PositionSnapshot, bar: dict[str, float]) -> bool:
        if snap.state in (PositionState.FLAT, PositionState.CLOSED):
            return False
        if snap.tp1_hit:
            return False  # after TP1, BE/trailing take over
        if snap.stop_price is None:
            return False
        if snap.direction == "long":
            return bar["low"] <= snap.stop_price
        return bar["high"] >= snap.stop_price

    def _apply_stop_loss(
        self, snap: PositionSnapshot, bar: dict[str, float],
    ) -> tuple[PositionSnapshot, TransitionEvent, str, float, float]:
        if snap.stop_price is not None:
            if snap.direction == "long":
                fill = min(snap.stop_price, bar["open"])
            else:
                fill = max(snap.stop_price, bar["open"])
        else:
            fill = bar["close"]
        fill = self._slippage_adjust(fill, snap.direction)
        original_qty = snap.quantity
        pnl = self._fill_pnl(snap, fill, original_qty)
        snap = replace(
            snap,
            state=PositionState.CLOSED,
            realized_pnl=snap.realized_pnl + pnl,
            unrealized_pnl=0.0,
            quantity=0.0,
        )
        direction_label = "L" if snap.direction == "long" else "S"
        return snap, TransitionEvent.STOP_LOSS_HIT, f"SL {direction_label}", fill, original_qty

    # ── Take-profit 1 (partial) ───────────────────────────────────────

    def _should_take_profit_1(
        self, snap: PositionSnapshot, bar: dict[str, float], exit_signal: bool,
    ) -> bool:
        if snap.state in (PositionState.FLAT, PositionState.CLOSED):
            return False
        if snap.tp1_hit:
            return False
        if not self._cfg.partial_tp.enabled:
            return False

        trigger = self._cfg.partial_tp.trigger
        if trigger == "signal":
            if not exit_signal:
                return False
            return self._is_in_profit(snap, bar["close"], self._cfg.partial_tp.profit_distance_factor)
        if trigger == "r_multiple":
            return self._check_r_multiple_tp1(snap, bar)
        # fixed_pct: no exit_signal needed, just profit distance
        return self._is_in_profit(snap, bar["close"], self._cfg.partial_tp.profit_distance_factor)

    def _check_r_multiple_tp1(self, snap: PositionSnapshot, bar: dict[str, float]) -> bool:
        if snap.stop_price is None or snap.quantity == 0:
            return False
        stop_dist = abs(snap.avg_entry_price - snap.stop_price)
        if stop_dist == 0:
            return False
        tp1_dist = stop_dist * self._cfg.partial_tp.r_multiple
        if snap.direction == "long":
            return bar["high"] >= snap.avg_entry_price + tp1_dist
        return bar["low"] <= snap.avg_entry_price - tp1_dist

    def _apply_take_profit_1(
        self,
        snap: PositionSnapshot,
        bar: dict[str, float],
        bar_index: int,
    ) -> tuple[PositionSnapshot, TransitionEvent, str, dict[str, Any]]:
        close_qty = snap.quantity * self._cfg.partial_tp.close_pct / 100.0
        remaining = snap.quantity - close_qty

        # R-multiple: fill at computed target (limit order semantics)
        if self._cfg.partial_tp.trigger == "r_multiple" and snap.stop_price is not None:
            stop_dist = abs(snap.avg_entry_price - snap.stop_price)
            tp1_dist = stop_dist * self._cfg.partial_tp.r_multiple
            if snap.direction == "long":
                tp1_target = snap.avg_entry_price + tp1_dist
            else:
                tp1_target = snap.avg_entry_price - tp1_dist
            fill = self._slippage_adjust(tp1_target, snap.direction)
        else:
            fill = self._slippage_adjust(bar["close"], snap.direction)

        pnl = self._fill_pnl(snap, fill, close_qty)

        # Set break-even price
        if snap.direction == "long":
            be_price = snap.avg_entry_price * self._cfg.break_even.buffer
        else:
            be_price = snap.avg_entry_price / self._cfg.break_even.buffer

        snap = replace(
            snap,
            state=PositionState.PARTIALLY_CLOSED,
            quantity=remaining,
            realized_pnl=snap.realized_pnl + pnl,
            tp1_hit=True,
            tp1_bar_index=bar_index,
            stop_price=be_price,
            break_even_price=be_price,
        )
        direction_label = "L" if snap.direction == "long" else "S"
        order = {
            "action": "close_partial",
            "quantity": close_qty,
            "filled_qty": close_qty,
            "price": fill,
            "reason": f"TP1 {direction_label}",
        }
        return snap, TransitionEvent.TAKE_PROFIT_1_HIT, f"TP1 {direction_label}", order

    # ── Break-even ────────────────────────────────────────────────────

    def _should_break_even(self, snap: PositionSnapshot, bar: dict[str, float]) -> bool:
        if snap.state in (PositionState.FLAT, PositionState.CLOSED):
            return False
        if not self._cfg.break_even.enabled:
            return False

        activation = self._cfg.break_even.activation

        if activation == "after_tp1":
            if not snap.tp1_hit:
                return False
            return snap.break_even_price is not None

        if activation == "r_multiple":
            # Already activated and price set — keep checking for hit
            if snap.break_even_price is not None:
                return True
            # Check R-multiple threshold to activate
            if snap.stop_price is None or snap.quantity <= 0:
                return False
            r_unit = abs(snap.avg_entry_price - snap.stop_price)
            if r_unit == 0:
                return False
            unrealized_r = snap.unrealized_pnl / (r_unit * snap.quantity)
            return unrealized_r >= self._cfg.break_even.r_multiple

        if activation == "pct":
            if snap.break_even_price is not None:
                return True
            if snap.quantity <= 0 or snap.avg_entry_price <= 0:
                return False
            pnl_pct = snap.unrealized_pnl / (snap.avg_entry_price * snap.quantity) * 100
            return pnl_pct >= self._cfg.break_even.r_multiple

        return False

    def _apply_break_even(
        self, snap: PositionSnapshot, bar: dict[str, float],
    ) -> tuple[PositionSnapshot, TransitionEvent | None, str | None, float, float]:
        # Set break_even_price on first activation (r_multiple / pct modes)
        if snap.break_even_price is None:
            if snap.direction == "long":
                snap = replace(
                    snap,
                    break_even_price=snap.avg_entry_price * self._cfg.break_even.buffer,
                )
            else:
                snap = replace(
                    snap,
                    break_even_price=snap.avg_entry_price / self._cfg.break_even.buffer,
                )

        hit = False
        if snap.direction == "long" and bar["low"] <= snap.break_even_price:
            hit = True
        elif snap.direction == "short" and bar["high"] >= snap.break_even_price:
            hit = True

        if hit:
            original_qty = snap.quantity
            fill = self._slippage_adjust(snap.break_even_price, snap.direction)
            pnl = self._fill_pnl(snap, fill, original_qty)
            snap = replace(
                snap,
                state=PositionState.CLOSED,
                realized_pnl=snap.realized_pnl + pnl,
                unrealized_pnl=0.0,
                quantity=0.0,
            )
            direction_label = "L" if snap.direction == "long" else "S"
            return snap, TransitionEvent.BREAK_EVEN_HIT, f"BE {direction_label}", fill, original_qty

        # If not hit, update state to OPEN_BREAKEVEN
        if snap.state != PositionState.OPEN_BREAKEVEN:
            snap = replace(snap, state=PositionState.OPEN_BREAKEVEN)
        return snap, None, None, 0.0, 0.0

    # ── Trailing exit ─────────────────────────────────────────────────

    def _should_trailing_exit(
        self,
        snap: PositionSnapshot,
        bar: dict[str, float],
        trailing_signal: bool,
        bar_index: int,
    ) -> bool:
        if snap.state in (PositionState.FLAT, PositionState.CLOSED):
            return False
        if not trailing_signal:
            return False
        # If TP1 was hit, require profit (tighter exit post-TP1)
        if snap.tp1_hit:
            if snap.tp1_bar_index is not None and bar_index <= snap.tp1_bar_index:
                return False
            return self._is_in_profit_simple(snap, bar["close"])
        # Otherwise, signal-based exit fires unconditionally
        return True

    def _apply_trailing_exit(
        self, snap: PositionSnapshot, bar: dict[str, float],
    ) -> tuple[PositionSnapshot, TransitionEvent, str, float, float]:
        original_qty = snap.quantity
        fill = self._slippage_adjust(bar["close"], snap.direction)
        pnl = self._fill_pnl(snap, fill, original_qty)
        snap = replace(
            snap,
            state=PositionState.CLOSED,
            realized_pnl=snap.realized_pnl + pnl,
            unrealized_pnl=0.0,
            quantity=0.0,
        )
        direction_label = "L" if snap.direction == "long" else "S"
        return snap, TransitionEvent.TRAILING_EXIT_HIT, f"Trail {direction_label}", fill, original_qty

    # ── Time exit ─────────────────────────────────────────────────────

    def _should_time_exit(self, snap: PositionSnapshot) -> bool:
        if not self._cfg.time_exit.enabled:
            return False
        if snap.state in (PositionState.FLAT, PositionState.CLOSED):
            return False
        return snap.bars_in_position >= self._cfg.time_exit.max_bars

    def _apply_time_exit(
        self, snap: PositionSnapshot, bar: dict[str, float],
    ) -> tuple[PositionSnapshot, TransitionEvent, str, float, float]:
        original_qty = snap.quantity
        fill = bar["close"]
        pnl = self._fill_pnl(snap, fill, original_qty)
        snap = replace(
            snap,
            state=PositionState.CLOSED,
            realized_pnl=snap.realized_pnl + pnl,
            unrealized_pnl=0.0,
            quantity=0.0,
        )
        return snap, TransitionEvent.TIME_EXIT_HIT, "Time exit", fill, original_qty

    # ── Entry / pyramid ───────────────────────────────────────────────

    def _can_enter(
        self,
        snap: PositionSnapshot,
        bar: dict[str, float],
        bar_index: int,
        direction: str,
    ) -> bool:
        # Block bars cooldown
        if snap.last_order_bar_index is not None:
            if bar_index - snap.last_order_bar_index <= self._cfg.pyramid.block_bars:
                return False

        if snap.state == PositionState.FLAT:
            return True

        if snap.state == PositionState.CLOSED:
            return False

        # Pyramid conditions
        if not self._cfg.pyramid.enabled:
            return False
        if snap.direction != direction:
            return False
        if snap.pyramid_level >= self._cfg.pyramid.max_adds:
            return False
        # Price must have dipped enough for pyramid
        remaining = self._cfg.pyramid.max_adds - snap.pyramid_level
        if remaining <= 0:
            return False
        if snap.stop_price is not None:
            threshold_dist = (
                abs(snap.stop_price - snap.avg_entry_price)
                / remaining
                * self._cfg.pyramid.threshold_factor
            )
            if direction == "long":
                return bar["close"] <= snap.avg_entry_price - threshold_dist
            return bar["close"] >= snap.avg_entry_price + threshold_dist
        return False

    def _apply_entry(
        self,
        snap: PositionSnapshot,
        bar: dict[str, float],
        bar_index: int,
        direction: str,
        size: float,
        stop_override: float | None,
    ) -> tuple[PositionSnapshot, TransitionEvent, str, dict[str, Any]]:
        is_pyramid = snap.state not in (PositionState.FLAT, PositionState.CLOSED)
        price = bar["close"]

        if is_pyramid:
            new_qty = snap.quantity + size
            new_avg = (
                (snap.avg_entry_price * snap.quantity + price * size) / new_qty
            )
            snap = replace(
                snap,
                state=PositionState.OPEN_PYRAMIDED,
                quantity=new_qty,
                avg_entry_price=new_avg,
                pyramid_level=snap.pyramid_level + 1,
                last_order_bar_index=bar_index,
            )
            event = TransitionEvent.PYRAMID_ADD_FILLED
            reason = f"Pyramid L{snap.pyramid_level}"
        else:
            snap = replace(
                snap,
                state=PositionState.OPEN_INITIAL,
                direction=direction,
                quantity=size,
                avg_entry_price=price,
                stop_price=stop_override,
                break_even_price=None,
                realized_pnl=0.0,
                unrealized_pnl=0.0,
                pyramid_level=0,
                tp1_hit=False,
                tp1_bar_index=None,
                entry_bar_index=bar_index,
                last_order_bar_index=bar_index,
                bars_in_position=0,
            )
            event = TransitionEvent.ENTRY_FILLED
            reason = f"Entry {direction}"

        order = {
            "action": "entry" if not is_pyramid else "pyramid_add",
            "direction": direction,
            "quantity": size,
            "filled_qty": size,
            "price": price,
            "reason": reason,
        }
        return snap, event, reason, order

    def reset(self, snap: PositionSnapshot) -> PositionSnapshot:
        """Force-reset a snapshot back to FLAT."""
        return replace(
            snap,
            state=PositionState.FLAT,
            direction="flat",
            quantity=0.0,
            avg_entry_price=0.0,
            stop_price=None,
            break_even_price=None,
            realized_pnl=0.0,
            unrealized_pnl=0.0,
            pyramid_level=0,
            tp1_hit=False,
            tp1_bar_index=None,
            entry_bar_index=None,
            last_order_bar_index=None,
            bars_in_position=0,
        )

    # ── Helpers ───────────────────────────────────────────────────────

    def _slippage_adjust(self, price: float, direction: str) -> float:
        """Apply adverse slippage to a fill price."""
        pct = self._cfg.slippage_pct
        if pct == 0.0:
            return price
        if direction == "long":
            return price * (1 - pct / 100.0)
        return price * (1 + pct / 100.0)

    @staticmethod
    def _calc_unrealized(snap: PositionSnapshot, current_price: float) -> float:
        if snap.quantity == 0:
            return 0.0
        if snap.direction == "long":
            return (current_price - snap.avg_entry_price) * snap.quantity
        return (snap.avg_entry_price - current_price) * snap.quantity

    @staticmethod
    def _fill_pnl(snap: PositionSnapshot, fill_price: float, qty: float) -> float:
        if snap.direction == "long":
            return (fill_price - snap.avg_entry_price) * qty
        return (snap.avg_entry_price - fill_price) * qty

    def _is_in_profit(
        self, snap: PositionSnapshot, price: float, distance_factor: float,
    ) -> bool:
        if snap.quantity == 0:
            return False
        if snap.direction == "long":
            return price > snap.avg_entry_price and (
                abs(price - snap.avg_entry_price) >= abs(snap.avg_entry_price) * (distance_factor - 1)
            )
        return price < snap.avg_entry_price and (
            abs(snap.avg_entry_price - price) >= abs(snap.avg_entry_price) * (distance_factor - 1)
        )

    @staticmethod
    def _is_in_profit_simple(snap: PositionSnapshot, price: float) -> bool:
        if snap.direction == "long":
            return price > snap.avg_entry_price
        return price < snap.avg_entry_price

    @staticmethod
    def _close_order(
        snap: PositionSnapshot,
        reason: str | None,
        fill_price: float = 0.0,
        original_qty: float = 0.0,
    ) -> dict[str, Any]:
        return {
            "action": "close_all",
            "quantity": original_qty,
            "filled_qty": original_qty,
            "price": fill_price,
            "reason": reason,
        }
