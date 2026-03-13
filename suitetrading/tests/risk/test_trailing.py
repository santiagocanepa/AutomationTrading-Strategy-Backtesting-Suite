"""Tests for exit / trailing stop policies."""

from __future__ import annotations

import pytest

from suitetrading.risk.contracts import PositionSnapshot, PositionState
from suitetrading.risk.trailing import (
    ATRTrailingStop,
    BreakEvenPolicy,
    ChandelierExit,
    ExitPolicy,
    FixedTrailingStop,
    ParabolicSARStop,
    SignalTrailingExit,
    create_exit_policy,
)


# ── Helpers ───────────────────────────────────────────────────────────


def _long_snapshot(**kwargs) -> PositionSnapshot:
    defaults = {
        "state": PositionState.OPEN_INITIAL,
        "direction": "long",
        "quantity": 10.0,
        "avg_entry_price": 100.0,
        "stop_price": 95.0,
    }
    defaults.update(kwargs)
    return PositionSnapshot(**defaults)


def _short_snapshot(**kwargs) -> PositionSnapshot:
    defaults = {
        "state": PositionState.OPEN_INITIAL,
        "direction": "short",
        "quantity": 10.0,
        "avg_entry_price": 100.0,
        "stop_price": 105.0,
    }
    defaults.update(kwargs)
    return PositionSnapshot(**defaults)


def _bar(open_=100.0, high=105.0, low=95.0, close=102.0) -> dict[str, float]:
    return {"open": open_, "high": high, "low": low, "close": close}


# ═══════════════════════════════════════════════════════════════════════════════
# BreakEvenPolicy
# ═══════════════════════════════════════════════════════════════════════════════


class TestBreakEvenPolicy:
    def test_inactive_before_tp1(self):
        policy = BreakEvenPolicy(activation="after_tp1")
        snap = _long_snapshot(tp1_hit=False)
        should_exit, _, _ = policy.evaluate(snapshot=snap, bar=_bar())
        assert should_exit is False

    def test_long_be_hit(self):
        policy = BreakEvenPolicy(buffer=1.001, activation="after_tp1")
        snap = _long_snapshot(tp1_hit=True)
        be_price = 100.0 * 1.001  # 100.1
        bar = _bar(low=100.0)  # low ≤ be_price
        should_exit, updated_stop, reason = policy.evaluate(snapshot=snap, bar=bar)
        assert should_exit is True
        assert updated_stop == pytest.approx(be_price)
        assert "BE long" in reason

    def test_long_be_not_hit(self):
        policy = BreakEvenPolicy(buffer=1.001, activation="after_tp1")
        snap = _long_snapshot(tp1_hit=True)
        bar = _bar(low=101.0)  # low > be_price (100.1)
        should_exit, updated_stop, _ = policy.evaluate(snapshot=snap, bar=bar)
        assert should_exit is False
        assert updated_stop == pytest.approx(100.0 * 1.001)

    def test_short_be_hit(self):
        policy = BreakEvenPolicy(buffer=1.001, activation="after_tp1")
        snap = _short_snapshot(tp1_hit=True)
        be_price = 100.0 / 1.001
        bar = _bar(high=100.0)  # high ≥ be_price
        should_exit, _, reason = policy.evaluate(snapshot=snap, bar=bar)
        assert should_exit is True
        assert "BE short" in reason

    def test_r_multiple_activation(self):
        policy = BreakEvenPolicy(buffer=1.0, activation="r_multiple", r_multiple=1.0)
        snap = _long_snapshot(stop_price=95.0, tp1_hit=False)
        # Need 5pt profit for 1R; close=106 → 6pt profit → active
        bar = _bar(close=106.0, low=99.0)
        should_exit, _, _ = policy.evaluate(snapshot=snap, bar=bar)
        # BE at 100 * 1.0 = 100; low=99 ≤ 100 → hit
        assert should_exit is True


# ═══════════════════════════════════════════════════════════════════════════════
# FixedTrailingStop
# ═══════════════════════════════════════════════════════════════════════════════


class TestFixedTrailingStop:
    def test_long_trail_exit(self):
        policy = FixedTrailingStop(offset=3.0)
        snap = _long_snapshot(stop_price=None)
        bar = _bar(high=110.0, low=106.5)
        should_exit, stop, reason = policy.evaluate(snapshot=snap, bar=bar)
        # new_stop = 110 - 3 = 107; low=106.5 ≤ 107 → exit
        assert should_exit is True
        assert stop == pytest.approx(107.0)

    def test_long_trail_no_exit(self):
        policy = FixedTrailingStop(offset=3.0)
        snap = _long_snapshot(stop_price=None)
        bar = _bar(high=110.0, low=108.0)
        should_exit, stop, _ = policy.evaluate(snapshot=snap, bar=bar)
        assert should_exit is False
        assert stop == pytest.approx(107.0)

    def test_short_trail_exit(self):
        policy = FixedTrailingStop(offset=3.0)
        snap = _short_snapshot(stop_price=None)
        bar = _bar(low=90.0, high=93.5)
        should_exit, stop, _ = policy.evaluate(snapshot=snap, bar=bar)
        # new_stop = 90 + 3 = 93; high=93.5 ≥ 93 → exit
        assert should_exit is True
        assert stop == pytest.approx(93.0)

    def test_stop_ratchets_up_for_long(self):
        policy = FixedTrailingStop(offset=2.0)
        snap = _long_snapshot(stop_price=107.0)
        bar = _bar(high=112.0, low=111.0)
        should_exit, stop, _ = policy.evaluate(snapshot=snap, bar=bar)
        # new_stop = max(110, 107) = 110
        assert not should_exit
        assert stop == pytest.approx(110.0)

    def test_percentage_offset(self):
        policy = FixedTrailingStop(offset_pct=2.0)
        snap = _long_snapshot(stop_price=None)
        bar = _bar(high=100.0, low=97.5, close=98.0)
        should_exit, stop, _ = policy.evaluate(snapshot=snap, bar=bar)
        # trail_dist = 98 * 2% = 1.96; new_stop = 100 - 1.96 = 98.04
        assert stop == pytest.approx(98.04)


# ═══════════════════════════════════════════════════════════════════════════════
# ATRTrailingStop
# ═══════════════════════════════════════════════════════════════════════════════


class TestATRTrailingStop:
    def test_long_atr_trail(self):
        policy = ATRTrailingStop(atr_multiple=2.0)
        snap = _long_snapshot(stop_price=None)
        bar = _bar(high=110.0, low=107.0)
        indicators = {"atr": 2.0}
        should_exit, stop, _ = policy.evaluate(
            snapshot=snap, bar=bar, indicators=indicators,
        )
        # new_stop = 110 - 4 = 106; low=107 > 106 → no exit
        assert should_exit is False
        assert stop == pytest.approx(106.0)

    def test_short_atr_trail(self):
        policy = ATRTrailingStop(atr_multiple=2.0)
        snap = _short_snapshot(stop_price=None)
        bar = _bar(low=90.0, high=94.5)
        indicators = {"atr": 2.0}
        should_exit, stop, _ = policy.evaluate(
            snapshot=snap, bar=bar, indicators=indicators,
        )
        # new_stop = 90 + 4 = 94; high=94.5 ≥ 94 → exit
        assert should_exit is True
        assert stop == pytest.approx(94.0)

    def test_no_atr_returns_no_action(self):
        policy = ATRTrailingStop()
        snap = _long_snapshot()
        should_exit, stop, _ = policy.evaluate(snapshot=snap, bar=_bar())
        assert should_exit is False
        assert stop is None


# ═══════════════════════════════════════════════════════════════════════════════
# ChandelierExit
# ═══════════════════════════════════════════════════════════════════════════════


class TestChandelierExit:
    def test_long_chandelier(self):
        policy = ChandelierExit(atr_multiple=3.0)
        snap = _long_snapshot(stop_price=None)
        bar = _bar(high=115.0, low=105.0)
        indicators = {"atr": 2.0, "highest_high": 120.0}
        should_exit, stop, _ = policy.evaluate(
            snapshot=snap, bar=bar, indicators=indicators,
        )
        # new_stop = 120 - 6 = 114; low=105 ≤ 114 → exit
        assert should_exit is True
        assert stop == pytest.approx(114.0)

    def test_short_chandelier(self):
        policy = ChandelierExit(atr_multiple=3.0)
        snap = _short_snapshot(stop_price=None)
        bar = _bar(low=80.0, high=87.0)
        indicators = {"atr": 2.0, "lowest_low": 78.0}
        should_exit, stop, _ = policy.evaluate(
            snapshot=snap, bar=bar, indicators=indicators,
        )
        # new_stop = 78 + 6 = 84; high=87 ≥ 84 → exit
        assert should_exit is True
        assert stop == pytest.approx(84.0)


# ═══════════════════════════════════════════════════════════════════════════════
# ParabolicSARStop
# ═══════════════════════════════════════════════════════════════════════════════


class TestParabolicSARStop:
    def test_sar_tracks_state_across_bars(self):
        policy = ParabolicSARStop(af_start=0.02, af_step=0.02, af_max=0.20)
        snap = _long_snapshot()
        # Provide pre-existing state where SAR is well below the bar
        indicators: dict = {"sar_state": {"ep": 110.0, "af": 0.02, "sar": 90.0}}
        # new_sar = 90 + 0.02*(110-90) = 90.4; low=95 > 90.4 → no exit
        bar = _bar(high=112.0, low=95.0)
        should_exit, stop, _ = policy.evaluate(
            snapshot=snap, bar=bar, indicators=indicators,
        )
        assert should_exit is False
        assert stop == pytest.approx(90.4)
        assert "sar_state" in indicators
        # ep should update to new high
        assert indicators["sar_state"]["ep"] == pytest.approx(112.0)

    def test_sar_long_exit(self):
        policy = ParabolicSARStop(af_start=0.02)
        snap = _long_snapshot()
        indicators: dict = {"sar_state": {"ep": 110.0, "af": 0.1, "sar": 108.0}}
        # new_sar = 108 + 0.1*(110-108) = 108.2; low=108.0 ≤ 108.2 → exit
        bar = _bar(high=111.0, low=108.0)
        should_exit, _, reason = policy.evaluate(
            snapshot=snap, bar=bar, indicators=indicators,
        )
        assert should_exit is True
        assert "SAR long" in reason

    def test_sar_short_exit(self):
        policy = ParabolicSARStop()
        snap = _short_snapshot()
        indicators: dict = {"sar_state": {"ep": 90.0, "af": 0.1, "sar": 92.0}}
        # new_sar = 92 + 0.1*(90-92) = 91.8; high=92 ≥ 91.8 → exit
        bar = _bar(low=89.0, high=92.0)
        should_exit, _, reason = policy.evaluate(
            snapshot=snap, bar=bar, indicators=indicators,
        )
        assert should_exit is True
        assert "SAR short" in reason


# ═══════════════════════════════════════════════════════════════════════════════
# SignalTrailingExit
# ═══════════════════════════════════════════════════════════════════════════════


class TestSignalTrailingExit:
    def test_exits_on_signal_after_tp1(self):
        policy = SignalTrailingExit(signal_key="ssl_exit")
        snap = _long_snapshot(tp1_hit=True, tp1_bar_index=5, avg_entry_price=100.0)
        bar = _bar(close=110.0)
        indicators = {"ssl_exit": True}
        should_exit, _, reason = policy.evaluate(
            snapshot=snap, bar=bar, indicators=indicators, bar_index=10,
        )
        assert should_exit is True
        assert "Signal trail long" in reason

    def test_no_signal_no_exit(self):
        policy = SignalTrailingExit(signal_key="ssl_exit")
        snap = _long_snapshot(tp1_hit=True, tp1_bar_index=5)
        indicators = {"ssl_exit": False}
        should_exit, _, _ = policy.evaluate(
            snapshot=snap, bar=_bar(close=110.0), indicators=indicators, bar_index=10,
        )
        assert should_exit is False

    def test_no_exit_before_tp1(self):
        policy = SignalTrailingExit(signal_key="ssl_exit", require_after_tp1=True)
        snap = _long_snapshot(tp1_hit=False)
        indicators = {"ssl_exit": True}
        should_exit, _, _ = policy.evaluate(
            snapshot=snap, bar=_bar(close=110.0), indicators=indicators,
        )
        assert should_exit is False

    def test_no_exit_if_not_in_profit(self):
        policy = SignalTrailingExit(signal_key="ssl_exit", require_profit=True)
        snap = _long_snapshot(tp1_hit=True, tp1_bar_index=0, avg_entry_price=100.0)
        indicators = {"ssl_exit": True}
        # close < entry → not in profit
        should_exit, _, _ = policy.evaluate(
            snapshot=snap, bar=_bar(close=90.0), indicators=indicators, bar_index=5,
        )
        assert should_exit is False

    def test_short_signal_exit(self):
        policy = SignalTrailingExit(signal_key="ssl_exit")
        snap = _short_snapshot(tp1_hit=True, tp1_bar_index=1, avg_entry_price=100.0)
        bar = _bar(close=90.0)
        indicators = {"ssl_exit": True}
        should_exit, _, reason = policy.evaluate(
            snapshot=snap, bar=bar, indicators=indicators, bar_index=5,
        )
        assert should_exit is True
        assert "short" in reason


# ═══════════════════════════════════════════════════════════════════════════════
# Factory
# ═══════════════════════════════════════════════════════════════════════════════


class TestCreateExitPolicy:
    @pytest.mark.parametrize("model", ["break_even", "fixed", "atr", "chandelier", "parabolic_sar", "signal"])
    def test_creates_known_policies(self, model: str):
        policy = create_exit_policy(model)
        assert isinstance(policy, ExitPolicy)

    def test_unknown_model_raises(self):
        with pytest.raises(ValueError, match="Unknown exit policy"):
            create_exit_policy("nonexistent")
