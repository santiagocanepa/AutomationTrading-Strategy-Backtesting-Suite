"""On-Balance Volume (OBV) trend indicator.

Computes classic OBV and signals when it crosses above or below its
EMA, indicating volume-confirmed trend direction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from suitetrading.indicators.base import Indicator


class OBVTrend(Indicator):
    """OBV Trend — signal when OBV crosses its EMA."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        ma_period = int(params.get("ma_period", 20))
        mode = str(params.get("mode", "bullish"))
        hold_bars = int(params.get("hold_bars", 1))

        close = df["close"].values.astype(np.float64)
        volume = df["volume"].values.astype(np.float64)
        n = len(close)

        # Classic OBV
        obv = np.zeros(n)
        for i in range(1, n):
            if close[i] > close[i - 1]:
                obv[i] = obv[i - 1] + volume[i]
            elif close[i] < close[i - 1]:
                obv[i] = obv[i - 1] - volume[i]
            else:
                obv[i] = obv[i - 1]

        obv_series = pd.Series(obv, index=df.index)
        obv_ema = obv_series.ewm(span=ma_period, adjust=False).mean()

        if mode == "bullish":
            raw = obv_series > obv_ema
        else:
            raw = obv_series < obv_ema

        warmup = ma_period
        raw_series = pd.Series(raw.values, index=df.index, name="obv_signal", dtype=bool)
        raw_series.iloc[:warmup] = False
        return self._hold_bars(raw_series, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "ma_period": {"type": "int", "min": 5, "max": 50, "default": 20},
            "mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 1},
        }
