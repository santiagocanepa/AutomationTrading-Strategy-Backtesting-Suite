"""Squeeze Momentum (TTM Squeeze) indicator.

Detects consolidation (Bollinger Bands inside Keltner Channels) and signals
when the squeeze releases with momentum in the desired direction.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from suitetrading.indicators.base import Indicator


class SqueezeMomentum(Indicator):
    """TTM Squeeze — signal on squeeze release with momentum direction."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        bb_period = int(params.get("bb_period", 20))
        bb_mult = float(params.get("bb_mult", 2.0))
        kc_period = int(params.get("kc_period", 20))
        kc_mult = float(params.get("kc_mult", 1.5))
        mode = str(params.get("mode", "bullish"))
        hold_bars = int(params.get("hold_bars", 1))

        close = df["close"]
        high = df["high"]
        low = df["low"]

        # Bollinger Bands
        bb_mid = close.rolling(bb_period).mean()
        bb_std = close.rolling(bb_period).std(ddof=0)
        bb_upper = bb_mid + bb_mult * bb_std
        bb_lower = bb_mid - bb_mult * bb_std

        # Keltner Channels
        kc_mid = close.ewm(span=kc_period, adjust=False).mean()
        true_range = high - low
        kc_range = true_range.ewm(span=kc_period, adjust=False).mean() * kc_mult
        kc_upper = kc_mid + kc_range
        kc_lower = kc_mid - kc_range

        # Squeeze detection
        squeeze_on = (bb_lower > kc_lower) & (bb_upper < kc_upper)
        squeeze_off = ~squeeze_on
        release = squeeze_off & squeeze_on.shift(1)

        # Momentum: close - midline of (highest_high + lowest_low)/2, smoothed
        mom_period = max(bb_period, kc_period)
        highest_high = high.rolling(mom_period).max()
        lowest_low = low.rolling(mom_period).min()
        midline = (highest_high + lowest_low) / 2.0
        momentum = close - midline
        momentum = momentum.ewm(span=mom_period, adjust=False).mean()

        # Signal
        if mode == "bullish":
            raw = release & (momentum > 0)
        else:
            raw = release & (momentum < 0)

        warmup = max(bb_period, kc_period)
        raw_series = pd.Series(raw.values, index=df.index, name="squeeze_signal", dtype=bool)
        raw_series.iloc[:warmup] = False
        return self._hold_bars(raw_series, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            # Reduced: tie BB and KC periods together, narrow multiplier ranges
            "bb_period": {"type": "int", "min": 14, "max": 26, "default": 20},
            "bb_mult": {"type": "float", "min": 1.5, "max": 2.5, "default": 2.0, "step": 0.5},
            "kc_period": {"type": "int", "min": 14, "max": 26, "default": 20},
            "kc_mult": {"type": "float", "min": 1.0, "max": 2.0, "default": 1.5, "step": 0.5},
            "mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
            "hold_bars": {"type": "int", "min": 1, "max": 5, "default": 1},
        }
