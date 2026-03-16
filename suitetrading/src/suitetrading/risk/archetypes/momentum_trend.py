"""Archetype — Momentum Trend Following.

Momentum indicators for direction (ROC, Donchian, MA Crossover)
with SSL/Firestorm as risk filters. Wide stops as safety net,
signal-based exit, no early TP — let trends run.
"""

from __future__ import annotations

from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.contracts import RiskConfig


class MomentumTrend(RiskArchetype):
    name = "momentum_trend"

    def build_config(self, **overrides: object) -> RiskConfig:
        data: dict = {
            "archetype": self.name,
            "direction": "both",
            "initial_capital": 4_000.0,
            "commission_pct": 0.04,
            "sizing": {
                "model": "fixed_fractional",
                "risk_pct": 20.0,
                "max_risk_per_trade": 50.0,
                "max_leverage": 1.0,
            },
            "stop": {
                "model": "atr",
                "atr_multiple": 15.0,
            },
            "trailing": {
                "model": "atr",
                "trailing_mode": "signal",
                "atr_multiple": 10.0,
            },
            "partial_tp": {
                "enabled": False,
            },
            "break_even": {
                "enabled": False,
            },
            "pyramid": {
                "enabled": False,
            },
            "time_exit": {"enabled": False},
            "portfolio": {
                "enabled": False,
            },
        }
        self._apply_overrides(data, dict(overrides))
        return RiskConfig(**data)
