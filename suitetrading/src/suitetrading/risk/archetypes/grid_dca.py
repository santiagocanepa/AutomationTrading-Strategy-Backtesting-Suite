"""Archetype E — Grid / DCA.

Entries at predefined levels, take-profit on weighted average,
max levels configurable, mandatory drawdown cap.
"""

from __future__ import annotations

from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.contracts import RiskConfig


class GridDCA(RiskArchetype):
    name = "grid_dca"

    def build_config(self, **overrides: object) -> RiskConfig:
        data: dict = {
            "archetype": self.name,
            "direction": "long",  # most DCA strategies are long bias
            "initial_capital": 10_000.0,
            "commission_pct": 0.10,
            "sizing": {
                "model": "fixed_fractional",
                "risk_pct": 0.5,
                "max_risk_per_trade": 1.0,
                "max_leverage": 1.0,
            },
            "stop": {
                "model": "atr",
                "atr_multiple": 5.0,  # wide stop accommodates adverse grid fill
            },
            "trailing": {
                "model": "fixed",
                "fixed_offset": 0.0,
            },
            "partial_tp": {
                "enabled": True,
                "close_pct": 100.0,  # full close at weighted average target
                "trigger": "r_multiple",
                "r_multiple": 0.5,
                "profit_distance_factor": 1.005,
            },
            "break_even": {
                "enabled": False,
            },
            "pyramid": {
                "enabled": True,
                "max_adds": 8,         # up to 8 DCA levels
                "block_bars": 5,
                "threshold_factor": 1.0,
                "weighting": "equal",
            },
            "time_exit": {
                "enabled": True,
                "max_bars": 500,
            },
            "portfolio": {
                "max_portfolio_heat": 8.0,
                "max_drawdown_pct": 10.0,   # tight DD cap for grid
                "kill_switch_drawdown": 15.0,
                "max_gross_exposure": 2.0,
            },
        }
        self._apply_overrides(data, dict(overrides))
        return RiskConfig(**data)
