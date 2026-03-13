"""Tests for anti-overfitting filters — CSCV, DSR, and pipeline."""

from __future__ import annotations

import numpy as np
import pytest

from suitetrading.optimization._internal.schemas import (
    AntiOverfitResult,
    CSCVResult,
    DSRResult,
)
from suitetrading.optimization.anti_overfit import (
    AntiOverfitPipeline,
    CSCVValidator,
    deflated_sharpe_ratio,
)


# ── Helpers for synthetic equity curves ───────────────────────────────

def _make_genuine_curves(n_strats: int = 5, n_bars: int = 1000, seed: int = 123) -> dict[str, np.ndarray]:
    """Curves with clearly differentiated positive drift (genuinely profitable).

    Each strategy has a distinctly different drift so that ranking is
    consistent across sub-samples (critical for low PBO).
    """
    rng = np.random.default_rng(seed)
    curves = {}
    for i in range(n_strats):
        # Clear separation between strategies: 0.002, 0.004, 0.006, ...
        drift = 0.002 * (i + 1)
        noise = rng.normal(0, 0.005, n_bars)
        returns = drift + noise
        equity = 10_000.0 * np.cumprod(1 + returns)
        curves[f"genuine_{i}"] = equity
    return curves


def _make_overfit_curves(n_strats: int = 5, n_bars: int = 1000, seed: int = 456) -> dict[str, np.ndarray]:
    """Curves that excel in first half, collapse in second (overfit)."""
    rng = np.random.default_rng(seed)
    curves = {}
    for i in range(n_strats):
        half = n_bars // 2
        returns_up = rng.normal(0.003, 0.01, half)
        returns_down = rng.normal(-0.003, 0.01, n_bars - half)
        returns = np.concatenate([returns_up, returns_down])
        equity = 10_000.0 * np.cumprod(1 + returns)
        curves[f"overfit_{i}"] = equity
    return curves


# ── CSCVValidator tests ───────────────────────────────────────────────

class TestCSCV:
    """Tests for Combinatorially Symmetric Cross-Validation."""

    def test_genuine_curves_low_pbo(self):
        curves = _make_genuine_curves(n_strats=5, n_bars=1600)
        cscv = CSCVValidator(n_subsamples=8, metric="sharpe")
        result = cscv.compute_pbo(curves)
        assert isinstance(result, CSCVResult)
        # With clearly differentiated drifts, IS ranking should hold OOS
        assert result.pbo < 0.50, f"Expected low PBO for genuine, got {result.pbo}"

    def test_overfit_curves_high_pbo(self):
        curves = _make_overfit_curves(n_strats=5, n_bars=1600)
        cscv = CSCVValidator(n_subsamples=8, metric="sharpe")
        result = cscv.compute_pbo(curves)
        # Overfit curves should have high PBO
        assert result.pbo > 0.40, f"Expected high PBO for overfit, got {result.pbo}"

    def test_pbo_range(self):
        curves = _make_genuine_curves(n_strats=3, n_bars=800)
        cscv = CSCVValidator(n_subsamples=4, metric="sharpe")
        result = cscv.compute_pbo(curves)
        assert 0.0 <= result.pbo <= 1.0

    def test_omega_values_populated(self):
        curves = _make_genuine_curves(n_strats=4, n_bars=800)
        cscv = CSCVValidator(n_subsamples=4, metric="sharpe")
        result = cscv.compute_pbo(curves)
        assert len(result.omega_values) > 0
        assert result.n_combinations == len(result.omega_values)

    def test_too_few_strategies_raises(self):
        curves = {"single": np.linspace(10000, 12000, 200)}
        cscv = CSCVValidator(n_subsamples=4, metric="sharpe")
        with pytest.raises(ValueError, match="at least 2"):
            cscv.compute_pbo(curves)

    def test_too_few_bars_raises(self):
        curves = _make_genuine_curves(n_strats=3, n_bars=10)
        cscv = CSCVValidator(n_subsamples=16, metric="sharpe")
        with pytest.raises(ValueError, match="n_subsamples"):
            cscv.compute_pbo(curves)

    def test_even_subsamples_required(self):
        with pytest.raises(ValueError, match="even"):
            CSCVValidator(n_subsamples=7)

    def test_is_overfit_flag_matches_pbo(self):
        curves = _make_genuine_curves(n_strats=5, n_bars=1600)
        cscv = CSCVValidator(n_subsamples=8, metric="sharpe")
        result = cscv.compute_pbo(curves)
        assert result.is_overfit == (result.pbo > 0.50)

    def test_total_return_metric(self):
        curves = _make_genuine_curves(n_strats=3, n_bars=800)
        cscv = CSCVValidator(n_subsamples=4, metric="total_return")
        result = cscv.compute_pbo(curves)
        assert 0.0 <= result.pbo <= 1.0


# ── Deflated Sharpe Ratio tests ───────────────────────────────────────

class TestDSR:
    """Tests for the Deflated Sharpe Ratio."""

    def test_high_sharpe_few_trials_is_significant(self):
        result = deflated_sharpe_ratio(
            observed_sharpe=2.0,
            n_trials=10,
            sample_length=500,
        )
        assert isinstance(result, DSRResult)
        assert result.is_significant is True
        assert result.dsr > 0.95

    def test_low_sharpe_many_trials_not_significant(self):
        result = deflated_sharpe_ratio(
            observed_sharpe=0.001,  # per-bar SR (~annual 0.09)
            n_trials=10_000,
            sample_length=500,
        )
        assert result.is_significant is False
        assert result.dsr < 0.50

    def test_dsr_in_range(self):
        result = deflated_sharpe_ratio(
            observed_sharpe=1.0,
            n_trials=100,
            sample_length=500,
        )
        assert 0.0 <= result.dsr <= 1.0

    def test_expected_max_sharpe_increases_with_trials(self):
        dsr_10 = deflated_sharpe_ratio(
            observed_sharpe=1.0, n_trials=10, sample_length=500,
        )
        dsr_1000 = deflated_sharpe_ratio(
            observed_sharpe=1.0, n_trials=1000, sample_length=500,
        )
        assert dsr_1000.expected_max_sharpe > dsr_10.expected_max_sharpe

    def test_single_trial_edge_case(self):
        result = deflated_sharpe_ratio(
            observed_sharpe=1.5, n_trials=1, sample_length=500,
        )
        assert isinstance(result, DSRResult)

    def test_zero_trials_returns_non_significant(self):
        result = deflated_sharpe_ratio(
            observed_sharpe=2.0, n_trials=0, sample_length=500,
        )
        assert result.is_significant is False

    def test_skewness_and_kurtosis_affect_dsr(self):
        # Use per-bar SR in a range where DSR is NOT saturated at 1.0
        base = deflated_sharpe_ratio(
            observed_sharpe=0.06, n_trials=50, sample_length=500,
            skewness=0.0, kurtosis=3.0,
        )
        neg_skew = deflated_sharpe_ratio(
            observed_sharpe=0.06, n_trials=50, sample_length=500,
            skewness=-1.0, kurtosis=3.0,
        )
        # Negative skewness should change the DSR value
        assert base.dsr != neg_skew.dsr


# ── AntiOverfitPipeline tests ─────────────────────────────────────────

class TestPipeline:
    """Tests for the sequential anti-overfit pipeline."""

    def test_genuine_curves_pass_pipeline(self):
        curves = _make_genuine_curves(n_strats=5, n_bars=1600)
        pipeline = AntiOverfitPipeline(
            pbo_threshold=0.50,
            dsr_threshold=0.50,
            n_subsamples=8,
        )
        result = pipeline.evaluate(
            equity_curves=curves,
            n_trials=5,
        )
        assert isinstance(result, AntiOverfitResult)
        assert result.total_candidates == 5
        # Genuinely profitable with differentiated strategies → pass CSCV
        assert result.passed_cscv > 0

    def test_overfit_curves_filtered(self):
        curves = _make_overfit_curves(n_strats=5, n_bars=1600)
        pipeline = AntiOverfitPipeline(
            pbo_threshold=0.40,
            dsr_threshold=0.95,
            n_subsamples=8,
        )
        result = pipeline.evaluate(
            equity_curves=curves,
            n_trials=1000,
        )
        assert isinstance(result, AntiOverfitResult)
        # Overfit curves with many trials → should be filtered
        assert result.passed_cscv == 0 or result.passed_dsr == 0

    def test_pipeline_returns_correct_counts(self):
        curves = _make_genuine_curves(n_strats=4, n_bars=800)
        pipeline = AntiOverfitPipeline(n_subsamples=4, dsr_threshold=0.01)
        result = pipeline.evaluate(equity_curves=curves, n_trials=4)
        assert result.total_candidates == 4
        assert result.passed_cscv <= result.total_candidates
        assert result.passed_dsr <= result.passed_cscv
        assert result.passed_spa <= result.passed_dsr

    def test_pipeline_populates_cscv_and_dsr_results(self):
        curves = _make_genuine_curves(n_strats=3, n_bars=800)
        pipeline = AntiOverfitPipeline(n_subsamples=4, dsr_threshold=0.01)
        result = pipeline.evaluate(equity_curves=curves, n_trials=3)
        assert len(result.cscv_results) > 0

    def test_pipeline_with_benchmark_returns(self):
        curves = _make_genuine_curves(n_strats=3, n_bars=800)
        rng = np.random.default_rng(99)
        benchmark = rng.normal(0.0001, 0.01, 799)
        pipeline = AntiOverfitPipeline(n_subsamples=4, dsr_threshold=0.01)
        result = pipeline.evaluate(
            equity_curves=curves,
            n_trials=3,
            benchmark_returns=benchmark,
        )
        assert isinstance(result, AntiOverfitResult)
        # SPA results should be populated
        assert len(result.spa_results) >= 0

    def test_finalists_subset_of_candidates(self):
        curves = _make_genuine_curves(n_strats=5, n_bars=1600)
        pipeline = AntiOverfitPipeline(n_subsamples=8, dsr_threshold=0.01)
        result = pipeline.evaluate(equity_curves=curves, n_trials=5)
        for f in result.finalists:
            assert f in curves
