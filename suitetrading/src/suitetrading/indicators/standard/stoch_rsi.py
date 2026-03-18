"""Stochastic RSI indicator.

Applies the stochastic oscillator formula to RSI values, producing
K and D lines for oversold/overbought crossover signals.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from suitetrading.indicators.base import Indicator


class StochRSI(Indicator):
    """Stochastic RSI — K/D crossover at oversold or overbought levels."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        rsi_period = int(params.get("rsi_period", 14))
        stoch_period = int(params.get("stoch_period", 14))
        k_smooth = int(params.get("k_smooth", 3))
        d_smooth = int(params.get("d_smooth", 3))
        oversold = float(params.get("oversold", 20.0))
        overbought = float(params.get("overbought", 80.0))
        mode = str(params.get("mode", "oversold"))
        hold_bars = int(params.get("hold_bars", 1))

        close = df["close"].values.astype(np.float64)
        n = len(close)

        # RSI with Wilder smoothing
        delta = np.zeros(n)
        delta[1:] = close[1:] - close[:-1]

        gains = np.where(delta > 0, delta, 0.0)
        losses = np.where(delta < 0, -delta, 0.0)

        avg_gain = np.zeros(n)
        avg_loss = np.zeros(n)

        if n >= rsi_period + 1:
            avg_gain[rsi_period] = np.mean(gains[1 : rsi_period + 1])
            avg_loss[rsi_period] = np.mean(losses[1 : rsi_period + 1])

            for i in range(rsi_period + 1, n):
                avg_gain[i] = (avg_gain[i - 1] * (rsi_period - 1) + gains[i]) / rsi_period
                avg_loss[i] = (avg_loss[i - 1] * (rsi_period - 1) + losses[i]) / rsi_period

        rs = np.where(avg_loss > 0, avg_gain / avg_loss, 0.0)
        rsi = np.where(avg_loss > 0, 100.0 - 100.0 / (1.0 + rs), 100.0)
        rsi[:rsi_period] = np.nan

        rsi_series = pd.Series(rsi, index=df.index)

        # Stochastic of RSI
        rsi_min = rsi_series.rolling(stoch_period).min()
        rsi_max = rsi_series.rolling(stoch_period).max()
        rsi_range = rsi_max - rsi_min
        stoch_raw = np.where(rsi_range > 0, (rsi_series - rsi_min) / rsi_range * 100.0, 50.0)
        stoch_raw_series = pd.Series(stoch_raw, index=df.index)

        # K and D lines
        k_line = stoch_raw_series.rolling(k_smooth).mean()
        d_line = k_line.rolling(d_smooth).mean()

        # Crossover signals
        k_prev = k_line.shift(1)
        d_prev = d_line.shift(1)

        if mode == "oversold":
            # K crosses above D while K is below oversold
            raw = (k_prev <= d_prev) & (k_line > d_line) & (k_line < oversold)
        else:
            # K crosses below D while K is above overbought
            raw = (k_prev >= d_prev) & (k_line < d_line) & (k_line > overbought)

        warmup = rsi_period + stoch_period + max(k_smooth, d_smooth)
        raw_series = pd.Series(raw.values, index=df.index, name="stoch_rsi_signal", dtype=bool)
        raw_series.iloc[:warmup] = False
        return self._hold_bars(raw_series, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        # Reduced search space: fix smoothing to avoid overfitting
        # (8 → 4 optimizable params: period, oversold/overbought, mode, hold_bars)
        return {
            "rsi_period": {"type": "int", "min": 7, "max": 21, "default": 14},
            "stoch_period": {"type": "int", "min": 7, "max": 21, "default": 14},
            "oversold": {"type": "float", "min": 10.0, "max": 30.0, "default": 20.0, "step": 5.0},
            "overbought": {"type": "float", "min": 70.0, "max": 90.0, "default": 80.0, "step": 5.0},
            "mode": {"type": "str", "choices": ["oversold", "overbought"], "default": "oversold"},
            "hold_bars": {"type": "int", "min": 1, "max": 5, "default": 1},
        }
