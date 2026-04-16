"""Optimization & anti-overfitting module for SuiteTrading.

Public API
----------
Core (always available):

- ``OptunaOptimizer`` — Bayesian optimisation via Optuna.
- ``WalkForwardEngine`` — Walk-Forward Optimization (rolling / anchored).
- ``CSCVValidator`` — Combinatorially Symmetric Cross-Validation.
- ``deflated_sharpe_ratio`` — Deflated Sharpe Ratio test.
- ``AntiOverfitPipeline`` — Sequential CSCV → DSR → SPA filter.
- ``ParallelExecutor`` — Multiprocessing backtest execution.
- ``RollingPortfolioEvaluator`` — Rolling portfolio validation across windows.

Conditional (require optional dependencies):

- ``DEAPOptimizer`` — NSGA-II multi-objective via DEAP.
- ``FeatureImportanceEngine`` — XGBoost + SHAP search-space analysis.

Schemas:

- ``ObjectiveResult``, ``OptimizationResult``, ``WFOConfig``, ``WFOResult``,
  ``CSCVResult``, ``DSRResult``, ``SPAResult``, ``AntiOverfitResult``,
  ``StrategyReport``, ``PipelineResult``.
"""

from suitetrading.optimization._internal.schemas import (
    AntiOverfitResult,
    CSCVResult,
    DSRResult,
    ObjectiveResult,
    OptimizationResult,
    PipelineResult,
    SPAResult,
    StrategyReport,
    WFOConfig,
    WFOResult,
)
from suitetrading.optimization.anti_overfit import (
    AntiOverfitPipeline,
    CSCVValidator,
    deflated_sharpe_ratio,
)
from suitetrading.optimization.null_hypothesis import (
    NullHypothesisResult,
    NullHypothesisTest,
    permute_ohlcv,
)
from suitetrading.optimization.optuna_optimizer import OptunaOptimizer
from suitetrading.optimization.rolling_validation import (
    RollingPortfolioEvaluator,
    RollingValidationResult,
)
from suitetrading.optimization.parallel import ParallelExecutor
from suitetrading.optimization.walk_forward import WalkForwardEngine

# ── Conditional imports ───────────────────────────────────────────────

try:
    from suitetrading.optimization.deap_optimizer import DEAPOptimizer
except ImportError:
    DEAPOptimizer = None  # type: ignore[assignment,misc]

try:
    from suitetrading.optimization.feature_importance import FeatureImportanceEngine
except ImportError:
    FeatureImportanceEngine = None  # type: ignore[assignment,misc]


__all__ = [
    # Core
    "OptunaOptimizer",
    "WalkForwardEngine",
    "CSCVValidator",
    "deflated_sharpe_ratio",
    "AntiOverfitPipeline",
    "ParallelExecutor",
    # Null hypothesis
    "NullHypothesisTest",
    "NullHypothesisResult",
    "permute_ohlcv",
    # Conditional
    "DEAPOptimizer",
    "FeatureImportanceEngine",
    # Rolling validation
    "RollingPortfolioEvaluator",
    "RollingValidationResult",
    # Schemas
    "ObjectiveResult",
    "OptimizationResult",
    "WFOConfig",
    "WFOResult",
    "CSCVResult",
    "DSRResult",
    "SPAResult",
    "AntiOverfitResult",
    "StrategyReport",
    "PipelineResult",
]
