"""Shared builder for fullrisk archetype variants.

Centralises the risk configuration so fullrisk_pyr, fullrisk_time,
fullrisk_all variants avoid duplication.
"""

from __future__ import annotations

from suitetrading.risk.archetypes.base import RiskArchetype
from suitetrading.risk.contracts import RiskConfig


def fullrisk_config(
    name: str,
    *,
    pyramid_enabled: bool = False,
    time_exit_enabled: bool = False,
    stop_model: str = "atr",
    trailing_mode: str = "signal",
    overrides: dict,
) -> RiskConfig:
    """Build a fullrisk RiskConfig with optional pyramid/time_exit/stop_model/trailing_mode.

    Parameters
    ----------
    stop_model
        ``"atr"`` (default ATR-based) or ``"firestorm_tm"`` (dynamic bands).
    trailing_mode
        ``"signal"`` (exit on indicator flip) or ``"policy"`` (ATR-based trailing).
    """
    max_rpt = 15.0 if pyramid_enabled else 50.0
    stop_cfg: dict = (
        {"model": "firestorm_tm"}
        if stop_model == "firestorm_tm"
        else {"model": "atr", "atr_multiple": 10.0}
    )
    data: dict = {
        "archetype": name,
        "direction": "both",
        "initial_capital": 4_000.0,
        "commission_pct": 0.04,
        "sizing": {
            "model": "fixed_fractional",
            "risk_pct": 10.0,
            "max_risk_per_trade": max_rpt,
            "max_leverage": 1.0,
        },
        "stop": stop_cfg,
        "trailing": {"model": "atr", "trailing_mode": trailing_mode, "atr_multiple": 10.0},
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
            "enabled": pyramid_enabled,
            "max_adds": 3,
            "block_bars": 15,
            "threshold_factor": 1.01,
        },
        "time_exit": {
            "enabled": time_exit_enabled,
            "max_bars": 200,
        },
        "portfolio": {"enabled": False},
    }
    RiskArchetype._apply_overrides(data, overrides)
    return RiskConfig(**data)
