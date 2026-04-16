"""Portfolio-level risk management.

Controls that operate *above* individual positions: drawdown monitoring,
portfolio heat, exposure limits, kill switch and Monte Carlo robustness.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

import numpy as np

from suitetrading.risk.contracts import PortfolioLimits


@dataclass
class PortfolioState:
    """Snapshot of portfolio-level metrics."""

    equity: float = 0.0
    peak_equity: float = 0.0
    open_risk: float = 0.0          # sum of dollar-risk across open positions
    gross_exposure: float = 0.0     # sum |position_value| / equity
    net_exposure: float = 0.0       # sum signed(position_value) / equity
    active_positions: int = 0
    drawdown_pct: float = 0.0
    killed: bool = False
    kill_reason: str | None = None


class PortfolioRiskManager:
    """Aggregate risk controls across strategies and positions.

    This manager is stateful — call ``update()`` after each bar or trade
    to keep ``state`` current, then use ``approve_new_risk()`` before
    opening or adding to positions.
    """

    def __init__(self, limits: PortfolioLimits | None = None) -> None:
        self._limits = limits or PortfolioLimits()
        self.state = PortfolioState()

    # ── Core lifecycle ────────────────────────────────────────────────

    def update(
        self,
        *,
        equity: float,
        open_positions: list[dict[str, Any]] | None = None,
    ) -> PortfolioState:
        """Recalculate portfolio state from current equity and positions.

        Each dict in *open_positions* should contain at least:
        ``direction``, ``quantity``, ``entry_price``, ``current_price``,
        ``stop_price``.
        """
        open_positions = open_positions or []
        self.state.equity = equity
        self.state.peak_equity = max(self.state.peak_equity, equity)

        if self.state.peak_equity > 0:
            self.state.drawdown_pct = (
                (self.state.peak_equity - equity) / self.state.peak_equity * 100.0
            )
        else:
            self.state.drawdown_pct = 0.0

        # Exposure calculations
        total_risk = 0.0
        gross = 0.0
        net = 0.0
        for pos in open_positions:
            qty = pos.get("quantity", 0.0)
            entry = pos.get("entry_price", 0.0)
            current = pos.get("current_price", entry)
            stop = pos.get("stop_price")
            direction = pos.get("direction", "long")
            notional = qty * current

            if direction == "long":
                risk = qty * abs(current - stop) if stop is not None else notional * 0.02
                gross += notional
                net += notional
            else:
                risk = qty * abs(stop - current) if stop is not None else notional * 0.02
                gross += notional
                net -= notional

            total_risk += risk

        self.state.open_risk = total_risk
        self.state.active_positions = len(open_positions)
        self.state.gross_exposure = gross / equity if equity > 0 else 0.0
        self.state.net_exposure = net / equity if equity > 0 else 0.0

        # Kill switch
        if not self.state.killed and self.state.drawdown_pct >= self._limits.kill_switch_drawdown:
            self.state.killed = True
            self.state.kill_reason = (
                f"Drawdown {self.state.drawdown_pct:.1f}% >= kill threshold "
                f"{self._limits.kill_switch_drawdown:.1f}%"
            )

        return self.state

    # ── Gate: approve new risk ────────────────────────────────────────

    def approve_new_risk(
        self,
        *,
        proposed_risk: float,
        proposed_notional: float = 0.0,
        proposed_direction: str = "long",
    ) -> tuple[bool, str]:
        """Decide whether a new position/add is allowed.

        Returns ``(approved, reason)``.
        """
        if self.state.killed:
            return False, f"Kill switch active: {self.state.kill_reason}"

        # Drawdown gate
        if self.state.drawdown_pct >= self._limits.max_drawdown_pct:
            return False, (
                f"Drawdown {self.state.drawdown_pct:.1f}% >= max {self._limits.max_drawdown_pct:.1f}%"
            )

        # Portfolio heat
        equity = self.state.equity
        if equity > 0:
            heat_pct = (self.state.open_risk + proposed_risk) / equity * 100.0
            if heat_pct > self._limits.max_portfolio_heat:
                return False, (
                    f"Portfolio heat {heat_pct:.1f}% would exceed max {self._limits.max_portfolio_heat:.1f}%"
                )

        # Gross exposure
        if equity > 0 and proposed_notional > 0:
            new_gross = self.state.gross_exposure + proposed_notional / equity
            if new_gross > self._limits.max_gross_exposure:
                return False, (
                    f"Gross exposure {new_gross:.2f} would exceed max {self._limits.max_gross_exposure:.2f}"
                )

        return True, "approved"

    # ── Portfolio evaluation / report ─────────────────────────────────

    def evaluate_portfolio(
        self,
        *,
        returns: np.ndarray | None = None,
    ) -> dict[str, Any]:
        """Return a risk report dict for the current portfolio state."""
        report: dict[str, Any] = {
            "equity": self.state.equity,
            "peak_equity": self.state.peak_equity,
            "drawdown_pct": self.state.drawdown_pct,
            "open_risk": self.state.open_risk,
            "gross_exposure": self.state.gross_exposure,
            "net_exposure": self.state.net_exposure,
            "active_positions": self.state.active_positions,
            "killed": self.state.killed,
            "kill_reason": self.state.kill_reason,
            "action": self._recommend_action(),
        }
        if returns is not None and len(returns) > 0:
            report["monte_carlo"] = self.monte_carlo(returns)
        return report

    def _recommend_action(self) -> str:
        if self.state.killed:
            return "halt"
        if self.state.drawdown_pct >= self._limits.max_drawdown_pct * 0.8:
            return "reduce"
        return "approve"

    # ── Monte Carlo robustness ────────────────────────────────────────

    @staticmethod
    def monte_carlo(
        trade_returns: np.ndarray,
        n_simulations: int = 1000,
        seed: int | None = None,
    ) -> dict[str, Any]:
        """Bootstrap-reshuffle Monte Carlo over a sequence of trade returns.

        Returns percentiles of max-drawdown and terminal equity ratio.
        """
        rng = np.random.default_rng(seed)
        n_trades = len(trade_returns)
        if n_trades == 0:
            return {"error": "no trades"}

        max_dds: list[float] = []
        terminal_ratios: list[float] = []

        for _ in range(n_simulations):
            shuffled = rng.choice(trade_returns, size=n_trades, replace=True)
            equity_curve = np.cumprod(1.0 + shuffled)
            running_max = np.maximum.accumulate(equity_curve)
            drawdowns = (running_max - equity_curve) / running_max
            max_dds.append(float(np.max(drawdowns)) * 100.0)
            terminal_ratios.append(float(equity_curve[-1]))

        max_dds_arr = np.array(max_dds)
        terminal_arr = np.array(terminal_ratios)

        return {
            "max_dd_p50": float(np.percentile(max_dds_arr, 50)),
            "max_dd_p95": float(np.percentile(max_dds_arr, 95)),
            "max_dd_p99": float(np.percentile(max_dds_arr, 99)),
            "terminal_p5": float(np.percentile(terminal_arr, 5)),
            "terminal_p50": float(np.percentile(terminal_arr, 50)),
            "terminal_p95": float(np.percentile(terminal_arr, 95)),
            "prob_ruin": float(np.mean(terminal_arr < 0.5)),  # <50% of initial
            "n_simulations": n_simulations,
        }

    # ── Reset ─────────────────────────────────────────────────────────

    def reset(self) -> None:
        """Reset portfolio state (e.g. start of new simulation)."""
        self.state = PortfolioState()
