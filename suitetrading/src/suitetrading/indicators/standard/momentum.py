"""Momentum-based indicators — ROC, Donchian Channel, ADX filter, MA Crossover.

These indicators capture trend-following edge in crypto markets.
Unlike oscillators (RSI, WaveTrend), they signal when momentum is
present rather than when it's exhausted.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from suitetrading.indicators.base import Indicator


class ROC(Indicator):
    """Rate of Change — momentum > 0 means uptrend."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        period = int(params.get("period", 5))
        mode = str(params.get("mode", "bullish"))
        hold_bars = int(params.get("hold_bars", 1))

        close = df["close"]
        roc = close / close.shift(period) - 1.0

        if mode == "bullish":
            raw = roc > 0
        else:
            raw = roc < 0

        raw_series = pd.Series(raw.values, index=df.index, name="roc_signal", dtype=bool)
        raw_series.iloc[:period] = False
        return self._hold_bars(raw_series, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "period": {"type": "int", "min": 2, "max": 50, "default": 5},
            "mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 1},
        }


class DonchianBreakout(Indicator):
    """Donchian Channel breakout — signal when price hits N-bar high/low."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        period = int(params.get("period", 20))
        mode = str(params.get("mode", "upper"))
        hold_bars = int(params.get("hold_bars", 1))

        close = df["close"]
        high = df["high"]
        low = df["low"]

        if mode == "upper":
            channel = high.rolling(period).max()
            raw = close >= channel
        else:
            channel = low.rolling(period).min()
            raw = close <= channel

        raw_series = pd.Series(raw.values, index=df.index, name="donchian_signal", dtype=bool)
        raw_series.iloc[:period] = False
        return self._hold_bars(raw_series, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "period": {"type": "int", "min": 5, "max": 100, "default": 20},
            "mode": {"type": "str", "choices": ["upper", "lower"], "default": "upper"},
            "hold_bars": {"type": "int", "min": 1, "max": 20, "default": 1},
        }


class ADXFilter(Indicator):
    """ADX trend strength filter — signal when trend is strong enough."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 20.0))
        mode = str(params.get("mode", "strong"))
        hold_bars = int(params.get("hold_bars", 1))

        high = df["high"].values.astype(np.float64)
        low = df["low"].values.astype(np.float64)
        close = df["close"].values.astype(np.float64)
        n = len(close)

        # True Range
        tr = np.empty(n)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))

        # +DM / -DM
        plus_dm = np.zeros(n)
        minus_dm = np.zeros(n)
        for i in range(1, n):
            up_move = high[i] - high[i - 1]
            down_move = low[i - 1] - low[i]
            if up_move > down_move and up_move > 0:
                plus_dm[i] = up_move
            if down_move > up_move and down_move > 0:
                minus_dm[i] = down_move

        # Wilder smoothing
        atr = np.zeros(n)
        plus_di_smooth = np.zeros(n)
        minus_di_smooth = np.zeros(n)

        if n >= period:
            atr[period - 1] = np.mean(tr[:period])
            plus_di_smooth[period - 1] = np.mean(plus_dm[:period])
            minus_di_smooth[period - 1] = np.mean(minus_dm[:period])

            for i in range(period, n):
                atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
                plus_di_smooth[i] = (plus_di_smooth[i - 1] * (period - 1) + plus_dm[i]) / period
                minus_di_smooth[i] = (minus_di_smooth[i - 1] * (period - 1) + minus_dm[i]) / period

        # DI+ / DI- / DX / ADX
        plus_di = np.where(atr > 0, 100.0 * plus_di_smooth / atr, 0.0)
        minus_di = np.where(atr > 0, 100.0 * minus_di_smooth / atr, 0.0)
        di_sum = plus_di + minus_di
        dx = np.where(di_sum > 0, 100.0 * np.abs(plus_di - minus_di) / di_sum, 0.0)

        adx = np.zeros(n)
        start = 2 * period - 1
        if n > start:
            adx[start] = np.mean(dx[period:start + 1])
            for i in range(start + 1, n):
                adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

        if mode == "strong":
            raw = adx > threshold
        else:
            raw = adx <= threshold

        raw_series = pd.Series(raw, index=df.index, name="adx_signal", dtype=bool)
        raw_series.iloc[: 2 * period] = False
        return self._hold_bars(raw_series, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "period": {"type": "int", "min": 5, "max": 50, "default": 14},
            "threshold": {"type": "float", "min": 10.0, "max": 50.0, "default": 20.0},
            "mode": {"type": "str", "choices": ["strong", "weak"], "default": "strong"},
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 1},
        }


class MACrossover(Indicator):
    """Moving Average Crossover — signal when fast MA > slow MA."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        fast = int(params.get("fast_period", 50))
        slow = int(params.get("slow_period", 200))
        mode = str(params.get("mode", "bullish"))
        hold_bars = int(params.get("hold_bars", 1))

        close = df["close"]
        fast_ma = close.ewm(span=fast, adjust=False).mean()
        slow_ma = close.ewm(span=slow, adjust=False).mean()

        if mode == "bullish":
            raw = fast_ma > slow_ma
        else:
            raw = fast_ma < slow_ma

        warmup = max(fast, slow)
        raw_series = pd.Series(raw.values, index=df.index, name="ma_cross_signal", dtype=bool)
        raw_series.iloc[:warmup] = False
        return self._hold_bars(raw_series, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "fast_period": {"type": "int", "min": 5, "max": 100, "default": 50},
            "slow_period": {"type": "int", "min": 20, "max": 500, "default": 200},
            "mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 1},
        }
