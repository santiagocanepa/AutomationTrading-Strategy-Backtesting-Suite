"""Credit spread indicator (HYG/LQD ratio or FRED OAS spread).

HYG/LQD ratio rising = risk-on (high yield outperforming investment grade).
Ratio falling = risk-off (flight to quality).

Alternative: FRED BAMLH0A0HYM2 (OAS spread) where high spread = stress.

Requires ``credit_spread`` (HYG/LQD ratio) or ``hy_spread`` (FRED OAS)
column in the DataFrame.  Falls back to no-signal if absent.

References:
    Gilchrist & Zakrajšek (2012): "Credit Spreads and Business Cycle
    Fluctuations", AER.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from suitetrading.indicators.base import Indicator


class CreditSpreadIndicator(Indicator):
    """Signal based on credit spread regime (risk-on/risk-off)."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        lookback = int(params.get("lookback", 20))
        mode = str(params.get("mode", "risk_on"))
        hold_bars = int(params.get("hold_bars", 1))

        # Try credit_spread (HYG/LQD ratio), then hy_spread (FRED OAS)
        if "credit_spread" in df.columns:
            values = df["credit_spread"].ffill().values.astype(np.float64)
            invert = False
        elif "hy_spread" in df.columns:
            values = df["hy_spread"].ffill().values.astype(np.float64)
            invert = True  # OAS: high = stress, low = calm
        else:
            logger.debug("CreditSpread: no 'credit_spread' or 'hy_spread' column — returning all-False")
            return pd.Series(False, index=df.index, name="credit_spread", dtype=bool)

        n = len(values)
        sma = np.full(n, np.nan)
        for i in range(lookback, n):
            sma[i] = np.mean(values[i - lookback + 1 : i + 1])

        if mode == "risk_on":
            raw = values > sma if not invert else values < sma
        elif mode == "risk_off":
            raw = values < sma if not invert else values > sma
        elif mode == "momentum":
            # Cross above SMA (ratio rising) or cross below SMA (OAS falling)
            above = values > sma if not invert else values < sma
            prev_above = np.roll(above, 1)
            prev_above[0] = False
            raw = above & ~prev_above
        else:
            raw = np.full(n, False)

        raw = np.where(np.isnan(sma), False, raw)
        result = pd.Series(raw, index=df.index, name="credit_spread", dtype=bool)
        result.iloc[:lookback] = False
        return self._hold_bars(result, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "lookback": {"type": "int", "min": 10, "max": 60, "default": 20},
            "mode": {
                "type": "str",
                "choices": ["risk_on", "risk_off", "momentum"],
                "default": "risk_on",
            },
            "hold_bars": {"type": "int", "min": 1, "max": 20, "default": 1},
        }
