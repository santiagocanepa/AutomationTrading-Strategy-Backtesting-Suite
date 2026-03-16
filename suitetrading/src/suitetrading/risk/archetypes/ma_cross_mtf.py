"""Archetype — MTF-filtered momentum."""
from __future__ import annotations
from suitetrading.risk.archetypes.momentum_trend import MomentumTrend

class _Arch(MomentumTrend):
    name = "ma_cross_mtf"
