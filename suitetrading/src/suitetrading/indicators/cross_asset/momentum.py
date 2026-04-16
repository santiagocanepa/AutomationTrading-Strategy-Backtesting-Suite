"""Cross-asset momentum indicators.

Uses the return of a reference asset to predict direction of a target asset.
Based on Moskowitz, Ooi & Pedersen (2012) "Time Series Momentum".

Includes:
  - CrossAssetMomentum: simple ROC-based
  - CrossAssetMomentumInverse: inverted (ref up → target down)
  - VolScaledMomentum: Moskowitz-style (ROC / rolling_vol)
  - MacroRegimeSignal: level-based signal for VIX, spreads, yields

The reference data must be pre-merged into the target's DataFrame.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from suitetrading.indicators.base import Indicator


class CrossAssetMomentum(Indicator):
    """Cross-asset time-series momentum.

    Signal: ROC(reference, lookback) > 0 → bullish prediction for target.
    The reference column is expected to be forward-filled and aligned to
    the target's index.
    """

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        ref_col = str(params.get("reference_col", "ref_close"))
        lookback = int(params.get("lookback", 24))
        hold_bars = int(params.get("hold_bars", 3))
        mode = str(params.get("mode", "bullish"))

        if ref_col not in df.columns:
            return pd.Series(False, index=df.index, name="cross_momentum", dtype=bool)

        ref = df[ref_col]
        if ref.isna().all():
            return pd.Series(False, index=df.index, name="cross_momentum", dtype=bool)

        roc = ref / ref.shift(lookback) - 1.0

        if mode == "bullish":
            raw = roc > 0
        else:
            raw = roc < 0

        signal = pd.Series(raw.values, index=df.index, name="cross_momentum", dtype=bool)
        signal.iloc[:lookback] = False
        # NaN positions → False
        signal = signal.fillna(False)
        return self._hold_bars(signal, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "reference_col": {"type": "str", "default": "ref_close"},
            "lookback": {"type": "int", "min": 1, "max": 60, "default": 24},
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 3},
            "mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
        }


class CrossAssetMomentumInverse(Indicator):
    """Inverse cross-asset momentum — reference UP → target DOWN.

    Useful for: VIX → crypto (fear signal), TLT → equities (flight to safety).
    """

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        ref_col = str(params.get("reference_col", "ref_close"))
        lookback = int(params.get("lookback", 24))
        hold_bars = int(params.get("hold_bars", 3))
        mode = str(params.get("mode", "bullish"))

        if ref_col not in df.columns:
            return pd.Series(False, index=df.index, name="cross_momentum_inv", dtype=bool)

        ref = df[ref_col]
        if ref.isna().all():
            return pd.Series(False, index=df.index, name="cross_momentum_inv", dtype=bool)

        roc = ref / ref.shift(lookback) - 1.0

        # Inverse: reference UP → bearish for target, reference DOWN → bullish
        if mode == "bullish":
            raw = roc < 0  # reference down → target up
        else:
            raw = roc > 0  # reference up → target down

        signal = pd.Series(raw.values, index=df.index, name="cross_momentum_inv", dtype=bool)
        signal.iloc[:lookback] = False
        signal = signal.fillna(False)
        return self._hold_bars(signal, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "reference_col": {"type": "str", "default": "ref_close"},
            "lookback": {"type": "int", "min": 1, "max": 60, "default": 24},
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 3},
            "mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
        }


class VolScaledMomentum(Indicator):
    """Volatility-scaled cross-asset momentum (Moskowitz 2012).

    Signal = ROC(reference, lookback) / rolling_std(ROC, vol_window).
    Fires when the z-score exceeds a threshold — i.e., when momentum is
    unusually strong relative to recent volatility.
    """

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        ref_col = str(params.get("reference_col", "ref_close"))
        lookback = int(params.get("lookback", 12))
        vol_window = int(params.get("vol_window", 60))
        z_threshold = float(params.get("z_threshold", 0.5))
        hold_bars = int(params.get("hold_bars", 3))
        mode = str(params.get("mode", "bullish"))

        if ref_col not in df.columns:
            return pd.Series(False, index=df.index, name="vol_scaled_mom", dtype=bool)

        ref = df[ref_col].astype(float)
        if ref.isna().all():
            return pd.Series(False, index=df.index, name="vol_scaled_mom", dtype=bool)

        roc = ref / ref.shift(lookback) - 1.0
        vol = roc.rolling(vol_window).std()
        z = roc / vol.replace(0, np.nan)

        if mode == "bullish":
            raw = z > z_threshold
        else:
            raw = z < -z_threshold

        warmup = max(lookback, vol_window)
        signal = pd.Series(raw.values, index=df.index, name="vol_scaled_mom", dtype=bool)
        signal.iloc[:warmup] = False
        signal = signal.fillna(False)
        return self._hold_bars(signal, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "reference_col": {"type": "str", "default": "ref_close"},
            "lookback": {"type": "int", "min": 3, "max": 60, "default": 12},
            "vol_window": {"type": "int", "min": 20, "max": 120, "default": 60},
            "z_threshold": {"type": "float", "min": 0.0, "max": 2.0, "default": 0.5},
            "hold_bars": {"type": "int", "min": 1, "max": 10, "default": 3},
            "mode": {"type": "str", "choices": ["bullish", "bearish"], "default": "bullish"},
        }


class MacroRegimeSignal(Indicator):
    """Macro regime signal based on z-score of a macro variable.

    For VIX: high VIX (z > threshold) → risk-off (bearish for equities/crypto)
    For HY spread: high spread → risk-off
    For yield_spread: low/negative → bearish

    Mode 'risk_on' fires when z < -threshold (low fear). 'risk_off' when z > threshold.
    """

    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        ref_col = str(params.get("reference_col", "ref_value"))
        z_window = int(params.get("z_window", 60))
        z_threshold = float(params.get("z_threshold", 1.0))
        hold_bars = int(params.get("hold_bars", 5))
        mode = str(params.get("mode", "risk_on"))

        if ref_col not in df.columns:
            return pd.Series(False, index=df.index, name="macro_regime", dtype=bool)

        ref = df[ref_col].astype(float)
        if ref.isna().all():
            return pd.Series(False, index=df.index, name="macro_regime", dtype=bool)

        mean = ref.rolling(z_window).mean()
        std = ref.rolling(z_window).std().replace(0, np.nan)
        z = (ref - mean) / std

        if mode == "risk_on":
            raw = z < -z_threshold  # low VIX / low spread → risk on
        else:
            raw = z > z_threshold   # high VIX / high spread → risk off

        signal = pd.Series(raw.values, index=df.index, name="macro_regime", dtype=bool)
        signal.iloc[:z_window] = False
        signal = signal.fillna(False)
        return self._hold_bars(signal, hold_bars)

    def params_schema(self) -> dict[str, dict]:
        return {
            "reference_col": {"type": "str", "default": "ref_value"},
            "z_window": {"type": "int", "min": 20, "max": 252, "default": 60},
            "z_threshold": {"type": "float", "min": 0.0, "max": 3.0, "default": 1.0},
            "hold_bars": {"type": "int", "min": 1, "max": 20, "default": 5},
            "mode": {"type": "str", "choices": ["risk_on", "risk_off"], "default": "risk_on"},
        }
