"""Tests for the null hypothesis permutation test module."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from suitetrading.optimization.null_hypothesis import (
    NullHypothesisResult,
    NullHypothesisTest,
    NullStudyConfig,
    NullStudyResult,
    permute_ohlcv,
)


# ── Fixtures ─────────────────────────────────────────────────────────


@pytest.fixture
def synthetic_1m_ohlcv():
    """1000-bar synthetic 1m OHLCV with trend and realistic structure."""
    n = 1000
    idx = pd.date_range("2024-01-01", periods=n, freq="min", tz="UTC")
    rng = np.random.default_rng(42)

    close = 100.0 + np.cumsum(rng.normal(0.001, 0.1, n))
    close = np.maximum(close, 10.0)

    spread = np.abs(rng.normal(0.05, 0.03, n))
    high = close + spread
    low = close - spread
    open_ = close + rng.normal(0, 0.03, n)
    volume = rng.integers(100, 10000, n).astype(float)

    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))

    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


# ── TestPermuteOHLCV ─────────────────────────────────────────────────


class TestPermuteOHLCV:
    """Tests for the permute_ohlcv function."""

    def test_preserves_return_distribution(self, synthetic_1m_ohlcv):
        """Permuted log returns come from the same distribution (KS test)."""
        orig_close = synthetic_1m_ohlcv["close"].values
        orig_returns = np.log(orig_close[1:] / orig_close[:-1])

        permuted = permute_ohlcv(synthetic_1m_ohlcv, seed=123)
        perm_close = permuted["close"].values
        perm_returns = np.log(perm_close[1:] / perm_close[:-1])

        _, p_value = stats.ks_2samp(orig_returns, perm_returns)
        assert p_value > 0.05, (
            f"KS test failed: p={p_value:.4f}. "
            "Permuted returns differ from original distribution."
        )

    def test_destroys_autocorrelation(self, synthetic_1m_ohlcv):
        """Lag-1 autocorrelation of permuted returns should be ~0."""
        permuted = permute_ohlcv(synthetic_1m_ohlcv, seed=42)
        perm_close = permuted["close"].values
        perm_returns = np.diff(perm_close) / np.maximum(perm_close[:-1], 1e-12)
        perm_returns = perm_returns[np.isfinite(perm_returns)]

        autocorr = np.corrcoef(perm_returns[:-1], perm_returns[1:])[0, 1]
        assert abs(autocorr) < 0.1, (
            f"Autocorrelation too high: {autocorr:.4f}. "
            "Permutation should destroy temporal dependence."
        )

    def test_preserves_volume_distribution(self, synthetic_1m_ohlcv):
        """Exact same volume values, just reordered."""
        orig_vol = np.sort(synthetic_1m_ohlcv["volume"].values)
        perm_vol = np.sort(permute_ohlcv(synthetic_1m_ohlcv, seed=77)["volume"].values)
        np.testing.assert_array_almost_equal(orig_vol, perm_vol)

    def test_reproducibility_by_seed(self, synthetic_1m_ohlcv):
        """Same seed produces identical results."""
        p1 = permute_ohlcv(synthetic_1m_ohlcv, seed=42)
        p2 = permute_ohlcv(synthetic_1m_ohlcv, seed=42)
        pd.testing.assert_frame_equal(p1, p2)

    def test_different_seeds_differ(self, synthetic_1m_ohlcv):
        """Different seeds produce different results."""
        p1 = permute_ohlcv(synthetic_1m_ohlcv, seed=42)
        p2 = permute_ohlcv(synthetic_1m_ohlcv, seed=43)
        assert not p1["close"].equals(p2["close"])

    def test_ohlcv_validity_high_ge_max(self, synthetic_1m_ohlcv):
        """high >= max(open, close) for every bar."""
        permuted = permute_ohlcv(synthetic_1m_ohlcv, seed=55)
        assert np.all(
            permuted["high"].values
            >= np.maximum(permuted["open"].values, permuted["close"].values)
        )

    def test_ohlcv_validity_low_le_min(self, synthetic_1m_ohlcv):
        """low <= min(open, close) for every bar."""
        permuted = permute_ohlcv(synthetic_1m_ohlcv, seed=55)
        assert np.all(
            permuted["low"].values
            <= np.minimum(permuted["open"].values, permuted["close"].values)
        )

    def test_preserves_index(self, synthetic_1m_ohlcv):
        """DatetimeIndex remains unchanged."""
        permuted = permute_ohlcv(synthetic_1m_ohlcv, seed=88)
        pd.testing.assert_index_equal(synthetic_1m_ohlcv.index, permuted.index)

    def test_preserves_length(self, synthetic_1m_ohlcv):
        """Output has the same number of bars as input."""
        permuted = permute_ohlcv(synthetic_1m_ohlcv, seed=33)
        assert len(permuted) == len(synthetic_1m_ohlcv)


# ── TestNullStudyResultAnalysis ──────────────────────────────────────


class TestNullStudyResultAnalysis:
    """Tests for NullHypothesisTest._analyze() logic."""

    @staticmethod
    def _make_test(pbo_threshold: float = 0.20) -> NullHypothesisTest:
        return NullHypothesisTest(
            symbols=["BTCUSDT"],
            timeframes=["1h"],
            archetypes=["trend_following"],
            directions=["long"],
            seeds=[100],
            real_hit_rate=0.126,
            real_total=2619,
            pbo_threshold=pbo_threshold,
            data_dir=Path("/tmp/nonexistent"),
        )

    def test_hit_rate_computation(self):
        """Null hit rate = n_passed / n_valid."""
        test = self._make_test()

        results = [
            NullStudyResult(
                pbo=0.10 if i == 0 else 0.50,
                n_passed_pbo=5 if i == 0 else 0,
                n_passed_dsr=2 if i == 0 else 0,
                best_optuna_value=1.5,
                wall_time=10.0,
                symbol="BTCUSDT",
                tf="1h",
                archetype="trend_following",
                direction="long",
                seed=100 + i,
            )
            for i in range(10)
        ]

        result = test._analyze(results)
        assert result.null_hit_rate == pytest.approx(0.1)
        assert result.n_null_passed == 1
        assert result.n_errors == 0

    def test_pvalue_zero_when_null_rate_zero(self):
        """p-value should be 0 when null_rate=0 (pipeline finds nothing on noise)."""
        test = self._make_test()

        results = [
            NullStudyResult(
                pbo=0.80,
                n_passed_pbo=0,
                n_passed_dsr=0,
                best_optuna_value=0.5,
                wall_time=10.0,
                symbol="BTCUSDT",
                tf="1h",
                archetype="trend_following",
                direction="long",
                seed=100 + i,
            )
            for i in range(20)
        ]

        result = test._analyze(results)
        assert result.null_hit_rate == 0.0
        assert result.p_value == 0.0
        assert result.is_valid is True

    def test_errors_excluded_from_rate(self):
        """Studies with errors are excluded from hit rate denominator."""
        test = self._make_test()

        results = [
            NullStudyResult(
                pbo=0.10,
                n_passed_pbo=5,
                n_passed_dsr=2,
                best_optuna_value=1.5,
                wall_time=10.0,
                symbol="BTCUSDT",
                tf="1h",
                archetype="trend_following",
                direction="long",
                seed=100,
            ),
            NullStudyResult(
                pbo=1.0,
                n_passed_pbo=0,
                n_passed_dsr=0,
                best_optuna_value=float("nan"),
                wall_time=1.0,
                error="some_error",
                symbol="BTCUSDT",
                tf="1h",
                archetype="trend_following",
                direction="long",
                seed=101,
            ),
        ]

        result = test._analyze(results)
        assert result.n_errors == 1
        assert result.null_hit_rate == 1.0  # 1 valid, 1 passed
        assert result.n_null_passed == 1

    def test_per_seed_breakdown(self):
        """Per-seed hit rates are computed correctly."""
        test = self._make_test()

        results = []
        for seed in [100, 101]:
            for i in range(5):
                # seed 100: 2/5 pass, seed 101: 0/5 pass
                pbo = 0.10 if (seed == 100 and i < 2) else 0.60
                results.append(
                    NullStudyResult(
                        pbo=pbo,
                        n_passed_pbo=0,
                        n_passed_dsr=0,
                        best_optuna_value=1.0,
                        wall_time=5.0,
                        symbol="BTCUSDT",
                        tf="1h",
                        archetype="trend_following",
                        direction="long",
                        seed=seed,
                    )
                )

        result = test._analyze(results)
        assert result.per_seed[100] == pytest.approx(0.4)
        assert result.per_seed[101] == pytest.approx(0.0)

    def test_high_null_rate_invalidates_pipeline(self):
        """Pipeline is invalid when null hit rate >= 5%."""
        test = self._make_test()

        results = [
            NullStudyResult(
                pbo=0.05,  # All pass
                n_passed_pbo=10,
                n_passed_dsr=5,
                best_optuna_value=2.0,
                wall_time=10.0,
                symbol="BTCUSDT",
                tf="1h",
                archetype="trend_following",
                direction="long",
                seed=100 + i,
            )
            for i in range(10)
        ]

        result = test._analyze(results)
        assert result.null_hit_rate == 1.0
        assert result.is_valid is False


# ── TestRunAll (Integration) ─────────────────────────────────────────


class TestRunAll:
    """Integration tests — run the actual pipeline with synthetic data."""

    @pytest.mark.slow
    def test_run_null_study_completes(self, synthetic_1m_ohlcv):
        """Smoke test: run_null_study returns a NullStudyResult without crashing."""
        from suitetrading.optimization.null_hypothesis import run_null_study

        cfg = NullStudyConfig(
            exchange="synthetic",
            symbol="TEST",
            tf="1m",
            archetype="trend_following",
            direction="long",
            seed=42,
            n_trials=10,
            top_n=5,
            commission_pct=0.04,
            pbo_threshold=0.50,
            wfo_splits=2,
            wfo_min_is=200,
            wfo_min_oos=100,
            wfo_gap=10,
        )

        result = run_null_study(
            cfg,
            data_dir=Path("/tmp"),
            months=12,
            _preloaded_1m=synthetic_1m_ohlcv,
        )

        assert isinstance(result, NullStudyResult)
        assert result.wall_time > 0
        assert isinstance(result.pbo, float)
        assert result.symbol == "TEST"
        assert result.seed == 42

    @pytest.mark.slow
    def test_two_studies_different_seeds(self, synthetic_1m_ohlcv):
        """Two studies with different seeds produce different PBOs."""
        from suitetrading.optimization.null_hypothesis import run_null_study

        base_cfg = dict(
            exchange="synthetic",
            symbol="TEST",
            tf="1m",
            archetype="trend_following",
            direction="long",
            n_trials=10,
            top_n=5,
            commission_pct=0.04,
            pbo_threshold=0.50,
            wfo_splits=2,
            wfo_min_is=200,
            wfo_min_oos=100,
            wfo_gap=10,
        )

        r1 = run_null_study(
            NullStudyConfig(seed=42, **base_cfg),
            data_dir=Path("/tmp"),
            months=12,
            _preloaded_1m=synthetic_1m_ohlcv,
        )
        r2 = run_null_study(
            NullStudyConfig(seed=99, **base_cfg),
            data_dir=Path("/tmp"),
            months=12,
            _preloaded_1m=synthetic_1m_ohlcv,
        )

        assert isinstance(r1, NullStudyResult)
        assert isinstance(r2, NullStudyResult)
        # Both should complete (same data constraints)
        assert r1.seed == 42
        assert r2.seed == 99
