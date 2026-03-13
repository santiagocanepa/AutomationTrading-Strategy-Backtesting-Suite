"""WaveTrend indicator — exact Pine Script replica.

Two modes:
  1. **Reversal**: wt1 crosses wt2 while in oversold/overbought zone.
  2. **Divergence**: price makes new low/high but wt2 does not (via pivots).

Pine logic (f_wavetrend):
    esa  = EMA(hlc3, channel_len)
    de   = EMA(|hlc3 - esa|, channel_len)
    ci   = (hlc3 - esa) / (0.015 * de)
    wt1  = EMA(ci, average_len)
    wt2  = SMA(wt1, ma_len)
    oversold  = wt2 <= os_level (-60)
    overbought = wt2 >= ob_level (60)
    crossUp   = crossover(wt1, wt2)
    crossDown = crossunder(wt1, wt2)

Reversal signal:
    buy  = crossUp AND oversold  (within lookback window)
    sell = crossDown AND overbought

Divergence (f_findDivs):
    Uses pivothigh/pivotlow on wt2, then checks if price makes
    lower low / higher high while WT makes higher low / lower high.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

from suitetrading.indicators.base import Indicator

# ── Core WaveTrend oscillator ────────────────────────────────────


@njit(cache=True)
def _ema(data: np.ndarray, period: int) -> np.ndarray:
    n = len(data)
    out = np.empty(n, dtype=np.float64)
    alpha = 2.0 / (period + 1)
    out[0] = data[0]
    for i in range(1, n):
        out[i] = alpha * data[i] + (1.0 - alpha) * out[i - 1]
    return out


@njit(cache=True)
def _sma(data: np.ndarray, period: int) -> np.ndarray:
    n = len(data)
    out = np.full(n, np.nan, dtype=np.float64)
    cumsum = 0.0
    for i in range(n):
        cumsum += data[i]
        if i >= period:
            cumsum -= data[i - period]
        if i >= period - 1:
            out[i] = cumsum / period
    return out


@njit(cache=True)
def _wavetrend_core(
    hlc3: np.ndarray,
    channel_len: int,
    average_len: int,
    ma_len: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute wt1 and wt2.

    Returns (wt1, wt2).
    """
    esa = _ema(hlc3, channel_len)

    # de = EMA(|hlc3 - esa|, channel_len)
    abs_diff = np.empty(len(hlc3), dtype=np.float64)
    for i in range(len(hlc3)):
        abs_diff[i] = abs(hlc3[i] - esa[i])
    de = _ema(abs_diff, channel_len)

    # ci = (hlc3 - esa) / (0.015 * de)
    ci = np.empty(len(hlc3), dtype=np.float64)
    for i in range(len(hlc3)):
        denom = 0.015 * de[i]
        ci[i] = (hlc3[i] - esa[i]) / denom if denom != 0.0 else 0.0

    wt1 = _ema(ci, average_len)
    wt2 = _sma(wt1, ma_len)

    return wt1, wt2


def wavetrend(
    high: np.ndarray | pd.Series,
    low: np.ndarray | pd.Series,
    close: np.ndarray | pd.Series,
    channel_len: int = 9,
    average_len: int = 12,
    ma_len: int = 3,
) -> tuple[pd.Series, pd.Series]:
    """Compute WaveTrend oscillator (wt1, wt2).

    Parameters
    ----------
    high, low, close : array-like
    channel_len : int
        EMA period for ESA and DE (default 9).
    average_len : int
        EMA period for wt1 (default 12).
    ma_len : int
        SMA period for wt2 (default 3).
    """
    idx = close.index if isinstance(close, pd.Series) else None

    h = np.asarray(high, dtype=np.float64)
    lo = np.asarray(low, dtype=np.float64)
    c = np.asarray(close, dtype=np.float64)
    hlc3 = (h + lo + c) / 3.0

    wt1, wt2 = _wavetrend_core(hlc3, channel_len, average_len, ma_len)

    if idx is not None:
        return pd.Series(wt1, index=idx, name="wt1"), pd.Series(wt2, index=idx, name="wt2")
    return pd.Series(wt1, name="wt1"), pd.Series(wt2, name="wt2")


# ── Reversal signals ─────────────────────────────────────────────


def wavetrend_reversal(
    wt1: pd.Series,
    wt2: pd.Series,
    ob_level: float = 60.0,
    os_level: float = -60.0,
) -> tuple[pd.Series, pd.Series]:
    """Detect oversold/overbought cross reversals.

    - buy = wt1 crosses above wt2 AND wt2 <= os_level
    - sell = wt1 crosses below wt2 AND wt2 >= ob_level
    """
    cross_up = (wt1 > wt2) & (wt1.shift(1, fill_value=0) <= wt2.shift(1, fill_value=0))
    cross_down = (wt1 < wt2) & (wt1.shift(1, fill_value=0) >= wt2.shift(1, fill_value=0))

    oversold = wt2 <= os_level
    overbought = wt2 >= ob_level

    buy = cross_up & oversold
    sell = cross_down & overbought
    return buy.rename("wt_rev_buy"), sell.rename("wt_rev_sell")


# ── Divergence signals ───────────────────────────────────────────


@njit(cache=True)
def _pivot_high(data: np.ndarray, left: int, right: int) -> np.ndarray:
    """Detect pivot highs (returns value at pivot point, NaN otherwise)."""
    n = len(data)
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(left, n - right):
        val = data[i]
        is_pivot = True
        for j in range(i - left, i):
            if data[j] >= val:
                is_pivot = False
                break
        if is_pivot:
            for j in range(i + 1, i + right + 1):
                if data[j] >= val:
                    is_pivot = False
                    break
        if is_pivot:
            out[i] = val
    return out


@njit(cache=True)
def _pivot_low(data: np.ndarray, left: int, right: int) -> np.ndarray:
    """Detect pivot lows (returns value at pivot point, NaN otherwise)."""
    n = len(data)
    out = np.full(n, np.nan, dtype=np.float64)
    for i in range(left, n - right):
        val = data[i]
        is_pivot = True
        for j in range(i - left, i):
            if data[j] <= val:
                is_pivot = False
                break
        if is_pivot:
            for j in range(i + 1, i + right + 1):
                if data[j] <= val:
                    is_pivot = False
                    break
        if is_pivot:
            out[i] = val
    return out


@njit(cache=True)
def _find_divergences(
    wt2: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    ob_level: float,
    os_level: float,
    lookback_left: int,
    lookback_right: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Detect regular divergences between price and wt2.

    Returns (bear_div, bull_div) boolean arrays.

    Pine logic (simplified from f_findDivs):
    - fractalTop on wt2 at ob_level: if price HH but wt2 LH → bearish div
    - fractalBot on wt2 at os_level: if price LL but wt2 HL → bullish div
    """
    n = len(wt2)
    bear = np.zeros(n, dtype=np.bool_)
    bull = np.zeros(n, dtype=np.bool_)

    # Track last pivot values
    last_pivot_high_wt = np.nan
    last_pivot_high_price = np.nan
    last_pivot_low_wt = np.nan
    last_pivot_low_price = np.nan

    pivot_h = _pivot_high(wt2, lookback_left, lookback_right)
    pivot_l = _pivot_low(wt2, lookback_left, lookback_right)

    for i in range(n):
        # Check pivot high at offset lookback_right (Pine uses src[2] for lookback_right=1 → shifted by 2)
        if not np.isnan(pivot_h[i]) and wt2[i] >= ob_level:
            cur_wt = wt2[i]
            cur_price = high[i]
            if not np.isnan(last_pivot_high_wt):  # noqa: SIM102
                # Bear div: price higher high, WT lower high
                if cur_price > last_pivot_high_price and cur_wt < last_pivot_high_wt:
                    bear[i] = True
            last_pivot_high_wt = cur_wt
            last_pivot_high_price = cur_price

        if not np.isnan(pivot_l[i]) and wt2[i] <= os_level:
            cur_wt = wt2[i]
            cur_price = low[i]
            if not np.isnan(last_pivot_low_wt):  # noqa: SIM102
                # Bull div: price lower low, WT higher low
                if cur_price < last_pivot_low_price and cur_wt > last_pivot_low_wt:
                    bull[i] = True
            last_pivot_low_wt = cur_wt
            last_pivot_low_price = cur_price

    return bear, bull


def wavetrend_divergence(
    wt1: pd.Series,
    wt2: pd.Series,
    high: pd.Series,
    low: pd.Series,
    ob_level: float = 60.0,
    os_level: float = -60.0,
    lookback_left: int = 20,
    lookback_right: int = 1,
    divergence_length: int = 20,
) -> tuple[pd.Series, pd.Series]:
    """Detect WaveTrend divergences.

    Two detection methods (OR'd together like Pine):
    1. Pivot-based: fractal pivots on wt2 + price comparison
    2. Extreme-cross: wt1 crosses lowest/highest of wt1 over divergence_length

    Returns (bull_div, bear_div) boolean Series.
    """
    idx = wt1.index

    w1 = np.asarray(wt1, dtype=np.float64)
    w2 = np.asarray(wt2, dtype=np.float64)
    h = np.asarray(high, dtype=np.float64)
    lo = np.asarray(low, dtype=np.float64)

    # Method 1: Pivot-based divergence
    bear_pivot, bull_pivot = _find_divergences(w2, h, lo, ob_level, os_level, lookback_left, lookback_right)

    # Method 2: Extreme cross divergence
    # bullishWTDivergence = crossover(wt1, lowest(wt1, divergence_length))
    # bearishWTDivergence = crossunder(wt1, highest(wt1, divergence_length))
    n = len(w1)
    bull_extreme = np.zeros(n, dtype=np.bool_)
    bear_extreme = np.zeros(n, dtype=np.bool_)

    for i in range(divergence_length, n):
        lowest = w1[i - divergence_length : i].min()
        highest = w1[i - divergence_length : i].max()

        # Crossover wt1, lowest → wt1 was below, now above
        if i > 0 and w1[i] > lowest and w1[i - 1] <= lowest:
            bull_extreme[i] = True
        if i > 0 and w1[i] < highest and w1[i - 1] >= highest:
            bear_extreme[i] = True

    bull = np.asarray(bull_pivot) | bull_extreme
    bear = np.asarray(bear_pivot) | bear_extreme

    return (
        pd.Series(bull, index=idx, name="wt_div_bull"),
        pd.Series(bear, index=idx, name="wt_div_bear"),
    )


# ── Indicator ABC wrappers ───────────────────────────────────────


class WaveTrendReversal(Indicator):
    """WaveTrend Reversal — oversold/overbought cross signal."""

    def compute(
        self,
        df: pd.DataFrame,
        *,
        channel_len: int = 9,
        average_len: int = 12,
        ma_len: int = 3,
        ob_level: float = 60.0,
        os_level: float = -60.0,
        hold_bars: int = 3,
        direction: str = "long",
    ) -> pd.Series:
        self._validate_ohlcv(df)
        wt1, wt2 = wavetrend(df["high"], df["low"], df["close"], channel_len, average_len, ma_len)
        buy, sell = wavetrend_reversal(wt1, wt2, ob_level, os_level)
        raw = buy if direction == "long" else sell
        return self._hold_bars(raw, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "channel_len": {"type": "int", "min": 2, "max": 50, "default": 9},
            "average_len": {"type": "int", "min": 2, "max": 50, "default": 12},
            "ma_len": {"type": "int", "min": 2, "max": 10, "default": 3},
            "ob_level": {"type": "float", "min": 20.0, "max": 100.0, "default": 60.0},
            "os_level": {"type": "float", "min": -100.0, "max": -20.0, "default": -60.0},
            "hold_bars": {"type": "int", "min": 1, "max": 20, "default": 3},
        }


class WaveTrendDivergence(Indicator):
    """WaveTrend Divergence — pivot + extreme cross divergence detection."""

    def compute(
        self,
        df: pd.DataFrame,
        *,
        channel_len: int = 9,
        average_len: int = 12,
        ma_len: int = 3,
        ob_level: float = 60.0,
        os_level: float = -60.0,
        lookback_left: int = 20,
        lookback_right: int = 1,
        divergence_length: int = 20,
        hold_bars: int = 3,
        direction: str = "long",
    ) -> pd.Series:
        self._validate_ohlcv(df)
        wt1, wt2 = wavetrend(df["high"], df["low"], df["close"], channel_len, average_len, ma_len)
        bull, bear = wavetrend_divergence(
            wt1, wt2, df["high"], df["low"],
            ob_level, os_level, lookback_left, lookback_right, divergence_length,
        )
        raw = bull if direction == "long" else bear
        return self._hold_bars(raw, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "channel_len": {"type": "int", "min": 2, "max": 50, "default": 9},
            "average_len": {"type": "int", "min": 2, "max": 50, "default": 12},
            "ma_len": {"type": "int", "min": 2, "max": 10, "default": 3},
            "ob_level": {"type": "float", "min": 20.0, "max": 100.0, "default": 60.0},
            "os_level": {"type": "float", "min": -100.0, "max": -20.0, "default": -60.0},
            "lookback_left": {"type": "int", "min": 5, "max": 50, "default": 20},
            "lookback_right": {"type": "int", "min": 1, "max": 5, "default": 1},
            "divergence_length": {"type": "int", "min": 5, "max": 50, "default": 20},
            "hold_bars": {"type": "int", "min": 1, "max": 20, "default": 3},
        }
