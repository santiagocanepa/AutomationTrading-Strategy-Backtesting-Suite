"""Risk management engine: contracts, state machine, position sizing, archetypes."""

from suitetrading.risk.contracts import (
    BreakEvenConfig,
    PartialTPConfig,
    PortfolioLimits,
    PositionSnapshot,
    PositionState,
    PyramidConfig,
    RiskConfig,
    SizingConfig,
    StopConfig,
    TimeExitConfig,
    TrailingConfig,
    TransitionEvent,
    TransitionResult,
)
from suitetrading.risk.position_sizing import (
    ATRSizer,
    FixedFractionalSizer,
    KellySizer,
    OptimalFSizer,
    PositionSizer,
    create_sizer,
)
from suitetrading.risk.state_machine import PositionStateMachine
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

__all__ = [
    # Contracts
    "PositionState",
    "TransitionEvent",
    "PositionSnapshot",
    "TransitionResult",
    "RiskConfig",
    "SizingConfig",
    "StopConfig",
    "TrailingConfig",
    "PartialTPConfig",
    "BreakEvenConfig",
    "PyramidConfig",
    "TimeExitConfig",
    "PortfolioLimits",
    # State machine
    "PositionStateMachine",
    # Sizing
    "PositionSizer",
    "FixedFractionalSizer",
    "ATRSizer",
    "KellySizer",
    "OptimalFSizer",
    "create_sizer",
    # Exit policies
    "ExitPolicy",
    "BreakEvenPolicy",
    "FixedTrailingStop",
    "ATRTrailingStop",
    "ChandelierExit",
    "ParabolicSARStop",
    "SignalTrailingExit",
    "create_exit_policy",
]
