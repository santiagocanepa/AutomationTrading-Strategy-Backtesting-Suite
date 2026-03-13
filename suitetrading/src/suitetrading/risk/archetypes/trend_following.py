"""Archetype A — Trend Following.

Low win-rate / high R:R profile: wide stops, aggressive trailing,
pyramiding allowed, no early partial TP.
"""

from __future__ import annotations

from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.contracts import RiskConfig


class TrendFollowing(RiskArchetype):
    name = "trend_following"

    def build_config(self, **overrides: object) -> RiskConfig:
        data: dict = {
            "archetype": self.name,
            "direction": "both",
            "initial_capital": 10_000.0,
            "commission_pct": 0.10,
            "sizing": {
                "model": "fixed_fractional",
                "risk_pct": 0.5,
                "max_risk_per_trade": 2.0,
                "max_leverage": 1.0,
            },
            "stop": {
                "model": "firestorm_tm",
                "atr_multiple": 3.0,
                "ftm_period": 9,
                "ftm_multiplier": 1.8,
            },
            "trailing": {
                "model": "atr",
                "atr_multiple": 2.5,
            },
            "partial_tp": {
                "enabled": True,
                "close_pct": 30.0,
                "trigger": "r_multiple",
                "r_multiple": 0.5,
                "profit_distance_factor": 1.005,
            },
            "break_even": {
                "enabled": True,
                "buffer": 1.0007,
                "activation": "after_tp1",
            },
            "pyramid": {
                "enabled": True,
                "max_adds": 3,
                "block_bars": 20,
                "threshold_factor": 1.0,
                "weighting": "decreasing",
            },
            "time_exit": {"enabled": True, "max_bars": 200},
            "portfolio": {
                "max_portfolio_heat": 12.0,
                "max_drawdown_pct": 20.0,
                "kill_switch_drawdown": 25.0,
            },
        }
        self._apply_overrides(data, dict(overrides))
        return RiskConfig(**data)
