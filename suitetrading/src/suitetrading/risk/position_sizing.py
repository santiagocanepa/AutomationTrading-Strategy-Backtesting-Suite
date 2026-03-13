"""Position sizing models: fixed fractional, ATR-based, Kelly, Optimal f.

Every sizer implements the same ``size()`` contract and respects hard
safety caps defined in :class:`SizingConfig`.
"""

from __future__ import annotations

import math
import warnings
from abc import ABC, abstractmethod

from suitetrading.risk.contracts import SizingConfig


class PositionSizer(ABC):
    """ABC for all position sizing models."""

    @abstractmethod
    def size(
        self,
        *,
        equity: float,
        entry_price: float,
        stop_price: float | None = None,
        volatility_value: float | None = None,
        strategy_stats: dict | None = None,
        portfolio_state: dict | None = None,
    ) -> float:
        """Return the position size in *base units* (e.g. contracts/coins)."""
        ...

    # ── Safety clamp applied by every concrete sizer ──────────────────

    @staticmethod
    def _clamp(raw_size: float, cfg: SizingConfig, equity: float, entry_price: float) -> float:
        """Enforce min/max size and max-leverage caps."""
        if raw_size <= 0 or not math.isfinite(raw_size):
            return 0.0
        max_from_leverage = (equity * cfg.max_leverage) / entry_price if entry_price > 0 else 0.0
        clamped = min(raw_size, cfg.max_position_size, max_from_leverage)
        if clamped < cfg.min_position_size:
            return 0.0
        return clamped


# ── Concrete sizers ───────────────────────────────────────────────────


class FixedFractionalSizer(PositionSizer):
    """Risk a fixed percentage of equity per trade.

    ``size = equity * risk_pct / |entry - stop|``
    """

    def __init__(self, cfg: SizingConfig | None = None) -> None:
        self._cfg = cfg or SizingConfig()

    def size(
        self,
        *,
        equity: float,
        entry_price: float,
        stop_price: float | None = None,
        volatility_value: float | None = None,
        strategy_stats: dict | None = None,
        portfolio_state: dict | None = None,
    ) -> float:
        if stop_price is None or entry_price == stop_price:
            return 0.0
        risk_amount = equity * self._cfg.risk_pct / 100.0
        risk_amount = min(risk_amount, equity * self._cfg.max_risk_per_trade / 100.0)
        stop_distance = abs(entry_price - stop_price)
        if stop_distance == 0:
            return 0.0
        raw = risk_amount / stop_distance
        return self._clamp(raw, self._cfg, equity, entry_price)


class ATRSizer(PositionSizer):
    """Size inversely proportional to volatility (ATR).

    ``size = equity * risk_pct / (ATR * atr_multiple)``
    """

    def __init__(self, cfg: SizingConfig | None = None) -> None:
        self._cfg = cfg or SizingConfig()

    def size(
        self,
        *,
        equity: float,
        entry_price: float,
        stop_price: float | None = None,
        volatility_value: float | None = None,
        strategy_stats: dict | None = None,
        portfolio_state: dict | None = None,
    ) -> float:
        if volatility_value is None or volatility_value <= 0:
            return 0.0
        risk_amount = equity * self._cfg.risk_pct / 100.0
        risk_amount = min(risk_amount, equity * self._cfg.max_risk_per_trade / 100.0)
        denominator = volatility_value * self._cfg.atr_multiple
        if denominator <= 0:
            return 0.0
        raw = risk_amount / denominator
        return self._clamp(raw, self._cfg, equity, entry_price)


class KellySizer(PositionSizer):
    """Kelly Criterion with fractional cap.

    ``K = win_rate - (1 - win_rate) / payoff_ratio``
    Actual fraction used: ``K * kelly_fraction``
    """

    def __init__(self, cfg: SizingConfig | None = None) -> None:
        self._cfg = cfg or SizingConfig()

    def size(
        self,
        *,
        equity: float,
        entry_price: float,
        stop_price: float | None = None,
        volatility_value: float | None = None,
        strategy_stats: dict | None = None,
        portfolio_state: dict | None = None,
    ) -> float:
        stats = strategy_stats or {}
        win_rate = stats.get("win_rate", 0.0)
        payoff_ratio = stats.get("payoff_ratio", 0.0)

        if payoff_ratio <= 0 or win_rate <= 0 or win_rate >= 1.0:
            return 0.0

        kelly_pct = win_rate - (1.0 - win_rate) / payoff_ratio
        if kelly_pct <= 0:
            return 0.0

        fractional = kelly_pct * self._cfg.kelly_fraction
        # Hard cap: never exceed max_risk_per_trade
        fractional = min(fractional, self._cfg.max_risk_per_trade / 100.0)

        risk_amount = equity * fractional
        if stop_price is not None and stop_price != entry_price:
            stop_distance = abs(entry_price - stop_price)
            raw = risk_amount / stop_distance
        else:
            raw = risk_amount / entry_price if entry_price > 0 else 0.0

        return self._clamp(raw, self._cfg, equity, entry_price)


class OptimalFSizer(PositionSizer):
    """Optimal f (Ralph Vince) — experimental.

    Maximises terminal wealth relative over historical trades.
    Always emits a warning: not recommended as default.
    """

    def __init__(self, cfg: SizingConfig | None = None) -> None:
        self._cfg = cfg or SizingConfig()

    def size(
        self,
        *,
        equity: float,
        entry_price: float,
        stop_price: float | None = None,
        volatility_value: float | None = None,
        strategy_stats: dict | None = None,
        portfolio_state: dict | None = None,
    ) -> float:
        stats = strategy_stats or {}
        trades: list[float] = stats.get("trades", [])
        if len(trades) < 10:
            return 0.0

        optimal_f = self._compute_optimal_f(trades)
        if optimal_f <= 0:
            return 0.0

        warnings.warn(
            "OptimalFSizer is experimental — consider fractional Kelly instead",
            UserWarning,
            stacklevel=2,
        )

        # Use half of optimal_f as safety margin
        fraction = optimal_f * 0.5
        fraction = min(fraction, self._cfg.max_risk_per_trade / 100.0)
        risk_amount = equity * fraction

        if stop_price is not None and stop_price != entry_price:
            raw = risk_amount / abs(entry_price - stop_price)
        else:
            raw = risk_amount / entry_price if entry_price > 0 else 0.0

        return self._clamp(raw, self._cfg, equity, entry_price)

    @staticmethod
    def _compute_optimal_f(trades: list[float]) -> float:
        """Find the f that maximises TWR over the trade sequence."""
        biggest_loss = abs(min(trades))
        if biggest_loss == 0:
            return 0.0

        best_f = 0.0
        best_twr = 0.0
        for f_int in range(1, 101):
            f_test = f_int / 100.0
            twr = 1.0
            for trade in trades:
                hpr = 1.0 + f_test * (-trade / biggest_loss)
                if hpr <= 0:
                    twr = 0.0
                    break
                twr *= hpr
            if twr > best_twr:
                best_twr = twr
                best_f = f_test
        return best_f


# ── Factory ───────────────────────────────────────────────────────────

_SIZERS: dict[str, type[PositionSizer]] = {
    "fixed_fractional": FixedFractionalSizer,
    "atr": ATRSizer,
    "kelly": KellySizer,
    "optimal_f": OptimalFSizer,
}


def create_sizer(cfg: SizingConfig) -> PositionSizer:
    """Instantiate a sizer from config."""
    cls = _SIZERS.get(cfg.model)
    if cls is None:
        raise ValueError(f"Unknown sizing model: {cfg.model!r}. Available: {list(_SIZERS)}")
    return cls(cfg)
