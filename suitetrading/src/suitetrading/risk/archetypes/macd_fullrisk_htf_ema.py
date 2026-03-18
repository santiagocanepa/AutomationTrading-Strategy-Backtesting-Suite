"""Archetype — MACD entry + full risk + EMA as HTF filter."""
from __future__ import annotations
from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.archetypes._fullrisk_base import fullrisk_config
from suitetrading.risk.contracts import RiskConfig


class _Arch(RiskArchetype):
    name = "macd_fullrisk_htf_ema"

    def build_config(self, **overrides: object) -> RiskConfig:
        return fullrisk_config(self.name, overrides=dict(overrides))
