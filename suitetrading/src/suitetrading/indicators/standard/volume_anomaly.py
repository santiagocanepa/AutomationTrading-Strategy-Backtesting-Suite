"""Volume anomaly detection — spikes and directional conviction.

High volume with directional price movement indicates institutional
conviction.  Volume spikes also serve as a proxy for liquidation cascades
in crypto markets (large forced exits create volume bursts).

Production-ready: computed purely from OHLCV, available in real-time.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from suitetrading.indicators.base import Indicator


class VolumeSpike(Indicator):
    """Signal when volume exceeds a multiple of its rolling average.

    Combines volume magnitude (spike) with price direction to confirm
    that the volume is actionable.  Useful as entry confirmation or
    standalone signal for momentum strategies.
    """

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        lookback = int(params.get("lookback", 20))
        threshold = float(params.get("threshold", 2.0))
        mode = str(params.get("mode", "bullish"))
        hold_bars = int(params.get("hold_bars", 1))

        volume = df["volume"].values.astype(np.float64)
        close = df["close"].values.astype(np.float64)
        open_ = df["open"].values.astype(np.float64)

        # Rolling volume SMA
        vol_sma = np.full(len(volume), np.nan, dtype=np.float64)
        cumvol = np.cumsum(volume)
        for i in range(lookback - 1, len(volume)):
            start_sum = cumvol[i - lookback] if i >= lookback else 0.0
            vol_sma[i] = (cumvol[i] - start_sum) / lookback

        # Spike: volume > threshold × SMA
        spike = volume > threshold * vol_sma

        # Directional filter
        if mode == "bullish":
            direction = close > open_
        else:
            direction = close < open_

        raw = spike & direction
        raw = np.where(np.isnan(vol_sma), False, raw)
        result = pd.Series(raw, index=df.index, name="vol_spike", dtype=bool)
        result.iloc[:lookback] = False
        return self._hold_bars(result, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "lookback": {"type": "int", "min": 10, "max": 50, "default": 20},
            "threshold": {"type": "float", "min": 1.5, "max": 5.0, "step": 0.5, "default": 2.0},
            "mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
            "hold_bars": {"type": "int", "min": 1, "max": 5, "default": 1},
        }
