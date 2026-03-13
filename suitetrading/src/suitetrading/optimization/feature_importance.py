"""Feature importance analysis via XGBoost meta-model + SHAP.

Builds a surrogate model from optimisation results (params → metric),
then uses SHAP to identify which parameters drive performance.

Requires ``xgboost>=2.0`` and ``shap>=0.44`` (optional dependencies).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from loguru import logger

try:
    import xgboost as xgb

    HAS_XGB = True
except ImportError:
    HAS_XGB = False

try:
    import shap

    HAS_SHAP = True
except ImportError:
    HAS_SHAP = False


class FeatureImportanceEngine:
    """Meta-model based feature importance for search space reduction.

    Parameters
    ----------
    metric
        Target metric column name (e.g. ``"sharpe"``).
    n_estimators
        Number of XGBoost boosting rounds.
    max_depth
        Maximum tree depth.
    """

    def __init__(
        self,
        *,
        metric: str = "sharpe",
        n_estimators: int = 200,
        max_depth: int = 6,
    ) -> None:
        if not HAS_XGB:
            raise ImportError(
                "xgboost is required for FeatureImportanceEngine. "
                "Install with: pip install xgboost>=2.0"
            )
        self._metric = metric
        self._n_estimators = n_estimators
        self._max_depth = max_depth
        self._model: xgb.XGBRegressor | None = None
        self._shap_values: np.ndarray | None = None
        self._feature_names: list[str] = []

    def fit(
        self,
        results_df: pd.DataFrame,
    ) -> dict[str, float]:
        """Fit the XGBoost meta-model and compute feature importances.

        Parameters
        ----------
        results_df
            DataFrame where columns are parameter names + the target metric.
            The target column must match ``self._metric``.

        Returns
        -------
        Dict mapping feature name → mean absolute SHAP value (if shap
        available) or XGBoost gain importance.
        """
        if self._metric not in results_df.columns:
            raise ValueError(
                f"Metric {self._metric!r} not in columns: "
                f"{list(results_df.columns)}"
            )

        feature_cols = [c for c in results_df.columns if c != self._metric]
        X = results_df[feature_cols].copy()
        y = results_df[self._metric].values

        # Encode categorical columns
        for col in X.select_dtypes(include=["object", "category"]).columns:
            X[col] = X[col].astype("category").cat.codes

        self._feature_names = list(X.columns)

        self._model = xgb.XGBRegressor(
            n_estimators=self._n_estimators,
            max_depth=self._max_depth,
            learning_rate=0.1,
            random_state=42,
            verbosity=0,
        )
        self._model.fit(X.values, y)

        importances = self._compute_importances(X)

        logger.info(
            "Feature importance: {} features, top-3: {}",
            len(importances),
            sorted(importances.items(), key=lambda x: -x[1])[:3],
        )
        return importances

    def _compute_importances(self, X: pd.DataFrame) -> dict[str, float]:
        """Compute importances via SHAP or fallback to XGBoost gain."""
        if HAS_SHAP and self._model is not None:
            explainer = shap.TreeExplainer(self._model)
            sv = explainer.shap_values(X.values)
            self._shap_values = sv
            mean_abs = np.abs(sv).mean(axis=0)
            return {
                name: float(mean_abs[i])
                for i, name in enumerate(self._feature_names)
            }

        # Fallback: XGBoost built-in importance
        if self._model is not None:
            raw = self._model.feature_importances_
            return {
                name: float(raw[i])
                for i, name in enumerate(self._feature_names)
            }
        return {}

    def suggest_space_reduction(
        self,
        importances: dict[str, float],
        threshold: float = 0.01,
    ) -> dict[str, float]:
        """Suggest features to keep (importance > threshold).

        Parameters
        ----------
        importances
            Output of ``fit()``.
        threshold
            Minimum importance to retain a feature.

        Returns
        -------
        Dict of feature_name → importance for features above threshold.
        """
        kept = {k: v for k, v in importances.items() if v > threshold}
        dropped = set(importances.keys()) - set(kept.keys())
        if dropped:
            logger.info(
                "Space reduction: dropping {} features below threshold {}: {}",
                len(dropped), threshold, sorted(dropped),
            )
        return kept

    def get_shap_values(self) -> np.ndarray | None:
        """Return raw SHAP values (None if shap not available or not fitted)."""
        return self._shap_values

    def get_mutual_information(
        self,
        results_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """Compute pairwise mutual information between features.

        Uses sklearn's ``mutual_info_regression`` to measure non-linear
        dependency between each feature pair.
        """
        from sklearn.feature_selection import mutual_info_regression

        feature_cols = [c for c in results_df.columns if c != self._metric]
        X = results_df[feature_cols].copy()

        # Encode categoricals
        for col in X.select_dtypes(include=["object", "category"]).columns:
            X[col] = X[col].astype("category").cat.codes

        n_features = len(feature_cols)
        mi_matrix = np.zeros((n_features, n_features))

        for i in range(n_features):
            mi = mutual_info_regression(
                X.values, X.iloc[:, i].values, random_state=42,
            )
            mi_matrix[i, :] = mi

        return pd.DataFrame(
            mi_matrix, index=feature_cols, columns=feature_cols,
        )
