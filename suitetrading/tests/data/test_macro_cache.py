"""Tests for macro data cache manager."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from suitetrading.data.macro_cache import MacroCacheManager


# ── Fixtures ──────────────────────────────────────────────────────────

def _sample_series(name: str = "vix", n: int = 100) -> pd.Series:
    idx = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    rng = np.random.default_rng(42)
    return pd.Series(15.0 + rng.normal(0, 2, n), index=idx, name=name)


def _sample_df(n: int = 100) -> pd.DataFrame:
    idx = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    rng = np.random.default_rng(42)
    close = 100 + np.cumsum(rng.normal(0, 0.5, n))
    return pd.DataFrame(
        {"open": close + 0.1, "high": close + 0.5, "low": close - 0.5,
         "close": close, "volume": 1_000_000.0},
        index=idx,
    )


@pytest.fixture
def cache(tmp_path: Path) -> MacroCacheManager:
    return MacroCacheManager(cache_dir=tmp_path / "macro")


# ── Tests ─────────────────────────────────────────────────────────────

class TestPutAndGet:
    def test_roundtrip_series(self, cache: MacroCacheManager):
        original = _sample_series("vix")
        cache.put("vix", original)
        loaded = cache.get("vix", max_age_days=1)
        assert isinstance(loaded, pd.Series)
        assert len(loaded) == len(original)
        assert loaded.name == "vix"
        pd.testing.assert_index_equal(loaded.index, original.index)

    def test_roundtrip_dataframe(self, cache: MacroCacheManager):
        original = _sample_df()
        cache.put("hyg", original)
        loaded = cache.get("hyg", max_age_days=1)
        assert isinstance(loaded, pd.DataFrame)
        assert set(loaded.columns) == {"open", "high", "low", "close", "volume"}

    def test_get_returns_none_when_missing(self, cache: MacroCacheManager):
        assert cache.get("nonexistent") is None

    def test_get_returns_none_when_stale(self, cache: MacroCacheManager):
        cache.put("vix", _sample_series())
        # Backdate the meta timestamp
        meta_path = cache._dir / "_meta.json"
        meta = json.loads(meta_path.read_text())
        meta["vix"] = time.time() - 86400 * 5  # 5 days ago
        meta_path.write_text(json.dumps(meta))

        assert cache.get("vix", max_age_days=1) is None

    def test_get_or_cached_ignores_age(self, cache: MacroCacheManager):
        cache.put("vix", _sample_series())
        meta_path = cache._dir / "_meta.json"
        meta = json.loads(meta_path.read_text())
        meta["vix"] = time.time() - 86400 * 30  # 30 days ago
        meta_path.write_text(json.dumps(meta))

        result = cache.get_or_cached("vix")
        assert result is not None
        assert len(result) == 100


class TestRefresh:
    def test_refresh_skips_fresh(self, cache: MacroCacheManager):
        cache.put("vix", _sample_series())
        mock_dl = MagicMock()
        cache.refresh_fred(mock_dl, keys=["vix"], force=False, max_age_days=1)
        mock_dl.download.assert_not_called()

    def test_refresh_force_updates(self, cache: MacroCacheManager):
        cache.put("vix", _sample_series(n=50))
        mock_dl = MagicMock()
        mock_dl.download.return_value = _sample_series(n=200)
        cache.refresh_fred(mock_dl, keys=["vix"], force=True)
        mock_dl.download.assert_called_once()
        loaded = cache.get("vix", max_age_days=1)
        assert len(loaded) == 200

    def test_fallback_to_cached_on_api_error(self, cache: MacroCacheManager):
        original = _sample_series()
        cache.put("vix", original)
        # Backdate so it's stale
        meta = json.loads((cache._dir / "_meta.json").read_text())
        meta["vix"] = time.time() - 86400 * 5
        (cache._dir / "_meta.json").write_text(json.dumps(meta))

        mock_dl = MagicMock()
        mock_dl.download.side_effect = ConnectionError("API down")
        paths = cache.refresh_fred(mock_dl, keys=["vix"], force=True)
        assert "vix" in paths
        # Cached file should still exist
        assert paths["vix"].exists()


class TestAlignment:
    def test_get_aligned_forward_fills(self, cache: MacroCacheManager):
        daily = _sample_series("vix", n=100)
        cache.put("vix", daily)

        # 4h index — 6 bars per day, should forward-fill daily values
        hourly_idx = pd.date_range("2023-01-02", periods=600, freq="4h", tz="UTC")
        aligned = cache.get_aligned(["vix"], hourly_idx)

        assert len(aligned) == 600
        assert "vix" in aligned.columns
        # Should have no NaN after the first few bars (before first daily value)
        valid = aligned["vix"].dropna()
        assert len(valid) > 500

    def test_get_aligned_missing_key_produces_nan(self, cache: MacroCacheManager):
        idx = pd.date_range("2023-01-01", periods=100, freq="h", tz="UTC")
        aligned = cache.get_aligned(["nonexistent"], idx)
        assert aligned["nonexistent"].isna().all()

    def test_get_aligned_uses_close_for_dataframes(self, cache: MacroCacheManager):
        df = _sample_df(n=100)
        cache.put("hyg", df)

        idx = pd.date_range("2023-01-02", periods=200, freq="4h", tz="UTC")
        aligned = cache.get_aligned(["hyg"], idx)
        assert "hyg" in aligned.columns
        # Values should be from the close column
        assert not aligned["hyg"].isna().all()
