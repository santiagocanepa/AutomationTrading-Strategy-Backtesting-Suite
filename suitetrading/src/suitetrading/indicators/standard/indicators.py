"""Standard indicators: thin wrappers around TA-Lib / pandas-ta.

Each class subclasses ``Indicator`` and delegates the heavy math to
TA-Lib for speed.  The ``compute`` method always returns a boolean
pd.Series (True = signal active).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import talib

from suitetrading.indicators.base import Indicator


class RSI(Indicator):
    """RSI oversold/overbought signal."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        period = int(params.get("period", 14))
        threshold = float(params.get("threshold", 30.0))
        mode = str(params.get("mode", "oversold"))
        hold_bars = int(params.get("hold_bars", 3))

        rsi = talib.RSI(df["close"].values, timeperiod=period)
        prev_rsi = np.roll(rsi, 1)
        prev_rsi[0] = 50.0  # neutral seed
        if mode == "oversold":
            raw = (rsi < threshold) & (prev_rsi >= threshold)
        else:
            raw = (rsi > threshold) & (prev_rsi <= threshold)
        raw_series = pd.Series(raw, index=df.index, name="rsi_signal", dtype=bool)
        return self._hold_bars(raw_series, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "period": {"type": "int", "min": 2, "max": 100, "default": 14},
            "threshold": {"type": "float", "min": 5.0, "max": 95.0, "default": 30.0},
            "mode": {"type": "str", "choices": ["oversold", "overbought"], "default": "oversold"},
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 3},
        }


class EMA(Indicator):
    """EMA crossover: price crossing above/below the EMA."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        period = int(params.get("period", 21))
        mode = str(params.get("mode", "above"))
        hold_bars = int(params.get("hold_bars", 3))

        ema = talib.EMA(df["close"].values, timeperiod=period)
        close = df["close"].values
        if mode == "above":
            raw = (close > ema) & (np.roll(close, 1) <= np.roll(ema, 1))
        else:
            raw = (close < ema) & (np.roll(close, 1) >= np.roll(ema, 1))
        raw[0] = False
        raw_series = pd.Series(raw, index=df.index, name="ema_signal", dtype=bool)
        return self._hold_bars(raw_series, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            # Narrowed: period [2-200], hold_bars [1-5] (r=-0.076)
            "period": {"type": "int", "min": 2, "max": 200, "default": 21},
            "mode": {"type": "str", "choices": ["above", "below"], "default": "above"},
            "hold_bars": {"type": "int", "min": 1, "max": 5, "default": 3},
        }


class MACD(Indicator):
    """MACD histogram cross zero."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        fast = int(params.get("fast", 12))
        slow = int(params.get("slow", 26))
        signal_period = int(params.get("signal", 9))
        mode = str(params.get("mode", "bullish"))
        hold_bars = int(params.get("hold_bars", 3))

        _macd, _signal, hist = talib.MACD(
            df["close"].values,
            fastperiod=fast,
            slowperiod=slow,
            signalperiod=signal_period,
        )
        prev_hist = np.roll(hist, 1)
        prev_hist[0] = 0.0
        if mode == "bullish":
            raw = (hist > 0) & (prev_hist <= 0)
        else:
            raw = (hist < 0) & (prev_hist >= 0)
        raw_series = pd.Series(raw, index=df.index, name="macd_signal", dtype=bool)
        return self._hold_bars(raw_series, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            # Narrowed: fast [2-40] (top1% median=15), slow [5-80], hold [1-8]
            "fast": {"type": "int", "min": 2, "max": 40, "default": 12},
            "slow": {"type": "int", "min": 5, "max": 80, "default": 26},
            "signal": {"type": "int", "min": 2, "max": 30, "default": 9},
            "mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
            "hold_bars": {"type": "int", "min": 1, "max": 8, "default": 3},
        }


class ATR(Indicator):
    """ATR breakout: true when ATR exceeds its own moving average."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        period = int(params.get("period", 14))
        ma_period = int(params.get("ma_period", 50))
        multiplier = float(params.get("multiplier", 1.5))

        atr = talib.ATR(df["high"].values, df["low"].values, df["close"].values, timeperiod=period)
        atr_ma = talib.SMA(atr, timeperiod=ma_period)
        signal = atr > (atr_ma * multiplier)
        signal = np.where(np.isnan(signal), False, signal)
        return pd.Series(signal, index=df.index, name="atr_signal", dtype=bool)

    def params_schema(self) -> dict[str, dict]:
        return {
            "period": {"type": "int", "min": 2, "max": 100, "default": 14},
            "ma_period": {"type": "int", "min": 5, "max": 200, "default": 50},
            "multiplier": {"type": "float", "min": 0.5, "max": 5.0, "default": 1.5},
        }


class VWAP(Indicator):
    """VWAP deviation: signal when price crosses above/below VWAP."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        mode = str(params.get("mode", "above"))
        hold_bars = int(params.get("hold_bars", 3))

        typical = (df["high"] + df["low"] + df["close"]) / 3.0
        cum_tp_vol = (typical * df["volume"]).cumsum()
        cum_vol = df["volume"].cumsum()
        vwap = cum_tp_vol / cum_vol.replace(0, np.nan)
        vwap = vwap.ffill()

        close = df["close"]
        prev_close = close.shift(1)
        prev_vwap = vwap.shift(1)
        if mode == "above":
            raw = (close > vwap) & (prev_close <= prev_vwap)
        else:
            raw = (close < vwap) & (prev_close >= prev_vwap)
        raw = raw.fillna(False)
        raw_series = pd.Series(raw, index=df.index, name="vwap_signal", dtype=bool)
        return self._hold_bars(raw_series, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "mode": {"type": "str", "choices": ["above", "below"], "default": "above"},
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 3},
        }


class BollingerBands(Indicator):
    """Bollinger Band touch: signal when price touches lower/upper band."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        period = int(params.get("period", 20))
        nbdev = float(params.get("nbdev", 2.0))
        mode = str(params.get("mode", "lower"))
        hold_bars = int(params.get("hold_bars", 3))

        upper, middle, lower = talib.BBANDS(
            df["close"].values,
            timeperiod=period,
            nbdevup=nbdev,
            nbdevdn=nbdev,
        )
        close = df["close"].values
        prev_close = np.roll(close, 1)
        prev_lower = np.roll(lower, 1)
        prev_upper = np.roll(upper, 1)
        if mode == "lower":
            raw = (close <= lower) & (prev_close > prev_lower)
        else:
            raw = (close >= upper) & (prev_close < prev_upper)
        raw[0] = False
        raw = np.where(np.isnan(raw), False, raw)
        raw_series = pd.Series(raw, index=df.index, name="bbands_signal", dtype=bool)
        return self._hold_bars(raw_series, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            # Narrowed: nbdev [0.5-2.5] (top1% median=0.71, r=-0.144), hold [1-5]
            "period": {"type": "int", "min": 5, "max": 50, "default": 20},
            "nbdev": {"type": "float", "min": 0.5, "max": 2.5, "default": 1.0},
            "mode": {"type": "str", "choices": ["lower", "upper"], "default": "lower"},
            "hold_bars": {"type": "int", "min": 1, "max": 5, "default": 3},
        }
