"""Tests for tier-1 signals: TakerVolume, Basis, CrossSectionalMomentum, macro archetypes."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.config.archetypes import ARCHETYPE_INDICATORS
from suitetrading.indicators.futures.basis import BasisIndicator
from suitetrading.indicators.futures.taker_volume import TakerVolumeIndicator
from suitetrading.indicators.registry import get_indicator
from suitetrading.indicators.standard.cs_momentum import CrossSectionalMomentum


# ── Fixtures ──────────────────────────────────────────────────────────

def _ohlcv(n: int = 300, seed: int = 42, **extra_cols: float) -> pd.DataFrame:
    """Synthetic OHLCV with optional extra columns."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n, freq="4h", tz="UTC")
    close = 100.0 + np.cumsum(rng.normal(0.01, 0.5, n))
    close = np.maximum(close, 10.0)
    df = pd.DataFrame(
        {
            "open": close + rng.normal(0, 0.2, n),
            "high": close + np.abs(rng.normal(0.3, 0.2, n)),
            "low": close - np.abs(rng.normal(0.3, 0.2, n)),
            "close": close,
            "volume": rng.integers(500, 5000, n).astype(float),
        },
        index=idx,
    )
    for col, val in extra_cols.items():
        df[col] = val + rng.normal(0, 0.01, n)
    return df


# ── TakerVolume Tests ─────────────────────────────────────────────────

class TestTakerVolume:
    def test_buy_pressure_when_ratio_high(self):
        df = _ohlcv(200, taker_buy_ratio=0.60)
        ind = TakerVolumeIndicator()
        sig = ind.compute(df, lookback=20, threshold=0.55, mode="buy_pressure")
        assert isinstance(sig, pd.Series)
        assert sig.dtype == bool
        assert sig.iloc[25:].sum() > 100

    def test_sell_pressure_when_ratio_low(self):
        df = _ohlcv(200, taker_buy_ratio=0.40)
        ind = TakerVolumeIndicator()
        sig = ind.compute(df, lookback=20, threshold=0.55, mode="sell_pressure")
        assert sig.iloc[25:].sum() > 100

    def test_missing_column_returns_false(self):
        df = _ohlcv(100)
        ind = TakerVolumeIndicator()
        sig = ind.compute(df)
        assert not sig.any()
        assert len(sig) == 100

    def test_params_schema(self):
        schema = TakerVolumeIndicator().params_schema()
        assert "lookback" in schema
        assert "threshold" in schema
        assert "mode" in schema
        assert "hold_bars" in schema
        assert schema["threshold"]["type"] == "float"


# ── Basis Tests ───────────────────────────────────────────────────────

class TestBasis:
    def test_reversal_long_on_deep_backwardation(self):
        """Deeply negative basis (z < -2) → reversal_long True."""
        rng = np.random.default_rng(42)
        df = _ohlcv(300, basis=0.0)
        # 270 bars of normal basis, then 30 bars of extreme backwardation
        df["basis"] = np.concatenate([
            rng.normal(0.1, 0.02, 270),
            np.full(30, -0.5),
        ])
        ind = BasisIndicator()
        sig = ind.compute(df, lookback=50, extreme_z=2.0, mode="reversal_long", hold_bars=3)
        # First extreme bar at 270: lookback window is all normal → z ≈ -30
        assert sig.iloc[270:].sum() > 5

    def test_reversal_short_on_high_premium(self):
        """Very positive basis (z > 2) → reversal_short True."""
        rng = np.random.default_rng(42)
        df = _ohlcv(300, basis=0.0)
        df["basis"] = np.concatenate([
            rng.normal(0.1, 0.02, 270),
            np.full(30, 0.8),
        ])
        ind = BasisIndicator()
        sig = ind.compute(df, lookback=50, extreme_z=2.0, mode="reversal_short", hold_bars=3)
        assert sig.iloc[270:].sum() > 5

    def test_missing_column_returns_false(self):
        df = _ohlcv(100)
        ind = BasisIndicator()
        sig = ind.compute(df)
        assert not sig.any()

    def test_params_schema(self):
        schema = BasisIndicator().params_schema()
        assert "lookback" in schema
        assert "extreme_z" in schema
        assert "mode" in schema
        assert schema["extreme_z"]["type"] == "float"


# ── CrossSectionalMomentum Tests ──────────────────────────────────────

class TestCSMomentum:
    def test_winners_when_rank_high(self):
        df = _ohlcv(200)
        df["cs_momentum_rank"] = 0.8  # Top quintile
        ind = CrossSectionalMomentum()
        sig = ind.compute(df, rank_threshold=0.5, mode="winners")
        assert sig.sum() == 200

    def test_losers_when_rank_low(self):
        df = _ohlcv(200)
        df["cs_momentum_rank"] = 0.1  # Bottom quintile
        ind = CrossSectionalMomentum()
        sig = ind.compute(df, rank_threshold=0.5, mode="losers")
        assert sig.sum() == 200

    def test_no_signal_when_rank_middle(self):
        df = _ohlcv(200)
        df["cs_momentum_rank"] = 0.5
        ind = CrossSectionalMomentum()
        sig_win = ind.compute(df, rank_threshold=0.7, mode="winners")
        sig_los = ind.compute(df, rank_threshold=0.7, mode="losers")
        assert sig_win.sum() == 0
        assert sig_los.sum() == 0

    def test_missing_column_returns_false(self):
        df = _ohlcv(100)
        ind = CrossSectionalMomentum()
        sig = ind.compute(df)
        assert not sig.any()

    def test_params_schema(self):
        schema = CrossSectionalMomentum().params_schema()
        assert "rank_threshold" in schema
        assert "mode" in schema
        assert schema["rank_threshold"]["type"] == "float"


# ── Registry Tests ────────────────────────────────────────────────────

class TestTier1Registry:
    def test_taker_volume_registered(self):
        assert isinstance(get_indicator("taker_volume"), TakerVolumeIndicator)

    def test_basis_registered(self):
        assert isinstance(get_indicator("basis"), BasisIndicator)

    def test_cs_momentum_registered(self):
        assert isinstance(get_indicator("cs_momentum"), CrossSectionalMomentum)


# ── Macro Archetype Factory Tests ─────────────────────────────────────

class TestMacroArchetypeFactory:
    EXPECTED_ARCHETYPES = [
        f"{entry}_macro_{macro}_fullrisk_pyr"
        for entry in ["roc", "macd", "ema", "donchian", "divergence", "ssl"]
        for macro in ["vrp", "yield_curve", "hurst"]
    ]

    def test_18_macro_archetypes_in_config(self):
        """All 18 macro archetypes exist in ARCHETYPE_INDICATORS."""
        for name in self.EXPECTED_ARCHETYPES:
            assert name in ARCHETYPE_INDICATORS, f"Missing archetype: {name}"

    def test_total_count(self):
        assert len(self.EXPECTED_ARCHETYPES) == 18

    def test_archetype_structure_valid(self):
        """Each macro archetype has correct indicator structure."""
        for name in self.EXPECTED_ARCHETYPES:
            cfg = ARCHETYPE_INDICATORS[name]
            assert len(cfg["entry"]) == 2, f"{name}: expected 2 entry indicators"
            assert "ssl_channel" in cfg.get("auxiliary", []), f"{name}: missing ssl_channel auxiliary"
            assert len(cfg.get("exit", [])) >= 1, f"{name}: missing exit indicator"
            assert cfg.get("combination_mode") == "excluyente", f"{name}: wrong combination_mode"

    def test_macro_filter_in_entry(self):
        """Each archetype includes its macro filter in the entry list."""
        for name in self.EXPECTED_ARCHETYPES:
            cfg = ARCHETYPE_INDICATORS[name]
            entries = cfg["entry"]
            has_macro = any(m in entries for m in ["vrp", "yield_curve", "hurst"])
            assert has_macro, f"{name}: no macro filter in entry list"

    def test_archetypes_auto_registered_in_risk(self):
        """Auto-registration picks up all 18 (they end in _fullrisk_pyr)."""
        from suitetrading.risk.archetypes import ARCHETYPE_REGISTRY
        for name in self.EXPECTED_ARCHETYPES:
            assert name in ARCHETYPE_REGISTRY, f"Risk archetype not auto-registered: {name}"
