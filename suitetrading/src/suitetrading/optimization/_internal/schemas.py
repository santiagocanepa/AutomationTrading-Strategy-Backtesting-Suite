"""Data contracts for the optimization module.

Lightweight dataclasses — no heavy logic, fast imports, no circular deps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


# ── Objective result (single backtest evaluated by optimizer) ─────────

@dataclass
class ObjectiveResult:
    """Result of evaluating one parameter set via the objective function."""

    run_id: str
    params: dict[str, Any]
    metrics: dict[str, float | int]
    equity_curve: np.ndarray
    trades: list[dict[str, Any]]
    is_error: bool = False
    error_msg: str | None = None


# ── Optimization result (study summary) ──────────────────────────────

@dataclass
class OptimizationResult:
    """Summary of an Optuna study run."""

    study_name: str
    n_trials: int
    n_completed: int
    n_pruned: int
    best_value: float
    best_params: dict[str, Any]
    best_run_id: str
    wall_time_sec: float
    trials_per_sec: float


# ── Walk-Forward Optimization ─────────────────────────────────────────

@dataclass
class WFOConfig:
    """Configuration for walk-forward optimization."""

    n_splits: int = 5
    is_ratio: float = 0.75
    oos_ratio: float = 0.25
    gap_bars: int = 20
    mode: str = "rolling"  # "rolling" | "anchored"
    min_is_bars: int = 500
    min_oos_bars: int = 100

    def __post_init__(self) -> None:
        if self.mode not in ("rolling", "anchored"):
            raise ValueError(f"WFO mode must be 'rolling' or 'anchored', got {self.mode!r}")
        if self.is_ratio + self.oos_ratio > 1.0:
            raise ValueError("is_ratio + oos_ratio must be <= 1.0")
        if self.n_splits < 2:
            raise ValueError("n_splits must be >= 2")


@dataclass
class WFOResult:
    """Result of a walk-forward optimization run."""

    config: WFOConfig
    n_candidates: int
    splits: list[dict[str, Any]]
    oos_equity_curves: dict[str, np.ndarray]
    oos_metrics: dict[str, dict[str, float]]
    degradation: dict[str, float]


# ── Anti-overfitting ──────────────────────────────────────────────────

@dataclass
class CSCVResult:
    """Result of Combinatorially Symmetric Cross-Validation."""

    pbo: float
    n_subsamples: int
    n_combinations: int
    omega_values: np.ndarray
    is_overfit: bool
    details: dict[str, Any] | None = None


@dataclass
class DSRResult:
    """Result of Deflated Sharpe Ratio test."""

    dsr: float
    expected_max_sharpe: float
    observed_sharpe: float
    is_significant: bool


@dataclass
class SPAResult:
    """Result of Hansen's Superior Predictive Ability test."""

    p_value: float
    is_superior: bool
    statistic: float
    benchmark: str


@dataclass
class AntiOverfitResult:
    """Aggregated result of the full anti-overfitting pipeline."""

    total_candidates: int
    passed_cscv: int
    passed_dsr: int
    passed_spa: int
    finalists: list[str]
    cscv_results: dict[str, CSCVResult] = field(default_factory=dict)
    dsr_results: dict[str, DSRResult] = field(default_factory=dict)
    spa_results: dict[str, SPAResult] = field(default_factory=dict)


# ── Strategy report (per finalist) ───────────────────────────────────

@dataclass
class StrategyReport:
    """Full validation evidence for a single finalist strategy."""

    run_id: str
    params: dict[str, Any]
    archetype: str
    symbol: str
    timeframe: str
    is_metrics: dict[str, float]
    oos_metrics: dict[str, float]
    degradation_ratio: float
    pbo: float
    dsr: float
    spa_p_value: float
    passed_all_filters: bool


# ── Pipeline result (end-to-end) ──────────────────────────────────────

@dataclass
class PipelineResult:
    """End-to-end result of the optimization pipeline."""

    optimizer_result: OptimizationResult
    wfo_result: WFOResult
    anti_overfit_result: AntiOverfitResult
    finalists: list[StrategyReport]
    total_wall_time_sec: float
