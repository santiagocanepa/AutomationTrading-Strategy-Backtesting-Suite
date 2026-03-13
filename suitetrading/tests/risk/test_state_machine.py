"""Tests for PositionStateMachine — deterministic bar FSM."""

from __future__ import annotations

import pytest

from suitetrading.risk.contracts import (
    PositionSnapshot,
    PositionState,
    RiskConfig,
    TransitionEvent,
)
from suitetrading.risk.state_machine import PositionStateMachine


# ── Helpers ───────────────────────────────────────────────────────────


def _cfg(**overrides) -> RiskConfig:
    """Build a RiskConfig with sensible test defaults."""
    data: dict = {
        "initial_capital": 10_000,
        "sizing": {"model": "fixed_fractional", "risk_pct": 1.0},
        "partial_tp": {"enabled": True, "close_pct": 50.0, "trigger": "signal", "profit_distance_factor": 1.01},
        "break_even": {"enabled": True, "buffer": 1.001, "activation": "after_tp1"},
        "pyramid": {"enabled": True, "max_adds": 2, "block_bars": 5, "threshold_factor": 1.0},
        "time_exit": {"enabled": False},
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(data.get(k), dict):
            data[k].update(v)
        else:
            data[k] = v
    return RiskConfig(**data)


def _bar(o=100.0, h=105.0, l=95.0, c=102.0) -> dict[str, float]:
    return {"open": o, "high": h, "low": l, "close": c}


def _enter_long(fsm: PositionStateMachine, *, price: float = 100.0, stop: float = 95.0, size: float = 10.0, bar_index: int = 0):
    """Helper: put FSM into OPEN_INITIAL long."""
    snap = fsm.initial_snapshot()
    bar = {"open": price, "high": price + 1, "low": price - 1, "close": price}
    result = fsm.evaluate_bar(
        snap, bar, bar_index,
        entry_signal=True, entry_direction="long",
        entry_size=size, stop_override=stop,
    )
    return result.snapshot


# ═══════════════════════════════════════════════════════════════════════════════
# Entry
# ═══════════════════════════════════════════════════════════════════════════════


class TestEntry:
    def test_entry_from_flat(self):
        fsm = PositionStateMachine(_cfg())
        snap = fsm.initial_snapshot()
        assert snap.state == PositionState.FLAT

        result = fsm.evaluate_bar(
            snap, _bar(c=100.0), 0,
            entry_signal=True, entry_direction="long",
            entry_size=10.0, stop_override=95.0,
        )
        assert result.snapshot.state == PositionState.OPEN_INITIAL
        assert result.event == TransitionEvent.ENTRY_FILLED
        assert result.snapshot.direction == "long"
        assert result.snapshot.quantity == 10.0
        assert result.snapshot.avg_entry_price == pytest.approx(100.0)
        assert result.snapshot.stop_price == pytest.approx(95.0)

    def test_no_entry_without_signal(self):
        fsm = PositionStateMachine(_cfg())
        snap = fsm.initial_snapshot()
        result = fsm.evaluate_bar(snap, _bar(), 0, entry_signal=False)
        assert result.snapshot.state == PositionState.FLAT
        assert result.event is None

    def test_short_entry(self):
        fsm = PositionStateMachine(_cfg())
        snap = fsm.initial_snapshot()
        result = fsm.evaluate_bar(
            snap, _bar(c=100.0), 0,
            entry_signal=True, entry_direction="short",
            entry_size=5.0, stop_override=105.0,
        )
        assert result.snapshot.direction == "short"
        assert result.snapshot.quantity == 5.0


# ═══════════════════════════════════════════════════════════════════════════════
# Stop-loss
# ═══════════════════════════════════════════════════════════════════════════════


class TestStopLoss:
    def test_long_stop_hit(self):
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, bar_index=0)

        # bar low touches stop
        result = fsm.evaluate_bar(snap, _bar(l=94.0), 1)
        assert result.snapshot.state == PositionState.CLOSED
        assert result.event == TransitionEvent.STOP_LOSS_HIT
        assert result.snapshot.quantity == 0.0

    def test_long_stop_not_hit(self):
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, bar_index=0)

        result = fsm.evaluate_bar(snap, _bar(l=96.0, c=102.0), 1)
        assert result.snapshot.state == PositionState.OPEN_INITIAL
        assert result.event is None

    def test_short_stop_hit(self):
        fsm = PositionStateMachine(_cfg())
        snap = fsm.initial_snapshot()
        result = fsm.evaluate_bar(
            snap, _bar(c=100.0), 0,
            entry_signal=True, entry_direction="short",
            entry_size=10.0, stop_override=105.0,
        )
        snap = result.snapshot
        # high touches stop
        result = fsm.evaluate_bar(snap, _bar(h=106.0), 1)
        assert result.event == TransitionEvent.STOP_LOSS_HIT
        assert result.snapshot.state == PositionState.CLOSED

    def test_stop_loss_has_priority_over_entry(self):
        """SL fires even if entry_signal is True on same bar."""
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, bar_index=0)

        result = fsm.evaluate_bar(
            snap, _bar(l=90.0), 1,
            entry_signal=True, entry_direction="long",
            entry_size=5.0,
        )
        assert result.event == TransitionEvent.STOP_LOSS_HIT

    def test_stop_loss_pnl_calculation(self):
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        result = fsm.evaluate_bar(snap, _bar(l=94.0), 1)
        # PnL = (95 - 100) * 10 = -50
        assert result.snapshot.realized_pnl == pytest.approx(-50.0)


# ═══════════════════════════════════════════════════════════════════════════════
# Partial take-profit (TP1)
# ═══════════════════════════════════════════════════════════════════════════════


class TestTakeProfit1:
    def test_tp1_on_exit_signal_in_profit(self):
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        # Price moved up and exit_signal fires
        result = fsm.evaluate_bar(
            snap, _bar(c=102.0, l=101.0), 20,
            exit_signal=True,
        )
        assert result.event == TransitionEvent.TAKE_PROFIT_1_HIT
        assert result.snapshot.tp1_hit is True
        assert result.snapshot.quantity == pytest.approx(5.0)  # 50% closed
        assert result.snapshot.realized_pnl == pytest.approx(10.0)  # (102-100)*5

    def test_no_tp1_without_exit_signal(self):
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, bar_index=0)

        result = fsm.evaluate_bar(snap, _bar(c=102.0, l=101.0), 20)
        assert result.snapshot.tp1_hit is False

    def test_tp1_not_repeated(self):
        """TP1 should only fire once."""
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        r1 = fsm.evaluate_bar(snap, _bar(c=102.0, l=101.0), 20, exit_signal=True)
        assert r1.snapshot.tp1_hit is True

        r2 = fsm.evaluate_bar(r1.snapshot, _bar(c=104.0, l=103.0), 21, exit_signal=True)
        # TP1 already hit — should not repeat
        assert r2.event != TransitionEvent.TAKE_PROFIT_1_HIT


# ═══════════════════════════════════════════════════════════════════════════════
# Break-even
# ═══════════════════════════════════════════════════════════════════════════════


class TestBreakEven:
    def test_be_activates_after_tp1(self):
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        # Trigger TP1
        r1 = fsm.evaluate_bar(snap, _bar(c=102.0, l=101.0), 20, exit_signal=True)
        assert r1.snapshot.tp1_hit is True
        assert r1.snapshot.break_even_price is not None

    def test_be_closes_when_hit(self):
        cfg = _cfg(break_even={"enabled": True, "buffer": 1.001, "activation": "after_tp1"})
        fsm = PositionStateMachine(cfg)
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        # Trigger TP1
        r1 = fsm.evaluate_bar(snap, _bar(c=102.0, l=101.0), 20, exit_signal=True)
        be = r1.snapshot.break_even_price
        assert be is not None

        # Bar that touches BE level
        r2 = fsm.evaluate_bar(r1.snapshot, _bar(l=be - 0.5, c=be + 1), 21)
        assert r2.snapshot.state == PositionState.CLOSED
        assert r2.event == TransitionEvent.BREAK_EVEN_HIT


# ═══════════════════════════════════════════════════════════════════════════════
# Trailing exit
# ═══════════════════════════════════════════════════════════════════════════════


class TestTrailingExit:
    def test_trailing_exit_after_tp1(self):
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        # TP1
        r1 = fsm.evaluate_bar(snap, _bar(c=102.0, l=101.0), 20, exit_signal=True)
        assert r1.snapshot.tp1_hit is True

        # Trailing signal fires when in profit, after tp1 bar
        r2 = fsm.evaluate_bar(
            r1.snapshot, _bar(c=104.0, l=103.0), 22,
            trailing_signal=True,
        )
        assert r2.event == TransitionEvent.TRAILING_EXIT_HIT
        assert r2.snapshot.state == PositionState.CLOSED

    def test_no_trailing_before_tp1(self):
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, bar_index=0)

        result = fsm.evaluate_bar(
            snap, _bar(c=110.0), 5,
            trailing_signal=True,
        )
        assert result.event != TransitionEvent.TRAILING_EXIT_HIT

    def test_no_trailing_on_tp1_bar(self):
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        # TP1 fires on bar 20
        r1 = fsm.evaluate_bar(snap, _bar(c=102.0, l=101.0), 20, exit_signal=True)

        # Trailing signal on same bar should NOT exit (bar_index <= tp1_bar_index)
        r2 = fsm.evaluate_bar(
            r1.snapshot, _bar(c=103.0, l=102.0), 20,
            trailing_signal=True,
        )
        assert r2.event != TransitionEvent.TRAILING_EXIT_HIT


# ═══════════════════════════════════════════════════════════════════════════════
# Time exit
# ═══════════════════════════════════════════════════════════════════════════════


class TestTimeExit:
    def test_time_exit_fires(self):
        cfg = _cfg(time_exit={"enabled": True, "max_bars": 10})
        fsm = PositionStateMachine(cfg)
        snap = _enter_long(fsm, price=100.0, stop=95.0, bar_index=0)

        # Simulate 10 bars
        for i in range(1, 10):
            r = fsm.evaluate_bar(snap, _bar(l=96.0), i)
            snap = r.snapshot

        # On bar 10 the position has been in 10 bars → exit
        r = fsm.evaluate_bar(snap, _bar(l=96.0), 10)
        assert r.event == TransitionEvent.TIME_EXIT_HIT
        assert r.snapshot.state == PositionState.CLOSED

    def test_time_exit_disabled(self):
        cfg = _cfg(time_exit={"enabled": False})
        fsm = PositionStateMachine(cfg)
        snap = _enter_long(fsm, price=100.0, stop=95.0, bar_index=0)

        for i in range(1, 200):
            r = fsm.evaluate_bar(snap, _bar(l=96.0), i)
            snap = r.snapshot

        assert snap.state != PositionState.CLOSED


# ═══════════════════════════════════════════════════════════════════════════════
# Pyramiding
# ═══════════════════════════════════════════════════════════════════════════════


class TestPyramiding:
    def test_pyramid_add(self):
        cfg = _cfg(pyramid={"enabled": True, "max_adds": 2, "block_bars": 0, "threshold_factor": 1.0})
        fsm = PositionStateMachine(cfg)
        snap = _enter_long(fsm, price=100.0, stop=90.0, size=10.0, bar_index=0)

        # Price dips — threshold_dist = |90-100|/2 * 1.0 = 5
        # close=94 ≤ 100-5=95 → pyramid allowed
        r = fsm.evaluate_bar(
            snap, _bar(c=94.0, l=93.0), 1,
            entry_signal=True, entry_direction="long",
            entry_size=5.0, stop_override=90.0,
        )
        assert r.event == TransitionEvent.PYRAMID_ADD_FILLED
        assert r.snapshot.pyramid_level == 1
        assert r.snapshot.quantity == pytest.approx(15.0)

    def test_pyramid_block_bars(self):
        cfg = _cfg(pyramid={"enabled": True, "max_adds": 2, "block_bars": 10, "threshold_factor": 1.0})
        fsm = PositionStateMachine(cfg)
        snap = _enter_long(fsm, price=100.0, stop=90.0, size=10.0, bar_index=0)

        # Try pyramid on bar 5 — should be blocked (within 10 bars of last order at bar 0)
        r = fsm.evaluate_bar(
            snap, _bar(c=94.0, l=93.0), 5,
            entry_signal=True, entry_direction="long",
            entry_size=5.0,
        )
        assert r.event is None

    def test_pyramid_max_adds_respected(self):
        cfg = _cfg(pyramid={"enabled": True, "max_adds": 1, "block_bars": 0, "threshold_factor": 1.0})
        fsm = PositionStateMachine(cfg)
        snap = _enter_long(fsm, price=100.0, stop=80.0, size=10.0, bar_index=0)

        # threshold_dist = |80-100|/1 * 1.0 = 20; close must be ≤ 80
        r1 = fsm.evaluate_bar(
            snap, _bar(c=79.0, l=81.0, h=82.0), 1,
            entry_signal=True, entry_direction="long",
            entry_size=5.0, stop_override=80.0,
        )
        assert r1.event == TransitionEvent.PYRAMID_ADD_FILLED
        assert r1.snapshot.pyramid_level == 1

        # Second pyramid add should fail — max_adds=1
        r2 = fsm.evaluate_bar(
            r1.snapshot, _bar(c=75.0, l=81.0, h=82.0), 2,
            entry_signal=True, entry_direction="long",
            entry_size=5.0,
        )
        assert r2.event is None


# ═══════════════════════════════════════════════════════════════════════════════
# Reset
# ═══════════════════════════════════════════════════════════════════════════════


class TestReset:
    def test_reset_returns_flat(self):
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, bar_index=0)
        assert snap.state != PositionState.FLAT

        flat = fsm.reset(snap)
        assert flat.state == PositionState.FLAT
        assert flat.quantity == 0.0
        assert flat.direction == "flat"


# ═══════════════════════════════════════════════════════════════════════════════
# Determinism
# ═══════════════════════════════════════════════════════════════════════════════


class TestDeterminism:
    def test_same_inputs_same_output(self):
        """The FSM must be pure: identical inputs → identical outputs."""
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, bar_index=0)
        bar = _bar(l=94.0)

        r1 = fsm.evaluate_bar(snap, bar, 1)
        r2 = fsm.evaluate_bar(snap, bar, 1)

        assert r1.snapshot.state == r2.snapshot.state
        assert r1.event == r2.event
        assert r1.snapshot.realized_pnl == r2.snapshot.realized_pnl


# ═══════════════════════════════════════════════════════════════════════════════
# Priority contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestPriorityContract:
    def test_sl_has_priority_over_tp1(self):
        """If both SL and TP1 conditions met, SL must win."""
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        # Bar where low touches stop AND there's an exit signal with price in profit
        # This shouldn't be possible in reality (low ≤ stop means loss),
        # but ensures the priority contract
        result = fsm.evaluate_bar(
            snap, _bar(c=102.0, l=94.0), 20,
            exit_signal=True,
        )
        assert result.event == TransitionEvent.STOP_LOSS_HIT


# ═══════════════════════════════════════════════════════════════════════════════
# Gap-aware stop-loss fills
# ═══════════════════════════════════════════════════════════════════════════════


def _enter_short(fsm: PositionStateMachine, *, price: float = 100.0, stop: float = 105.0, size: float = 10.0, bar_index: int = 0):
    """Helper: put FSM into OPEN_INITIAL short."""
    snap = fsm.initial_snapshot()
    bar = {"open": price, "high": price + 1, "low": price - 1, "close": price}
    result = fsm.evaluate_bar(
        snap, bar, bar_index,
        entry_signal=True, entry_direction="short",
        entry_size=size, stop_override=stop,
    )
    return result.snapshot


class TestGapAwareSL:
    def test_long_gap_down_fills_at_open(self):
        """Gap-down past stop → fill at bar open, not stop price."""
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        # Bar opens at 90 (gap down past 95)
        result = fsm.evaluate_bar(snap, _bar(o=90.0, h=91.0, l=89.0, c=90.5), 1)
        assert result.event == TransitionEvent.STOP_LOSS_HIT
        # PnL = (90 - 100) * 10 = -100, not (95-100)*10=-50
        assert result.snapshot.realized_pnl == pytest.approx(-100.0)

    def test_short_gap_up_fills_at_open(self):
        """Gap-up past stop → fill at bar open, not stop price."""
        fsm = PositionStateMachine(_cfg())
        snap = _enter_short(fsm, price=100.0, stop=105.0, size=10.0, bar_index=0)

        # Bar opens at 110 (gap up past 105)
        result = fsm.evaluate_bar(snap, _bar(o=110.0, h=112.0, l=109.0, c=111.0), 1)
        assert result.event == TransitionEvent.STOP_LOSS_HIT
        # PnL = (100 - 110) * 10 = -100
        assert result.snapshot.realized_pnl == pytest.approx(-100.0)

    def test_no_gap_fills_at_stop(self):
        """Normal touch (no gap) → fill at theoretical stop price."""
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        # Bar opens at 97 (above stop), low touches 94
        result = fsm.evaluate_bar(snap, _bar(o=97.0, h=98.0, l=94.0, c=96.0), 1)
        assert result.event == TransitionEvent.STOP_LOSS_HIT
        # min(95, 97) = 95 → PnL = (95-100)*10 = -50
        assert result.snapshot.realized_pnl == pytest.approx(-50.0)

    def test_gap_pnl_worse_than_theoretical(self):
        """Gap fill always produces worse PnL than theoretical stop."""
        fsm = PositionStateMachine(_cfg())
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        # Normal stop
        r_normal = fsm.evaluate_bar(snap, _bar(o=97.0, l=94.0, c=96.0), 1)
        # Gap stop
        r_gap = fsm.evaluate_bar(snap, _bar(o=90.0, l=89.0, c=90.5), 1)

        assert r_gap.snapshot.realized_pnl < r_normal.snapshot.realized_pnl


# ═══════════════════════════════════════════════════════════════════════════════
# Slippage
# ═══════════════════════════════════════════════════════════════════════════════


class TestSlippage:
    def test_slippage_reduces_long_sl_fill(self):
        """Slippage makes long SL fill worse (lower price)."""
        cfg_slip = _cfg(slippage_pct=0.1)
        cfg_no = _cfg(slippage_pct=0.0)

        fsm_slip = PositionStateMachine(cfg_slip)
        fsm_no = PositionStateMachine(cfg_no)

        snap_slip = _enter_long(fsm_slip, price=100.0, stop=95.0, size=10.0)
        snap_no = _enter_long(fsm_no, price=100.0, stop=95.0, size=10.0)

        bar = _bar(o=97.0, l=94.0, c=96.0)
        r_slip = fsm_slip.evaluate_bar(snap_slip, bar, 1)
        r_no = fsm_no.evaluate_bar(snap_no, bar, 1)

        # Slippage → worse PnL for long
        assert r_slip.snapshot.realized_pnl < r_no.snapshot.realized_pnl

    def test_slippage_increases_short_sl_fill(self):
        """Slippage makes short SL fill worse (higher price)."""
        cfg_slip = _cfg(slippage_pct=0.1)
        cfg_no = _cfg(slippage_pct=0.0)

        fsm_slip = PositionStateMachine(cfg_slip)
        fsm_no = PositionStateMachine(cfg_no)

        snap_slip = _enter_short(fsm_slip, price=100.0, stop=105.0, size=10.0)
        snap_no = _enter_short(fsm_no, price=100.0, stop=105.0, size=10.0)

        bar = _bar(o=103.0, h=106.0, l=102.0, c=104.0)
        r_slip = fsm_slip.evaluate_bar(snap_slip, bar, 1)
        r_no = fsm_no.evaluate_bar(snap_no, bar, 1)

        # Slippage → worse PnL for short
        assert r_slip.snapshot.realized_pnl < r_no.snapshot.realized_pnl

    def test_zero_slippage_no_effect(self):
        """slippage_pct=0 → identical PnL to baseline."""
        fsm = PositionStateMachine(_cfg(slippage_pct=0.0))
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0)

        result = fsm.evaluate_bar(snap, _bar(o=97.0, l=94.0), 1)
        # Fill = min(95, 97) = 95 → PnL = (95-100)*10 = -50
        assert result.snapshot.realized_pnl == pytest.approx(-50.0)

    def test_slippage_on_r_multiple_tp1(self):
        """Slippage applies to R-multiple TP1 target price."""
        cfg_slip = _cfg(slippage_pct=0.1, partial_tp={"enabled": True, "close_pct": 50.0, "trigger": "r_multiple", "r_multiple": 1.0})
        cfg_no = _cfg(slippage_pct=0.0, partial_tp={"enabled": True, "close_pct": 50.0, "trigger": "r_multiple", "r_multiple": 1.0})

        fsm_slip = PositionStateMachine(cfg_slip)
        fsm_no = PositionStateMachine(cfg_no)

        snap_slip = _enter_long(fsm_slip, price=100.0, stop=95.0, size=10.0)
        snap_no = _enter_long(fsm_no, price=100.0, stop=95.0, size=10.0)

        # target = 100 + 5*1.0 = 105. high=106 triggers
        bar = _bar(o=104.0, h=106.0, l=103.0, c=105.0)
        r_slip = fsm_slip.evaluate_bar(snap_slip, bar, 1)
        r_no = fsm_no.evaluate_bar(snap_no, bar, 1)

        assert r_slip.event == TransitionEvent.TAKE_PROFIT_1_HIT
        assert r_no.event == TransitionEvent.TAKE_PROFIT_1_HIT
        assert r_slip.snapshot.realized_pnl < r_no.snapshot.realized_pnl

    def test_slippage_on_tp1(self):
        """Slippage also affects TP1 fill."""
        cfg_slip = _cfg(slippage_pct=0.1)
        cfg_no = _cfg(slippage_pct=0.0)

        fsm_slip = PositionStateMachine(cfg_slip)
        fsm_no = PositionStateMachine(cfg_no)

        snap_slip = _enter_long(fsm_slip, price=100.0, stop=95.0, size=10.0)
        snap_no = _enter_long(fsm_no, price=100.0, stop=95.0, size=10.0)

        bar = _bar(o=102.0, h=103.0, l=101.0, c=102.0)
        r_slip = fsm_slip.evaluate_bar(snap_slip, bar, 20, exit_signal=True)
        r_no = fsm_no.evaluate_bar(snap_no, bar, 20, exit_signal=True)

        assert r_slip.event == TransitionEvent.TAKE_PROFIT_1_HIT
        assert r_no.event == TransitionEvent.TAKE_PROFIT_1_HIT
        # Slippage reduces long TP1 profit
        assert r_slip.snapshot.realized_pnl < r_no.snapshot.realized_pnl


# ═══════════════════════════════════════════════════════════════════════════════
# R-Multiple TP1
# ═══════════════════════════════════════════════════════════════════════════════


def _r_multiple_cfg(**overrides) -> RiskConfig:
    """RiskConfig with r_multiple TP1 trigger and no slippage."""
    data: dict = {
        "initial_capital": 10_000,
        "slippage_pct": 0.0,
        "sizing": {"model": "fixed_fractional", "risk_pct": 1.0},
        "partial_tp": {"enabled": True, "close_pct": 50.0, "trigger": "r_multiple", "r_multiple": 1.0},
        "break_even": {"enabled": True, "buffer": 1.001, "activation": "after_tp1"},
        "pyramid": {"enabled": False, "max_adds": 0},
        "time_exit": {"enabled": False},
    }
    for k, v in overrides.items():
        if isinstance(v, dict) and isinstance(data.get(k), dict):
            data[k].update(v)
        else:
            data[k] = v
    return RiskConfig(**data)


class TestRMultipleTP1:
    def test_r_multiple_tp1_long_hit_by_high(self):
        """Long TP1 fires when bar high reaches entry + stop_dist * r_multiple."""
        cfg = _r_multiple_cfg(partial_tp={"enabled": True, "close_pct": 50.0, "trigger": "r_multiple", "r_multiple": 1.0})
        fsm = PositionStateMachine(cfg)
        # entry=100, stop=95 → stop_dist=5, target=105
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        result = fsm.evaluate_bar(snap, _bar(o=103.0, h=106.0, l=102.0, c=104.0), 1)
        assert result.event == TransitionEvent.TAKE_PROFIT_1_HIT
        assert result.snapshot.tp1_hit is True
        assert result.snapshot.quantity == pytest.approx(5.0)

    def test_r_multiple_tp1_long_not_reached(self):
        """TP1 does NOT fire when high < target."""
        cfg = _r_multiple_cfg(partial_tp={"enabled": True, "close_pct": 50.0, "trigger": "r_multiple", "r_multiple": 1.0})
        fsm = PositionStateMachine(cfg)
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        # target=105, high=104 → not reached
        result = fsm.evaluate_bar(snap, _bar(o=103.0, h=104.0, l=102.0, c=103.5), 1)
        assert result.snapshot.tp1_hit is False
        assert result.event != TransitionEvent.TAKE_PROFIT_1_HIT

    def test_r_multiple_tp1_no_exit_signal_needed(self):
        """R-multiple trigger does not depend on exit_signal."""
        cfg = _r_multiple_cfg()
        fsm = PositionStateMachine(cfg)
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        # No exit_signal provided, but high reaches target
        result = fsm.evaluate_bar(snap, _bar(o=103.0, h=106.0, l=102.0, c=104.0), 1, exit_signal=False)
        assert result.event == TransitionEvent.TAKE_PROFIT_1_HIT

    def test_r_multiple_tp1_fill_at_target_not_close(self):
        """R-multiple fill uses target price, not bar close."""
        cfg = _r_multiple_cfg()
        fsm = PositionStateMachine(cfg)
        # entry=100, stop=95 → target=105
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        result = fsm.evaluate_bar(snap, _bar(o=103.0, h=110.0, l=102.0, c=108.0), 1)
        assert result.event == TransitionEvent.TAKE_PROFIT_1_HIT
        # PnL should be (105-100)*5 = 25, NOT (108-100)*5 = 40
        assert result.snapshot.realized_pnl == pytest.approx(25.0)

    def test_r_multiple_tp1_short(self):
        """Short TP1 fires when bar low reaches entry - stop_dist * r_multiple."""
        cfg = _r_multiple_cfg()
        fsm = PositionStateMachine(cfg)
        snap = _enter_short(fsm, price=100.0, stop=105.0, size=10.0, bar_index=0)
        # stop_dist=5, target=95

        result = fsm.evaluate_bar(snap, _bar(o=97.0, h=98.0, l=94.0, c=96.0), 1)
        assert result.event == TransitionEvent.TAKE_PROFIT_1_HIT
        assert result.snapshot.tp1_hit is True
        # PnL = (100-95)*5 = 25
        assert result.snapshot.realized_pnl == pytest.approx(25.0)

    def test_r_multiple_tp1_no_stop_skips(self):
        """If stop_price is None, r_multiple TP1 returns False."""
        cfg = _r_multiple_cfg()
        fsm = PositionStateMachine(cfg)
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)
        # Remove stop_price
        from dataclasses import replace as dc_replace
        snap = dc_replace(snap, stop_price=None)

        result = fsm.evaluate_bar(snap, _bar(o=103.0, h=110.0, l=102.0, c=108.0), 1)
        assert result.snapshot.tp1_hit is False

    def test_r_multiple_tp1_then_be_chain(self):
        """Full chain: Entry → TP1 (r_multiple) → Break-even hit."""
        cfg = _r_multiple_cfg(
            partial_tp={"enabled": True, "close_pct": 50.0, "trigger": "r_multiple", "r_multiple": 0.5},
            break_even={"enabled": True, "buffer": 1.001, "activation": "after_tp1"},
        )
        fsm = PositionStateMachine(cfg)
        # entry=100, stop=95 → stop_dist=5, r_multiple=0.5 → target=102.5
        snap = _enter_long(fsm, price=100.0, stop=95.0, size=10.0, bar_index=0)

        # Bar 1: high=103 triggers TP1 at 102.5
        r1 = fsm.evaluate_bar(snap, _bar(o=101.0, h=103.0, l=100.5, c=102.0), 1)
        assert r1.event == TransitionEvent.TAKE_PROFIT_1_HIT
        assert r1.snapshot.tp1_hit is True
        assert r1.snapshot.quantity == pytest.approx(5.0)
        assert r1.snapshot.break_even_price is not None

        # Bar 2: price drops to break-even level
        be = r1.snapshot.break_even_price
        r2 = fsm.evaluate_bar(r1.snapshot, _bar(o=101.0, h=101.5, l=be - 0.5, c=be + 0.5), 2)
        assert r2.event == TransitionEvent.BREAK_EVEN_HIT
        assert r2.snapshot.state == PositionState.CLOSED
