"""Combine per-indicator boolean signals into a final entry signal."""

from __future__ import annotations

import math

import pandas as pd

from suitetrading.indicators.base import IndicatorState


def combine_signals(
    signals: dict[str, pd.Series],
    states: dict[str, IndicatorState],
    num_optional_required: int = 1,
    *,
    combination_mode: str = "excluyente",
    majority_threshold: int | None = None,
) -> pd.Series:
    """Replicate Pine Script excluyente / opcional / desactivado logic.

    Parameters
    ----------
    signals:
        Mapping indicator_name → boolean Series (True = condition met).
    states:
        Mapping indicator_name → IndicatorState.
    num_optional_required:
        Minimum optional indicators that must be True.
    combination_mode:
        ``"excluyente"`` — original AND chain (default).
        ``"majority"`` — N-of-M voting; ignores IndicatorState and
        treats all non-DESACTIVADO indicators equally.
    majority_threshold:
        For ``"majority"`` mode only.  Minimum number of indicators
        that must be True.  Defaults to ``ceil(active_count / 2)``.

    Returns
    -------
    pd.Series[bool]
        Combined entry signal.
    """
    if combination_mode == "majority":
        return _combine_majority(signals, states, majority_threshold)

    return _combine_excluyente(signals, states, num_optional_required)


def _combine_excluyente(
    signals: dict[str, pd.Series],
    states: dict[str, IndicatorState],
    num_optional_required: int = 1,
) -> pd.Series:
    """Original AND-chain logic with EXCLUYENTE / OPCIONAL."""
    if not signals:
        return pd.Series(False, index=pd.RangeIndex(0), dtype=bool)
    index = next(iter(signals.values())).index
    excluyente_mask = pd.Series(True, index=index)
    optional_count = pd.Series(0, index=index, dtype="int32")

    has_optional = False
    for name, series in signals.items():
        state = states.get(name, IndicatorState.DESACTIVADO)
        if state == IndicatorState.DESACTIVADO:
            continue
        if state == IndicatorState.EXCLUYENTE:
            excluyente_mask &= series
        elif state == IndicatorState.OPCIONAL:
            optional_count += series.astype("int32")
            has_optional = True

    if not has_optional:
        return excluyente_mask
    return excluyente_mask & (optional_count >= num_optional_required)


def _combine_majority(
    signals: dict[str, pd.Series],
    states: dict[str, IndicatorState],
    threshold: int | None,
) -> pd.Series:
    """Majority-vote: signal when >= *threshold* indicators agree."""
    if not signals:
        return pd.Series(False, index=pd.RangeIndex(0), dtype=bool)
    index = next(iter(signals.values())).index
    vote_count = pd.Series(0, index=index, dtype="int32")
    active_count = 0

    for name, series in signals.items():
        state = states.get(name, IndicatorState.DESACTIVADO)
        if state == IndicatorState.DESACTIVADO:
            continue
        vote_count += series.astype("int32")
        active_count += 1

    if active_count == 0:
        return pd.Series(False, index=index)

    required = threshold if threshold is not None else math.ceil(active_count / 2)
    return vote_count >= required
