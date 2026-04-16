"""Custom indicator package.

Implemented: Firestorm (+ TM), SSL Channel (+ Low), and WaveTrend (Reversal + Divergence).
Squeeze Momentum is in standard/squeeze.py.
"""

from suitetrading.indicators.custom.firestorm import Firestorm, FirestormTM, firestorm
from suitetrading.indicators.custom.ssl_channel import SSLChannel, SSLChannelLow, ssl_channel
from suitetrading.indicators.custom.wavetrend import (
    WaveTrendDivergence,
    WaveTrendReversal,
    wavetrend,
)

__all__ = [
    "Firestorm",
    "FirestormTM",
    "SSLChannel",
    "SSLChannelLow",
    "WaveTrendDivergence",
    "WaveTrendReversal",
    "firestorm",
    "ssl_channel",
    "wavetrend",
]
