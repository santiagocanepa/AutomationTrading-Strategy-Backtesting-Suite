"""Data contracts and schemas for the backtesting module.

Every dataclass here is lightweight, serialisable and free of heavy
logic so it can be imported anywhere without circular dependencies.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

import pandas as pd


# ── Dataset bundle ────────────────────────────────────────────────────

@dataclass
class BacktestDataset:
    """Self-contained bundle of validated OHLCV data for a single run.

    ``ohlcv`` is the base-timeframe DataFrame (DatetimeIndex, OHLCV
    columns).  ``aligned_frames`` holds any higher-timeframe frames
    already forward-filled to the base index.
    """

    exchange: str
    symbol: str
    base_timeframe: str
    ohlcv: pd.DataFrame
    aligned_frames: dict[str, pd.DataFrame] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Strategy signals ──────────────────────────────────────────────────

@dataclass
class StrategySignals:
    """Pre-computed boolean signal arrays aligned to the base timeframe.

    Only ``entry_long`` is mandatory — the rest default to *None* which
    the engine interprets as "not applicable".
    """

    entry_long: pd.Series
    entry_short: pd.Series | None = None
    exit_long: pd.Series | None = None
    exit_short: pd.Series | None = None
    trailing_long: pd.Series | None = None
    trailing_short: pd.Series | None = None
    indicators_payload: dict[str, pd.Series | pd.DataFrame | float] = field(
        default_factory=dict,
    )


# ── Grid request ──────────────────────────────────────────────────────

@dataclass
class GridRequest:
    """Specification for a parameter grid run."""

    symbols: list[str]
    timeframes: list[str]
    indicator_space: dict[str, dict[str, list[Any]]]
    risk_space: dict[str, list[Any]]
    archetypes: list[str]


# ── Individual run config (one point in the grid) ─────────────────────

@dataclass
class RunConfig:
    """Fully resolved configuration for a single backtest run.

    ``run_id`` is a deterministic hash of the full configuration so that
    re-running the same config produces the same id.
    """

    symbol: str
    timeframe: str
    archetype: str
    indicator_params: dict[str, dict[str, Any]]
    risk_overrides: dict[str, Any]
    run_id: str = ""

    def __post_init__(self) -> None:
        if not self.run_id:
            self.run_id = self._compute_id()

    def _compute_id(self) -> str:
        payload = json.dumps(
            {
                "symbol": self.symbol,
                "timeframe": self.timeframe,
                "archetype": self.archetype,
                "indicator_params": self.indicator_params,
                "risk_overrides": self.risk_overrides,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ── Checkpoint ────────────────────────────────────────────────────────

@dataclass
class BacktestCheckpoint:
    """Tracks the outcome of a single chunk execution."""

    run_id: str
    chunk_id: int
    status: str  # "pending" | "running" | "done" | "error"
    started_at: str = ""
    finished_at: str = ""
    output_path: str = ""
    error: str = ""


# ── Single-run result row ─────────────────────────────────────────────

RESULT_COLUMNS: list[str] = [
    "run_id",
    "symbol",
    "timeframe",
    "archetype",
    "mode",
    "net_profit",
    "total_return_pct",
    "sharpe",
    "sortino",
    "max_drawdown_pct",
    "calmar",
    "win_rate",
    "profit_factor",
    "average_trade",
    "max_consecutive_losses",
    "total_trades",
]
