"""Portfolio weight optimization — Markowitz, Risk Parity, Fractional Kelly, Equal Weight.

Given N strategy return series and a covariance matrix, finds optimal
weight allocation under various objectives and constraints.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.optimize import minimize
from loguru import logger


@dataclass
class PortfolioWeights:
    """Result of portfolio optimization."""

    weights: np.ndarray          # (N,) weight vector
    strategy_ids: list[str]
    method: str
    expected_return: float
    expected_volatility: float
    expected_sharpe: float
    metrics: dict[str, float]    # Additional method-specific metrics


class PortfolioOptimizer:
    """Multi-method portfolio weight optimizer."""

    def __init__(self, risk_free_rate: float = 0.0) -> None:
        self._rf = risk_free_rate

    def optimize(
        self,
        returns: np.ndarray,
        strategy_ids: list[str],
        method: str = "min_variance",
        **kwargs: Any,
    ) -> PortfolioWeights:
        """Dispatch to the selected optimization method."""
        methods = {
            "min_variance": self._min_variance,
            "risk_parity": self._risk_parity,
            "kelly": self._fractional_kelly,
            "equal": self._equal_weight,
        }
        if method not in methods:
            raise ValueError(f"Unknown method: {method!r}")
        return methods[method](returns, strategy_ids, **kwargs)

    def _min_variance(self, returns: np.ndarray, ids: list[str], **kw: Any) -> PortfolioWeights:
        """Markowitz minimum variance with long-only constraint."""
        n = returns.shape[1]
        cov = np.cov(returns, rowvar=False, ddof=1)

        # Regularize covariance to ensure positive-definite
        cov += np.eye(n) * 1e-8

        def objective(w: np.ndarray) -> float:
            return float(w @ cov @ w)

        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        bounds = [(0.0, 1.0)] * n
        x0 = np.ones(n) / n

        result = minimize(
            objective,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-12},
        )

        if not result.success:
            logger.warning("Min-variance optimization did not converge: {}", result.message)

        weights = result.x
        weights = np.clip(weights, 0.0, None)
        weights /= weights.sum()

        port_stats = self._portfolio_stats(returns, weights)
        logger.debug(
            "Min-variance: vol={:.6f}, sharpe={:.4f}",
            port_stats["expected_volatility"], port_stats["expected_sharpe"],
        )

        return PortfolioWeights(
            weights=weights,
            strategy_ids=ids,
            method="min_variance",
            expected_return=port_stats["expected_return"],
            expected_volatility=port_stats["expected_volatility"],
            expected_sharpe=port_stats["expected_sharpe"],
            metrics={"converged": float(result.success), "iterations": float(result.nit)},
        )

    def _risk_parity(self, returns: np.ndarray, ids: list[str], **kw: Any) -> PortfolioWeights:
        """Equal Risk Contribution (risk parity).

        Each strategy contributes equally to total portfolio risk.
        Risk contribution of asset i: RC_i = w_i * (cov @ w)_i / (w^T @ cov @ w)
        Target: all RC_i equal to 1/N.
        """
        n = returns.shape[1]
        cov = np.cov(returns, rowvar=False, ddof=1)
        cov += np.eye(n) * 1e-8

        target_risk = 1.0 / n

        def risk_contribution(w: np.ndarray) -> np.ndarray:
            port_var = w @ cov @ w
            if port_var < 1e-16:
                return np.ones(n) / n
            marginal = cov @ w
            rc = w * marginal / port_var
            return rc

        def objective(w: np.ndarray) -> float:
            rc = risk_contribution(w)
            return float(np.sum((rc - target_risk) ** 2))

        constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}]
        bounds = [(1e-6, 1.0)] * n
        x0 = np.ones(n) / n

        result = minimize(
            objective,
            x0,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options={"maxiter": 1000, "ftol": 1e-14},
        )

        if not result.success:
            logger.warning("Risk-parity optimization did not converge: {}", result.message)

        weights = result.x
        weights = np.clip(weights, 0.0, None)
        weights /= weights.sum()

        port_stats = self._portfolio_stats(returns, weights)
        rc_final = risk_contribution(weights)
        rc_spread = float(np.max(rc_final) - np.min(rc_final))

        logger.debug(
            "Risk-parity: vol={:.6f}, sharpe={:.4f}, rc_spread={:.6f}",
            port_stats["expected_volatility"], port_stats["expected_sharpe"], rc_spread,
        )

        return PortfolioWeights(
            weights=weights,
            strategy_ids=ids,
            method="risk_parity",
            expected_return=port_stats["expected_return"],
            expected_volatility=port_stats["expected_volatility"],
            expected_sharpe=port_stats["expected_sharpe"],
            metrics={
                "converged": float(result.success),
                "rc_spread": rc_spread,
                "rc_max": float(np.max(rc_final)),
                "rc_min": float(np.min(rc_final)),
            },
        )

    def _fractional_kelly(
        self,
        returns: np.ndarray,
        ids: list[str],
        kelly_fraction: float = 0.5,
        max_weight: float = 0.25,
        **kw: Any,
    ) -> PortfolioWeights:
        """Fractional Kelly criterion.

        Kelly optimal: w* = cov_inv @ mu
        Fractional: w = kelly_fraction * w*
        Clip to [0, max_weight] and renormalize.
        """
        n = returns.shape[1]
        mu = np.mean(returns, axis=0)
        cov = np.cov(returns, rowvar=False, ddof=1)
        cov += np.eye(n) * 1e-8

        try:
            cov_inv = np.linalg.inv(cov)
        except np.linalg.LinAlgError:
            logger.warning("Singular covariance, falling back to pseudo-inverse")
            cov_inv = np.linalg.pinv(cov)

        # Full Kelly weights
        kelly_weights = cov_inv @ mu

        # Apply fractional scaling
        weights = kelly_fraction * kelly_weights

        # Long-only: clip negatives
        weights = np.clip(weights, 0.0, max_weight)

        # Renormalize to sum to 1
        w_sum = weights.sum()
        if w_sum < 1e-12:
            logger.warning("All Kelly weights near zero, falling back to equal weight")
            weights = np.ones(n) / n
        else:
            weights /= w_sum

        port_stats = self._portfolio_stats(returns, weights)

        logger.debug(
            "Fractional Kelly (f={:.2f}): sharpe={:.4f}, max_w={:.4f}",
            kelly_fraction, port_stats["expected_sharpe"], float(np.max(weights)),
        )

        return PortfolioWeights(
            weights=weights,
            strategy_ids=ids,
            method="kelly",
            expected_return=port_stats["expected_return"],
            expected_volatility=port_stats["expected_volatility"],
            expected_sharpe=port_stats["expected_sharpe"],
            metrics={
                "kelly_fraction": kelly_fraction,
                "max_weight": float(np.max(weights)),
                "n_nonzero": float(np.sum(weights > 1e-6)),
            },
        )

    def _equal_weight(self, returns: np.ndarray, ids: list[str], **kw: Any) -> PortfolioWeights:
        """Naive 1/N equal weight baseline."""
        n = returns.shape[1]
        weights = np.ones(n) / n
        port_stats = self._portfolio_stats(returns, weights)

        logger.debug(
            "Equal weight (N={}): sharpe={:.4f}", n, port_stats["expected_sharpe"],
        )

        return PortfolioWeights(
            weights=weights,
            strategy_ids=ids,
            method="equal",
            expected_return=port_stats["expected_return"],
            expected_volatility=port_stats["expected_volatility"],
            expected_sharpe=port_stats["expected_sharpe"],
            metrics={"n_strategies": float(n)},
        )

    def _portfolio_stats(self, returns: np.ndarray, weights: np.ndarray) -> dict[str, float]:
        """Compute expected return, vol, sharpe for given weights."""
        port_returns = returns @ weights
        exp_ret = float(np.mean(port_returns))
        exp_vol = float(np.std(port_returns, ddof=1))
        sharpe = (exp_ret - self._rf) / exp_vol if exp_vol > 1e-12 else 0.0
        return {
            "expected_return": exp_ret,
            "expected_volatility": exp_vol,
            "expected_sharpe": sharpe,
        }
