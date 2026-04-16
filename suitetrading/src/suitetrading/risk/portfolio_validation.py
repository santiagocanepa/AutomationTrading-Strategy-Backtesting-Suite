"""Portfolio validation — DSR, alpha decay, clustering, regime-conditional, tail risk.

Five cheap validation tests that run in seconds on existing portfolio data.
Designed to be called after every portfolio build as standard output.

References:
    - Bailey & López de Prado (2014): "The Deflated Sharpe Ratio"
    - Lo (2002): "The Statistics of Sharpe Ratios"
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import stats
from scipy.cluster import hierarchy
from loguru import logger


@dataclass
class ValidationResult:
    """Aggregated portfolio validation results."""

    deflated_sharpe: dict[str, float]
    alpha_decay: dict[str, Any]
    clustering: dict[str, Any]
    regime_conditional: dict[str, Any]
    tail_risk: dict[str, float]
    summary: dict[str, Any]


class PortfolioValidator:
    """Run 5 cheap validation tests on a constructed portfolio."""

    # ── 1. Deflated Sharpe Ratio ─────────────────────────────────

    def deflated_sharpe_ratio(
        self,
        returns: np.ndarray,
        n_trials: int,
    ) -> dict[str, float]:
        """Compute the Deflated Sharpe Ratio (Bailey & López de Prado 2014).

        Adjusts the observed Sharpe for multiple testing, skewness, and kurtosis.
        A DSR > 0.95 means the Sharpe is significant at the 5% level even after
        accounting for `n_trials` strategies tested.

        Parameters
        ----------
        returns : 1D portfolio return series
        n_trials : total number of strategies tested across all discovery runs
        """
        T = len(returns)
        if T < 30:
            return {"dsr": 0.0, "observed_sharpe": 0.0, "expected_max_sharpe": 0.0,
                    "sharpe_std": 0.0, "n_trials": n_trials, "T": T, "significant": False}

        sr = float(np.mean(returns) / np.std(returns, ddof=1))
        skew = float(stats.skew(returns))
        kurt = float(stats.kurtosis(returns))  # excess kurtosis (Fisher)

        # Variance of Sharpe ratio estimator (Lo 2002, adjusted)
        var_sr = (1.0 - skew * sr + ((kurt + 2) / 4.0) * sr ** 2) / (T - 1)
        var_sr = max(var_sr, 1e-12)
        std_sr = np.sqrt(var_sr)

        # Expected maximum Sharpe from N independent trials under null (SR=0)
        # E[max] ≈ sqrt(V[SR]) * z_N
        # z_N ≈ (1-γ)*Φ⁻¹(1 - 1/N) + γ*Φ⁻¹(1 - 1/(N*e))
        gamma = 0.5772156649  # Euler-Mascheroni
        e = np.e
        N = max(n_trials, 2)

        z1 = stats.norm.ppf(1.0 - 1.0 / N)
        z2 = stats.norm.ppf(1.0 - 1.0 / (N * e))
        z_n = (1.0 - gamma) * z1 + gamma * z2

        expected_max_sr = std_sr * z_n

        # DSR = Φ((SR_obs - SR_max) / std_SR)
        dsr = float(stats.norm.cdf((sr - expected_max_sr) / std_sr))

        result = {
            "dsr": round(dsr, 6),
            "observed_sharpe_per_bar": round(sr, 8),
            "expected_max_sharpe": round(expected_max_sr, 8),
            "sharpe_std": round(std_sr, 8),
            "skewness": round(skew, 4),
            "excess_kurtosis": round(kurt, 4),
            "n_trials": n_trials,
            "T": T,
            "significant_5pct": dsr > 0.95,
            "significant_10pct": dsr > 0.90,
        }

        logger.info(
            "DSR: {:.4f} (SR={:.6f}, E[max]={:.6f}, N={}, T={}) → {}",
            dsr, sr, expected_max_sr, n_trials, T,
            "SIGNIFICANT" if dsr > 0.95 else "NOT significant",
        )
        return result

    # ── 2. Alpha Decay Analysis ──────────────────────────────────

    def alpha_decay_analysis(
        self,
        returns: np.ndarray,
        n_windows: int = 8,
    ) -> dict[str, Any]:
        """Split portfolio returns into N equal windows. Compute Sharpe per window.

        Fits a linear regression: if slope < 0, the edge is decaying over time.

        Parameters
        ----------
        returns : 1D portfolio return series
        n_windows : number of equal-length time windows
        """
        T = len(returns)
        window_size = T // n_windows
        if window_size < 20:
            n_windows = max(T // 20, 2)
            window_size = T // n_windows

        windows: list[dict[str, float]] = []
        for i in range(n_windows):
            start = i * window_size
            end = start + window_size if i < n_windows - 1 else T
            chunk = returns[start:end]
            std = float(np.std(chunk, ddof=1))
            sr = float(np.mean(chunk)) / std if std > 1e-12 else 0.0
            windows.append({
                "window": i + 1,
                "start_bar": start,
                "end_bar": end,
                "sharpe_per_bar": round(sr, 8),
                "mean_return": round(float(np.mean(chunk)), 8),
                "volatility": round(std, 8),
                "total_return_pct": round(float(np.prod(1.0 + chunk) - 1.0) * 100, 4),
            })

        # Linear regression: window_index vs Sharpe
        x = np.arange(n_windows, dtype=np.float64)
        y = np.array([w["sharpe_per_bar"] for w in windows])
        slope, intercept, r_value, p_value, std_err = stats.linregress(x, y)

        # Classify decay
        if p_value < 0.10 and slope < 0:
            decay_status = "DECAYING"
        elif p_value < 0.10 and slope > 0:
            decay_status = "IMPROVING"
        else:
            decay_status = "STABLE"

        # Ratio: last window Sharpe / first window Sharpe
        first_sr = windows[0]["sharpe_per_bar"]
        last_sr = windows[-1]["sharpe_per_bar"]
        decay_ratio = last_sr / first_sr if abs(first_sr) > 1e-12 else 0.0

        result = {
            "windows": windows,
            "slope": round(float(slope), 8),
            "intercept": round(float(intercept), 8),
            "r_squared": round(float(r_value ** 2), 4),
            "p_value": round(float(p_value), 4),
            "decay_ratio": round(decay_ratio, 4),
            "status": decay_status,
            "n_windows": n_windows,
        }

        logger.info(
            "Alpha decay: slope={:.6f}, p={:.4f}, ratio={:.2f} → {}",
            slope, p_value, decay_ratio, decay_status,
        )
        return result

    # ── 3. Strategy Clustering ───────────────────────────────────

    def strategy_clustering(
        self,
        returns_matrix: np.ndarray,
        strategy_ids: list[str],
        thresholds: tuple[float, ...] = (0.5, 0.6, 0.7, 0.8),
    ) -> dict[str, Any]:
        """Determine how many truly independent strategies exist.

        Uses hierarchical clustering at multiple correlation thresholds
        and computes the effective N (accounting for average correlation).

        Parameters
        ----------
        returns_matrix : (T, N) per-strategy returns
        strategy_ids : list of strategy identifiers
        thresholds : correlation thresholds for clustering analysis
        """
        _, n = returns_matrix.shape

        # Correlation matrix
        corr = np.corrcoef(returns_matrix, rowvar=False)
        corr[np.isnan(corr)] = 0.0
        np.fill_diagonal(corr, 1.0)

        # Average pairwise correlation
        upper = corr[np.triu_indices(n, k=1)]
        avg_corr = float(np.mean(upper))
        avg_abs_corr = float(np.mean(np.abs(upper)))

        # Effective N: N / (1 + (N-1) * avg_abs_corr)
        effective_n = n / (1.0 + (n - 1) * avg_abs_corr) if avg_abs_corr < 1.0 else 1.0

        # Hierarchical clustering at different thresholds
        dist_matrix = 1.0 - np.abs(corr)
        np.fill_diagonal(dist_matrix, 0.0)
        condensed = dist_matrix[np.triu_indices(n, k=1)]
        condensed = np.clip(condensed, 0.0, 2.0)

        linkage = hierarchy.linkage(condensed, method="average")

        cluster_analysis: list[dict[str, Any]] = []
        for thresh in thresholds:
            cut_dist = 1.0 - thresh
            labels = hierarchy.fcluster(linkage, t=cut_dist, criterion="distance")
            n_clusters = len(set(labels))

            # Cluster sizes
            sizes: dict[int, int] = {}
            for lab in labels:
                sizes[lab] = sizes.get(lab, 0) + 1

            cluster_analysis.append({
                "correlation_threshold": thresh,
                "n_clusters": n_clusters,
                "largest_cluster": max(sizes.values()),
                "singleton_clusters": sum(1 for s in sizes.values() if s == 1),
            })

        # Top correlated pairs
        abs_corr = np.abs(corr)
        np.fill_diagonal(abs_corr, 0.0)
        flat_idx = np.argsort(abs_corr.ravel())[::-1]
        top_pairs: list[dict[str, Any]] = []
        seen: set[tuple[int, int]] = set()
        for idx in flat_idx:
            i, j = divmod(idx, n)
            if i >= j:
                continue
            pair = (min(i, j), max(i, j))
            if pair in seen:
                continue
            seen.add(pair)
            top_pairs.append({
                "strategy_a": strategy_ids[i],
                "strategy_b": strategy_ids[j],
                "correlation": round(float(corr[i, j]), 4),
            })
            if len(top_pairs) >= 5:
                break

        result = {
            "n_strategies": n,
            "effective_n": round(effective_n, 1),
            "avg_correlation": round(avg_corr, 4),
            "avg_abs_correlation": round(avg_abs_corr, 4),
            "diversification_real": round(effective_n / n, 4),
            "cluster_analysis": cluster_analysis,
            "top_correlated_pairs": top_pairs,
        }

        logger.info(
            "Clustering: N={}, effective_N={:.1f} ({:.0f}% real diversification), avg_corr={:.3f}",
            n, effective_n, effective_n / n * 100, avg_corr,
        )
        return result

    # ── 4. Regime-Conditional Analysis ───────────────────────────

    def regime_conditional(
        self,
        returns: np.ndarray,
        vol_lookback: int = 60,
    ) -> dict[str, Any]:
        """Compute portfolio performance under different volatility regimes.

        Classifies each bar by rolling volatility percentile and drawdown state,
        then computes Sharpe per regime. Answers: does the portfolio only work
        in calm/bull markets, or does it also perform in stress?

        Parameters
        ----------
        returns : 1D portfolio return series
        vol_lookback : window for rolling volatility computation
        """
        T = len(returns)
        vol_lookback = min(vol_lookback, T // 4)

        # Rolling volatility
        rolling_vol = np.zeros(T, dtype=np.float64)
        for i in range(vol_lookback, T):
            rolling_vol[i] = np.std(returns[i - vol_lookback:i], ddof=1)

        # Volatility quantiles (computed on non-zero portion)
        valid_vol = rolling_vol[vol_lookback:]
        q25, q50, q75 = np.percentile(valid_vol, [25, 50, 75])

        # Drawdown state
        equity = np.cumprod(1.0 + returns)
        peak = np.maximum.accumulate(equity)
        drawdown = (peak - equity) / np.where(peak > 0, peak, 1.0)

        # Classify regimes
        regimes = np.full(T, "warmup", dtype=object)
        for i in range(vol_lookback, T):
            if drawdown[i] > 0.05:
                regimes[i] = "deep_drawdown"
            elif rolling_vol[i] > q75:
                regimes[i] = "high_vol"
            elif rolling_vol[i] < q25:
                regimes[i] = "low_vol"
            else:
                regimes[i] = "normal"

        # Compute metrics per regime
        regime_metrics: dict[str, dict[str, float]] = {}
        for regime_name in ("low_vol", "normal", "high_vol", "deep_drawdown"):
            mask = regimes == regime_name
            count = int(np.sum(mask))
            if count < 10:
                regime_metrics[regime_name] = {
                    "bars": count, "sharpe_per_bar": 0.0, "mean_return": 0.0,
                    "volatility": 0.0, "pct_of_total": 0.0, "win_rate": 0.0,
                }
                continue

            regime_ret = returns[mask]
            std = float(np.std(regime_ret, ddof=1))
            sr = float(np.mean(regime_ret)) / std if std > 1e-12 else 0.0
            wr = float(np.mean(regime_ret > 0)) * 100

            regime_metrics[regime_name] = {
                "bars": count,
                "sharpe_per_bar": round(sr, 8),
                "mean_return": round(float(np.mean(regime_ret)), 8),
                "volatility": round(std, 8),
                "pct_of_total": round(count / (T - vol_lookback) * 100, 1),
                "win_rate": round(wr, 1),
                "total_return_pct": round(float(np.sum(regime_ret)) * 100, 4),
            }

        # Key check: is Sharpe positive in ALL regimes?
        all_positive = all(
            regime_metrics[r]["sharpe_per_bar"] > 0
            for r in ("low_vol", "normal", "high_vol", "deep_drawdown")
            if regime_metrics[r]["bars"] >= 10
        )

        # Stress ratio: high_vol Sharpe / normal Sharpe
        normal_sr = regime_metrics["normal"]["sharpe_per_bar"]
        highvol_sr = regime_metrics["high_vol"]["sharpe_per_bar"]
        stress_ratio = highvol_sr / normal_sr if abs(normal_sr) > 1e-12 else 0.0

        result = {
            "regimes": regime_metrics,
            "all_regimes_positive": all_positive,
            "stress_ratio": round(stress_ratio, 4),
            "vol_lookback": vol_lookback,
        }

        logger.info(
            "Regime analysis: all_positive={}, stress_ratio={:.2f} (high_vol/normal Sharpe)",
            all_positive, stress_ratio,
        )
        return result

    # ── 5. Tail Risk Analysis ────────────────────────────────────

    def tail_risk(
        self,
        returns: np.ndarray,
    ) -> dict[str, float]:
        """Compute VaR, CVaR (Expected Shortfall), and tail statistics.

        Parameters
        ----------
        returns : 1D portfolio return series
        """
        T = len(returns)

        # VaR (negative quantile = loss threshold)
        var_95 = float(np.percentile(returns, 5))
        var_99 = float(np.percentile(returns, 1))

        # CVaR = mean of returns below VaR (Expected Shortfall)
        cvar_95 = float(np.mean(returns[returns <= var_95])) if np.any(returns <= var_95) else var_95
        cvar_99 = float(np.mean(returns[returns <= var_99])) if np.any(returns <= var_99) else var_99

        # Tail ratio: avg gain in top 5% / |avg loss in bottom 5%|
        top_5 = returns[returns >= np.percentile(returns, 95)]
        bot_5 = returns[returns <= np.percentile(returns, 5)]
        tail_ratio = float(np.mean(top_5)) / abs(float(np.mean(bot_5))) if abs(np.mean(bot_5)) > 1e-12 else 0.0

        # Max consecutive losses
        losing_streak = 0
        max_streak = 0
        for r in returns:
            if r < 0:
                losing_streak += 1
                max_streak = max(max_streak, losing_streak)
            else:
                losing_streak = 0

        # Worst single bar
        worst_bar = float(np.min(returns))
        best_bar = float(np.max(returns))

        # Probability of loss > 2% in a single bar
        prob_large_loss = float(np.mean(returns < -0.02))

        result = {
            "var_95": round(var_95 * 100, 6),
            "var_99": round(var_99 * 100, 6),
            "cvar_95": round(cvar_95 * 100, 6),
            "cvar_99": round(cvar_99 * 100, 6),
            "tail_ratio": round(tail_ratio, 4),
            "worst_bar_pct": round(worst_bar * 100, 6),
            "best_bar_pct": round(best_bar * 100, 6),
            "max_losing_streak": max_streak,
            "prob_loss_gt_2pct": round(prob_large_loss * 100, 4),
            "skewness": round(float(stats.skew(returns)), 4),
            "excess_kurtosis": round(float(stats.kurtosis(returns)), 4),
            "T": T,
        }

        logger.info(
            "Tail risk: VaR95={:.4f}%, CVaR95={:.4f}%, tail_ratio={:.2f}, worst={:.4f}%",
            result["var_95"], result["cvar_95"], tail_ratio, result["worst_bar_pct"],
        )
        return result

    # ── Run All ──────────────────────────────────────────────────

    def run_all(
        self,
        returns_matrix: np.ndarray,
        weights: np.ndarray,
        strategy_ids: list[str],
        n_trials: int = 2500,
        n_decay_windows: int = 8,
    ) -> ValidationResult:
        """Run all 5 validation tests and return consolidated result.

        Parameters
        ----------
        returns_matrix : (T, N) per-strategy return series
        weights : (N,) portfolio weight vector
        strategy_ids : list of strategy identifiers
        n_trials : total WFO studies tested across all discovery runs
        n_decay_windows : number of windows for alpha decay analysis
        """
        weights = np.asarray(weights, dtype=np.float64)
        port_returns = returns_matrix @ weights

        logger.info("Running portfolio validation suite ({} strategies, T={})...",
                     len(strategy_ids), len(port_returns))

        dsr = self.deflated_sharpe_ratio(port_returns, n_trials)
        decay = self.alpha_decay_analysis(port_returns, n_decay_windows)
        clusters = self.strategy_clustering(returns_matrix, strategy_ids)
        regime = self.regime_conditional(port_returns)
        tail = self.tail_risk(port_returns)

        # Summary verdict
        summary = {
            "dsr_significant": dsr["significant_5pct"],
            "dsr_value": dsr["dsr"],
            "alpha_stable": decay["status"] != "DECAYING",
            "alpha_decay_status": decay["status"],
            "effective_strategies": clusters["effective_n"],
            "diversification_pct": clusters["diversification_real"] * 100,
            "all_regimes_positive": regime["all_regimes_positive"],
            "stress_ratio": regime["stress_ratio"],
            "cvar_99_pct": tail["cvar_99"],
            "tail_ratio": tail["tail_ratio"],
        }

        # Overall pass: DSR significant + alpha not decaying + real diversification
        overall_pass = (
            dsr["significant_5pct"]
            and decay["status"] != "DECAYING"
            and clusters["effective_n"] >= 5
            and regime["all_regimes_positive"]
        )
        summary["overall_pass"] = overall_pass

        logger.info(
            "Validation complete: DSR={:.4f}{}, decay={}, eff_N={:.0f}, regimes={}, → {}",
            dsr["dsr"],
            " ✓" if dsr["significant_5pct"] else " ✗",
            decay["status"],
            clusters["effective_n"],
            "all+" if regime["all_regimes_positive"] else "MIXED",
            "PASS" if overall_pass else "FAIL",
        )

        return ValidationResult(
            deflated_sharpe=dsr,
            alpha_decay=decay,
            clustering=clusters,
            regime_conditional=regime,
            tail_risk=tail,
            summary=summary,
        )
