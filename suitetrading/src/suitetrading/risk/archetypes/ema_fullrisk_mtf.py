"""Archetype — full risk management chain."""
from __future__ import annotations
from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.contracts import RiskConfig

class _Arch(RiskArchetype):
    name = "ema_fullrisk_mtf"

    def build_config(self, **overrides: object) -> RiskConfig:
        data: dict = {
            "archetype": self.name,
            "direction": "both",
            "initial_capital": 4_000.0,
            "commission_pct": 0.04,
            "sizing": {
                "model": "fixed_fractional",
                "risk_pct": 10.0,
                "max_risk_per_trade": 50.0,
                "max_leverage": 1.0,
            },
            "stop": {
                "model": "atr",
                "atr_multiple": 10.0,
            },
            "trailing": {
                "model": "atr",
                "trailing_mode": "signal",
                "atr_multiple": 10.0,
            },
            "partial_tp": {
                "enabled": True,
                "close_pct": 30.0,
                "trigger": "r_multiple",
                "r_multiple": 1.0,
            },
            "break_even": {
                "enabled": True,
                "buffer": 1.001,
                "activation": "after_tp1",
            },
            "pyramid": {
                "enabled": False,
            },
            "time_exit": {"enabled": False},
            "portfolio": {"enabled": False},
        }
        self._apply_overrides(data, dict(overrides))
        return RiskConfig(**data)
