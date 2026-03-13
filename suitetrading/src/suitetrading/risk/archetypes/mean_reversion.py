"""Archetype B — Mean Reversion.

High win-rate / low R:R profile: tight stops, fixed take-profit,
no pyramiding, early break-even, time exit recommended.
"""

from __future__ import annotations

from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.contracts import RiskConfig


class MeanReversion(RiskArchetype):
    name = "mean_reversion"

    def build_config(self, **overrides: object) -> RiskConfig:
        data: dict = {
            "archetype": self.name,
            "direction": "both",
            "initial_capital": 10_000.0,
            "commission_pct": 0.10,
            "sizing": {
                "model": "fixed_fractional",
                "risk_pct": 1.0,
                "max_risk_per_trade": 2.0,
                "max_leverage": 1.0,
            },
            "stop": {
                "model": "atr",
                "atr_multiple": 1.5,
            },
            "trailing": {
                "model": "fixed",
                "fixed_offset": 0.0,
            },
            "partial_tp": {
                "enabled": True,
                "close_pct": 60.0,
                "trigger": "r_multiple",
                "r_multiple": 0.3,
                "profit_distance_factor": 1.005,
            },
            "break_even": {
                "enabled": True,
                "buffer": 1.001,
                "activation": "after_tp1",
            },
            "pyramid": {
                "enabled": False,
                "max_adds": 0,
            },
            "time_exit": {
                "enabled": True,
                "max_bars": 50,
            },
            "portfolio": {
                "max_portfolio_heat": 10.0,
                "max_drawdown_pct": 15.0,
                "kill_switch_drawdown": 20.0,
            },
        }
        self._apply_overrides(data, dict(overrides))
        return RiskConfig(**data)
