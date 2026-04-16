"""Open interest indicators for crypto futures markets.

OI divergence from price is a classic derivatives signal:

    Price ↑ + OI ↑ → New longs entering → strong bullish
    Price ↑ + OI ↓ → Short covering rally → weak (bearish divergence)
    Price ↓ + OI ↑ → New shorts entering → strong bearish
    Price ↓ + OI ↓ → Long liquidation → weak (bullish divergence)

Data source: Binance ``GET /futures/data/openInterestHist``
Available at 5m/15m/30m/1h/2h/4h/6h/12h/1d resolution.
In production, poll every 5m for low-TF strategies.

Requires ``open_interest`` column in the OHLCV DataFrame.
Falls back to no-signal if column is absent.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from suitetrading.indicators.base import Indicator


class OIDivergence(Indicator):
    """Signal when price and open interest diverge.

    Detects situations where price moves one direction but OI moves
    the opposite, indicating weak conviction in the price move.
    """

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        period = int(params.get("period", 14))
        mode = str(params.get("mode", "bullish"))
        hold_bars = int(params.get("hold_bars", 3))

        if "open_interest" not in df.columns:
            return pd.Series(False, index=df.index, name="oi_div", dtype=bool)

        close = df["close"].values.astype(np.float64)
        oi = df["open_interest"].ffill().values.astype(np.float64)
        n = len(close)

        raw = np.full(n, False, dtype=bool)
        for i in range(period, n):
            prev_close = close[i - period]
            prev_oi = oi[i - period]
            if prev_close < 1e-12 or prev_oi < 1e-12:
                continue

            price_roc = close[i] / prev_close - 1.0
            oi_roc = oi[i] / prev_oi - 1.0

            if mode == "bullish":
                # Price down but OI up → new longs at lower prices
                raw[i] = (price_roc < 0) and (oi_roc > 0)
            else:
                # Price up but OI down → short covering rally (weak)
                raw[i] = (price_roc > 0) and (oi_roc < 0)

        result = pd.Series(raw, index=df.index, name="oi_div", dtype=bool)
        result.iloc[:period] = False
        return self._hold_bars(result, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "period": {"type": "int", "min": 5, "max": 40, "default": 14},
            "mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 3},
        }


class LongShortRatio(Indicator):
    """Contrarian signal on extreme long/short account ratios.

    When the ratio is extreme (most accounts long), it's a contrarian
    short signal.  When most accounts are short, contrarian long.

    Requires ``long_short_ratio`` column in the OHLCV DataFrame.
    Falls back to no-signal if column is absent.
    """

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        lookback = int(params.get("lookback", 30))
        extreme_z = float(params.get("extreme_z", 2.0))
        mode = str(params.get("mode", "contrarian_long"))
        hold_bars = int(params.get("hold_bars", 3))

        if "long_short_ratio" not in df.columns:
            return pd.Series(False, index=df.index, name="ls_ratio", dtype=bool)

        ratio = df["long_short_ratio"].ffill().values.astype(np.float64)
        n = len(ratio)

        raw = np.full(n, False, dtype=bool)
        for i in range(lookback, n):
            window = ratio[i - lookback : i]
            mean = np.mean(window)
            std = np.std(window, ddof=1)
            if std < 1e-12:
                continue
            z = (ratio[i] - mean) / std

            if mode == "contrarian_long":
                # Extreme short positioning → contrarian long
                raw[i] = z < -extreme_z
            else:
                # Extreme long positioning → contrarian short
                raw[i] = z > extreme_z

        result = pd.Series(raw, index=df.index, name="ls_ratio", dtype=bool)
        result.iloc[:lookback] = False
        return self._hold_bars(result, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "lookback": {"type": "int", "min": 10, "max": 100, "default": 30},
            "extreme_z": {"type": "float", "min": 1.0, "max": 4.0, "step": 0.5, "default": 2.0},
            "mode": {
                "type": "str",
                "choices": ["contrarian_long", "contrarian_short"],
                "default": "contrarian_long",
            },
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 3},
        }
