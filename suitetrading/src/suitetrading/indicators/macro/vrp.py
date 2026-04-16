"""Variance Risk Premium indicator.

VRP = Implied Variance (VIX²) − Realized Variance.

Positive VRP means the market is overpaying for downside protection
(normal state).  Negative VRP signals panic pricing — realized vol
exceeds what options market expected.

Requires ``vix`` column in the OHLCV DataFrame, added externally
via ``MacroCacheManager.get_aligned()``.  Falls back to no-signal
if column is absent.

References:
    Quantpedia #0020: "Volatility Risk Premium", Return 26%, Vol 19%
    Carr & Wu (2009): "Variance Risk Premiums", RFS.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from suitetrading.indicators.base import Indicator


class VRPIndicator(Indicator):
    """Signal on Variance Risk Premium regime."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        realized_window = int(params.get("realized_window", 20))
        mode = str(params.get("mode", "risk_on"))
        hold_bars = int(params.get("hold_bars", 1))

        if "vix" not in df.columns:
            logger.debug("VRP: 'vix' column absent — returning all-False")
            return pd.Series(False, index=df.index, name="vrp", dtype=bool)

        vix = df["vix"].ffill().values.astype(np.float64)
        close = df["close"].values.astype(np.float64)

        # Implied variance (annualized): (VIX/100)²
        implied_var = (vix / 100.0) ** 2

        # Realized variance (annualized): rolling var of log returns × 252
        log_rets = np.diff(np.log(close), prepend=np.nan)
        n = len(log_rets)
        realized_var = np.full(n, np.nan)
        for i in range(realized_window, n):
            window = log_rets[i - realized_window + 1 : i + 1]
            realized_var[i] = np.var(window, ddof=1) * 252

        vrp = implied_var - realized_var

        if mode == "risk_on":
            raw = vrp > 0
        else:
            raw = vrp < 0

        raw = np.where(np.isnan(vrp), False, raw)
        result = pd.Series(raw, index=df.index, name="vrp", dtype=bool)
        result.iloc[:realized_window] = False
        return self._hold_bars(result, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "realized_window": {"type": "int", "min": 10, "max": 60, "default": 20},
            "mode": {
                "type": "str",
                "choices": ["risk_on", "risk_off"],
                "default": "risk_on",
            },
            "hold_bars": {"type": "int", "min": 1, "max": 20, "default": 1},
        }
