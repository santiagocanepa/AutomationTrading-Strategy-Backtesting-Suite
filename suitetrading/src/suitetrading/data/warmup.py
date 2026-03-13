"""Warmup period calculator for indicators across timeframes.

Calculates how much historical data is needed before indicators produce
valid signals, expressed as a ``timedelta`` from the first desired bar.
"""

from __future__ import annotations

from datetime import timedelta

from suitetrading.data.timeframes import normalize_timeframe, tf_to_seconds


# Known warmup requirements in *bars of the indicator's native timeframe*.
# Format: indicator_key → bars needed before first valid signal.
INDICATOR_WARMUP: dict[str, int] = {
    "ema_9": 50,
    "ema_21": 100,
    "ema_50": 200,
    "ema_200": 600,
    "sma_9": 50,
    "sma_50": 200,
    "sma_200": 600,
    "rsi_14": 100,
    "macd_12_26_9": 150,
    "bbands_20": 120,
    "atr_14": 100,
    "stoch_14": 100,
    "adx_14": 100,
    "squeeze": 200,
    "wavetrend": 150,
    "ssl_channel": 100,
    "firestorm": 200,
}

DEFAULT_WARMUP_BARS = 200


class WarmupCalculator:
    """Compute the warmup ``timedelta`` needed for a set of indicators."""

    def calculate(
        self,
        indicators: list[dict],
        base_tf: str = "1m",
    ) -> timedelta:
        """Return the maximum warmup needed across all *indicators*.

        Each dict in *indicators* must have at least:
        - ``"key"``: str matching a key in ``INDICATOR_WARMUP``
        - ``"timeframe"``: str, the TF the indicator runs on

        Uses ``DEFAULT_WARMUP_BARS`` for unrecognized indicators.
        """
        if not indicators:
            return timedelta(0)

        max_td = timedelta(0)
        for ind in indicators:
            td = self._indicator_warmup(ind, base_tf)
            if td > max_td:
                max_td = td
        return max_td

    def calculate_from_config(self, config: dict) -> timedelta:
        """Convenience wrapper: pull indicators list + base_tf from config."""
        indicators = config.get("indicators", [])
        base_tf = config.get("base_timeframe", "1m")
        return self.calculate(indicators, base_tf)

    @staticmethod
    def _indicator_warmup(indicator: dict, base_tf: str) -> timedelta:
        """Compute warmup timedelta for a single indicator."""
        key = indicator.get("key", "")
        tf = normalize_timeframe(indicator.get("timeframe", base_tf))
        bars = INDICATOR_WARMUP.get(key, DEFAULT_WARMUP_BARS)
        return _tf_to_timedelta(tf, bars)


def _tf_to_timedelta(tf: str, bars: int) -> timedelta:
    """Convert *bars* of timeframe *tf* to a ``timedelta``."""
    secs = tf_to_seconds(tf)
    if secs is None:
        # Monthly — approximate at 30 days
        return timedelta(days=30 * bars)
    return timedelta(seconds=secs * bars)
