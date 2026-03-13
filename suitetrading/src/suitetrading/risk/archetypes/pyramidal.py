"""Archetype D — Pyramidal Scaling.

Structured position building with multiple add levels, configurable
group or per-level stops, and TP/trail of the total.
"""

from __future__ import annotations

from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.contracts import RiskConfig


class PyramidalScaling(RiskArchetype):
    name = "pyramidal"

    def build_config(self, **overrides: object) -> RiskConfig:
        data: dict = {
            "archetype": self.name,
            "direction": "both",
            "initial_capital": 10_000.0,
            "commission_pct": 0.10,
            "sizing": {
                "model": "fixed_fractional",
                "risk_pct": 0.5,
                "max_risk_per_trade": 1.5,
                "max_leverage": 1.0,
            },
            "stop": {
                "model": "atr",
                "atr_multiple": 3.0,
            },
            "trailing": {
                "model": "atr",
                "atr_multiple": 2.0,
            },
            "partial_tp": {
                "enabled": True,
                "close_pct": 25.0,
                "trigger": "r_multiple",
                "r_multiple": 0.5,
                "profit_distance_factor": 1.01,
            },
            "break_even": {
                "enabled": True,
                "buffer": 1.001,
                "activation": "r_multiple",
                "r_multiple": 1.5,
            },
            "pyramid": {
                "enabled": True,
                "max_adds": 4,       # initial + 4 adds = 5 levels total
                "block_bars": 10,
                "threshold_factor": 1.0,
                "weighting": "decreasing",
            },
            "time_exit": {"enabled": False},
            "portfolio": {
                "max_portfolio_heat": 10.0,
                "max_drawdown_pct": 15.0,
                "kill_switch_drawdown": 20.0,
            },
        }
        self._apply_overrides(data, dict(overrides))
        return RiskConfig(**data)
