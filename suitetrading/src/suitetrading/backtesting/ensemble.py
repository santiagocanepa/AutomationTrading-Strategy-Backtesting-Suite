"""Ensemble backtester — blend N strategy equity curves into a portfolio.

Simulates a portfolio of multiple strategies with configurable weights
and rebalancing frequency.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from loguru import logger


@dataclass
class EnsembleResult:
    """Result of an ensemble backtest."""

    equity_curve: np.ndarray                        # Portfolio equity curve
    strategy_contributions: dict[str, np.ndarray]   # Per-strategy contribution
    weights_history: np.ndarray | None              # (T, N) if rebalanced
    metrics: dict[str, float]
    rebalance_dates: list[int] | None


class EnsembleBacktester:
    """Blend N equity curves into a portfolio with optional rebalancing."""

    def __init__(self, initial_capital: float = 100_000.0) -> None:
        self._capital = initial_capital

    def run(
        self,
        equity_curves: dict[str, np.ndarray],
        weights: np.ndarray,
        strategy_ids: list[str],
        rebalance_freq: str = "none",
        bars_per_day: int = 24,
    ) -> EnsembleResult:
        """Run ensemble simulation.

        With rebalance_freq="none": simple weighted blend.
        With rebalancing: periodically recompute allocations.
        """
        n = len(strategy_ids)
        if n == 0:
            raise ValueError("No strategies provided")
        if len(weights) != n:
            raise ValueError(f"weights length {len(weights)} != strategy count {n}")

        weights = np.asarray(weights, dtype=np.float64)
        weights = weights / weights.sum()  # ensure normalized

        # Align lengths
        min_len = min(len(equity_curves[s]) for s in strategy_ids)
        if min_len < 2:
            raise ValueError(f"Equity curves too short: {min_len}")

        # Build returns matrix (T-1, N)
        returns_list: list[np.ndarray] = []
        for sid in strategy_ids:
            eq = np.asarray(equity_curves[sid][:min_len], dtype=np.float64)
            prev = np.roll(eq, 1)
            prev[0] = eq[0]
            ret = np.where(prev != 0, (eq - prev) / prev, 0.0)
            returns_list.append(ret[1:])  # drop first bar (no return)

        returns_mat = np.column_stack(returns_list)  # (T-1, N)
        t = returns_mat.shape[0]

        # Determine rebalance intervals
        rebalance_interval = self._compute_rebalance_interval(rebalance_freq, bars_per_day)

        if rebalance_interval <= 0:
            # No rebalancing: constant weights
            port_returns = returns_mat @ weights
            equity = np.empty(t + 1, dtype=np.float64)
            equity[0] = self._capital
            equity[1:] = self._capital * np.cumprod(1.0 + port_returns)

            # Per-strategy contribution: weighted equity component
            contributions: dict[str, np.ndarray] = {}
            for i, sid in enumerate(strategy_ids):
                strat_contrib = returns_mat[:, i] * weights[i]
                contrib_eq = np.empty(t + 1, dtype=np.float64)
                contrib_eq[0] = self._capital * weights[i]
                contrib_eq[1:] = self._capital * weights[i] * np.cumprod(1.0 + returns_mat[:, i])
                contributions[sid] = contrib_eq

            metrics = self._compute_metrics(equity)
            logger.info(
                "Ensemble (no rebalance): {} strategies, sharpe={:.4f}, max_dd={:.2f}%",
                n, metrics.get("sharpe", 0.0), metrics.get("max_drawdown_pct", 0.0),
            )

            return EnsembleResult(
                equity_curve=equity,
                strategy_contributions=contributions,
                weights_history=None,
                metrics=metrics,
                rebalance_dates=None,
            )

        # With rebalancing
        equity = np.empty(t + 1, dtype=np.float64)
        equity[0] = self._capital
        weights_history = np.empty((t + 1, n), dtype=np.float64)
        weights_history[0] = weights.copy()
        current_weights = weights.copy()
        rebalance_dates: list[int] = []

        # Track per-strategy dollar allocation
        allocations = self._capital * current_weights  # (N,) dollar amount per strategy

        for bar in range(t):
            # Apply returns: each strategy grows independently
            allocations = allocations * (1.0 + returns_mat[bar])
            equity[bar + 1] = allocations.sum()
            weights_history[bar + 1] = allocations / equity[bar + 1] if equity[bar + 1] > 0 else current_weights

            # Rebalance at interval
            if (bar + 1) % rebalance_interval == 0:
                current_weights = weights.copy()
                allocations = equity[bar + 1] * current_weights
                weights_history[bar + 1] = current_weights
                rebalance_dates.append(bar + 1)

        # Per-strategy contribution (approximate: final allocation)
        contributions = {}
        for i, sid in enumerate(strategy_ids):
            contributions[sid] = weights_history[:, i] * equity

        metrics = self._compute_metrics(equity)
        logger.info(
            "Ensemble (rebalance={}): {} strategies, {} rebalances, sharpe={:.4f}",
            rebalance_freq, n, len(rebalance_dates), metrics.get("sharpe", 0.0),
        )

        return EnsembleResult(
            equity_curve=equity,
            strategy_contributions=contributions,
            weights_history=weights_history,
            metrics=metrics,
            rebalance_dates=rebalance_dates,
        )

    def _compute_metrics(self, equity: np.ndarray) -> dict[str, float]:
        """Compute portfolio-level metrics."""
        if len(equity) < 2:
            return {
                "total_return_pct": 0.0, "sharpe": 0.0, "sortino": 0.0,
                "max_drawdown_pct": 0.0, "calmar": 0.0,
            }

        returns = np.diff(equity) / np.where(equity[:-1] != 0, equity[:-1], 1.0)

        total_return_pct = (equity[-1] / equity[0] - 1.0) * 100.0 if equity[0] > 0 else 0.0

        # Sharpe (annualized assuming hourly bars, crypto 365*24)
        mean_ret = float(np.mean(returns))
        std_ret = float(np.std(returns, ddof=1))
        ann_factor = np.sqrt(365 * 24)
        sharpe = mean_ret / std_ret * ann_factor if std_ret > 1e-12 else 0.0

        # Sortino
        downside = returns[returns < 0]
        dd_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0.0
        sortino = mean_ret / dd_std * ann_factor if dd_std > 1e-12 else 0.0

        # Max drawdown
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / np.where(peak > 0, peak, 1.0)
        max_dd_pct = float(np.max(drawdown) * 100.0)

        # Calmar
        calmar = total_return_pct / max_dd_pct if max_dd_pct > 0 else 0.0

        return {
            "total_return_pct": round(total_return_pct, 4),
            "sharpe": round(sharpe, 4),
            "sortino": round(sortino, 4),
            "max_drawdown_pct": round(max_dd_pct, 4),
            "calmar": round(calmar, 4),
        }

    @staticmethod
    def _compute_rebalance_interval(freq: str, bars_per_day: int) -> int:
        """Convert rebalance frequency string to bar interval."""
        mapping = {
            "none": 0,
            "daily": bars_per_day,
            "weekly": bars_per_day * 7,
            "monthly": bars_per_day * 30,
        }
        interval = mapping.get(freq, 0)
        if interval == 0 and freq != "none":
            logger.warning("Unknown rebalance frequency '{}', using no rebalance", freq)
        return interval
