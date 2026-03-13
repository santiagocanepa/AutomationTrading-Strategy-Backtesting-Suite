"""SSL Channel indicator — exact Pine Script replica.

Pine logic (simplified):
    smaHigh = EMA(high, length)
    smaLow  = EMA(low,  length)
    Hlv = 0  (init)
    Hlv = close > smaHigh ? 1 : close < smaLow ? -1 : Hlv[1]
    sslDown = Hlv < 0 ? smaHigh : smaLow
    sslUp   = Hlv < 0 ? smaLow  : smaHigh
    ssl_compra  = sslUp > sslDown   (level)
    ssl_venta   = sslUp < sslDown   (level)
    ssl_compra1 = crossover(sslUp, sslDown)   (cross — used for hold-bars)
    ssl_venta1  = crossunder(sslUp, sslDown)

For risk management the *level* signals (ssl_compra / ssl_venta) are used.
For entry the *cross* signals with hold-bars are used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit

from suitetrading.indicators.base import Indicator

# ── Core computation (Numba for speed) ────────────────────────────


@njit(cache=True)
def _ssl_channel_core(
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    ema_high: np.ndarray,
    ema_low: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute Hlv, sslUp, sslDown arrays.

    Returns (ssl_up, ssl_down, hlv).
    """
    n = len(close)
    hlv = np.zeros(n, dtype=np.float64)
    ssl_up = np.empty(n, dtype=np.float64)
    ssl_down = np.empty(n, dtype=np.float64)

    for i in range(n):
        if i == 0:  # noqa: SIM108
            prev_hlv = 0.0
        else:
            prev_hlv = hlv[i - 1]

        if close[i] > ema_high[i]:
            hlv[i] = 1.0
        elif close[i] < ema_low[i]:
            hlv[i] = -1.0
        else:
            hlv[i] = prev_hlv

        if hlv[i] < 0:
            ssl_down[i] = ema_high[i]
            ssl_up[i] = ema_low[i]
        else:
            ssl_down[i] = ema_low[i]
            ssl_up[i] = ema_high[i]

    return ssl_up, ssl_down, hlv


def ssl_channel(
    high: np.ndarray | pd.Series,
    low: np.ndarray | pd.Series,
    close: np.ndarray | pd.Series,
    length: int = 12,
) -> tuple[pd.Series, pd.Series]:
    """Compute SSL Channel.

    Parameters
    ----------
    high, low, close : array-like
        OHLC price data.
    length : int
        EMA period (default 12, matching Pine default).

    Returns
    -------
    ssl_up, ssl_down : pd.Series
        The two SSL lines. ``ssl_up > ssl_down`` = bullish.
    """
    idx = close.index if isinstance(close, pd.Series) else None

    h = np.asarray(high, dtype=np.float64)
    lo = np.asarray(low, dtype=np.float64)
    c = np.asarray(close, dtype=np.float64)

    # EMA of high and low (Pine uses ta.ema despite variable names saying "sma")
    ema_h = _ema(h, length)
    ema_l = _ema(lo, length)

    ssl_up, ssl_down, _ = _ssl_channel_core(h, lo, c, ema_h, ema_l)

    if idx is not None:
        return (
            pd.Series(ssl_up, index=idx, name="ssl_up"),
            pd.Series(ssl_down, index=idx, name="ssl_down"),
        )
    return (
        pd.Series(ssl_up, name="ssl_up"),
        pd.Series(ssl_down, name="ssl_down"),
    )


# ── Derived signals ──────────────────────────────────────────────


def ssl_cross_signals(
    ssl_up: pd.Series,
    ssl_down: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Return crossover / crossunder boolean Series.

    - ``buy`` = ssl_up crosses above ssl_down
    - ``sell`` = ssl_up crosses below ssl_down
    """
    above = ssl_up > ssl_down
    buy = above & ~above.shift(1, fill_value=False)
    sell = ~above & above.shift(1, fill_value=True)
    return buy.rename("ssl_cross_buy"), sell.rename("ssl_cross_sell")


def ssl_level_signals(
    ssl_up: pd.Series,
    ssl_down: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Return level (non-cross) boolean Series.

    - ``buy`` = ssl_up > ssl_down (persistent)
    - ``sell`` = ssl_up < ssl_down (persistent)
    """
    buy = ssl_up > ssl_down
    sell = ssl_up < ssl_down
    return buy.rename("ssl_level_buy"), sell.rename("ssl_level_sell")


# ── EMA helper ───────────────────────────────────────────────────


@njit(cache=True)
def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average matching Pine Script's ta.ema."""
    n = len(data)
    out = np.empty(n, dtype=np.float64)
    alpha = 2.0 / (period + 1)

    # Seed with first value (Pine behaviour)
    out[0] = data[0]
    for i in range(1, n):
        out[i] = alpha * data[i] + (1.0 - alpha) * out[i - 1]
    return out


# ── Indicator ABC wrapper ────────────────────────────────────────


class SSLChannel(Indicator):
    """SSL Channel — entry signal indicator (cross + hold-bars)."""

    def compute(
        self,
        df: pd.DataFrame,
        *,
        length: int = 12,
        hold_bars: int = 4,
        direction: str = "long",
    ) -> pd.Series:
        self._validate_ohlcv(df)
        ssl_up, ssl_down = ssl_channel(df["high"], df["low"], df["close"], length)
        buy_cross, sell_cross = ssl_cross_signals(ssl_up, ssl_down)

        raw = buy_cross if direction == "long" else sell_cross
        return self._hold_bars(raw, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "length": {"type": "int", "min": 2, "max": 200, "default": 12},
            "hold_bars": {"type": "int", "min": 1, "max": 20, "default": 4},
        }


class SSLChannelLow(Indicator):
    """SSL Channel LOW — trailing stop signal (cross only, no hold-bars)."""

    def compute(
        self,
        df: pd.DataFrame,
        *,
        length: int = 12,
        direction: str = "long",
    ) -> pd.Series:
        self._validate_ohlcv(df)
        ssl_up, ssl_down = ssl_channel(df["high"], df["low"], df["close"], length)
        buy_cross, sell_cross = ssl_cross_signals(ssl_up, ssl_down)

        # For longs, trailing triggers when sell cross fires
        return sell_cross if direction == "long" else buy_cross

    def params_schema(self) -> dict[str, dict]:
        return {
            "length": {"type": "int", "min": 2, "max": 200, "default": 12},
        }
