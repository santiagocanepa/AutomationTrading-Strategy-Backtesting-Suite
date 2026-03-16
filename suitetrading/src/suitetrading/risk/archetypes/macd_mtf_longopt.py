"""Archetype — direction-optimized."""
from __future__ import annotations
from suitetrading.risk.archetypes.momentum_trend import MomentumTrend

class _Arch(MomentumTrend):
    name = "macd_mtf_longopt"
