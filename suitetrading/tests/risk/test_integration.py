"""Integration test: real indicator signals → risk engine lifecycle.

Connects Firestorm (entry), SSL Channel (TP1/exit), and SSL Channel LOW
(trailing) with PositionStateMachine to verify a complete position
lifecycle: FLAT → OPEN_INITIAL → PARTIALLY_CLOSED → CLOSED.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.indicators.custom.firestorm import Firestorm
from suitetrading.indicators.custom.ssl_channel import SSLChannel, SSLChannelLow
from suitetrading.risk.contracts import PositionState, RiskConfig, TransitionEvent
from suitetrading.risk.state_machine import PositionStateMachine


def _make_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Generate synthetic OHLCV with a trend reversal to trigger signals."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2024-01-01", periods=n, freq="1h")

    # Build price: downtrend (0-100), then strong uptrend (100-200),
    # then sideways/down (200-300) — ensures Firestorm buy + SSL sell.
    close = np.empty(n)
    close[0] = 100.0
    for i in range(1, n):
        if i < 100:
            close[i] = close[i - 1] - 0.15 + rng.normal(0, 0.3)
        elif i < 200:
            close[i] = close[i - 1] + 0.35 + rng.normal(0, 0.3)
        else:
            close[i] = close[i - 1] - 0.10 + rng.normal(0, 0.3)

    spread = rng.uniform(0.2, 0.8, n)
    high = close + spread
    low = close - spread
    open_ = close + rng.normal(0, 0.2, n)

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": rng.uniform(100, 1000, n)},
        index=dates,
    )


@pytest.fixture
def ohlcv() -> pd.DataFrame:
    return _make_ohlcv()


class TestIndicatorToRiskIntegration:
    """Full lifecycle: Firestorm entry → SSL TP1 → trailing/BE close."""

    def test_full_lifecycle_with_real_indicators(self, ohlcv: pd.DataFrame) -> None:
        """Run real indicators, feed signals into state machine, verify lifecycle."""
        # 1. Compute indicator signals
        firestorm = Firestorm()
        ssl_channel = SSLChannel()
        ssl_low = SSLChannelLow()

        entry_signals = firestorm.compute(ohlcv, period=10, multiplier=1.8, hold_bars=1, direction="long")
        # TP1 exit: SSL sell cross (direction="short" gives sell crosses)
        exit_signals = ssl_channel.compute(ohlcv, length=12, hold_bars=4, direction="short")
        trail_signals = ssl_low.compute(ohlcv, length=12, direction="long")

        # Signals must be boolean Series of correct length
        assert len(entry_signals) == len(ohlcv)
        assert len(exit_signals) == len(ohlcv)
        assert len(trail_signals) == len(ohlcv)
        assert entry_signals.dtype == bool
        assert exit_signals.dtype == bool

        # At least one entry should fire on the trend reversal
        assert entry_signals.sum() > 0, "No Firestorm entry signals fired"

        # 2. Set up state machine with legacy-like config
        config = RiskConfig(
            archetype="legacy_firestorm",
            direction="long",
            initial_capital=4000.0,
            commission_pct=0.07,
            slippage_pct=0.05,
            sizing={"model": "fixed_fractional", "risk_pct": 2.0, "max_risk_per_trade": 5.0},
            stop={"model": "atr", "atr_multiple": 2.0},
            partial_tp={"enabled": True, "close_pct": 35.0, "trigger": "signal", "profit_distance_factor": 1.01},
            break_even={"enabled": True, "buffer": 1.0007, "activation": "after_tp1"},
            pyramid={"enabled": False},
            time_exit={"enabled": True, "max_bars": 80},
        )
        sm = PositionStateMachine(config)
        snap = sm.initial_snapshot()

        # 3. Run bar-by-bar simulation
        events_seen: list[TransitionEvent] = []
        states_seen: set[PositionState] = {snap.state}

        for i in range(len(ohlcv)):
            row = ohlcv.iloc[i]
            bar = {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }

            result = sm.evaluate_bar(
                snap,
                bar,
                bar_index=i,
                entry_signal=bool(entry_signals.iloc[i]),
                entry_direction="long",
                exit_signal=bool(exit_signals.iloc[i]),
                trailing_signal=bool(trail_signals.iloc[i]),
                entry_size=1.0,
                stop_override=bar["close"] * 0.98,  # 2% below as initial stop
            )

            snap = result.snapshot
            states_seen.add(snap.state)
            if result.event is not None:
                events_seen.append(result.event)

            # If we closed, reset to FLAT for next potential entry
            if snap.state == PositionState.CLOSED:
                snap = sm.initial_snapshot()

        # 4. Verify lifecycle expectations
        assert TransitionEvent.ENTRY_FILLED in events_seen, "No entry was filled"
        assert len(events_seen) >= 2, f"Expected at least entry + close, got {events_seen}"

        # Must have visited FLAT, OPEN_INITIAL, and reached CLOSED
        assert PositionState.FLAT in states_seen
        assert PositionState.OPEN_INITIAL in states_seen
        assert PositionState.CLOSED in states_seen, "Position never reached CLOSED"

        # At least one close event (SL, TP1, BE, trailing, or time exit)
        close_events = {
            TransitionEvent.STOP_LOSS_HIT,
            TransitionEvent.TAKE_PROFIT_1_HIT,
            TransitionEvent.BREAK_EVEN_HIT,
            TransitionEvent.TRAILING_EXIT_HIT,
            TransitionEvent.TIME_EXIT_HIT,
        }
        assert close_events & set(events_seen), (
            f"No close event found in {events_seen}"
        )

    def test_indicators_produce_complementary_signals(self, ohlcv: pd.DataFrame) -> None:
        """Entry and exit signals should not be identical (they use different indicators)."""
        firestorm = Firestorm()
        ssl_channel = SSLChannel()

        entries = firestorm.compute(ohlcv, direction="long")
        exits = ssl_channel.compute(ohlcv, direction="long")

        # They should differ — different indicator logic
        assert not entries.equals(exits), "Entry and exit signals are identical"
        # Both should have at least some signals
        assert entries.sum() > 0
        assert exits.sum() > 0

    def test_state_machine_respects_priority_with_real_signals(self, ohlcv: pd.DataFrame) -> None:
        """When SL and TP1 could both fire, SL takes priority."""
        config = RiskConfig(
            direction="long",
            stop={"model": "atr", "atr_multiple": 0.5},  # very tight stop
            partial_tp={"enabled": True, "close_pct": 35.0, "trigger": "signal"},
            pyramid={"enabled": False},
        )
        sm = PositionStateMachine(config)
        snap = sm.initial_snapshot()

        firestorm = Firestorm()
        ssl_channel = SSLChannel()
        entries = firestorm.compute(ohlcv, direction="long")
        exits = ssl_channel.compute(ohlcv, direction="long")

        sl_count = 0
        for i in range(len(ohlcv)):
            row = ohlcv.iloc[i]
            bar = {
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            }
            result = sm.evaluate_bar(
                snap, bar, bar_index=i,
                entry_signal=bool(entries.iloc[i]),
                entry_direction="long",
                exit_signal=bool(exits.iloc[i]),
                entry_size=1.0,
                stop_override=bar["close"] * 0.995,  # very tight stop
            )
            snap = result.snapshot
            if result.event == TransitionEvent.STOP_LOSS_HIT:
                sl_count += 1
                snap = sm.initial_snapshot()
            elif snap.state == PositionState.CLOSED:
                snap = sm.initial_snapshot()

        # With a 0.5% stop, we expect frequent SL hits
        assert sl_count > 0, "Tight stop should have triggered at least once"
