"""Archetype — direction-optimized."""
from __future__ import annotations
from suitetrading.risk.archetypes.momentum_trend import MomentumTrend

class _Arch(MomentumTrend):
    name = "ma_x_ssl_longopt"
