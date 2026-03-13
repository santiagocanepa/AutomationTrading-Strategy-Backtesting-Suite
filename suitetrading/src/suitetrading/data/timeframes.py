"""Unified timeframe mapping — single source of truth for the entire project.

Every module that needs timeframe conversion must import from here, never
maintain its own mapping.  The canonical internal key is a short lowercase
string like ``"1m"``, ``"4h"``, ``"1d"``.
"""

from __future__ import annotations

from typing import ClassVar

# ── Master mapping ───────────────────────────────────────────────────────────
# Each entry: internal_key → {pine, binance, ccxt, pandas, seconds}
# ``None`` means the representation does not exist for that system.

TIMEFRAME_MAP: dict[str, dict[str, str | int | None]] = {
    "1m":  {"pine": "1",   "binance": "1m",  "ccxt": "1m",  "alpaca": "1Min",   "pandas": "1min",   "seconds": 60},
    "3m":  {"pine": "3",   "binance": "3m",  "ccxt": "3m",  "alpaca": None,     "pandas": "3min",   "seconds": 180},
    "5m":  {"pine": "5",   "binance": "5m",  "ccxt": "5m",  "alpaca": "5Min",   "pandas": "5min",   "seconds": 300},
    "15m": {"pine": "15",  "binance": "15m", "ccxt": "15m", "alpaca": "15Min",  "pandas": "15min",  "seconds": 900},
    "30m": {"pine": "30",  "binance": "30m", "ccxt": "30m", "alpaca": "30Min",  "pandas": "30min",  "seconds": 1800},
    "45m": {"pine": "45",  "binance": None,  "ccxt": None,  "alpaca": None,     "pandas": "45min",  "seconds": 2700},
    "1h":  {"pine": "60",  "binance": "1h",  "ccxt": "1h",  "alpaca": "1Hour",  "pandas": "1h",     "seconds": 3600},
    "4h":  {"pine": "240", "binance": "4h",  "ccxt": "4h",  "alpaca": "4Hour",  "pandas": "4h",     "seconds": 14400},
    "1d":  {"pine": "D",   "binance": "1d",  "ccxt": "1d",  "alpaca": "1Day",   "pandas": "1D",     "seconds": 86400},
    "1w":  {"pine": "W",   "binance": "1w",  "ccxt": "1w",  "alpaca": "1Week",  "pandas": "1W-MON", "seconds": 604800},
    "1M":  {"pine": "M",   "binance": "1M",  "ccxt": "1M",  "alpaca": "1Month", "pandas": "1ME",    "seconds": None},
}

VALID_TIMEFRAMES: frozenset[str] = frozenset(TIMEFRAME_MAP)

# Reverse look-ups built once at import time
_ALIASES: dict[str, str] = {}
for _key, _info in TIMEFRAME_MAP.items():
    _ALIASES[_key] = _key
    for _field in ("pine", "binance", "ccxt", "alpaca", "pandas"):
        _val = _info[_field]
        if _val is not None and _val not in _ALIASES:
            _ALIASES[str(_val)] = _key

# Extra common aliases not covered by the map
_ALIASES.update({"1min": "1m", "3min": "3m", "5min": "5m", "15min": "15m",
                 "30min": "30m", "45min": "45m"})

# ── Public helpers ───────────────────────────────────────────────────────────


def normalize_timeframe(tf: str) -> str:
    """Convert any known TF representation to the canonical internal key.

    Accepts Pine Script (``"60"``), Binance (``"1h"``), pandas (``"1h"``),
    or the internal key itself.

    Raises ``ValueError`` for unknown strings.
    """
    result = _ALIASES.get(tf)
    if result is None:
        raise ValueError(
            f"Unknown timeframe {tf!r}. Valid keys: {sorted(VALID_TIMEFRAMES)}"
        )
    return result


def tf_to_pandas_offset(tf: str) -> str:
    """Return the pandas offset alias for *tf* (e.g. ``'1h'`` → ``'1h'``)."""
    key = normalize_timeframe(tf)
    return str(TIMEFRAME_MAP[key]["pandas"])


def tf_to_seconds(tf: str) -> int | None:
    """Return duration in seconds, or ``None`` for variable-length TFs (1M)."""
    key = normalize_timeframe(tf)
    val = TIMEFRAME_MAP[key]["seconds"]
    return int(val) if val is not None else None


def tf_to_binance(tf: str) -> str | None:
    """Return the Binance API string, or ``None`` if the TF has no native equivalent."""
    key = normalize_timeframe(tf)
    val = TIMEFRAME_MAP[key]["binance"]
    return str(val) if val is not None else None


def tf_to_ccxt(tf: str) -> str | None:
    """Return the CCXT string, or ``None`` if unavailable."""
    key = normalize_timeframe(tf)
    val = TIMEFRAME_MAP[key]["ccxt"]
    return str(val) if val is not None else None


def tf_to_alpaca(tf: str) -> str | None:
    """Return the Alpaca TimeFrame string, or ``None`` if unavailable."""
    key = normalize_timeframe(tf)
    val = TIMEFRAME_MAP[key]["alpaca"]
    return str(val) if val is not None else None


def tf_to_pine(tf: str) -> str:
    """Return the Pine Script string (e.g. ``'1h'`` → ``'60'``)."""
    key = normalize_timeframe(tf)
    return str(TIMEFRAME_MAP[key]["pine"])


def is_intraday(tf: str) -> bool:
    """Return ``True`` for timeframes ≤ 4h, ``False`` for D/W/M."""
    secs = tf_to_seconds(tf)
    if secs is None:
        return False  # 1M is not intraday
    return secs <= 14400


def partition_scheme(tf: str) -> str:
    """Return ``'monthly'`` for intraday TFs, ``'yearly'`` for daily+."""
    return "monthly" if is_intraday(tf) else "yearly"
