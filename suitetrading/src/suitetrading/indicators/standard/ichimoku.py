"""Ichimoku TK Cross indicator.

Signals Tenkan-Kijun crossovers confirmed by price position relative
to the Kumo (cloud) formed by Senkou Span A and Senkou Span B.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from suitetrading.indicators.base import Indicator


class IchimokuTKCross(Indicator):
    """Ichimoku TK Cross — Tenkan/Kijun crossover with cloud confirmation."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        tenkan_period = int(params.get("tenkan_period", 9))
        kijun_period = int(params.get("kijun_period", 26))
        senkou_period = int(params.get("senkou_period", 52))
        mode = str(params.get("mode", "bullish"))
        hold_bars = int(params.get("hold_bars", 1))

        high = df["high"]
        low = df["low"]
        close = df["close"]

        # Tenkan-sen (conversion line)
        tenkan = (high.rolling(tenkan_period).max() + low.rolling(tenkan_period).min()) / 2.0

        # Kijun-sen (base line)
        kijun = (high.rolling(kijun_period).max() + low.rolling(kijun_period).min()) / 2.0

        # Senkou Span A (leading span A) — not displaced, used for current cloud
        senkou_a = (tenkan + kijun) / 2.0

        # Senkou Span B (leading span B) — not displaced, used for current cloud
        senkou_b = (high.rolling(senkou_period).max() + low.rolling(senkou_period).min()) / 2.0

        cloud_top = pd.concat([senkou_a, senkou_b], axis=1).max(axis=1)
        cloud_bottom = pd.concat([senkou_a, senkou_b], axis=1).min(axis=1)

        # Crossover detection
        tenkan_prev = tenkan.shift(1)
        kijun_prev = kijun.shift(1)

        if mode == "bullish":
            cross = (tenkan_prev <= kijun_prev) & (tenkan > kijun)
            above_cloud = close > cloud_top
            raw = cross & above_cloud
        else:
            cross = (tenkan_prev >= kijun_prev) & (tenkan < kijun)
            below_cloud = close < cloud_bottom
            raw = cross & below_cloud

        warmup = senkou_period
        raw_series = pd.Series(raw.values, index=df.index, name="ichimoku_tk_signal", dtype=bool)
        raw_series.iloc[:warmup] = False
        return self._hold_bars(raw_series, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            # Narrow ranges around classic Ichimoku periods (9/26/52)
            "tenkan_period": {"type": "int", "min": 7, "max": 13, "default": 9},
            "kijun_period": {"type": "int", "min": 20, "max": 35, "default": 26},
            "senkou_period": {"type": "int", "min": 40, "max": 65, "default": 52},
            "mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
            "hold_bars": {"type": "int", "min": 1, "max": 5, "default": 1},
        }
