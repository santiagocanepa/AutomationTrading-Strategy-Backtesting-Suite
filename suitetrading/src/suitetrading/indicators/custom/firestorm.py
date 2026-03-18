"""Firestorm indicator — exact Pine Script replica.

This is a **Supertrend variant** that uses:
  - ``ohlc4`` as the source (not ``hl2`` like standard Supertrend)
  - EMA of True Range (not SMA/RMA like standard ATR)
  - Ratchet logic: bands only tighten, never widen, within a trend

Pine logic:
    src = ohlc4
    atr = EMA(true_range, Periods)
    up = src - Multiplier * atr
    up = close[1] > up[1] ? max(up, up[1]) : up     # ratchet up
    dn = src + Multiplier * atr
    dn = close[1] < dn[1] ? min(dn, dn[1]) : dn     # ratchet down
    trend = 1 initially
    trend = -1 and close > dn[1] → 1
    trend =  1 and close < up[1] → -1
    buy  = trend changed from -1 to 1
    sell = trend changed from 1 to -1

Also exports the *TM variant* (Firestorm TM) used for stop-loss. Same algo
but can run on a different timeframe with different parameters.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

from suitetrading.indicators.base import Indicator


@njit(cache=True)
def _true_range(high: np.ndarray, low: np.ndarray, close: np.ndarray) -> np.ndarray:
    """True Range matching Pine Script's ta.tr."""
    n = len(high)
    tr = np.empty(n, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, max(hc, lc))
    return tr


@njit(cache=True)
def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """EMA matching Pine Script's ta.ema (seed = first value)."""
    n = len(data)
    out = np.empty(n, dtype=np.float64)
    alpha = 2.0 / (period + 1)
    out[0] = data[0]
    for i in range(1, n):
        out[i] = alpha * data[i] + (1.0 - alpha) * out[i - 1]
    return out


@njit(cache=True)
def _firestorm_core(
    ohlc4: np.ndarray,
    close: np.ndarray,
    atr_ema: np.ndarray,
    multiplier: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Core Firestorm computation.

    Returns (up, dn, trend, buy_signal, sell_signal).
    """
    n = len(close)
    up = np.empty(n, dtype=np.float64)
    dn = np.empty(n, dtype=np.float64)
    trend = np.ones(n, dtype=np.int64)
    buy = np.zeros(n, dtype=np.bool_)
    sell = np.zeros(n, dtype=np.bool_)

    for i in range(n):
        raw_up = ohlc4[i] - multiplier * atr_ema[i]
        raw_dn = ohlc4[i] + multiplier * atr_ema[i]

        if i == 0:
            up[i] = raw_up
            dn[i] = raw_dn
        else:
            # Ratchet: up can only move up when in uptrend
            up[i] = max(raw_up, up[i - 1]) if close[i - 1] > up[i - 1] else raw_up
            # Ratchet: dn can only move down when in downtrend
            dn[i] = min(raw_dn, dn[i - 1]) if close[i - 1] < dn[i - 1] else raw_dn

        if i == 0:
            trend[i] = 1
        else:
            prev_trend = trend[i - 1]
            if prev_trend == -1 and close[i] > dn[i - 1]:
                trend[i] = 1
            elif prev_trend == 1 and close[i] < up[i - 1]:
                trend[i] = -1
            else:
                trend[i] = prev_trend

            # Signal on trend change
            if trend[i] == 1 and trend[i - 1] == -1:
                buy[i] = True
            elif trend[i] == -1 and trend[i - 1] == 1:
                sell[i] = True

    return up, dn, trend, buy, sell


def firestorm(
    open_: np.ndarray | pd.Series,
    high: np.ndarray | pd.Series,
    low: np.ndarray | pd.Series,
    close: np.ndarray | pd.Series,
    period: int = 10,
    multiplier: float = 1.8,
) -> dict[str, pd.Series]:
    """Compute Firestorm indicator.

    Parameters
    ----------
    open_, high, low, close : array-like
        OHLC price data.
    period : int
        ATR EMA period (default 10).
    multiplier : float
        ATR multiplier for band width (default 1.8).

    Returns
    -------
    dict with keys: 'up', 'dn', 'trend', 'buy', 'sell'
    """
    idx = close.index if isinstance(close, pd.Series) else None

    o = np.asarray(open_, dtype=np.float64)
    h = np.asarray(high, dtype=np.float64)
    lo = np.asarray(low, dtype=np.float64)
    c = np.asarray(close, dtype=np.float64)

    ohlc4 = (o + h + lo + c) / 4.0
    tr = _true_range(h, lo, c)
    atr_ema = _ema(tr, period)

    up_arr, dn_arr, trend_arr, buy_arr, sell_arr = _firestorm_core(ohlc4, c, atr_ema, multiplier)

    def _to_series(arr: np.ndarray, name: str) -> pd.Series:
        if idx is not None:
            return pd.Series(arr, index=idx, name=name)
        return pd.Series(arr, name=name)

    return {
        "up": _to_series(up_arr, "firestorm_up"),
        "dn": _to_series(dn_arr, "firestorm_dn"),
        "trend": _to_series(trend_arr, "firestorm_trend"),
        "buy": _to_series(buy_arr, "firestorm_buy"),
        "sell": _to_series(sell_arr, "firestorm_sell"),
    }


# ── Indicator ABC wrappers ───────────────────────────────────────


class Firestorm(Indicator):
    """Firestorm — entry signal indicator (trend reversal + hold-bars)."""

    def compute(
        self,
        df: pd.DataFrame,
        *,
        period: int = 10,
        multiplier: float = 1.8,
        hold_bars: int = 1,
        direction: str = "long",
    ) -> pd.Series:
        self._validate_ohlcv(df)
        result = firestorm(df["open"], df["high"], df["low"], df["close"], period, multiplier)
        raw = result["buy"] if direction == "long" else result["sell"]
        return self._hold_bars(raw, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        # Narrowed: multiplier [0.5-1.5] (top1% optimal ~0.9, r=-0.302)
        # hold_bars [1-10] (top1% mean ~14 but r=-0.233, low is better)
        return {
            "period": {"type": "int", "min": 2, "max": 50, "default": 10},
            "multiplier": {"type": "float", "min": 0.5, "max": 1.5, "default": 0.9},
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 1},
        }


class FirestormTM(Indicator):
    """Firestorm TM — stop-loss band generator (no entry signals).

    Returns the `up` band as the "signal" for convenience. Access
    `firestorm()` directly for both bands.
    """

    def compute(
        self,
        df: pd.DataFrame,
        *,
        period: int = 9,
        multiplier: float = 0.9,
        direction: str = "long",
    ) -> pd.Series:
        self._validate_ohlcv(df)
        result = firestorm(df["open"], df["high"], df["low"], df["close"], period, multiplier)
        # For long SL: we use the `up` band; for short SL: the `dn` band
        return result["up"] if direction == "long" else result["dn"]

    def params_schema(self) -> dict[str, dict]:
        # Narrowed: multiplier [0.5-1.2] (top1% optimal [0.8-1.0])
        return {
            "period": {"type": "int", "min": 2, "max": 50, "default": 9},
            "multiplier": {"type": "float", "min": 0.5, "max": 1.2, "default": 0.9},
        }
