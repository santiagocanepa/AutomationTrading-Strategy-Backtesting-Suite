"""Yield Curve Spread indicator (10Y−2Y treasury spread).

Inverted yield curve (spread < 0) historically precedes recessions
by 6−18 months.  Steepening after inversion signals recovery.

Requires ``yield_spread`` column in the OHLCV DataFrame, added
externally via ``MacroCacheManager.get_aligned()``.  Falls back
to no-signal if column is absent.

References:
    Estrella & Mishkin (1998): "Predicting U.S. Recessions", REStat.
    FRED series T10Y2Y.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from suitetrading.indicators.base import Indicator


class YieldCurveIndicator(Indicator):
    """Signal based on yield curve spread regime."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        threshold = float(params.get("threshold", 0.0))
        mode = str(params.get("mode", "normal"))
        lookback = int(params.get("lookback", 20))
        hold_bars = int(params.get("hold_bars", 1))

        if "yield_spread" not in df.columns:
            logger.debug("YieldCurve: 'yield_spread' column absent — returning all-False")
            return pd.Series(False, index=df.index, name="yield_curve", dtype=bool)

        spread = df["yield_spread"].ffill().values.astype(np.float64)
        n = len(spread)

        if mode == "normal":
            # True when spread > threshold (healthy economy)
            raw = spread > threshold
        elif mode == "inverted":
            # True when spread < -|threshold| (recession signal, contrarian)
            raw = spread < -abs(threshold)
        elif mode == "steepening":
            # True when spread is rising (above its own SMA)
            sma = np.full(n, np.nan)
            for i in range(lookback, n):
                sma[i] = np.mean(spread[i - lookback + 1 : i + 1])
            raw = spread > sma
        else:
            raw = np.full(n, False)

        raw = np.where(np.isnan(spread), False, raw)
        result = pd.Series(raw, index=df.index, name="yield_curve", dtype=bool)
        if mode == "steepening":
            result.iloc[:lookback] = False
        return self._hold_bars(result, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "threshold": {"type": "float", "min": -0.5, "max": 1.0, "step": 0.1, "default": 0.0},
            "mode": {
                "type": "str",
                "choices": ["normal", "inverted", "steepening"],
                "default": "normal",
            },
            "lookback": {"type": "int", "min": 5, "max": 60, "default": 20},
            "hold_bars": {"type": "int", "min": 1, "max": 20, "default": 1},
        }
