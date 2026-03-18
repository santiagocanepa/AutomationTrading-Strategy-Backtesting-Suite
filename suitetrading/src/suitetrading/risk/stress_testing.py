"""Portfolio stress testing — Monte Carlo, crisis replay, perturbation analysis.

Provides tools to stress-test a portfolio under extreme conditions:
block bootstrap (preserving correlation), synthetic flash crashes,
weight perturbation, and correlation regime shifts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from loguru import logger


@dataclass
class StressTestResult:
    """Aggregated stress test results."""

    monte_carlo: dict[str, float] | None = None
    crisis_replay: dict[str, dict[str, float]] | None = None
    weight_perturbation: dict[str, float] | None = None
    correlation_shift: dict[str, float] | None = None
    overall_pass: bool = False


class PortfolioStressTester:
    """Multi-scenario stress testing for strategy portfolios."""

    def __init__(self, initial_capital: float = 100_000.0) -> None:
        self._capital = initial_capital

    def run_all(
        self,
        returns_matrix: np.ndarray,
        weights: np.ndarray,
        strategy_ids: list[str],
        *,
        n_monte_carlo: int = 10_000,
        block_size: int = 20,
        crisis_periods: dict[str, tuple[int, int]] | None = None,
        seed: int = 42,
    ) -> StressTestResult:
        """Run all stress tests and return aggregated results."""
        logger.info(
            "Running full stress test suite: {} strategies, T={}",
            len(strategy_ids), returns_matrix.shape[0],
        )

        mc = self.monte_carlo_block_bootstrap(
            returns_matrix, weights,
            n_simulations=n_monte_carlo, block_size=block_size, seed=seed,
        )

        cr: dict[str, dict[str, float]] | None = None
        if crisis_periods:
            cr = self.crisis_replay(returns_matrix, weights, crisis_periods)

        wp = self.weight_perturbation(returns_matrix, weights, seed=seed)

        cs = self.correlation_regime_shift(returns_matrix, weights, seed=seed)

        # Overall pass: MC max_dd_p95 < 50%, Sharpe CV < 0.30
        mc_pass = mc.get("max_dd_p95", 100.0) < 50.0
        wp_pass = wp.get("sharpe_cv", 1.0) < 0.30
        overall = mc_pass and wp_pass

        logger.info(
            "Stress test complete: mc_pass={}, wp_pass={}, overall={}",
            mc_pass, wp_pass, overall,
        )

        return StressTestResult(
            monte_carlo=mc,
            crisis_replay=cr,
            weight_perturbation=wp,
            correlation_shift=cs,
            overall_pass=overall,
        )

    def monte_carlo_block_bootstrap(
        self,
        returns_matrix: np.ndarray,
        weights: np.ndarray,
        n_simulations: int = 10_000,
        block_size: int = 20,
        seed: int = 42,
    ) -> dict[str, float]:
        """Block bootstrap Monte Carlo preserving inter-strategy correlation.

        Returns: max_dd_p5, max_dd_p50, max_dd_p95, max_dd_p99,
                 terminal_p5, terminal_p50, terminal_p95, prob_ruin
        """
        rng = np.random.default_rng(seed)
        t, n = returns_matrix.shape
        weights = np.asarray(weights, dtype=np.float64)

        if t < block_size:
            logger.warning("T={} < block_size={}, adjusting block_size", t, block_size)
            block_size = max(1, t // 2)

        n_blocks = (t + block_size - 1) // block_size  # ceil division
        max_start = t - block_size  # max valid start index

        max_dds = np.empty(n_simulations, dtype=np.float64)
        terminals = np.empty(n_simulations, dtype=np.float64)

        for sim in range(n_simulations):
            # Sample block start indices
            starts = rng.integers(0, max_start + 1, size=n_blocks)

            # Concatenate blocks (preserving cross-strategy correlation within blocks)
            blocks: list[np.ndarray] = []
            for s in starts:
                blocks.append(returns_matrix[s : s + block_size])
            synth = np.concatenate(blocks, axis=0)[:t]  # trim to original length

            # Portfolio returns for this simulation
            port_ret = synth @ weights

            # Build equity curve
            equity = self._capital * np.cumprod(1.0 + port_ret)

            # Max drawdown
            peak = np.maximum.accumulate(equity)
            dd = (peak - equity) / np.where(peak > 0, peak, 1.0)
            max_dds[sim] = float(np.max(dd)) * 100.0

            # Terminal value ratio
            terminals[sim] = equity[-1] / self._capital

        result = {
            "max_dd_p5": float(np.percentile(max_dds, 5)),
            "max_dd_p50": float(np.percentile(max_dds, 50)),
            "max_dd_p95": float(np.percentile(max_dds, 95)),
            "max_dd_p99": float(np.percentile(max_dds, 99)),
            "terminal_p5": float(np.percentile(terminals, 5)),
            "terminal_p50": float(np.percentile(terminals, 50)),
            "terminal_p95": float(np.percentile(terminals, 95)),
            "prob_ruin": float(np.mean(terminals < 0.5)),
            "n_simulations": float(n_simulations),
        }

        logger.debug(
            "MC block bootstrap: max_dd_p95={:.1f}%, terminal_p50={:.3f}, prob_ruin={:.4f}",
            result["max_dd_p95"], result["terminal_p50"], result["prob_ruin"],
        )
        return result

    def crisis_replay(
        self,
        returns_matrix: np.ndarray,
        weights: np.ndarray,
        crisis_periods: dict[str, tuple[int, int]],
    ) -> dict[str, dict[str, float]]:
        """Replay portfolio through historical crisis periods.

        For each crisis: compute max DD, time to recovery, min equity.
        """
        weights = np.asarray(weights, dtype=np.float64)
        t = returns_matrix.shape[0]
        results: dict[str, dict[str, float]] = {}

        for name, (start, end) in crisis_periods.items():
            if start < 0 or end > t or start >= end:
                logger.warning("Invalid crisis period '{}': ({}, {}), T={}", name, start, end, t)
                continue

            crisis_returns = returns_matrix[start:end]
            port_ret = crisis_returns @ weights

            # Build equity curve through crisis
            equity = self._capital * np.cumprod(1.0 + port_ret)
            equity = np.insert(equity, 0, self._capital)  # prepend initial

            peak = np.maximum.accumulate(equity)
            dd = (peak - equity) / np.where(peak > 0, peak, 1.0)
            max_dd = float(np.max(dd)) * 100.0
            min_equity = float(np.min(equity))

            # Time to recovery: bars from max DD to equity back at pre-crisis level
            max_dd_idx = int(np.argmax(dd))
            recovery_bars = 0
            for j in range(max_dd_idx, len(equity)):
                if equity[j] >= equity[0]:
                    recovery_bars = j - max_dd_idx
                    break
            else:
                recovery_bars = -1  # did not recover within crisis window

            total_return = (equity[-1] / equity[0] - 1.0) * 100.0

            results[name] = {
                "max_drawdown_pct": round(max_dd, 4),
                "min_equity": round(min_equity, 2),
                "total_return_pct": round(total_return, 4),
                "recovery_bars": float(recovery_bars),
                "duration_bars": float(end - start),
            }

            logger.debug(
                "Crisis '{}': max_dd={:.1f}%, return={:.1f}%, recovery={}",
                name, max_dd, total_return, recovery_bars,
            )

        return results

    def weight_perturbation(
        self,
        returns_matrix: np.ndarray,
        weights: np.ndarray,
        perturbation_pct: float = 10.0,
        n_trials: int = 1000,
        seed: int = 42,
    ) -> dict[str, float]:
        """Perturb weights by +/-perturbation_pct and measure Sharpe stability.

        Returns: sharpe_mean, sharpe_std, sharpe_min, sharpe_max, sharpe_cv
        """
        rng = np.random.default_rng(seed)
        weights = np.asarray(weights, dtype=np.float64)
        pct = perturbation_pct / 100.0
        sharpes = np.empty(n_trials, dtype=np.float64)

        for trial in range(n_trials):
            # Perturb each weight by uniform [-pct, +pct] of its value
            noise = rng.uniform(-pct, pct, size=len(weights))
            perturbed = weights * (1.0 + noise)
            perturbed = np.clip(perturbed, 0.0, None)
            w_sum = perturbed.sum()
            if w_sum < 1e-12:
                perturbed = np.ones_like(weights) / len(weights)
            else:
                perturbed /= w_sum

            port_ret = returns_matrix @ perturbed
            mean_r = float(np.mean(port_ret))
            std_r = float(np.std(port_ret, ddof=1))
            sharpes[trial] = mean_r / std_r if std_r > 1e-12 else 0.0

        sharpe_mean = float(np.mean(sharpes))
        sharpe_std = float(np.std(sharpes, ddof=1))
        sharpe_cv = abs(sharpe_std / sharpe_mean) if abs(sharpe_mean) > 1e-12 else float("inf")

        result = {
            "sharpe_mean": round(sharpe_mean, 6),
            "sharpe_std": round(sharpe_std, 6),
            "sharpe_min": round(float(np.min(sharpes)), 6),
            "sharpe_max": round(float(np.max(sharpes)), 6),
            "sharpe_cv": round(sharpe_cv, 6),
            "perturbation_pct": perturbation_pct,
            "n_trials": float(n_trials),
        }

        logger.debug(
            "Weight perturbation: sharpe_mean={:.4f}, cv={:.4f}",
            sharpe_mean, sharpe_cv,
        )
        return result

    def correlation_regime_shift(
        self,
        returns_matrix: np.ndarray,
        weights: np.ndarray,
        target_corr: float = 0.8,
        n_simulations: int = 1000,
        seed: int = 42,
    ) -> dict[str, float]:
        """Simulate correlation increasing to target_corr during stress.

        Uses Cholesky decomposition to generate correlated returns.
        Returns: max_dd_shift, sharpe_shift, dr_shift
        """
        rng = np.random.default_rng(seed)
        t, n_strat = returns_matrix.shape
        weights = np.asarray(weights, dtype=np.float64)

        # Original stats for comparison
        orig_port = returns_matrix @ weights
        orig_sharpe = float(np.mean(orig_port)) / float(np.std(orig_port, ddof=1)) if np.std(orig_port, ddof=1) > 1e-12 else 0.0

        orig_vols = np.std(returns_matrix, axis=0, ddof=1)
        orig_dr_num = float(np.dot(weights, orig_vols))
        orig_dr_den = float(np.std(orig_port, ddof=1))
        orig_dr = orig_dr_num / orig_dr_den if orig_dr_den > 1e-12 else 1.0

        # Build target correlation matrix: all off-diagonal = target_corr
        target_corr_mat = np.full((n_strat, n_strat), target_corr)
        np.fill_diagonal(target_corr_mat, 1.0)

        # Build target covariance: diag(vol) @ corr @ diag(vol)
        means = np.mean(returns_matrix, axis=0)
        vol_diag = np.diag(orig_vols)
        target_cov = vol_diag @ target_corr_mat @ vol_diag

        # Ensure positive-definite
        eigvals = np.linalg.eigvalsh(target_cov)
        if np.min(eigvals) < 0:
            target_cov += np.eye(n_strat) * (abs(np.min(eigvals)) + 1e-8)

        # Cholesky decomposition
        try:
            chol = np.linalg.cholesky(target_cov)
        except np.linalg.LinAlgError:
            logger.warning("Cholesky failed for target correlation, adding regularization")
            target_cov += np.eye(n_strat) * 1e-6
            chol = np.linalg.cholesky(target_cov)

        max_dds = np.empty(n_simulations, dtype=np.float64)
        sharpes = np.empty(n_simulations, dtype=np.float64)
        drs = np.empty(n_simulations, dtype=np.float64)

        for sim in range(n_simulations):
            # Generate correlated returns using Cholesky
            z = rng.standard_normal((t, n_strat))
            shifted_returns = z @ chol.T + means

            port_ret = shifted_returns @ weights

            # Max DD
            equity = np.cumprod(1.0 + port_ret)
            peak = np.maximum.accumulate(equity)
            dd = (peak - equity) / np.where(peak > 0, peak, 1.0)
            max_dds[sim] = float(np.max(dd)) * 100.0

            # Sharpe
            std_r = float(np.std(port_ret, ddof=1))
            sharpes[sim] = float(np.mean(port_ret)) / std_r if std_r > 1e-12 else 0.0

            # DR
            shifted_vols = np.std(shifted_returns, axis=0, ddof=1)
            dr_num = float(np.dot(weights, shifted_vols))
            dr_den = std_r
            drs[sim] = dr_num / dr_den if dr_den > 1e-12 else 1.0

        result = {
            "max_dd_shift_p50": round(float(np.percentile(max_dds, 50)), 4),
            "max_dd_shift_p95": round(float(np.percentile(max_dds, 95)), 4),
            "sharpe_shift_mean": round(float(np.mean(sharpes)), 6),
            "sharpe_shift_vs_orig": round(float(np.mean(sharpes)) - orig_sharpe, 6),
            "dr_shift_mean": round(float(np.mean(drs)), 4),
            "dr_shift_vs_orig": round(float(np.mean(drs)) - orig_dr, 4),
            "target_corr": target_corr,
            "n_simulations": float(n_simulations),
        }

        logger.debug(
            "Correlation shift (target={:.2f}): sharpe_delta={:.4f}, dr_delta={:.4f}",
            target_corr, result["sharpe_shift_vs_orig"], result["dr_shift_vs_orig"],
        )
        return result
