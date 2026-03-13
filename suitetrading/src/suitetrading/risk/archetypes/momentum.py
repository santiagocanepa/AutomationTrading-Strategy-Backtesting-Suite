"""Archetype D — Momentum.

Mid win-rate / mid R:R: RSI+MACD+EMA majority voting.
Moderate stops, trailing enabled, no pyramiding.
"""

from __future__ import annotations

from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.contracts import RiskConfig


class Momentum(RiskArchetype):
    name = "momentum"

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
                "atr_multiple": 2.0,
            },
            "trailing": {
                "model": "atr",
                "atr_multiple": 2.0,
            },
            "partial_tp": {
                "enabled": True,
                "close_pct": 50.0,
                "trigger": "r_multiple",
                "r_multiple": 0.5,
                "profit_distance_factor": 1.005,
            },
            "break_even": {
                "enabled": True,
                "buffer": 1.003,
                "activation": "r_multiple",
                "r_multiple": 1.5,
            },
            "pyramid": {
                "enabled": False,
                "max_adds": 0,
            },
            "time_exit": {
                "enabled": True,
                "max_bars": 100,
            },
            "portfolio": {
                "max_portfolio_heat": 12.0,
                "max_drawdown_pct": 18.0,
                "kill_switch_drawdown": 22.0,
            },
        }
        self._apply_overrides(data, dict(overrides))
        return RiskConfig(**data)
