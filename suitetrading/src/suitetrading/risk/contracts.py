"""Core contracts, types and configuration for the risk management engine.

This module defines the shared vocabulary used by every other module in
``suitetrading.risk``.  It is intentionally free of heavy logic so that
imports are lightweight and circular dependencies are impossible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum, Enum, auto
from typing import Any

from pydantic import BaseModel, Field, model_validator


# ── Position lifecycle states ─────────────────────────────────────────

class PositionState(Enum):
    """States for the position lifecycle FSM."""

    FLAT = auto()
    OPEN_INITIAL = auto()
    OPEN_BREAKEVEN = auto()
    OPEN_TRAILING = auto()
    OPEN_PYRAMIDED = auto()
    PARTIALLY_CLOSED = auto()
    CLOSED = auto()


# ── Transition events ─────────────────────────────────────────────────

class TransitionEvent(StrEnum):
    """Explicit events that drive state machine transitions."""

    ENTRY_FILLED = "entry_filled"
    PYRAMID_ADD_FILLED = "pyramid_add_filled"
    STOP_LOSS_HIT = "stop_loss_hit"
    TAKE_PROFIT_1_HIT = "take_profit_1_hit"
    BREAK_EVEN_HIT = "break_even_hit"
    TRAILING_EXIT_HIT = "trailing_exit_hit"
    TIME_EXIT_HIT = "time_exit_hit"
    KILL_SWITCH_TRIGGERED = "kill_switch_triggered"
    FLAT_RESET = "flat_reset"


# ── Position snapshot ─────────────────────────────────────────────────

@dataclass
class PositionSnapshot:
    """Self-contained snapshot of a position at a given bar.

    ``quantity`` always reflects the *filled* amount, not the requested
    amount.  In bar-based mode (Sprint 3-4) every fill is complete so
    filled == requested.  In event-driven mode (Sprint 6) partial fills
    may produce intermediate snapshots where ``quantity`` < requested.
    """

    state: PositionState = PositionState.FLAT
    direction: str = "flat"  # "long" | "short" | "flat"
    quantity: float = 0.0
    avg_entry_price: float = 0.0
    stop_price: float | None = None
    break_even_price: float | None = None
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    pyramid_level: int = 0
    tp1_hit: bool = False
    tp1_bar_index: int | None = None
    entry_bar_index: int | None = None
    last_order_bar_index: int | None = None
    bars_in_position: int = 0


# ── Transition result ─────────────────────────────────────────────────

@dataclass
class TransitionResult:
    """Outcome of evaluating a single bar through the state machine.

    Each dict in ``orders`` describes an *intent*, not execution.  Keys:

    - ``action``: ``"entry"`` | ``"pyramid_add"`` | ``"close_partial"`` |
      ``"close_all"`` | ``"modify_stop"``
    - ``quantity``: requested qty
    - ``filled_qty``: filled qty (== ``quantity`` in bar-based mode)
    - ``price``: fill price (gap-aware, slippage-adjusted)

    In bar-based mode ``filled_qty`` always equals ``quantity``.
    In event-driven mode (Sprint 6), partial fills will produce
    multiple ``TransitionResult`` objects for the same order.
    """

    snapshot: PositionSnapshot
    event: TransitionEvent | None = None
    reason: str | None = None
    orders: list[dict[str, Any]] = field(default_factory=list)
    state_changed: bool = False


# ── Risk configuration (Pydantic-validated) ───────────────────────────

class SizingConfig(BaseModel):
    """Configuration for position sizing."""

    model: str = "fixed_fractional"
    risk_pct: float = Field(default=1.0, ge=0.01, le=100.0)
    kelly_fraction: float = Field(default=0.5, ge=0.01, le=1.0)
    atr_multiple: float = Field(default=2.0, ge=0.1, le=20.0)
    max_risk_per_trade: float = Field(default=5.0, ge=0.1, le=100.0)
    min_position_size: float = Field(default=0.0, ge=0.0)
    max_position_size: float = Field(default=1e12, gt=0.0)
    max_leverage: float = Field(default=1.0, ge=1.0, le=125.0)


class StopConfig(BaseModel):
    """Configuration for initial stop loss.

    Supported models: ``"atr"`` (ATR-based), ``"firestorm_tm"``
    (Firestorm TM bands), ``"fixed_pct"`` (percentage of price).
    """

    model: str = "atr"  # "atr" | "firestorm_tm" | "fixed_pct"
    atr_multiple: float = Field(default=2.0, ge=0.1, le=20.0)
    fixed_pct: float = Field(default=2.0, ge=0.01, le=50.0)
    ftm_period: int = Field(default=9, ge=2, le=100)
    ftm_multiplier: float = Field(default=1.8, ge=0.5, le=5.0)


class TrailingConfig(BaseModel):
    """Configuration for trailing stop / exit policy."""

    model: str = "atr"
    trailing_mode: str = "signal"  # "signal" | "policy"
    atr_multiple: float = Field(default=2.5, ge=0.1, le=20.0)
    fixed_offset: float = Field(default=0.0, ge=0.0)
    chandelier_period: int = Field(default=22, ge=1, le=200)
    sar_af_start: float = Field(default=0.02, ge=0.001, le=0.1)
    sar_af_step: float = Field(default=0.02, ge=0.001, le=0.1)
    sar_af_max: float = Field(default=0.2, ge=0.01, le=1.0)


class PartialTPConfig(BaseModel):
    """Configuration for partial take-profit."""

    enabled: bool = True
    close_pct: float = Field(default=35.0, ge=1.0, le=100.0)
    trigger: str = "signal"  # "signal" | "r_multiple" | "fixed_pct"
    r_multiple: float = Field(default=1.0, ge=0.1, le=20.0)
    profit_distance_factor: float = Field(default=1.01, ge=1.0, le=5.0)


class BreakEvenConfig(BaseModel):
    """Configuration for break-even adjustment."""

    enabled: bool = True
    buffer: float = Field(default=1.0007, ge=1.0, le=1.05)
    activation: str = "after_tp1"  # "after_tp1" | "r_multiple" | "pct"
    r_multiple: float = Field(default=1.0, ge=0.1, le=20.0)


class PyramidConfig(BaseModel):
    """Configuration for pyramiding."""

    enabled: bool = True
    max_adds: int = Field(default=3, ge=0, le=20)
    block_bars: int = Field(default=15, ge=0, le=500)
    threshold_factor: float = Field(default=1.01, ge=1.0, le=2.0)
    weighting: str = "fibonacci"  # "fibonacci" | "equal" | "decreasing"


class TimeExitConfig(BaseModel):
    """Configuration for time-based exits."""

    enabled: bool = False
    max_bars: int = Field(default=100, ge=1, le=10000)


class PortfolioLimits(BaseModel):
    """Portfolio-level risk limits."""

    enabled: bool = False
    max_portfolio_heat: float = Field(default=15.0, ge=0.1, le=100.0)
    max_drawdown_pct: float = Field(default=20.0, ge=1.0, le=100.0)
    max_gross_exposure: float = Field(default=1.0, ge=0.0, le=10.0)
    max_net_exposure: float = Field(default=1.0, ge=0.0, le=10.0)
    max_correlated_positions: int = Field(default=5, ge=1, le=50)
    correlation_threshold: float = Field(default=0.7, ge=0.0, le=1.0)
    kill_switch_drawdown: float = Field(default=25.0, ge=1.0, le=100.0)


class RiskConfig(BaseModel):
    """Full validated configuration for the risk management engine."""

    archetype: str = "mixed"
    direction: str = "both"  # "long" | "short" | "both"
    initial_capital: float = Field(default=4000.0, gt=0.0)
    commission_pct: float = Field(default=0.10, ge=0.0, le=10.0)
    slippage_pct: float = Field(default=0.0, ge=0.0, le=5.0)
    sizing: SizingConfig = Field(default_factory=SizingConfig)
    stop: StopConfig = Field(default_factory=StopConfig)
    trailing: TrailingConfig = Field(default_factory=TrailingConfig)
    partial_tp: PartialTPConfig = Field(default_factory=PartialTPConfig)
    break_even: BreakEvenConfig = Field(default_factory=BreakEvenConfig)
    pyramid: PyramidConfig = Field(default_factory=PyramidConfig)
    time_exit: TimeExitConfig = Field(default_factory=TimeExitConfig)
    portfolio: PortfolioLimits = Field(default_factory=PortfolioLimits)

    @model_validator(mode="after")
    def _validate_consistency(self) -> "RiskConfig":
        if self.pyramid.enabled and self.sizing.max_risk_per_trade * (self.pyramid.max_adds + 1) > 100:
            raise ValueError(
                "pyramid max_adds × max_risk_per_trade could exceed 100% equity"
            )
        return self
