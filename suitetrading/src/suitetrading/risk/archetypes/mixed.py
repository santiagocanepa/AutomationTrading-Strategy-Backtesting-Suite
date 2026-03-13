"""Archetype C — Mixed (Partial TP + Trail).

Closes a portion at TP1, moves to break-even, trails the remainder.
The most versatile profile for moderate R:R strategies.
"""

from __future__ import annotations

from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.contracts import RiskConfig


class Mixed(RiskArchetype):
    name = "mixed"

    def build_config(self, **overrides: object) -> RiskConfig:
        data: dict = {
            "archetype": self.name,
            "direction": "both",
            "initial_capital": 10_000.0,
            "commission_pct": 0.10,
            "sizing": {
                "model": "fixed_fractional",
                "risk_pct": 1.0,
                "max_risk_per_trade": 3.0,
                "max_leverage": 1.0,
            },
            "stop": {
                "model": "atr",
                "atr_multiple": 2.0,
            },
            "trailing": {
                "model": "atr",
                "atr_multiple": 2.0,
            },
            "partial_tp": {
                "enabled": True,
                "close_pct": 30.0,
                "trigger": "r_multiple",
                "r_multiple": 0.5,
                "profit_distance_factor": 1.01,
            },
            "break_even": {
                "enabled": True,
                "buffer": 1.0007,
                "activation": "after_tp1",
            },
            "pyramid": {
                "enabled": True,
                "max_adds": 2,
                "block_bars": 15,
                "threshold_factor": 1.01,
                "weighting": "equal",
            },
            "time_exit": {"enabled": False},
            "portfolio": {
                "max_portfolio_heat": 15.0,
                "max_drawdown_pct": 20.0,
                "kill_switch_drawdown": 25.0,
            },
        }
        self._apply_overrides(data, dict(overrides))
        return RiskConfig(**data)
