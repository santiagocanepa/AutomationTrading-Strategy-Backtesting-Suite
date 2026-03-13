"""Custom indicator package.

Currently implemented: Firestorm, SSL Channel, and WaveTrend variants.
ASH, Squeeze Momentum, and Fibonacci MAI remain Sprint 2 deliverables.
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
