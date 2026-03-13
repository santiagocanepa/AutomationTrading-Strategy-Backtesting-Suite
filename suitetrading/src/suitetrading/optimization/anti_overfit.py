"""Anti-overfitting filters — CSCV, Deflated Sharpe Ratio, and pipeline.

Implements the statistical tests that separate genuinely profitable
strategies from artifacts of in-sample optimisation.

References
----------
- Bailey, D. H. et al. (2014). *The Deflated Sharpe Ratio*.
- Bailey, D. H. et al. (2017). *The Probability of Backtest Overfitting*.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

import numpy as np
from loguru import logger
from scipy import stats

from suitetrading.optimization._internal.schemas import (
    AntiOverfitResult,
    CSCVResult,
    DSRResult,
    SPAResult,
)


# ── Combinatorially Symmetric Cross-Validation ────────────────────────

class CSCVValidator:
    """Probability of Backtest Overfitting via CSCV.

    Splits the backtest period into *S* equal sub-samples, then for each
    C(S, S/2) combination assigns half to IS and half to OOS.  Measures how
    often the IS-best strategy ranks poorly OOS.

    Parameters
    ----------
    n_subsamples
        Number of temporal sub-samples (must be even, default 16).
    metric
        Performance metric to rank strategies (``"sharpe"``).
    max_combinations
        Cap on the number of combinations to evaluate
        (to keep runtime bounded for large *S*).
    """

    def __init__(
        self,
        *,
        n_subsamples: int = 16,
        metric: str = "sharpe",
        max_combinations: int = 5_000,
    ) -> None:
        if n_subsamples < 2 or n_subsamples % 2 != 0:
            raise ValueError("n_subsamples must be an even integer >= 2")
        self._S = n_subsamples
        self._metric = metric
        self._max_combos = max_combinations

    def compute_pbo(
        self,
        equity_curves: dict[str, np.ndarray],
    ) -> CSCVResult:
        """Compute the Probability of Backtest Overfitting (PBO).

        Parameters
        ----------
        equity_curves
            Mapping ``strategy_id → equity_curve`` (1-D arrays).
            All curves must have the same length.

        Returns
        -------
        CSCVResult
            Contains PBO ∈ [0, 1] and diagnostic information.
        """
        ids = list(equity_curves.keys())
        n_strats = len(ids)
        if n_strats < 2:
            raise ValueError("Need at least 2 strategies for CSCV")

        curves = np.array([equity_curves[k] for k in ids], dtype=np.float64)
        n_bars = curves.shape[1]
        S = self._S

        if n_bars < S:
            raise ValueError(
                f"Equity curves have {n_bars} bars but n_subsamples={S}"
            )

        # Split into S sub-samples and compute returns per sub-sample
        sub_len = n_bars // S
        # sub_metrics[s, k] = metric for strategy k in sub-sample s
        sub_metrics = np.zeros((S, n_strats), dtype=np.float64)
        for s in range(S):
            start = s * sub_len
            end = start + sub_len if s < S - 1 else n_bars
            for k in range(n_strats):
                sub_eq = curves[k, start:end]
                sub_metrics[s, k] = self._compute_metric(sub_eq)

        # Generate C(S, S/2) combinations
        half = S // 2
        all_combos = list(itertools.combinations(range(S), half))

        # Cap combinations to limit runtime
        if len(all_combos) > self._max_combos:
            rng = np.random.default_rng(0)
            indices = rng.choice(len(all_combos), self._max_combos, replace=False)
            all_combos = [all_combos[i] for i in sorted(indices)]

        n_combos = len(all_combos)
        omega_values = np.zeros(n_combos, dtype=np.float64)

        for ci, is_subs in enumerate(all_combos):
            oos_subs = tuple(s for s in range(S) if s not in is_subs)

            # Aggregate metrics per strategy
            is_score = sub_metrics[list(is_subs), :].mean(axis=0)
            oos_score = sub_metrics[list(oos_subs), :].mean(axis=0)

            # Best strategy in IS
            best_is_idx = int(np.argmax(is_score))

            # Rank of that strategy in OOS (0 = worst, n_strats-1 = best)
            oos_ranks = np.argsort(np.argsort(oos_score)).astype(np.float64)
            relative_rank = oos_ranks[best_is_idx] / (n_strats - 1)

            # ω = logit(relative_rank), clamp to avoid ±inf
            clamped = np.clip(relative_rank, 0.01, 0.99)
            omega_values[ci] = np.log(clamped / (1.0 - clamped))

        pbo = float(np.mean(omega_values <= 0.0))

        logger.info(
            "CSCV: PBO={:.3f} (S={}, combos={}, strategies={})",
            pbo, S, n_combos, n_strats,
        )

        return CSCVResult(
            pbo=pbo,
            n_subsamples=S,
            n_combinations=n_combos,
            omega_values=omega_values,
            is_overfit=pbo > 0.50,
            details={"strategy_ids": ids, "sub_sample_length": sub_len},
        )

    def _compute_metric(self, equity: np.ndarray) -> float:
        """Compute the target metric from an equity segment."""
        if len(equity) < 2:
            return 0.0
        returns = np.diff(equity) / equity[:-1]
        returns = returns[np.isfinite(returns)]
        if len(returns) == 0:
            return 0.0
        if self._metric == "sharpe":
            std = np.std(returns, ddof=1)
            return float(np.mean(returns) / std) if std > 1e-12 else 0.0
        if self._metric == "total_return":
            return float(equity[-1] / equity[0] - 1.0) if equity[0] > 0 else 0.0
        if self._metric == "sortino":
            downside = returns[returns < 0]
            ds_std = np.std(downside, ddof=1) if len(downside) > 1 else 1e-12
            return float(np.mean(returns) / ds_std) if ds_std > 1e-12 else 0.0
        raise ValueError(f"Unsupported metric: {self._metric!r}")


# ── Deflated Sharpe Ratio ─────────────────────────────────────────────

def deflated_sharpe_ratio(
    *,
    observed_sharpe: float,
    n_trials: int,
    sample_length: int,
    sharpe_std: float | None = None,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> DSRResult:
    """Compute the Deflated Sharpe Ratio (DSR).

    Adjusts the observed Sharpe ratio for the number of trials
    (selection bias) via Bailey & López de Prado (2014).

    Parameters
    ----------
    observed_sharpe
        The best observed **per-bar** Sharpe ratio (mean/std of returns).
    n_trials
        How many strategy configurations were tested.
    sample_length
        Number of return observations (bars).
    sharpe_std
        Std dev of per-bar Sharpe ratios across trials.  When *None*
        (default), uses the theoretical null ``1 / sqrt(sample_length)``
        which is the sampling distribution of SR under H₀: SR = 0.
    skewness
        Skewness of the returns distribution.
    kurtosis
        Kurtosis of the returns distribution (excess = kurtosis - 3).
    """
    if n_trials <= 1:
        return DSRResult(
            dsr=0.0,
            expected_max_sharpe=0.0,
            observed_sharpe=observed_sharpe,
            is_significant=False,
        )

    if sharpe_std is None:
        sharpe_std = 1.0 / math.sqrt(max(sample_length, 1))

    # Expected maximum Sharpe under null = Euler-Mascheroni correction
    euler_mascheroni = 0.5772156649
    e_max_sr = sharpe_std * (
        (1 - euler_mascheroni) * stats.norm.ppf(1 - 1.0 / n_trials)
        + euler_mascheroni * stats.norm.ppf(1 - 1.0 / (n_trials * math.e))
    )

    # SR* adjusted for non-normality (Bailey & López de Prado, eq. 5)
    sr_adj = observed_sharpe * math.sqrt(sample_length - 1)
    excess_kurt = kurtosis - 3.0
    denom_inner = (
        1.0
        - skewness * observed_sharpe
        + (excess_kurt / 4.0) * observed_sharpe ** 2
    )
    if denom_inner < 1e-12:
        logger.warning(
            "DSR denom_inner={:.6f} < 0 (skew={:.3f}, kurt={:.3f}, SR={:.6f})",
            denom_inner, skewness, kurtosis, observed_sharpe,
        )
        return DSRResult(
            dsr=0.0,
            expected_max_sharpe=float(e_max_sr),
            observed_sharpe=observed_sharpe,
            is_significant=False,
        )
    denom = math.sqrt(denom_inner)

    test_stat = (sr_adj - e_max_sr * math.sqrt(sample_length - 1)) / denom
    dsr = float(stats.norm.cdf(test_stat))

    logger.info(
        "DSR: observed_SR={:.3f}, E[max(SR)]={:.3f}, DSR={:.4f}, "
        "n_trials={}, T={}",
        observed_sharpe, e_max_sr, dsr, n_trials, sample_length,
    )

    return DSRResult(
        dsr=dsr,
        expected_max_sharpe=float(e_max_sr),
        observed_sharpe=observed_sharpe,
        is_significant=dsr > 0.95,
    )


# ── Anti-Overfit Pipeline ────────────────────────────────────────────

class AntiOverfitPipeline:
    """Sequential filter: CSCV → DSR → (optional) Hansen SPA.

    Parameters
    ----------
    pbo_threshold
        Max PBO for a strategy to pass CSCV (default 0.50).
    dsr_threshold
        Min DSR p-value to pass deflated Sharpe test (default 0.95).
    spa_significance
        Significance level for Hansen SPA test (default 0.05).
    n_subsamples
        Passed to ``CSCVValidator``.
    """

    def __init__(
        self,
        *,
        pbo_threshold: float = 0.50,
        dsr_threshold: float = 0.95,
        spa_significance: float = 0.05,
        n_subsamples: int = 16,
        metric: str = "sharpe",
    ) -> None:
        self._pbo_th = pbo_threshold
        self._dsr_th = dsr_threshold
        self._spa_sig = spa_significance
        self._cscv = CSCVValidator(n_subsamples=n_subsamples, metric=metric)

    def evaluate(
        self,
        *,
        equity_curves: dict[str, np.ndarray],
        n_trials: int,
        sample_length: int | None = None,
        benchmark_returns: np.ndarray | None = None,
    ) -> AntiOverfitResult:
        """Run the full anti-overfitting pipeline.

        Parameters
        ----------
        equity_curves
            ``strategy_id → OOS equity_curve``.
        n_trials
            Total parameter combinations tested during optimisation.
        sample_length
            Number of return observations (inferred from curves if None).
        benchmark_returns
            Returns for Hansen SPA benchmark (e.g. buy-and-hold).
        """
        ids = list(equity_curves.keys())

        if sample_length is None:
            sample_length = max(len(v) for v in equity_curves.values()) if equity_curves else 0

        # ── Stage 1: CSCV ──
        cscv_results: dict[str, CSCVResult] = {}
        passed_cscv_ids: list[str] = []

        if len(ids) >= 2:
            cscv_result = self._cscv.compute_pbo(equity_curves)
            for sid in ids:
                cscv_results[sid] = cscv_result
            if not cscv_result.is_overfit:
                passed_cscv_ids = list(ids)
            else:
                passed_cscv_ids = []
        else:
            # Single strategy — skip CSCV, pass through
            passed_cscv_ids = list(ids)

        # ── Stage 2: DSR ──
        dsr_results: dict[str, DSRResult] = {}
        passed_dsr_ids: list[str] = []

        for sid in passed_cscv_ids:
            eq = equity_curves[sid]
            returns = np.diff(eq) / np.maximum(eq[:-1], 1e-12)
            returns = returns[np.isfinite(returns)]
            if len(returns) < 30:
                logger.warning(
                    "DSR skipped for {}: only {} returns (min 30)",
                    sid, len(returns),
                )
                continue

            mean_r = float(np.mean(returns))
            std_r = float(np.std(returns, ddof=1))
            obs_sharpe = mean_r / std_r if std_r > 1e-12 else 0.0

            dsr_res = deflated_sharpe_ratio(
                observed_sharpe=obs_sharpe,
                n_trials=n_trials,
                sample_length=len(returns),
                skewness=float(stats.skew(returns)),
                kurtosis=float(stats.kurtosis(returns, fisher=False)),
            )
            dsr_results[sid] = dsr_res
            if dsr_res.is_significant:
                passed_dsr_ids.append(sid)

        # ── Stage 3: Hansen SPA (optional) ──
        spa_results: dict[str, SPAResult] = {}
        passed_spa_ids: list[str] = []

        if benchmark_returns is not None:
            passed_spa_ids = self._run_spa(
                passed_dsr_ids, equity_curves, benchmark_returns, spa_results,
            )
        else:
            passed_spa_ids = list(passed_dsr_ids)

        finalists = passed_spa_ids

        logger.info(
            "Anti-overfit pipeline: {}/{} passed CSCV, {}/{} passed DSR, "
            "{}/{} passed SPA → {} finalists",
            len(passed_cscv_ids), len(ids),
            len(passed_dsr_ids), len(passed_cscv_ids),
            len(passed_spa_ids), len(passed_dsr_ids),
            len(finalists),
        )

        return AntiOverfitResult(
            total_candidates=len(ids),
            passed_cscv=len(passed_cscv_ids),
            passed_dsr=len(passed_dsr_ids),
            passed_spa=len(passed_spa_ids),
            finalists=finalists,
            cscv_results=cscv_results,
            dsr_results=dsr_results,
            spa_results=spa_results,
        )

    def _run_spa(
        self,
        candidate_ids: list[str],
        equity_curves: dict[str, np.ndarray],
        benchmark_returns: np.ndarray,
        spa_results: dict[str, SPAResult],
    ) -> list[str]:
        """Run Hansen SPA test for each candidate."""
        passed: list[str] = []
        try:
            from arch.bootstrap import SPA as ArchSPA
            for sid in candidate_ids:
                eq = equity_curves[sid]
                strat_returns = np.diff(eq) / eq[:-1]
                strat_returns = strat_returns[np.isfinite(strat_returns)]
                min_len = min(len(strat_returns), len(benchmark_returns))
                if min_len < 10:
                    continue
                # SPA(benchmark_loss, model_losses): tests if any model
                # has lower avg loss than benchmark.
                # We negate returns so "lower loss" = "higher return".
                bench_loss = -benchmark_returns[:min_len]
                model_loss = -strat_returns[:min_len].reshape(-1, 1)
                spa = ArchSPA(bench_loss, model_loss, reps=1000)
                spa.compute()
                # pvalues returns an array or scalar; take the max (consistent)
                pvals = spa.pvalues
                p_val = float(np.max(pvals)) if hasattr(pvals, '__len__') else float(pvals)
                is_sup = p_val < self._spa_sig
                spa_results[sid] = SPAResult(
                    p_value=p_val,
                    is_superior=is_sup,
                    statistic=float(getattr(spa, "statistic", 0.0)),
                    benchmark="buy_and_hold",
                )
                if is_sup:
                    passed.append(sid)
        except ImportError:
            logger.warning(
                "arch not available — skipping Hansen SPA, passing all through"
            )
            passed = list(candidate_ids)
            for sid in candidate_ids:
                spa_results[sid] = SPAResult(
                    p_value=0.0,
                    is_superior=True,
                    statistic=0.0,
                    benchmark="skipped",
                )
        return passed
