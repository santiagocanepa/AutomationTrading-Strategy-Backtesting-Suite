"""Taker buy/sell volume ratio indicator for crypto futures.

Taker buy ratio > 0.5 means aggressive buyers dominate (bullish).
Taker buy ratio < 0.5 means aggressive sellers dominate (bearish).

Requires ``taker_buy_ratio`` column (buy_vol / total_vol) in DataFrame.
Data source: Binance ``GET /fapi/v1/takeLongShortRatio``.
Falls back to no-signal if column is absent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from suitetrading.indicators.base import Indicator


class TakerVolumeIndicator(Indicator):
    """Signal on taker buy/sell volume pressure."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        lookback = int(params.get("lookback", 20))
        threshold = float(params.get("threshold", 0.55))
        mode = str(params.get("mode", "buy_pressure"))
        hold_bars = int(params.get("hold_bars", 1))

        if "taker_buy_ratio" not in df.columns:
            logger.debug("TakerVolume: 'taker_buy_ratio' column absent — returning all-False")
            return pd.Series(False, index=df.index, name="taker_volume", dtype=bool)

        ratio = df["taker_buy_ratio"].ffill().values.astype(np.float64)
        n = len(ratio)

        # Smooth with rolling mean to reduce noise
        smoothed = np.full(n, np.nan)
        for i in range(lookback, n):
            smoothed[i] = np.mean(ratio[i - lookback + 1 : i + 1])

        if mode == "buy_pressure":
            raw = smoothed > threshold
        else:  # sell_pressure
            raw = smoothed < (1.0 - threshold)

        raw = np.where(np.isnan(smoothed), False, raw)
        result = pd.Series(raw, index=df.index, name="taker_volume", dtype=bool)
        result.iloc[:lookback] = False
        return self._hold_bars(result, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "lookback": {"type": "int", "min": 5, "max": 50, "default": 20},
            "threshold": {"type": "float", "min": 0.51, "max": 0.70, "step": 0.01, "default": 0.55},
            "mode": {
                "type": "str",
                "choices": ["buy_pressure", "sell_pressure"],
                "default": "buy_pressure",
            },
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 1},
        }
