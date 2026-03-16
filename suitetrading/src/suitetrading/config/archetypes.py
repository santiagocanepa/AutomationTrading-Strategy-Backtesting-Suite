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
    htf_filter: str | None  # Higher TF indicator name (e.g. "ema")
    htf_timeframe: str | None  # Target TF (e.g. "1d")


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
    "momentum_trend": {
        "entry": ["roc", "donchian"],
        "auxiliary": ["ssl_channel"],
        "exit": ["roc"],
        "trailing": ["ssl_channel"],
        "combination_mode": "majority",
        "majority_threshold": 1,
    },
    "donchian_simple": {
        "entry": ["donchian"],
        "auxiliary": [],
        "exit": ["donchian"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "roc_simple": {
        "entry": ["roc"],
        "auxiliary": [],
        "exit": ["roc"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "ma_cross_simple": {
        "entry": ["ma_crossover"],
        "auxiliary": [],
        "exit": ["ma_crossover"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "adx_simple": {
        "entry": ["adx_filter"],
        "auxiliary": [],
        "exit": ["adx_filter"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "roc_adx": {
        "entry": ["roc", "adx_filter"],
        "auxiliary": [],
        "exit": ["roc"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "roc_ma": {
        "entry": ["roc", "ma_crossover"],
        "auxiliary": [],
        "exit": ["roc", "ma_crossover"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "roc_ssl": {
        "entry": ["roc"],
        "auxiliary": ["ssl_channel"],
        "exit": ["roc"],
        "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "donchian_adx": {
        "entry": ["donchian", "adx_filter"],
        "auxiliary": [],
        "exit": ["donchian"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "ma_ssl": {
        "entry": ["ma_crossover"],
        "auxiliary": ["ssl_channel"],
        "exit": ["ma_crossover"],
        "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ma_adx": {
        "entry": ["ma_crossover", "adx_filter"],
        "auxiliary": [],
        "exit": ["ma_crossover"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "donchian_ssl": {
        "entry": ["donchian"],
        "auxiliary": ["ssl_channel"],
        "exit": ["donchian"],
        "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "donchian_roc": {
        "entry": ["donchian", "roc"],
        "auxiliary": [],
        "exit": ["donchian", "roc"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "triple_momentum": {
        "entry": ["roc", "ma_crossover", "adx_filter"],
        "auxiliary": [],
        "exit": ["roc", "ma_crossover"],
        "trailing": [],
        "combination_mode": "majority",
        "majority_threshold": 2,
    },
    "roc_fire": {
        "entry": ["roc"],
        "auxiliary": ["firestorm_tm"],
        "exit": ["roc"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "ssl_roc": {
        "entry": ["roc"],
        "auxiliary": ["ssl_channel"],
        "exit": ["roc"],
        "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ssl_ma": {
        "entry": ["ma_crossover"],
        "auxiliary": ["ssl_channel"],
        "exit": ["ma_crossover"],
        "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "fire_roc": {
        "entry": ["roc"],
        "auxiliary": ["firestorm_tm"],
        "exit": ["roc"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "fire_ma": {
        "entry": ["ma_crossover"],
        "auxiliary": ["firestorm_tm"],
        "exit": ["ma_crossover"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "wt_roc": {
        "entry": ["wavetrend_reversal", "roc"],
        "auxiliary": [],
        "exit": ["wavetrend_reversal", "roc"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "macd_simple": {
        "entry": ["macd"],
        "auxiliary": [],
        "exit": ["macd"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "macd_roc": {
        "entry": ["macd", "roc"],
        "auxiliary": [],
        "exit": ["macd", "roc"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "macd_ssl": {
        "entry": ["macd"],
        "auxiliary": ["ssl_channel"],
        "exit": ["macd"],
        "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "macd_adx": {
        "entry": ["macd", "adx_filter"],
        "auxiliary": [],
        "exit": ["macd"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "ema_simple": {
        "entry": ["ema"],
        "auxiliary": [],
        "exit": ["ema"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "ema_roc": {
        "entry": ["ema", "roc"],
        "auxiliary": [],
        "exit": ["ema", "roc"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "ema_adx": {
        "entry": ["ema", "adx_filter"],
        "auxiliary": [],
        "exit": ["ema"],
        "trailing": [],
        "combination_mode": "excluyente",
    },
    "roc_donch_ssl": {
        "entry": ["roc", "donchian"],
        "auxiliary": ["ssl_channel"],
        "exit": ["roc", "donchian"],
        "trailing": ["ssl_channel"],
        "combination_mode": "majority",
        "majority_threshold": 1,
    },
    "roc_ma_ssl": {
        "entry": ["roc", "ma_crossover"],
        "auxiliary": ["ssl_channel"],
        "exit": ["roc", "ma_crossover"],
        "trailing": ["ssl_channel"],
        "combination_mode": "majority",
        "majority_threshold": 1,
    },
    "macd_roc_adx": {
        "entry": ["macd", "roc", "adx_filter"],
        "auxiliary": [],
        "exit": ["macd", "roc"],
        "trailing": [],
        "combination_mode": "majority",
        "majority_threshold": 2,
    },
    "ema_roc_adx": {
        "entry": ["ema", "roc", "adx_filter"],
        "auxiliary": [],
        "exit": ["ema", "roc"],
        "trailing": [],
        "combination_mode": "majority",
        "majority_threshold": 2,
    },
    # ── MTF archetypes: entry on base TF, filtered by daily EMA trend ──
    "roc_mtf": {
        "entry": ["roc"],
        "auxiliary": [],
        "exit": ["roc"],
        "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover",
        "htf_timeframe": "1d",
    },
    "ma_cross_mtf": {
        "entry": ["ma_crossover"],
        "auxiliary": [],
        "exit": ["ma_crossover"],
        "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover",
        "htf_timeframe": "1d",
    },
    "macd_mtf": {
        "entry": ["macd"],
        "auxiliary": [],
        "exit": ["macd"],
        "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover",
        "htf_timeframe": "1d",
    },
    "roc_ssl_mtf": {
        "entry": ["roc"],
        "auxiliary": ["ssl_channel"],
        "exit": ["roc"],
        "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover",
        "htf_timeframe": "1d",
    },
    "ema_roc_mtf": {
        "entry": ["ema", "roc"],
        "auxiliary": [],
        "exit": ["ema", "roc"],
        "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover",
        "htf_timeframe": "1d",
    },
    # ── Direction-optimized ──
    "roc_mtf_longopt": {
        "entry": ["roc"], "auxiliary": [], "exit": ["roc"], "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "roc_shortopt": {
        "entry": ["roc"], "auxiliary": [], "exit": ["roc"], "trailing": [],
        "combination_mode": "excluyente",
    },
    "macd_mtf_longopt": {
        "entry": ["macd"], "auxiliary": [], "exit": ["macd"], "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "macd_shortopt": {
        "entry": ["macd"], "auxiliary": [], "exit": ["macd"], "trailing": [],
        "combination_mode": "excluyente",
    },
    "ma_x_ssl_longopt": {
        "entry": ["ma_crossover"], "auxiliary": ["ssl_channel"],
        "exit": ["ma_crossover"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "ema_mtf_longopt": {
        "entry": ["ema"], "auxiliary": [], "exit": ["ema"], "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    # ── Wave 3 ──
    "rsi_roc": {
        "entry": ["rsi", "roc"], "auxiliary": [], "exit": ["rsi", "roc"], "trailing": [],
        "combination_mode": "excluyente",
    },
    "rsi_mtf": {
        "entry": ["rsi"], "auxiliary": [], "exit": ["rsi"], "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "bband_roc": {
        "entry": ["bollinger_bands", "roc"], "auxiliary": [],
        "exit": ["bollinger_bands", "roc"], "trailing": [],
        "combination_mode": "excluyente",
    },
    "wt_filter_roc": {
        "entry": ["roc"], "auxiliary": ["wavetrend_reversal"],
        "exit": ["roc"], "trailing": ["wavetrend_reversal"],
        "combination_mode": "excluyente",
    },
    "roc_mtf_roc": {
        "entry": ["roc"], "auxiliary": [], "exit": ["roc"], "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "roc", "htf_timeframe": "1d",
    },
    "macd_roc_mtf": {
        "entry": ["macd", "roc"], "auxiliary": [], "exit": ["macd", "roc"], "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    # ── Wave 4 ──
    "donchian_mtf": {
        "entry": ["donchian"], "auxiliary": [], "exit": ["donchian"], "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "donchian_roc_mtf": {
        "entry": ["donchian", "roc"], "auxiliary": [], "exit": ["donchian", "roc"], "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "ema_adx_mtf": {
        "entry": ["ema", "adx_filter"], "auxiliary": [], "exit": ["ema"], "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "roc_macd_mtf": {
        "entry": ["roc", "macd"], "auxiliary": [], "exit": ["roc", "macd"], "trailing": [],
        "combination_mode": "excluyente",
        "htf_filter": "roc", "htf_timeframe": "1d",
    },
    "ssl_adx_mtf": {
        "entry": ["adx_filter"], "auxiliary": ["ssl_channel"],
        "exit": ["adx_filter"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "triple_mtf": {
        "entry": ["roc", "macd", "adx_filter"], "auxiliary": [],
        "exit": ["roc", "macd"], "trailing": [],
        "combination_mode": "majority", "majority_threshold": 2,
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
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


def get_htf_filter(archetype: str) -> tuple[str | None, str | None]:
    """Return (indicator_name, timeframe) for higher-TF filter, or (None, None)."""
    cfg = ARCHETYPE_INDICATORS[archetype]
    return cfg.get("htf_filter"), cfg.get("htf_timeframe")