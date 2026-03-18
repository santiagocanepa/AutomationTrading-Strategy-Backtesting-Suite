"""Archetype — MA Crossover + full risk chain + pyramid + Firestorm TM stops."""
from __future__ import annotations
from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.archetypes._fullrisk_base import fullrisk_config
from suitetrading.risk.contracts import RiskConfig


class _Arch(RiskArchetype):
    name = "ma_x_fullrisk_pyr_ftm"

    def build_config(self, **overrides: object) -> RiskConfig:
        return fullrisk_config(self.name, pyramid_enabled=True, stop_model="firestorm_tm", overrides=dict(overrides))
