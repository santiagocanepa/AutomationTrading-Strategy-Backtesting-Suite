"""Spot-futures basis (premium/discount) indicator for crypto.

High positive basis = futures trading at premium = overleveraged longs.
Negative basis = backwardation = potential short squeeze.

Uses z-score of basis to detect extremes (same pattern as FundingRate).

Requires ``basis`` column ((futures - spot) / spot * 100) in DataFrame.
Data source: Binance ``GET /fapi/v1/basis``.
Falls back to no-signal if column is absent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from suitetrading.indicators.base import Indicator


class BasisIndicator(Indicator):
    """Contrarian signal on extreme spot-futures basis."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        lookback = int(params.get("lookback", 30))
        extreme_z = float(params.get("extreme_z", 2.0))
        mode = str(params.get("mode", "reversal_long"))
        hold_bars = int(params.get("hold_bars", 3))

        if "basis" not in df.columns:
            logger.debug("Basis: 'basis' column absent — returning all-False")
            return pd.Series(False, index=df.index, name="basis", dtype=bool)

        basis = df["basis"].ffill().values.astype(np.float64)
        n = len(basis)

        raw = np.full(n, False, dtype=bool)
        for i in range(lookback, n):
            window = basis[i - lookback : i]
            mean = np.mean(window)
            std = np.std(window, ddof=1)
            if std < 1e-12:
                continue
            z = (basis[i] - mean) / std

            if mode == "reversal_long":
                raw[i] = z < -extreme_z
            else:  # reversal_short
                raw[i] = z > extreme_z

        result = pd.Series(raw, index=df.index, name="basis", dtype=bool)
        result.iloc[:lookback] = False
        return self._hold_bars(result, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "lookback": {"type": "int", "min": 10, "max": 100, "default": 30},
            "extreme_z": {"type": "float", "min": 1.0, "max": 4.0, "step": 0.5, "default": 2.0},
            "mode": {
                "type": "str",
                "choices": ["reversal_long", "reversal_short"],
                "default": "reversal_long",
            },
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 3},
        }
