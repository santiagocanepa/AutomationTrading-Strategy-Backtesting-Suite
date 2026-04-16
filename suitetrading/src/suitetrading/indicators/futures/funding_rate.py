"""Funding rate indicators for crypto perpetual futures.

Funding rate extremes are well-documented mean reversion signals:
when funding is very positive, longs pay shorts at each settlement
(every 8h on Binance).  Eventually longs unwind, causing price drops.

    Extreme positive funding → contrarian short signal
    Extreme negative funding → contrarian long signal

Data source: Binance ``GET /fapi/v1/fundingRate`` (8h frequency).
In production, poll once per funding settlement.

Requires ``funding_rate`` column in the OHLCV DataFrame.
Falls back to no-signal if column is absent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from suitetrading.indicators.base import Indicator


class FundingRate(Indicator):
    """Signal on extreme funding rate levels (z-score based).

    Uses rolling z-score of funding rate to detect extremes.
    The z-score approach adapts to different market regimes where
    the "normal" funding rate level shifts.
    """

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        lookback = int(params.get("lookback", 30))
        extreme_z = float(params.get("extreme_z", 2.0))
        mode = str(params.get("mode", "reversal_long"))
        hold_bars = int(params.get("hold_bars", 3))

        if "funding_rate" not in df.columns:
            return pd.Series(False, index=df.index, name="funding", dtype=bool)

        funding = df["funding_rate"].ffill().values.astype(np.float64)
        n = len(funding)

        raw = np.full(n, False, dtype=bool)
        for i in range(lookback, n):
            window = funding[i - lookback : i]
            mean = np.mean(window)
            std = np.std(window, ddof=1)
            if std < 1e-12:
                continue
            z = (funding[i] - mean) / std

            if mode == "reversal_long":
                raw[i] = z < -extreme_z
            else:
                raw[i] = z > extreme_z

        result = pd.Series(raw, index=df.index, name="funding", dtype=bool)
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
