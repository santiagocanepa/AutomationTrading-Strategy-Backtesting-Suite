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
    # ── Full risk chain (TP1 + BE + SSL trailing) ──
    "roc_fullrisk": {
        "entry": ["roc"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "roc_fullrisk_mtf": {
        "entry": ["roc"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "macd_fullrisk": {
        "entry": ["macd"], "auxiliary": ["ssl_channel"],
        "exit": ["macd"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ma_x_fullrisk": {
        "entry": ["ma_crossover"], "auxiliary": ["ssl_channel"],
        "exit": ["ma_crossover"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ema_fullrisk_mtf": {
        "entry": ["ema"], "auxiliary": ["ssl_channel"],
        "exit": ["ema"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    # ── Full risk chain + pyramid ──
    "roc_fullrisk_pyr": {
        "entry": ["roc"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "macd_fullrisk_pyr": {
        "entry": ["macd"], "auxiliary": ["ssl_channel"],
        "exit": ["macd"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ma_x_fullrisk_pyr": {
        "entry": ["ma_crossover"], "auxiliary": ["ssl_channel"],
        "exit": ["ma_crossover"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "roc_fullrisk_pyr_mtf": {
        "entry": ["roc"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    # ── Full risk chain + time exit ──
    "roc_fullrisk_time": {
        "entry": ["roc"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    # ── Full risk chain + pyramid + time exit (all features) ──
    "roc_fullrisk_all": {
        "entry": ["roc"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    # ── More indicators with pyramid ──
    "donchian_fullrisk_pyr": {
        "entry": ["donchian"], "auxiliary": ["ssl_channel"],
        "exit": ["donchian"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ema_fullrisk_pyr": {
        "entry": ["ema"], "auxiliary": ["ssl_channel"],
        "exit": ["ema"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "rsi_fullrisk_pyr": {
        "entry": ["rsi"], "auxiliary": ["ssl_channel"],
        "exit": ["rsi"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    # ── Cross-indicator combos with pyramid ──
    "roc_macd_fullrisk_pyr": {
        "entry": ["roc", "macd"], "auxiliary": ["ssl_channel"],
        "exit": ["roc", "macd"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "roc_ema_fullrisk_pyr": {
        "entry": ["roc", "ema"], "auxiliary": ["ssl_channel"],
        "exit": ["roc", "ema"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "macd_ema_fullrisk_pyr": {
        "entry": ["macd", "ema"], "auxiliary": ["ssl_channel"],
        "exit": ["macd", "ema"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "roc_adx_fullrisk_pyr": {
        "entry": ["roc", "adx_filter"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    # ── MTF variants of top performers ──
    "macd_fullrisk_pyr_mtf": {
        "entry": ["macd"], "auxiliary": ["ssl_channel"],
        "exit": ["macd"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "roc_adx_fullrisk_pyr_mtf": {
        "entry": ["roc", "adx_filter"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    # ── MACD time exit / all features ──
    "macd_fullrisk_time": {
        "entry": ["macd"], "auxiliary": ["ssl_channel"],
        "exit": ["macd"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "macd_fullrisk_all": {
        "entry": ["macd"], "auxiliary": ["ssl_channel"],
        "exit": ["macd"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    # ── New indicators with fullrisk + pyramid ──
    "ssl_fullrisk_pyr": {
        "entry": ["ssl_channel"], "auxiliary": [],
        "exit": ["ssl_channel"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "wt_fullrisk_pyr": {
        "entry": ["wavetrend_reversal"], "auxiliary": ["ssl_channel"],
        "exit": ["wavetrend_reversal"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "bband_fullrisk_pyr": {
        "entry": ["bollinger_bands"], "auxiliary": ["ssl_channel"],
        "exit": ["bollinger_bands"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    # ── Alternative HTF filters ──
    "roc_fullrisk_htf_macd": {
        "entry": ["roc"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "macd", "htf_timeframe": "1d",
    },
    "roc_fullrisk_pyr_htf_macd": {
        "entry": ["roc"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "macd", "htf_timeframe": "1d",
    },
    "macd_fullrisk_htf_ema": {
        "entry": ["macd"], "auxiliary": ["ssl_channel"],
        "exit": ["macd"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "ema", "htf_timeframe": "1d",
    },
    # ══ Sprint 8: FTM stop variants (firestorm_tm as auxiliary) ══════
    "roc_fullrisk_pyr_ftm": {
        "entry": ["roc"], "auxiliary": ["ssl_channel", "firestorm_tm"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "macd_fullrisk_pyr_ftm": {
        "entry": ["macd"], "auxiliary": ["ssl_channel", "firestorm_tm"],
        "exit": ["macd"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ma_x_fullrisk_pyr_ftm": {
        "entry": ["ma_crossover"], "auxiliary": ["ssl_channel", "firestorm_tm"],
        "exit": ["ma_crossover"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "roc_fullrisk_pyr_mtf_ftm": {
        "entry": ["roc"], "auxiliary": ["ssl_channel", "firestorm_tm"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "donchian_fullrisk_pyr_ftm": {
        "entry": ["donchian"], "auxiliary": ["ssl_channel", "firestorm_tm"],
        "exit": ["donchian"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ema_fullrisk_pyr_ftm": {
        "entry": ["ema"], "auxiliary": ["ssl_channel", "firestorm_tm"],
        "exit": ["ema"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "rsi_fullrisk_pyr_ftm": {
        "entry": ["rsi"], "auxiliary": ["ssl_channel", "firestorm_tm"],
        "exit": ["rsi"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "roc_macd_fullrisk_pyr_ftm": {
        "entry": ["roc", "macd"], "auxiliary": ["ssl_channel", "firestorm_tm"],
        "exit": ["roc", "macd"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "roc_ema_fullrisk_pyr_ftm": {
        "entry": ["roc", "ema"], "auxiliary": ["ssl_channel", "firestorm_tm"],
        "exit": ["roc", "ema"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "macd_ema_fullrisk_pyr_ftm": {
        "entry": ["macd", "ema"], "auxiliary": ["ssl_channel", "firestorm_tm"],
        "exit": ["macd", "ema"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    # ── Sprint 8: Trailing policy variants (ATR-based trailing) ──────
    "roc_fullrisk_pyr_trail_policy": {
        "entry": ["roc"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "macd_fullrisk_pyr_trail_policy": {
        "entry": ["macd"], "auxiliary": ["ssl_channel"],
        "exit": ["macd"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ma_x_fullrisk_pyr_trail_policy": {
        "entry": ["ma_crossover"], "auxiliary": ["ssl_channel"],
        "exit": ["ma_crossover"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "roc_fullrisk_pyr_mtf_trail_policy": {
        "entry": ["roc"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "donchian_fullrisk_pyr_trail_policy": {
        "entry": ["donchian"], "auxiliary": ["ssl_channel"],
        "exit": ["donchian"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    # ══ Sprint 9: New indicator archetypes ═══════════════════════════
    "squeeze_fullrisk_pyr": {
        "entry": ["squeeze"], "auxiliary": ["ssl_channel"],
        "exit": ["squeeze"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "stochrsi_fullrisk_pyr": {
        "entry": ["stoch_rsi"], "auxiliary": ["ssl_channel"],
        "exit": ["stoch_rsi"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ichimoku_fullrisk_pyr": {
        "entry": ["ichimoku"], "auxiliary": ["ssl_channel"],
        "exit": ["ichimoku"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "obv_fullrisk_pyr": {
        "entry": ["obv"], "auxiliary": ["ssl_channel"],
        "exit": ["obv"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "squeeze_roc_fullrisk_pyr": {
        "entry": ["squeeze", "roc"], "auxiliary": ["ssl_channel"],
        "exit": ["squeeze", "roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ichimoku_macd_fullrisk_pyr": {
        "entry": ["ichimoku", "macd"], "auxiliary": ["ssl_channel"],
        "exit": ["ichimoku", "macd"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "stochrsi_ema_fullrisk_pyr": {
        "entry": ["stoch_rsi", "ema"], "auxiliary": ["ssl_channel"],
        "exit": ["stoch_rsi", "ema"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "squeeze_fullrisk_pyr_mtf": {
        "entry": ["squeeze"], "auxiliary": ["ssl_channel"],
        "exit": ["squeeze"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "ichimoku_fullrisk_pyr_mtf": {
        "entry": ["ichimoku"], "auxiliary": ["ssl_channel"],
        "exit": ["ichimoku"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
        "htf_filter": "ma_crossover", "htf_timeframe": "1d",
    },
    "obv_roc_fullrisk_pyr": {
        "entry": ["obv", "roc"], "auxiliary": ["ssl_channel"],
        "exit": ["obv", "roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "squeeze_ssl_fullrisk_pyr": {
        "entry": ["squeeze"], "auxiliary": ["ssl_channel"],
        "exit": ["squeeze"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ichimoku_ssl_fullrisk_pyr": {
        "entry": ["ichimoku"], "auxiliary": ["ssl_channel"],
        "exit": ["ichimoku"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },

    # ── Phase 5: regime-filtered & multi-feature archetypes ──────────
    #
    # These use 2-4 indicators per strategy, combining entry signals
    # with regime filters and volume confirmation.  The higher feature
    # count creates stronger signal discrimination (fewer but more
    # confident entries).

    # Trend + regime filter (only trade when volatility is elevated)
    "roc_regime_fullrisk_pyr": {
        "entry": ["roc", "volatility_regime"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ema_regime_fullrisk_pyr": {
        "entry": ["ema", "volatility_regime"], "auxiliary": ["ssl_channel"],
        "exit": ["ema"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "macd_regime_fullrisk_pyr": {
        "entry": ["macd", "volatility_regime"], "auxiliary": ["ssl_channel"],
        "exit": ["macd"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "donchian_regime_fullrisk_pyr": {
        "entry": ["donchian", "volatility_regime"], "auxiliary": ["ssl_channel"],
        "exit": ["donchian"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },

    # Momentum + volume confirmation (entry on both momentum + volume spike)
    "roc_volspike_fullrisk_pyr": {
        "entry": ["roc", "volume_spike"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "donchian_volspike_fullrisk_pyr": {
        "entry": ["donchian", "volume_spike"], "auxiliary": ["ssl_channel"],
        "exit": ["donchian"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ema_volspike_fullrisk_pyr": {
        "entry": ["ema", "volume_spike"], "auxiliary": ["ssl_channel"],
        "exit": ["ema"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },

    # Divergence-based (mean reversion entries)
    "divergence_fullrisk_pyr": {
        "entry": ["momentum_divergence"], "auxiliary": ["ssl_channel"],
        "exit": ["momentum_divergence"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "divergence_adx_fullrisk_pyr": {
        "entry": ["momentum_divergence", "adx_filter"], "auxiliary": ["ssl_channel"],
        "exit": ["momentum_divergence"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },

    # Triple-stacked (3 entry features — maximum discrimination)
    "roc_adx_regime_fullrisk_pyr": {
        "entry": ["roc", "adx_filter", "volatility_regime"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "roc_volspike_regime_fullrisk_pyr": {
        "entry": ["roc", "volume_spike", "volatility_regime"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "ema_adx_regime_fullrisk_pyr": {
        "entry": ["ema", "adx_filter", "volatility_regime"], "auxiliary": ["ssl_channel"],
        "exit": ["ema"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },

    # Crypto-specific (need futures data; fall back to no-signal if absent)
    "funding_reversal_fullrisk_pyr": {
        "entry": ["funding_rate"], "auxiliary": ["ssl_channel"],
        "exit": ["funding_rate"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "roc_oi_fullrisk_pyr": {
        "entry": ["roc", "oi_divergence"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "roc_funding_fullrisk_pyr": {
        "entry": ["roc", "funding_rate"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "roc_lsratio_fullrisk_pyr": {
        "entry": ["roc", "long_short_ratio"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },

    # Multi-alpha: momentum + futures + regime (maximum feature stacking)
    "roc_funding_regime_fullrisk_pyr": {
        "entry": ["roc", "funding_rate", "volatility_regime"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },
    "roc_oi_regime_fullrisk_pyr": {
        "entry": ["roc", "oi_divergence", "volatility_regime"], "auxiliary": ["ssl_channel"],
        "exit": ["roc"], "trailing": ["ssl_channel"],
        "combination_mode": "excluyente",
    },

    # ══ Rich Archetype: Pine Script-level complexity ═════════════════
    # Entry indicators with dynamic states (Excluyente/Opcional/Desactivado),
    # per-indicator TF, and num_optional_required — all suggested by Optuna.
    # Aligned with Pine Script original: ASH, SSL, Squeeze, MACD, Firestorm,
    # WaveTrend, MTF MAs, + complementary indicators.
    "rich_stock": {
        "entry": [
            # Pine Script core (active by default in Pine)
            "ssl_channel",          # impulse (chart TF)
            "squeeze",              # mean-reversion within trend
            "firestorm",            # price action + volume
            "wavetrend_reversal",   # reversal detection
            "ma_crossover",         # MTF conditions (close vs SMA, per-indicator TF)
            "macd",                 # momentum confirmation
            # Complementary
            "bollinger_bands",      # volatility breakout
            "adx_filter",          # trend strength filter
            "rsi",                  # overbought/oversold
            "obv",                  # volume confirmation
            "ash",                  # absolute strength histogram
        ],
        "auxiliary": ["firestorm_tm"],
        "exit": ["ssl_channel", "wavetrend_reversal"],
        "trailing": ["ssl_channel_low"],
        "combination_mode": "excluyente",
    },

    # ══ Per-symbol Rich Archetypes (fANOVA-selected, top 7 per symbol) ══
    # Each symbol gets indicators ranked by fANOVA importance from v4
    # discovery (10K trials NSGA-II).  Reduces search space ~729x vs
    # rich_stock (3^7 vs 3^11 state combinations).
    "rich_spy": {
        "entry": ["ssl_channel", "wavetrend_reversal", "firestorm", "rsi", "adx_filter", "macd", "bollinger_bands"],
        "auxiliary": ["firestorm_tm"], "exit": ["ssl_channel", "wavetrend_reversal"],
        "trailing": ["ssl_channel_low"], "combination_mode": "excluyente",
    },
    "rich_qqq": {
        "entry": ["firestorm", "obv", "ash", "macd", "rsi", "wavetrend_reversal", "adx_filter"],
        "auxiliary": ["firestorm_tm"], "exit": ["wavetrend_reversal"],
        "trailing": ["ssl_channel_low"], "combination_mode": "excluyente",
    },
    "rich_tsla": {
        "entry": ["firestorm", "ash", "bollinger_bands", "wavetrend_reversal", "squeeze", "ssl_channel", "rsi"],
        "auxiliary": ["firestorm_tm"], "exit": ["ssl_channel", "wavetrend_reversal"],
        "trailing": ["ssl_channel_low"], "combination_mode": "excluyente",
    },
    "rich_nvda": {
        "entry": ["squeeze", "macd", "firestorm", "obv", "ash", "ma_crossover", "wavetrend_reversal"],
        "auxiliary": ["firestorm_tm"], "exit": ["wavetrend_reversal"],
        "trailing": ["ssl_channel_low"], "combination_mode": "excluyente",
    },
    "rich_aapl": {
        "entry": ["ash", "firestorm", "ssl_channel", "ma_crossover", "wavetrend_reversal", "macd", "bollinger_bands"],
        "auxiliary": ["firestorm_tm"], "exit": ["ssl_channel", "wavetrend_reversal"],
        "trailing": ["ssl_channel_low"], "combination_mode": "excluyente",
    },
    "rich_gld": {
        "entry": ["firestorm", "ma_crossover", "squeeze", "obv", "rsi", "macd", "bollinger_bands"],
        "auxiliary": ["firestorm_tm"], "exit": ["firestorm"],
        "trailing": ["ssl_channel_low"], "combination_mode": "excluyente",
    },
    "rich_xlk": {
        "entry": ["rsi", "firestorm", "ssl_channel", "ash", "squeeze", "adx_filter", "bollinger_bands"],
        "auxiliary": ["firestorm_tm"], "exit": ["ssl_channel"],
        "trailing": ["ssl_channel_low"], "combination_mode": "excluyente",
    },
    "rich_xle": {
        "entry": ["firestorm", "rsi", "obv", "wavetrend_reversal", "ma_crossover", "ssl_channel", "macd"],
        "auxiliary": ["firestorm_tm"], "exit": ["ssl_channel", "wavetrend_reversal"],
        "trailing": ["ssl_channel_low"], "combination_mode": "excluyente",
    },
    "rich_tlt": {
        "entry": ["firestorm", "ma_crossover", "rsi", "ssl_channel", "bollinger_bands", "obv", "macd"],
        "auxiliary": ["firestorm_tm"], "exit": ["ssl_channel"],
        "trailing": ["ssl_channel_low"], "combination_mode": "excluyente",
    },
    "rich_iwm": {
        "entry": ["macd", "firestorm", "ssl_channel", "ma_crossover", "bollinger_bands", "ash", "adx_filter"],
        "auxiliary": ["firestorm_tm"], "exit": ["ssl_channel"],
        "trailing": ["ssl_channel_low"], "combination_mode": "excluyente",
    },
}


# ── Tier-1 macro archetypes (auto-generated) ────────────────────────
# 6 entry indicators × 3 macro filters = 18 combinations.
# Each uses the base entry + macro filter as entry signals,
# ssl_channel as auxiliary/trailing, excluyente combination.

_MACRO_ENTRIES = {
    "roc": {"entry_ind": "roc", "exit_ind": "roc"},
    "macd": {"entry_ind": "macd", "exit_ind": "macd"},
    "ema": {"entry_ind": "ema", "exit_ind": "ema"},
    "donchian": {"entry_ind": "donchian", "exit_ind": "donchian"},
    "divergence": {"entry_ind": "momentum_divergence", "exit_ind": "momentum_divergence"},
    "ssl": {"entry_ind": "ssl_channel", "exit_ind": "ssl_channel"},
}

_MACRO_FILTERS = ["vrp", "yield_curve", "hurst"]

for _entry_key, _entry_cfg in _MACRO_ENTRIES.items():
    for _macro in _MACRO_FILTERS:
        _name = f"{_entry_key}_macro_{_macro}_fullrisk_pyr"
        ARCHETYPE_INDICATORS[_name] = {
            "entry": [_entry_cfg["entry_ind"], _macro],
            "auxiliary": ["ssl_channel"],
            "exit": [_entry_cfg["exit_ind"]],
            "trailing": ["ssl_channel"],
            "combination_mode": "excluyente",
        }

del _MACRO_ENTRIES, _MACRO_FILTERS, _entry_key, _entry_cfg, _macro, _name


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