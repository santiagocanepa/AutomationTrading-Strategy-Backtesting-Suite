"""Momentum divergence detection — price vs ROC oscillator.

Classical divergence: when price makes a new extreme but the oscillator
does not confirm, it signals exhaustion and a potential reversal.

    Bullish divergence: price lower low + ROC higher low → reversal up
    Bearish divergence: price higher high + ROC lower high → reversal down

Production-ready: computed purely from OHLCV, available in real-time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from suitetrading.indicators.base import Indicator


class MomentumDivergence(Indicator):
    """Detect divergence between price and ROC oscillator.

    Compares rolling extremes from the current lookback window vs the
    previous lookback window.  When price trends but momentum fades,
    a divergence signal fires.
    """

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        roc_period = int(params.get("roc_period", 14))
        lookback = int(params.get("lookback", 20))
        mode = str(params.get("mode", "bullish"))
        hold_bars = int(params.get("hold_bars", 3))

        close = df["close"].values.astype(np.float64)
        n = len(close)

        # ROC oscillator
        roc = np.zeros(n, dtype=np.float64)
        for i in range(roc_period, n):
            prev = close[i - roc_period]
            roc[i] = (close[i] / prev - 1.0) if prev > 1e-12 else 0.0

        # Compare current window vs previous window extremes
        warmup = roc_period + lookback * 2
        raw = np.full(n, False, dtype=bool)

        for i in range(warmup, n):
            curr_end = i + 1
            curr_start = i - lookback + 1
            prev_end = curr_start
            prev_start = prev_end - lookback

            if mode == "bullish":
                price_curr = np.min(close[curr_start:curr_end])
                price_prev = np.min(close[prev_start:prev_end])
                roc_curr = np.min(roc[curr_start:curr_end])
                roc_prev = np.min(roc[prev_start:prev_end])
                raw[i] = (price_curr < price_prev) and (roc_curr > roc_prev)
            else:
                price_curr = np.max(close[curr_start:curr_end])
                price_prev = np.max(close[prev_start:prev_end])
                roc_curr = np.max(roc[curr_start:curr_end])
                roc_prev = np.max(roc[prev_start:prev_end])
                raw[i] = (price_curr > price_prev) and (roc_curr < roc_prev)

        result = pd.Series(raw, index=df.index, name="divergence", dtype=bool)
        return self._hold_bars(result, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "roc_period": {"type": "int", "min": 5, "max": 30, "default": 14},
            "lookback": {"type": "int", "min": 10, "max": 50, "default": 20},
            "mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 3},
        }
