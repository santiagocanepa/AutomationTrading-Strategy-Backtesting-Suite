"""Market regime classification — TREND_UP, TREND_DOWN, RANGE, HIGH_VOL, CRASH.

Classifies each bar into a market regime using ADX for trend strength,
volatility percentiles, and drawdown speed.
"""
from __future__ import annotations

from enum import StrEnum

import numpy as np
import pandas as pd
from loguru import logger


class MarketRegime(StrEnum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    HIGH_VOL = "high_vol"
    CRASH = "crash"


class RegimeClassifier:
    """Classify each bar into a market regime."""

    def __init__(
        self,
        *,
        adx_period: int = 14,
        adx_trend_threshold: float = 25.0,
        vol_lookback: int = 100,
        vol_high_pctile: float = 90.0,
        crash_dd_threshold: float = 10.0,
        crash_speed_bars: int = 24,
    ) -> None:
        self._adx_period = adx_period
        self._adx_threshold = adx_trend_threshold
        self._vol_lookback = vol_lookback
        self._vol_pctile = vol_high_pctile
        self._crash_dd_thresh = crash_dd_threshold
        self._crash_bars = crash_speed_bars

    def classify(self, df: pd.DataFrame) -> pd.Series:
        """Return a Series of MarketRegime values for each bar.

        Priority order:
        1. CRASH: drawdown > threshold within crash_speed_bars
        2. HIGH_VOL: volatility above vol_high_pctile percentile
        3. TREND_UP: ADX > threshold AND close > EMA(50)
        4. TREND_DOWN: ADX > threshold AND close < EMA(50)
        5. RANGE: everything else

        Expects OHLCV DataFrame with columns: open, high, low, close, volume.
        """
        required = {"open", "high", "low", "close"}
        cols_lower = {c.lower() for c in df.columns}
        missing = required - cols_lower
        if missing:
            raise ValueError(f"DataFrame missing columns: {missing}")

        n = len(df)
        regimes = np.full(n, MarketRegime.RANGE, dtype=object)

        high = df["high"].values.astype(np.float64)
        low = df["low"].values.astype(np.float64)
        close = df["close"].values.astype(np.float64)

        # Compute ADX
        adx = self._compute_adx(high, low, close, self._adx_period)

        # Compute EMA(50) of close
        ema50 = self._ema(close, 50)

        # Compute rolling volatility (std of log returns)
        log_ret = np.zeros(n, dtype=np.float64)
        log_ret[1:] = np.log(np.where(close[:-1] > 0, close[1:] / close[:-1], 1.0))
        rolling_vol = self._rolling_std(log_ret, self._vol_lookback)

        # Compute rolling volatility percentile
        vol_pctile = self._rolling_percentile(rolling_vol, self._vol_lookback)

        # Compute fast drawdown for crash detection
        crash_mask = self._detect_crash(close, self._crash_dd_thresh, self._crash_bars)

        # Apply priority classification
        for i in range(n):
            if crash_mask[i]:
                regimes[i] = MarketRegime.CRASH
            elif vol_pctile[i] >= self._vol_pctile:
                regimes[i] = MarketRegime.HIGH_VOL
            elif adx[i] > self._adx_threshold and close[i] > ema50[i]:
                regimes[i] = MarketRegime.TREND_UP
            elif adx[i] > self._adx_threshold and close[i] < ema50[i]:
                regimes[i] = MarketRegime.TREND_DOWN
            # else: RANGE (default)

        result = pd.Series(regimes, index=df.index, name="regime")
        counts = {r.value: int(np.sum(regimes == r)) for r in MarketRegime}
        logger.debug("Regime classification: {}", counts)
        return result

    @staticmethod
    def _compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
        """Compute ADX using Wilder's smoothing (pure numpy)."""
        n = len(close)
        adx = np.zeros(n, dtype=np.float64)
        if n < period + 1:
            return adx

        # True Range
        tr = np.zeros(n, dtype=np.float64)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )

        # +DM, -DM
        plus_dm = np.zeros(n, dtype=np.float64)
        minus_dm = np.zeros(n, dtype=np.float64)
        for i in range(1, n):
            up = high[i] - high[i - 1]
            down = low[i - 1] - low[i]
            plus_dm[i] = up if (up > down and up > 0) else 0.0
            minus_dm[i] = down if (down > up and down > 0) else 0.0

        # Wilder's smoothing
        atr = np.zeros(n, dtype=np.float64)
        smooth_plus = np.zeros(n, dtype=np.float64)
        smooth_minus = np.zeros(n, dtype=np.float64)

        # Initial sums
        atr[period] = np.sum(tr[1 : period + 1])
        smooth_plus[period] = np.sum(plus_dm[1 : period + 1])
        smooth_minus[period] = np.sum(minus_dm[1 : period + 1])

        for i in range(period + 1, n):
            atr[i] = atr[i - 1] - atr[i - 1] / period + tr[i]
            smooth_plus[i] = smooth_plus[i - 1] - smooth_plus[i - 1] / period + plus_dm[i]
            smooth_minus[i] = smooth_minus[i - 1] - smooth_minus[i - 1] / period + minus_dm[i]

        # +DI, -DI
        plus_di = np.zeros(n, dtype=np.float64)
        minus_di = np.zeros(n, dtype=np.float64)
        for i in range(period, n):
            if atr[i] > 0:
                plus_di[i] = 100.0 * smooth_plus[i] / atr[i]
                minus_di[i] = 100.0 * smooth_minus[i] / atr[i]

        # DX
        dx = np.zeros(n, dtype=np.float64)
        for i in range(period, n):
            di_sum = plus_di[i] + minus_di[i]
            if di_sum > 0:
                dx[i] = 100.0 * abs(plus_di[i] - minus_di[i]) / di_sum

        # ADX: Wilder's smoothing of DX
        start = 2 * period
        if start < n:
            adx[start] = np.mean(dx[period : start + 1])
            for i in range(start + 1, n):
                adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

        return adx

    @staticmethod
    def _ema(data: np.ndarray, period: int) -> np.ndarray:
        """Exponential moving average (pure numpy)."""
        n = len(data)
        ema = np.zeros(n, dtype=np.float64)
        if n == 0:
            return ema
        alpha = 2.0 / (period + 1)
        ema[0] = data[0]
        for i in range(1, n):
            ema[i] = alpha * data[i] + (1.0 - alpha) * ema[i - 1]
        return ema

    @staticmethod
    def _rolling_std(data: np.ndarray, window: int) -> np.ndarray:
        """Rolling standard deviation (pure numpy)."""
        n = len(data)
        result = np.zeros(n, dtype=np.float64)
        if n < window:
            return result
        # Use cumsum trick for efficiency
        cumsum = np.cumsum(data)
        cumsum2 = np.cumsum(data ** 2)
        for i in range(window - 1, n):
            start = i - window + 1
            s = cumsum[i] - (cumsum[start - 1] if start > 0 else 0.0)
            s2 = cumsum2[i] - (cumsum2[start - 1] if start > 0 else 0.0)
            mean = s / window
            var = s2 / window - mean ** 2
            result[i] = np.sqrt(max(var, 0.0))
        return result

    @staticmethod
    def _rolling_percentile(data: np.ndarray, window: int) -> np.ndarray:
        """Rolling percentile rank of current value within its window."""
        n = len(data)
        result = np.zeros(n, dtype=np.float64)
        for i in range(window - 1, n):
            window_data = data[i - window + 1 : i + 1]
            current = data[i]
            result[i] = float(np.sum(window_data <= current)) / window * 100.0
        return result

    @staticmethod
    def _detect_crash(close: np.ndarray, dd_threshold: float, speed_bars: int) -> np.ndarray:
        """Detect crash: drawdown > threshold within speed_bars lookback."""
        n = len(close)
        crash = np.zeros(n, dtype=bool)
        dd_frac = dd_threshold / 100.0

        for i in range(speed_bars, n):
            window_peak = np.max(close[i - speed_bars : i + 1])
            if window_peak > 0:
                dd = (window_peak - close[i]) / window_peak
                if dd >= dd_frac:
                    crash[i] = True
        return crash
