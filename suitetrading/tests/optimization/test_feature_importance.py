"""Tests for FeatureImportanceEngine (XGBoost + SHAP)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

try:
    import xgboost  # noqa: F401
    HAS_XGB = True
except ImportError:
    HAS_XGB = False

pytestmark = pytest.mark.skipif(not HAS_XGB, reason="xgboost not installed")


from suitetrading.optimization.feature_importance import FeatureImportanceEngine


# ── Synthetic results DataFrame ───────────────────────────────────────

@pytest.fixture
def results_df():
    """DataFrame where 'important_param' clearly drives 'sharpe'."""
    rng = np.random.default_rng(42)
    n = 200
    important = rng.uniform(1, 50, n)
    noise1 = rng.uniform(0, 10, n)
    noise2 = rng.uniform(0, 1, n)
    # sharpe = f(important) + small noise
    sharpe = 0.1 * important + rng.normal(0, 0.5, n)
    return pd.DataFrame({
        "important_param": important,
        "noise_param1": noise1,
        "noise_param2": noise2,
        "sharpe": sharpe,
    })


# ── Tests ─────────────────────────────────────────────────────────────

class TestFeatureImportanceFit:
    """Test model fitting and importance computation."""

    def test_fit_returns_importances(self, results_df):
        engine = FeatureImportanceEngine(metric="sharpe", n_estimators=50)
        importances = engine.fit(results_df)
        assert isinstance(importances, dict)
        assert "important_param" in importances
        assert "noise_param1" in importances
        assert "noise_param2" in importances

    def test_important_param_ranks_highest(self, results_df):
        engine = FeatureImportanceEngine(metric="sharpe", n_estimators=100)
        importances = engine.fit(results_df)
        # important_param should have the highest importance
        sorted_imp = sorted(importances.items(), key=lambda x: -x[1])
        assert sorted_imp[0][0] == "important_param"

    def test_missing_metric_raises(self, results_df):
        engine = FeatureImportanceEngine(metric="nonexistent")
        with pytest.raises(ValueError, match="nonexistent"):
            engine.fit(results_df)

    def test_importances_are_non_negative(self, results_df):
        engine = FeatureImportanceEngine(metric="sharpe", n_estimators=50)
        importances = engine.fit(results_df)
        for v in importances.values():
            assert v >= 0.0


class TestSpaceReduction:
    """Test search space reduction suggestions."""

    def test_suggest_keeps_important(self, results_df):
        engine = FeatureImportanceEngine(metric="sharpe", n_estimators=100)
        importances = engine.fit(results_df)
        kept = engine.suggest_space_reduction(importances, threshold=0.01)
        assert "important_param" in kept

    def test_high_threshold_drops_noise(self, results_df):
        engine = FeatureImportanceEngine(metric="sharpe", n_estimators=100)
        importances = engine.fit(results_df)
        # Very high threshold should drop noise params
        max_imp = max(importances.values())
        kept = engine.suggest_space_reduction(importances, threshold=max_imp * 0.5)
        assert len(kept) < len(importances)


class TestSHAPValues:
    """Test SHAP integration (if shap is available)."""

    def test_shap_values_populated(self, results_df):
        engine = FeatureImportanceEngine(metric="sharpe", n_estimators=50)
        engine.fit(results_df)
        sv = engine.get_shap_values()
        # May be None if shap not installed
        try:
            import shap  # noqa: F401
            assert sv is not None
            assert sv.shape[1] == 3  # 3 features
        except ImportError:
            assert sv is None


class TestMutualInformation:
    """Test mutual information computation."""

    def test_mi_matrix_shape(self, results_df):
        engine = FeatureImportanceEngine(metric="sharpe")
        mi = engine.get_mutual_information(results_df)
        assert isinstance(mi, pd.DataFrame)
        n_features = len(results_df.columns) - 1  # minus metric
        assert mi.shape == (n_features, n_features)

    def test_mi_diagonal_positive(self, results_df):
        engine = FeatureImportanceEngine(metric="sharpe")
        mi = engine.get_mutual_information(results_df)
        for col in mi.columns:
            assert mi.loc[col, col] > 0
