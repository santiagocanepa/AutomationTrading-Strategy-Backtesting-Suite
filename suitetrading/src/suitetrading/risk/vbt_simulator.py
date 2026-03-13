"""VectorBT compatibility layer.

Defines the adapter contract between the pure-Python risk engine and a
future VectorBT PRO custom simulator.  The actual VBT integration is a
Sprint 4 deliverable — this module provides:

1. A clear interface contract (``VBTSimulatorAdapter``).
2. A vectorizability classification per archetype.
3. A minimal prototype that flattens ``RiskConfig`` into simple arrays
   for Numba-friendly simulation.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from suitetrading.risk.contracts import RiskConfig


# ── Vectorizability table ─────────────────────────────────────────────
# NOTE: "high" routes to simple runner (fixed stop only, no trail/BE/TP).
# All archetypes with trailing, break-even, partial-TP, or pyramiding
# MUST be "medium" or "low" to use the FSM runner.

VECTORIZABILITY: dict[str, str] = {
    "trend_following": "medium",   # needs trailing + break-even + pyramid
    "mean_reversion": "medium",    # needs trailing + partial TP
    "mixed": "medium",             # partial TP + trail adds branching
    "momentum": "medium",          # trailing + break-even
    "breakout": "medium",          # trailing + break-even
    "legacy_firestorm": "medium",
    "pyramidal": "low",            # sequential add logic
    "grid_dca": "low",             # sequential DCA levels
}


# ── Adapter contract ──────────────────────────────────────────────────

class VBTSimulatorAdapter:
    """Bridge between the pure-Python risk engine and VectorBT callbacks.

    Sprint 3 scope: contract definition + config flattening.
    Sprint 4 scope: Numba callback implementation.
    """

    def __init__(self, config: RiskConfig) -> None:
        self._cfg = config
        self._flat = self._flatten(config)

    @property
    def vectorizability(self) -> str:
        return VECTORIZABILITY.get(self._cfg.archetype, "low")

    @property
    def flat_config(self) -> dict[str, Any]:
        """Return a dict of plain scalars suitable for Numba closures."""
        return dict(self._flat)

    # ── Flatten config to simple types ────────────────────────────────

    @staticmethod
    def _flatten(cfg: RiskConfig) -> dict[str, float | int | bool]:
        """Convert nested Pydantic config into flat scalar dict.

        Keys use ``section__field`` convention (double underscore).
        """
        flat: dict[str, float | int | bool] = {
            "initial_capital": cfg.initial_capital,
            "commission_pct": cfg.commission_pct,
            "slippage_pct": cfg.slippage_pct,
            # Sizing
            "sizing__risk_pct": cfg.sizing.risk_pct,
            "sizing__max_risk_per_trade": cfg.sizing.max_risk_per_trade,
            "sizing__max_leverage": cfg.sizing.max_leverage,
            "sizing__atr_multiple": cfg.sizing.atr_multiple,
            # Stop
            "stop__atr_multiple": cfg.stop.atr_multiple,
            "stop__fixed_pct": cfg.stop.fixed_pct,
            # Trailing
            "trailing__atr_multiple": cfg.trailing.atr_multiple,
            "trailing__fixed_offset": cfg.trailing.fixed_offset,
            # Partial TP
            "partial_tp__enabled": cfg.partial_tp.enabled,
            "partial_tp__close_pct": cfg.partial_tp.close_pct,
            "partial_tp__r_multiple": cfg.partial_tp.r_multiple,
            # Break-even
            "break_even__enabled": cfg.break_even.enabled,
            "break_even__buffer": cfg.break_even.buffer,
            # Pyramid
            "pyramid__enabled": cfg.pyramid.enabled,
            "pyramid__max_adds": cfg.pyramid.max_adds,
            "pyramid__block_bars": cfg.pyramid.block_bars,
            "pyramid__threshold_factor": cfg.pyramid.threshold_factor,
            # Time exit
            "time_exit__enabled": cfg.time_exit.enabled,
            "time_exit__max_bars": cfg.time_exit.max_bars,
            # Portfolio
            "portfolio__max_portfolio_heat": cfg.portfolio.max_portfolio_heat,
            "portfolio__max_drawdown_pct": cfg.portfolio.max_drawdown_pct,
            "portfolio__kill_switch_drawdown": cfg.portfolio.kill_switch_drawdown,
        }
        return flat

    # ── Prototype: run a simplified bar-by-bar sim in pure numpy ──────

    def run_simple_backtest(
        self,
        *,
        open_: np.ndarray | None = None,
        close: np.ndarray,
        entries: np.ndarray,
        exits: np.ndarray,
        atr: np.ndarray | None = None,
    ) -> dict[str, Any]:
        """Minimal prototype of a bar-loop simulation over numpy arrays.

        Only supports single-position, no pyramiding, for archetypes with
        ``vectorizability == "high"``.  Full implementation in Sprint 4.

        Parameters
        ----------
        open_
            Open prices.  When provided the simulator uses gap-aware stop
            fills: ``min(stop, open)`` for longs, ``max(stop, open)`` for
            shorts.  Falls back to close-only mode when *None*.
        """
        n = len(close)
        if open_ is None:
            open_ = close
        equity_curve = np.full(n, self._cfg.initial_capital)
        equity = self._cfg.initial_capital
        in_position = False
        direction = 1  # 1=long
        entry_price = 0.0
        stop_price = 0.0
        qty = 0.0
        slip = self._flat.get("slippage_pct", 0.0)

        for i in range(1, n):
            equity_curve[i] = equity

            if in_position:
                # Check stop (gap-aware)
                if direction == 1 and close[i] <= stop_price:
                    fill = min(stop_price, open_[i])
                    if slip:
                        fill *= (1 - slip / 100.0)
                    pnl = (fill - entry_price) * qty
                    equity += pnl
                    in_position = False
                elif direction == -1 and close[i] >= stop_price:
                    fill = max(stop_price, open_[i])
                    if slip:
                        fill *= (1 + slip / 100.0)
                    pnl = (entry_price - fill) * qty
                    equity += pnl
                    in_position = False
                # Check exit signal
                elif exits[i]:
                    fill = close[i]
                    if slip:
                        fill *= (1 - slip / 100.0) if direction == 1 else (1 + slip / 100.0)
                    pnl = (fill - entry_price) * qty * direction
                    equity += pnl
                    in_position = False

                equity_curve[i] = equity

            if not in_position and entries[i]:
                entry_price = close[i]
                if atr is not None and atr[i] > 0:
                    stop_dist = atr[i] * self._flat.get("stop__atr_multiple", 2.0)
                else:
                    stop_dist = entry_price * self._flat.get("stop__fixed_pct", 2.0) / 100.0
                stop_price = entry_price - stop_dist * direction
                risk_amount = equity * self._flat["sizing__risk_pct"] / 100.0
                qty = risk_amount / stop_dist if stop_dist > 0 else 0.0
                in_position = qty > 0

        return {
            "equity_curve": equity_curve,
            "final_equity": equity,
            "total_return_pct": (equity / self._cfg.initial_capital - 1) * 100,
        }
