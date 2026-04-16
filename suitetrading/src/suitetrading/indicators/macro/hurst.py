"""Hurst exponent indicator for regime detection.

H > 0.55: persistent / trending — trend-following has edge
H ≈ 0.50: random walk — no exploitable structure
H < 0.45: antipersistent / mean-reverting — mean-reversion has edge

Uses Rescaled Range (R/S) analysis on log returns.  No external
data required — works on OHLCV close prices alone.

References:
    Hurst (1951): "Long-term storage capacity of reservoirs", ASCE.
    Lo (1991): "Long-term memory in stock market prices", Econometrica.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from suitetrading.indicators.base import Indicator


def _hurst_rs(series: np.ndarray) -> float:
    """Compute Hurst exponent via Rescaled Range (R/S) analysis.

    Splits the series into sub-segments of decreasing size (powers of 2),
    computes R/S for each, and fits log(R/S) vs log(n) to get H.
    """
    n = len(series)
    if n < 20:
        return 0.5

    max_k = int(np.log2(n))
    segment_sizes = [int(2**i) for i in range(3, max_k + 1) if 2**i <= n // 2]

    if len(segment_sizes) < 2:
        return 0.5

    rs_points: list[tuple[float, float]] = []
    for k in segment_sizes:
        n_segments = n // k
        rs_list: list[float] = []
        for p in range(n_segments):
            segment = series[p * k : (p + 1) * k]
            mean = np.mean(segment)
            dev = np.cumsum(segment - mean)
            R = np.max(dev) - np.min(dev)
            S = np.std(segment, ddof=1)
            if S > 1e-15:
                rs_list.append(R / S)
        if rs_list:
            rs_points.append((np.log(k), np.log(np.mean(rs_list))))

    if len(rs_points) < 2:
        return 0.5

    x, y = zip(*rs_points)
    slope, _, _, _, _ = sp_stats.linregress(x, y)
    return float(np.clip(slope, 0.0, 1.0))


class HurstIndicator(Indicator):
    """Signal based on rolling Hurst exponent regime."""

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        self._validate_ohlcv(df)
        window = int(params.get("window", 100))
        mode = str(params.get("mode", "trending"))
        threshold_high = float(params.get("threshold_high", 0.55))
        threshold_low = float(params.get("threshold_low", 0.45))
        hold_bars = int(params.get("hold_bars", 1))

        close = df["close"].values.astype(np.float64)
        log_rets = np.diff(np.log(close), prepend=np.nan)
        n = len(log_rets)

        hurst_values = np.full(n, np.nan)
        for i in range(window, n):
            segment = log_rets[i - window + 1 : i + 1]
            valid = segment[~np.isnan(segment)]
            if len(valid) >= 20:
                hurst_values[i] = _hurst_rs(valid)

        if mode == "trending":
            raw = hurst_values > threshold_high
        elif mode == "mean_reverting":
            raw = hurst_values < threshold_low
        elif mode == "any_edge":
            raw = (hurst_values > threshold_high) | (hurst_values < threshold_low)
        else:
            raw = np.full(n, False)

        raw = np.where(np.isnan(hurst_values), False, raw)
        result = pd.Series(raw, index=df.index, name="hurst", dtype=bool)
        result.iloc[:window] = False
        return self._hold_bars(result, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "window": {"type": "int", "min": 50, "max": 300, "default": 100},
            "mode": {
                "type": "str",
                "choices": ["trending", "mean_reverting", "any_edge"],
                "default": "trending",
            },
            "threshold_high": {"type": "float", "min": 0.52, "max": 0.65, "step": 0.01, "default": 0.55},
            "threshold_low": {"type": "float", "min": 0.35, "max": 0.48, "step": 0.01, "default": 0.45},
            "hold_bars": {"type": "int", "min": 1, "max": 20, "default": 1},
        }
