"""Volatility regime filter — ATR percentile classification.

Classifies market volatility by ranking current ATR against its rolling
history.  Trend-following strategies should trade when volatility is
elevated (``mode="trending"``); mean-reversion when it's low
(``mode="ranging"``).

Production-ready: computed purely from OHLCV, available in real-time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from suitetrading.indicators.base import Indicator


class VolatilityRegime(Indicator):
    """ATR percentile filter — only emit signal in the right volatility regime.

    Uses Wilder's ATR smoothing and rolling percentile rank.  Acts as a
    filter (auxiliary indicator), not a standalone entry signal.
    """

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        atr_period = int(params.get("atr_period", 14))
        lookback = int(params.get("lookback", 100))
        threshold = float(params.get("threshold", 50.0))
        mode = str(params.get("mode", "trending"))
        hold_bars = int(params.get("hold_bars", 1))

        high = df["high"].values.astype(np.float64)
        low = df["low"].values.astype(np.float64)
        close = df["close"].values.astype(np.float64)
        n = len(close)

        # True Range
        tr = np.empty(n, dtype=np.float64)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )

        # ATR via Wilder smoothing
        atr = np.zeros(n, dtype=np.float64)
        if n >= atr_period:
            atr[atr_period - 1] = np.mean(tr[:atr_period])
            for i in range(atr_period, n):
                atr[i] = (atr[i - 1] * (atr_period - 1) + tr[i]) / atr_period

        # Rolling percentile rank of ATR within lookback window
        warmup = atr_period + lookback - 1
        pct = np.full(n, np.nan, dtype=np.float64)
        for i in range(warmup, n):
            window = atr[i - lookback + 1 : i + 1]
            pct[i] = np.searchsorted(np.sort(window), atr[i]) / lookback * 100

        if mode == "trending":
            raw = pct > threshold
        else:
            raw = pct < threshold

        raw = np.where(np.isnan(pct), False, raw)
        result = pd.Series(raw, index=df.index, name="vol_regime", dtype=bool)
        result.iloc[:warmup] = False
        return self._hold_bars(result, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "atr_period": {"type": "int", "min": 7, "max": 30, "default": 14},
            "lookback": {"type": "int", "min": 50, "max": 200, "default": 100},
            "threshold": {"type": "float", "min": 20.0, "max": 80.0, "step": 5.0, "default": 50.0},
            "mode": {"type": "str", "choices": ["trending", "ranging"], "default": "trending"},
            "hold_bars": {"type": "int", "min": 1, "max": 5, "default": 1},
        }
