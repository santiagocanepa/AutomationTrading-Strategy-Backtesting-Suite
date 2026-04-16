"""Cross-sectional momentum rank filter.

Ranks assets by relative return (12−1 month momentum).  Only trades
assets in the top (winners) or bottom (losers) percentile.

The rank column ``cs_momentum_rank`` (0.0 = worst, 1.0 = best) is
pre-computed externally and injected into the DataFrame.  This
indicator only filters based on that rank.

Falls back to no-signal if column is absent.

References:
    Jegadeesh & Titman (1993): "Returns to Buying Winners and Selling
    Losers", Journal of Finance.
    Asness et al. (2014): "Fact, Fiction and Momentum Investing", JoPM.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from suitetrading.indicators.base import Indicator


class CrossSectionalMomentum(Indicator):
    """Signal based on cross-sectional momentum percentile rank."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        rank_threshold = float(params.get("rank_threshold", 0.5))
        mode = str(params.get("mode", "winners"))
        hold_bars = int(params.get("hold_bars", 1))

        if "cs_momentum_rank" not in df.columns:
            logger.debug("CSMomentum: 'cs_momentum_rank' column absent — returning all-False")
            return pd.Series(False, index=df.index, name="cs_momentum", dtype=bool)

        rank = df["cs_momentum_rank"].ffill().values.astype(np.float64)

        if mode == "winners":
            raw = rank >= rank_threshold
        else:  # losers
            raw = rank <= (1.0 - rank_threshold)

        raw = np.where(np.isnan(rank), False, raw)
        result = pd.Series(raw, index=df.index, name="cs_momentum", dtype=bool)
        return self._hold_bars(result, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "rank_threshold": {"type": "float", "min": 0.3, "max": 0.8, "step": 0.1, "default": 0.5},
            "mode": {
                "type": "str",
                "choices": ["winners", "losers"],
                "default": "winners",
            },
            "hold_bars": {"type": "int", "min": 1, "max": 20, "default": 1},
        }
