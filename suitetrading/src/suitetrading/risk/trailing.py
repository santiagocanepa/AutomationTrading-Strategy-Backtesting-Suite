"""Exit policies: trailing stops (fixed, ATR, Chandelier, SAR) and signal exits.

Every policy implements ``evaluate()`` with a unified return contract:
``(should_exit, updated_stop, reason)``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import pandas as pd

from suitetrading.risk.contracts import PositionSnapshot


class ExitPolicy(ABC):
    """ABC for all exit / trailing policies."""

    @abstractmethod
    def evaluate(
        self,
        *,
        snapshot: PositionSnapshot,
        bar: dict[str, float],
        indicators: dict[str, Any] | None = None,
        bar_index: int = 0,
    ) -> tuple[bool, float | None, str | None]:
        """Evaluate the exit policy for the current bar.

        Returns
        -------
        should_exit : bool
        updated_stop : float | None
            New trailing stop price (``None`` = no change).
        reason : str | None
        """
        ...


# ── Concrete policies ─────────────────────────────────────────────────


class BreakEvenPolicy(ExitPolicy):
    """Move SL to entry price (± commission buffer) after activation condition.

    Parameters
    ----------
    buffer : float
        Multiplicative buffer for commissions (e.g. 1.0007 ≈ 0.07%).
    activation : str
        ``"after_tp1"`` | ``"r_multiple"`` | ``"pct"``.
    r_multiple : float
        Required R-multiple of profit before activation (if ``activation="r_multiple"``).
    """

    def __init__(
        self,
        buffer: float = 1.0007,
        activation: str = "after_tp1",
        r_multiple: float = 1.0,
    ) -> None:
        self._buffer = buffer
        self._activation = activation
        self._r_multiple = r_multiple

    def evaluate(
        self,
        *,
        snapshot: PositionSnapshot,
        bar: dict[str, float],
        indicators: dict[str, Any] | None = None,
        bar_index: int = 0,
    ) -> tuple[bool, float | None, str | None]:
        if not self._is_active(snapshot, bar):
            return False, None, None

        if snapshot.direction == "long":
            be_price = snapshot.avg_entry_price * self._buffer
            if bar["low"] <= be_price:
                return True, be_price, "BE long"
            return False, be_price, None
        else:
            be_price = snapshot.avg_entry_price / self._buffer
            if bar["high"] >= be_price:
                return True, be_price, "BE short"
            return False, be_price, None

    def _is_active(self, snapshot: PositionSnapshot, bar: dict[str, float]) -> bool:
        if self._activation == "after_tp1":
            return snapshot.tp1_hit
        if self._activation == "r_multiple":
            if snapshot.stop_price is None:
                return False
            risk_per_unit = abs(snapshot.avg_entry_price - snapshot.stop_price)
            if risk_per_unit == 0:
                return False
            if snapshot.direction == "long":
                profit = bar["close"] - snapshot.avg_entry_price
            else:
                profit = snapshot.avg_entry_price - bar["close"]
            return profit >= risk_per_unit * self._r_multiple
        if self._activation == "pct":
            return snapshot.tp1_hit
        return False


class FixedTrailingStop(ExitPolicy):
    """Trail by a fixed offset in price or percentage.

    Parameters
    ----------
    offset : float
        Absolute price offset from the best price.
    offset_pct : float
        Percentage offset (used if *offset* is 0).
    """

    def __init__(self, offset: float = 0.0, offset_pct: float = 1.0) -> None:
        self._offset = offset
        self._offset_pct = offset_pct

    def evaluate(
        self,
        *,
        snapshot: PositionSnapshot,
        bar: dict[str, float],
        indicators: dict[str, Any] | None = None,
        bar_index: int = 0,
    ) -> tuple[bool, float | None, str | None]:
        trail_dist = self._offset if self._offset > 0 else bar["close"] * self._offset_pct / 100.0

        if snapshot.direction == "long":
            new_stop = bar["high"] - trail_dist
            if snapshot.stop_price is not None:
                new_stop = max(new_stop, snapshot.stop_price)
            if bar["low"] <= new_stop:
                return True, new_stop, "Fixed trail long"
            return False, new_stop, None
        else:
            new_stop = bar["low"] + trail_dist
            if snapshot.stop_price is not None:
                new_stop = min(new_stop, snapshot.stop_price)
            if bar["high"] >= new_stop:
                return True, new_stop, "Fixed trail short"
            return False, new_stop, None


class ATRTrailingStop(ExitPolicy):
    """Trail at ``N × ATR`` from the extreme price.

    Expects ``indicators["atr"]`` to contain the current ATR value.
    """

    def __init__(self, atr_multiple: float = 2.5) -> None:
        self._mult = atr_multiple

    def evaluate(
        self,
        *,
        snapshot: PositionSnapshot,
        bar: dict[str, float],
        indicators: dict[str, Any] | None = None,
        bar_index: int = 0,
    ) -> tuple[bool, float | None, str | None]:
        indicators = indicators or {}
        atr = indicators.get("atr")
        if atr is None or atr <= 0:
            return False, None, None

        trail_dist = atr * self._mult

        if snapshot.direction == "long":
            new_stop = bar["high"] - trail_dist
            if snapshot.stop_price is not None:
                new_stop = max(new_stop, snapshot.stop_price)
            if bar["low"] <= new_stop:
                return True, new_stop, "ATR trail long"
            return False, new_stop, None
        else:
            new_stop = bar["low"] + trail_dist
            if snapshot.stop_price is not None:
                new_stop = min(new_stop, snapshot.stop_price)
            if bar["high"] >= new_stop:
                return True, new_stop, "ATR trail short"
            return False, new_stop, None


class ChandelierExit(ExitPolicy):
    """Chandelier exit: trail from highest-high / lowest-low minus N × ATR.

    Expects ``indicators["highest_high"]``, ``indicators["lowest_low"]``,
    and ``indicators["atr"]``.
    """

    def __init__(self, atr_multiple: float = 3.0) -> None:
        self._mult = atr_multiple

    def evaluate(
        self,
        *,
        snapshot: PositionSnapshot,
        bar: dict[str, float],
        indicators: dict[str, Any] | None = None,
        bar_index: int = 0,
    ) -> tuple[bool, float | None, str | None]:
        indicators = indicators or {}
        atr = indicators.get("atr")
        if atr is None or atr <= 0:
            return False, None, None

        if snapshot.direction == "long":
            hh = indicators.get("highest_high", bar["high"])
            new_stop = hh - self._mult * atr
            if snapshot.stop_price is not None:
                new_stop = max(new_stop, snapshot.stop_price)
            if bar["low"] <= new_stop:
                return True, new_stop, "Chandelier long"
            return False, new_stop, None
        else:
            ll = indicators.get("lowest_low", bar["low"])
            new_stop = ll + self._mult * atr
            if snapshot.stop_price is not None:
                new_stop = min(new_stop, snapshot.stop_price)
            if bar["high"] >= new_stop:
                return True, new_stop, "Chandelier short"
            return False, new_stop, None


class ParabolicSARStop(ExitPolicy):
    """Parabolic SAR trailing exit.

    Maintains internal SAR state across bars.  Caller must track and re-feed
    ``indicators["sar_state"]`` across calls (a dict with ``ep``, ``af``,
    ``sar`` keys) or let the policy initialise from the entry bar.
    """

    def __init__(
        self,
        af_start: float = 0.02,
        af_step: float = 0.02,
        af_max: float = 0.20,
    ) -> None:
        self._af_start = af_start
        self._af_step = af_step
        self._af_max = af_max

    def evaluate(
        self,
        *,
        snapshot: PositionSnapshot,
        bar: dict[str, float],
        indicators: dict[str, Any] | None = None,
        bar_index: int = 0,
    ) -> tuple[bool, float | None, str | None]:
        indicators = indicators or {}
        state = indicators.get("sar_state")

        if state is None:
            # Initialise from current bar
            if snapshot.direction == "long":
                state = {"ep": bar["high"], "af": self._af_start, "sar": bar["low"]}
            else:
                state = {"ep": bar["low"], "af": self._af_start, "sar": bar["high"]}

        ep = state["ep"]
        af = state["af"]
        sar = state["sar"]

        # Update SAR
        new_sar = sar + af * (ep - sar)

        if snapshot.direction == "long":
            if bar["low"] <= new_sar:
                return True, new_sar, "SAR long"
            if bar["high"] > ep:
                ep = bar["high"]
                af = min(af + self._af_step, self._af_max)
        else:
            if bar["high"] >= new_sar:
                return True, new_sar, "SAR short"
            if bar["low"] < ep:
                ep = bar["low"]
                af = min(af + self._af_step, self._af_max)

        # Store updated state back
        indicators["sar_state"] = {"ep": ep, "af": af, "sar": new_sar}
        return False, new_sar, None


class SignalTrailingExit(ExitPolicy):
    """Exit triggered by an external signal (e.g. SSL LOW crossover).

    Expects ``indicators[signal_key]`` to be a boolean.
    """

    def __init__(
        self,
        signal_key: str = "ssl_exit",
        require_profit: bool = True,
        require_after_tp1: bool = True,
    ) -> None:
        self._signal_key = signal_key
        self._require_profit = require_profit
        self._require_after_tp1 = require_after_tp1

    def evaluate(
        self,
        *,
        snapshot: PositionSnapshot,
        bar: dict[str, float],
        indicators: dict[str, Any] | None = None,
        bar_index: int = 0,
    ) -> tuple[bool, float | None, str | None]:
        indicators = indicators or {}
        signal = indicators.get(self._signal_key, False)
        if not signal:
            return False, None, None

        if self._require_after_tp1 and not snapshot.tp1_hit:
            return False, None, None

        if self._require_after_tp1 and snapshot.tp1_bar_index is not None:
            if bar_index <= snapshot.tp1_bar_index:
                return False, None, None

        if self._require_profit:
            if snapshot.direction == "long" and bar["close"] <= snapshot.avg_entry_price:
                return False, None, None
            if snapshot.direction == "short" and bar["close"] >= snapshot.avg_entry_price:
                return False, None, None

        direction_label = "long" if snapshot.direction == "long" else "short"
        return True, None, f"Signal trail {direction_label}"


# ── Factory ───────────────────────────────────────────────────────────

_POLICIES: dict[str, type[ExitPolicy]] = {
    "break_even": BreakEvenPolicy,
    "fixed": FixedTrailingStop,
    "atr": ATRTrailingStop,
    "chandelier": ChandelierExit,
    "parabolic_sar": ParabolicSARStop,
    "signal": SignalTrailingExit,
}


def create_exit_policy(model: str, **kwargs: Any) -> ExitPolicy:
    """Instantiate an exit policy by name."""
    cls = _POLICIES.get(model)
    if cls is None:
        raise ValueError(f"Unknown exit policy: {model!r}. Available: {list(_POLICIES)}")
    return cls(**kwargs)
