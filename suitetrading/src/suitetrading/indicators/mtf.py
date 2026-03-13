"""Multi-timeframe helpers: resample OHLCV and align signals.

Delegates to :mod:`suitetrading.data.timeframes` for canonical TF mapping
and to :class:`suitetrading.data.resampler.OHLCVResampler` for resampling logic.
"""

from __future__ import annotations

import pandas as pd

from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.timeframes import (
    normalize_timeframe,
)

# Pine Script TF resolution ladder (kept for resolve_timeframe logic)
_TF_LADDER: dict[str, str] = {
    "1": "3",
    "3": "5",
    "5": "15",
    "15": "30",
    "30": "45",
    "45": "60",
    "60": "240",
    "240": "D",
    "D": "W",
    "W": "M",
    "M": "M",
}

_resampler = OHLCVResampler()


def resolve_timeframe(current_tf: str, selection: str) -> str:
    """Resolve '1 superior', '2 superiores', 'grafico', or literal TF."""
    if selection == "grafico":
        return current_tf
    if selection == "1 superior":
        return _TF_LADDER.get(current_tf, "M")
    if selection == "2 superiores":
        one_up = _TF_LADDER.get(current_tf, "M")
        return _TF_LADDER.get(one_up, "M")
    return selection


def resample_ohlcv(df: pd.DataFrame, target_tf: str, *, base_tf: str = "1m") -> pd.DataFrame:
    """Resample a lower-TF OHLCV DataFrame to *target_tf* and forward-fill.

    Accepts both Pine-style (``"60"``) and canonical (``"1h"``) TF strings.
    Delegates to :class:`OHLCVResampler` for consistent aggregation rules
    (45m epoch alignment, weekly Monday start, incomplete bar removal).
    """
    # Normalize: accept Pine or canonical keys
    try:
        canonical = normalize_timeframe(target_tf)
    except ValueError:
        raise ValueError(f"Unknown timeframe: {target_tf!r}")

    return _resampler.resample(df, canonical, base_tf=base_tf)


def align_to_base(
    htf_series: pd.Series,
    base_index: pd.DatetimeIndex,
) -> pd.Series:
    """Reindex a higher-TF series onto the base-TF index via forward-fill."""
    return htf_series.reindex(base_index, method="ffill")
