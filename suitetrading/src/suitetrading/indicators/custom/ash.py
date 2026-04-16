"""ASH (Absolute Strength Histogram) — exact Pine Script replica.

Measures absolute bull vs bear strength using one of three modes:
  - RSI:        directional price change
  - Stochastic: distance from lowest/highest in window
  - ADX:        directional high/low movement

Pipeline: raw bulls/bears → MA(length) → MA(smooth) → histogram.
Signal: green histogram = bullish, red/orange histogram = bearish.

Pine reference: Strategy-Indicators.pinescript lines 180-244.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from suitetrading.indicators.base import Indicator


# ── Moving average helpers (pure pandas/numpy) ─────────────────────


def _sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=1).mean()


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _wma(series: pd.Series, period: int) -> pd.Series:
    weights = np.arange(1, period + 1, dtype=np.float64)
    return series.rolling(window=period, min_periods=1).apply(
        lambda x: np.dot(x[-len(weights):], weights[-len(x):]) / weights[-len(x):].sum(),
        raw=True,
    )


def _ma(series: pd.Series, period: int, ma_type: str) -> pd.Series:
    """Apply moving average by type (mirrors Pine Script ash_ma helper)."""
    if ma_type == "sma":
        return _sma(series, period)
    if ma_type == "ema":
        return _ema(series, period)
    if ma_type == "wma":
        return _wma(series, period)
    return _ema(series, period)


# ── Core ASH computation ───────────────────────────────────────────


def ash_compute(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    *,
    length: int = 9,
    smooth: int = 3,
    mode: str = "rsi",
    ma_type: str = "ema",
) -> dict[str, pd.Series]:
    """Compute ASH components.

    Returns dict with: sm_bulls, sm_bears, diff, bullish, bearish.
    """
    mode = mode.lower()
    ma_type = ma_type.lower()

    # ── Raw bulls/bears by mode ──────────────────────────────────
    if mode == "rsi":
        delta = close - close.shift(1)
        abs_delta = delta.abs()
        bulls_raw = 0.5 * (abs_delta + delta)
        bears_raw = 0.5 * (abs_delta - delta)
    elif mode == "stochastic":
        bulls_raw = close - close.rolling(window=length, min_periods=1).min()
        bears_raw = close.rolling(window=length, min_periods=1).max() - close
    elif mode == "adx":
        h_delta = high - high.shift(1)
        l_delta = low.shift(1) - low
        bulls_raw = 0.5 * (h_delta.abs() + h_delta)
        bears_raw = 0.5 * (l_delta.abs() + l_delta)
    else:
        raise ValueError(f"Unknown ASH mode: {mode!r}")

    bulls_raw = bulls_raw.fillna(0.0)
    bears_raw = bears_raw.fillna(0.0)

    # ── Double smoothing (matches Pine Script) ───────────────────
    avg_bulls = _ma(bulls_raw, length, ma_type)
    avg_bears = _ma(bears_raw, length, ma_type)

    sm_bulls = _ma(avg_bulls, smooth, ma_type)
    sm_bears = _ma(avg_bears, smooth, ma_type)

    # ── Histogram ────────────────────────────────────────────────
    diff = (sm_bulls - sm_bears).abs()

    # ── Color logic (Pine Script replica) ────────────────────────
    # Green: diff > sm_bears AND diff <= sm_bulls AND sm_bulls growing
    # Red/Orange: diff > sm_bulls
    bulls_growing = sm_bulls >= sm_bulls.shift(1)
    bullish = (diff > sm_bears) & ~(diff > sm_bulls) & bulls_growing
    bearish = diff > sm_bulls

    # Fill NaN from shift operations
    bullish = bullish.fillna(False)
    bearish = bearish.fillna(False)

    return {
        "sm_bulls": sm_bulls,
        "sm_bears": sm_bears,
        "diff": diff,
        "bullish": bullish,
        "bearish": bearish,
    }


# ── Indicator ABC wrapper ─────────────────────────────────────────


class ASH(Indicator):
    """ASH — Absolute Strength Histogram signal indicator."""

    def compute(
        self,
        df: pd.DataFrame,
        *,
        length: int = 9,
        smooth: int = 3,
        mode: str = "rsi",
        ma_type: str = "ema",
        signal_mode: str = "bullish",
    ) -> pd.Series:
        self._validate_ohlcv(df)
        result = ash_compute(
            df["close"], df["high"], df["low"],
            length=length, smooth=smooth, mode=mode, ma_type=ma_type,
        )
        signal = result["bullish"] if signal_mode == "bullish" else result["bearish"]
        return signal.astype(bool)

    def params_schema(self) -> dict[str, dict]:
        return {
            "length": {"type": "int", "min": 3, "max": 30, "default": 9},
            "smooth": {"type": "int", "min": 1, "max": 10, "default": 3},
            "mode": {"type": "str", "choices": ["rsi", "stochastic", "adx"], "default": "rsi"},
            "ma_type": {"type": "str", "choices": ["ema", "sma", "wma"], "default": "ema"},
            "signal_mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
        }
