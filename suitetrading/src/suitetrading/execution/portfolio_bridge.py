"""Multi-strategy signal bridge — consolidate signals from 100+ strategies.

Runs N strategies in parallel, aggregates positions per asset,
and respects PortfolioLimits in real-time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from loguru import logger

from suitetrading.risk.contracts import PortfolioLimits, RiskConfig
from suitetrading.risk.portfolio import PortfolioRiskManager, PortfolioState


@dataclass
class StrategyPosition:
    """Represents a single strategy's current position."""

    strategy_id: str
    archetype: str
    symbol: str
    direction: str = "flat"  # "long" | "short" | "flat"
    quantity: float = 0.0
    entry_price: float = 0.0
    current_price: float = 0.0
    stop_price: float | None = None
    unrealized_pnl: float = 0.0
    weight: float = 0.0


@dataclass
class ConsolidatedPosition:
    """Net position per asset after consolidating all strategies."""

    symbol: str
    net_quantity: float = 0.0
    gross_quantity: float = 0.0
    long_quantity: float = 0.0
    short_quantity: float = 0.0
    contributing_strategies: list[str] = field(default_factory=list)


class PortfolioBridge:
    """Orchestrate 100+ strategies and consolidate positions.

    Manages the lifecycle of multiple strategies running in parallel,
    aggregates their signals into net positions per asset, and enforces
    portfolio-level risk limits.
    """

    def __init__(
        self,
        *,
        portfolio_limits: PortfolioLimits | None = None,
        strategy_weights: dict[str, float] | None = None,
        initial_capital: float = 100_000.0,
    ) -> None:
        self._limits = portfolio_limits or PortfolioLimits(enabled=True)
        self._weights = strategy_weights or {}
        self._capital = initial_capital
        self._risk_manager = PortfolioRiskManager(self._limits)
        self._positions: dict[str, StrategyPosition] = {}
        self._active_strategies: set[str] = set()

    def register_strategy(
        self,
        strategy_id: str,
        archetype: str,
        symbol: str,
        weight: float = 0.01,
    ) -> None:
        """Register a strategy for tracking."""
        self._positions[strategy_id] = StrategyPosition(
            strategy_id=strategy_id,
            archetype=archetype,
            symbol=symbol,
            weight=weight,
        )
        self._active_strategies.add(strategy_id)
        self._weights[strategy_id] = weight

    def deactivate_strategy(self, strategy_id: str) -> None:
        """Deactivate a strategy (stop processing signals)."""
        self._active_strategies.discard(strategy_id)
        logger.info("Deactivated strategy: {}", strategy_id)

    def activate_strategy(self, strategy_id: str) -> None:
        """Re-activate a previously deactivated strategy."""
        if strategy_id in self._positions:
            self._active_strategies.add(strategy_id)

    def process_signal(
        self,
        strategy_id: str,
        signal: str,  # "entry_long" | "entry_short" | "exit" | "flat"
        price: float,
        stop_price: float | None = None,
    ) -> dict[str, Any]:
        """Process a signal from a single strategy.

        Returns dict with action taken and reason.
        """
        if strategy_id not in self._active_strategies:
            return {"action": "ignored", "reason": "strategy_deactivated"}

        pos = self._positions.get(strategy_id)
        if pos is None:
            return {"action": "ignored", "reason": "strategy_not_registered"}

        if signal == "exit" or signal == "flat":
            pos.direction = "flat"
            pos.quantity = 0.0
            pos.unrealized_pnl = 0.0
            return {"action": "closed", "strategy_id": strategy_id}

        # Check portfolio limits before opening
        weight = self._weights.get(strategy_id, 0.01)
        proposed_notional = self._capital * weight
        proposed_risk = proposed_notional * 0.02  # ~2% of position as risk estimate

        approved, reason = self._risk_manager.approve_new_risk(
            proposed_risk=proposed_risk,
            proposed_notional=proposed_notional,
            proposed_direction="long" if signal == "entry_long" else "short",
        )

        if not approved:
            return {"action": "blocked", "reason": reason, "strategy_id": strategy_id}

        direction = "long" if signal == "entry_long" else "short"
        quantity = proposed_notional / price if price > 0 else 0.0

        pos.direction = direction
        pos.quantity = quantity
        pos.entry_price = price
        pos.current_price = price
        pos.stop_price = stop_price
        pos.weight = weight

        return {"action": "opened", "direction": direction, "quantity": quantity}

    def update_prices(self, prices: dict[str, float]) -> PortfolioState:
        """Update current prices and recalculate portfolio state.

        Parameters
        ----------
        prices
            symbol → current price
        """
        open_positions: list[dict[str, Any]] = []

        for sid, pos in self._positions.items():
            if pos.direction == "flat":
                continue
            if pos.symbol in prices:
                pos.current_price = prices[pos.symbol]
            if pos.direction == "long":
                pos.unrealized_pnl = (pos.current_price - pos.entry_price) * pos.quantity
            else:
                pos.unrealized_pnl = (pos.entry_price - pos.current_price) * pos.quantity

            open_positions.append({
                "direction": pos.direction,
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "current_price": pos.current_price,
                "stop_price": pos.stop_price,
            })

        equity = self._capital + sum(p.unrealized_pnl for p in self._positions.values())
        return self._risk_manager.update(equity=equity, open_positions=open_positions)

    def get_consolidated_positions(self) -> dict[str, ConsolidatedPosition]:
        """Aggregate all strategy positions into net positions per asset."""
        consolidated: dict[str, ConsolidatedPosition] = {}

        for sid, pos in self._positions.items():
            if pos.direction == "flat":
                continue

            if pos.symbol not in consolidated:
                consolidated[pos.symbol] = ConsolidatedPosition(symbol=pos.symbol)

            cp = consolidated[pos.symbol]
            if pos.direction == "long":
                cp.long_quantity += pos.quantity
                cp.net_quantity += pos.quantity
            else:
                cp.short_quantity += pos.quantity
                cp.net_quantity -= pos.quantity
            cp.gross_quantity += pos.quantity
            cp.contributing_strategies.append(sid)

        return consolidated

    def get_portfolio_summary(self) -> dict[str, Any]:
        """Return a summary of the current portfolio state."""
        active = sum(1 for p in self._positions.values() if p.direction != "flat")
        consolidated = self.get_consolidated_positions()
        total_pnl = sum(p.unrealized_pnl for p in self._positions.values())

        return {
            "active_strategies": len(self._active_strategies),
            "open_positions": active,
            "total_unrealized_pnl": round(total_pnl, 2),
            "consolidated_assets": len(consolidated),
            "portfolio_state": {
                "equity": self._risk_manager.state.equity,
                "drawdown_pct": self._risk_manager.state.drawdown_pct,
                "killed": self._risk_manager.state.killed,
            },
        }
