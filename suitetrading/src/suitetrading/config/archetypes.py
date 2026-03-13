"""Archetype → indicator mapping.

Single source of truth for which indicators each archetype uses.
Used by discovery, analysis, and paper-trading scripts.

Each archetype has:
- ``entry``: indicators whose boolean signals form the entry signal.
- ``auxiliary``: indicators that provide risk/SL bands or other non-entry
  data.  Their parameters are optimised but they do NOT participate in
  the entry signal combination.
- ``combination_mode``: how entry signals are combined.
  ``"excluyente"`` = strict AND (default).
  ``"majority"`` = N-of-M voting.
"""

from __future__ import annotations

from typing import TypedDict


class ArchetypeIndicators(TypedDict, total=False):
    entry: list[str]
    auxiliary: list[str]
    exit: list[str]
    trailing: list[str]
    combination_mode: str  # "excluyente" | "majority"
    majority_threshold: int


ARCHETYPE_INDICATORS: dict[str, ArchetypeIndicators] = {
    "trend_following": {
        "entry": ["ssl_channel", "firestorm"],
        "auxiliary": ["firestorm_tm"],
        "exit": ["ssl_channel"],
        "trailing": ["ssl_channel_low"],
        "combination_mode": "excluyente",
    },
    "mean_reversion": {
        "entry": ["wavetrend_reversal"],
        "auxiliary": [],
        "exit": ["wavetrend_reversal"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "mixed": {
        "entry": ["ssl_channel", "wavetrend_reversal", "firestorm"],
        "auxiliary": [],
        "exit": ["ssl_channel", "wavetrend_reversal"],
        "trailing": ["ssl_channel_low"],
        "combination_mode": "majority",
        "majority_threshold": 2,
    },
    "momentum": {
        "entry": ["rsi", "macd", "ema"],
        "auxiliary": [],
        "exit": ["rsi", "macd"],
        "trailing": [],
        "combination_mode": "majority",
        "majority_threshold": 2,
    },
    "breakout": {
        "entry": ["bollinger_bands", "atr", "ema"],
        "auxiliary": [],
        "exit": ["bollinger_bands"],
        "trailing": [],
        "combination_mode": "majority",
        "majority_threshold": 2,
    },
}


def get_entry_indicators(archetype: str) -> list[str]:
    """Return only the entry-signal indicators for an archetype."""
    cfg = ARCHETYPE_INDICATORS[archetype]
    return cfg["entry"]


def get_auxiliary_indicators(archetype: str) -> list[str]:
    """Return only the auxiliary (risk/SL) indicators for an archetype."""
    cfg = ARCHETYPE_INDICATORS[archetype]
    return cfg.get("auxiliary", [])


def get_all_indicators(archetype: str) -> list[str]:
    """Return entry + auxiliary indicators (all that need param optimisation)."""
    cfg = ARCHETYPE_INDICATORS[archetype]
    return cfg["entry"] + cfg.get("auxiliary", [])


def get_combination_mode(archetype: str) -> tuple[str, int | None]:
    """Return (combination_mode, majority_threshold) for an archetype."""
    cfg = ARCHETYPE_INDICATORS[archetype]
    mode = cfg.get("combination_mode", "excluyente")
    threshold = cfg.get("majority_threshold")
    return mode, threshold


def get_exit_indicators(archetype: str) -> list[str]:
    """Return exit-signal indicators for an archetype."""
    cfg = ARCHETYPE_INDICATORS[archetype]
    return cfg.get("exit", [])


def get_trailing_indicators(archetype: str) -> list[str]:
    """Return trailing-signal indicators for an archetype."""
    cfg = ARCHETYPE_INDICATORS[archetype]
    return cfg.get("trailing", [])
