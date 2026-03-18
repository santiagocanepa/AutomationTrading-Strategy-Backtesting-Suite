"""Strategy correlation analysis and diversification-based selection.

Measures pairwise correlation between strategy equity curves and selects
a maximally diversified subset using greedy forward selection.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from scipy import stats
from scipy.cluster import hierarchy
from loguru import logger


@dataclass
class CorrelationMatrix:
    """Pairwise correlation results."""

    strategy_ids: list[str]
    pearson: np.ndarray        # (N, N) Pearson correlation
    spearman: np.ndarray       # (N, N) Spearman rank correlation
    drawdown_corr: np.ndarray  # (N, N) Drawdown correlation
    avg_correlation: float     # Mean of upper triangle of Pearson matrix
    clusters: list[list[str]]  # Hierarchical clusters


class StrategyCorrelationAnalyzer:
    """Compute correlation matrices and cluster strategies."""

    def compute_matrix(self, equity_curves: dict[str, np.ndarray]) -> CorrelationMatrix:
        """Compute Pearson, Spearman, and drawdown correlation matrices."""
        ids = list(equity_curves.keys())
        n = len(ids)
        if n < 2:
            raise ValueError(f"Need >= 2 strategies, got {n}")

        # Align lengths to the shortest curve
        min_len = min(len(v) for v in equity_curves.values())
        if min_len < 3:
            raise ValueError(f"Equity curves too short: {min_len}")

        # Convert equity curves to returns
        returns_list: list[np.ndarray] = []
        dd_list: list[np.ndarray] = []
        for sid in ids:
            eq = np.asarray(equity_curves[sid][:min_len], dtype=np.float64)
            ret = np.diff(eq) / np.where(eq[:-1] != 0, eq[:-1], 1.0)
            returns_list.append(ret)
            dd_list.append(self._compute_drawdowns(eq)[1:])  # align with returns

        returns_mat = np.column_stack(returns_list)  # (T-1, N)
        dd_mat = np.column_stack(dd_list)

        # Pearson correlation of returns
        pearson = np.corrcoef(returns_mat, rowvar=False)

        # Spearman rank correlation of returns
        spearman = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                rho, _ = stats.spearmanr(returns_mat[:, i], returns_mat[:, j])
                spearman[i, j] = rho
                spearman[j, i] = rho

        # Drawdown correlation
        drawdown_corr = np.corrcoef(dd_mat, rowvar=False)

        # Fix any NaN from constant series
        for mat in (pearson, spearman, drawdown_corr):
            np.fill_diagonal(mat, 1.0)
            mat[np.isnan(mat)] = 0.0

        # Average correlation: upper triangle of Pearson
        upper_idx = np.triu_indices(n, k=1)
        avg_corr = float(np.mean(pearson[upper_idx]))

        # Hierarchical clustering
        clusters = self._cluster_strategies(pearson, ids)

        logger.debug(
            "Correlation matrix: {} strategies, avg_corr={:.3f}, {} clusters",
            n, avg_corr, len(clusters),
        )

        return CorrelationMatrix(
            strategy_ids=ids,
            pearson=pearson,
            spearman=spearman,
            drawdown_corr=drawdown_corr,
            avg_correlation=avg_corr,
            clusters=clusters,
        )

    def _compute_drawdowns(self, equity: np.ndarray) -> np.ndarray:
        """Compute drawdown series from equity curve."""
        peak = np.maximum.accumulate(equity)
        return (peak - equity) / np.where(peak > 0, peak, 1.0)

    def _cluster_strategies(
        self,
        corr_matrix: np.ndarray,
        ids: list[str],
        threshold: float = 0.7,
    ) -> list[list[str]]:
        """Hierarchical clustering using correlation distance."""
        n = len(ids)
        if n < 2:
            return [ids[:]]

        # Distance = 1 - |correlation|, clipped to [0, 2]
        dist_matrix = 1.0 - np.abs(corr_matrix)
        np.fill_diagonal(dist_matrix, 0.0)

        # Convert to condensed distance vector for scipy
        condensed = dist_matrix[np.triu_indices(n, k=1)]
        condensed = np.clip(condensed, 0.0, 2.0)

        linkage = hierarchy.linkage(condensed, method="average")
        # Cut at distance = 1 - threshold (high corr -> small distance -> same cluster)
        cut_distance = 1.0 - threshold
        labels = hierarchy.fcluster(linkage, t=cut_distance, criterion="distance")

        clusters: dict[int, list[str]] = {}
        for idx, label in enumerate(labels):
            clusters.setdefault(int(label), []).append(ids[idx])

        return list(clusters.values())


class DiversificationRatio:
    """Compute portfolio diversification ratio.

    DR = sum(individual_vols * weights) / portfolio_vol
    DR > 1.5 indicates good diversification.
    """

    @staticmethod
    def compute(returns_matrix: np.ndarray, weights: np.ndarray | None = None) -> float:
        """Compute DR from returns matrix (T x N) and optional weights."""
        _, n = returns_matrix.shape
        if weights is None:
            weights = np.ones(n) / n

        weights = np.asarray(weights, dtype=np.float64)
        individual_vols = np.std(returns_matrix, axis=0, ddof=1)
        weighted_vol_sum = float(np.dot(weights, individual_vols))

        port_returns = returns_matrix @ weights
        port_vol = float(np.std(port_returns, ddof=1))

        if port_vol < 1e-12:
            return 1.0
        return weighted_vol_sum / port_vol


class StrategySelector:
    """Greedy forward selection maximizing diversification ratio.

    Constraints:
    - avg correlation < max_avg_corr
    - max strategies per archetype cluster
    - max strategies per asset x timeframe combo
    """

    def __init__(
        self,
        *,
        target_count: int = 100,
        max_avg_corr: float = 0.30,
        max_per_archetype: int = 3,
        max_per_asset_tf: int = 2,
        min_sharpe: float = 0.0,
    ) -> None:
        self._target = target_count
        self._max_corr = max_avg_corr
        self._max_per_arch = max_per_archetype
        self._max_per_asset_tf = max_per_asset_tf
        self._min_sharpe = min_sharpe

    def select(
        self,
        equity_curves: dict[str, np.ndarray],
        metadata: dict[str, dict[str, str]],
    ) -> list[dict[str, Any]]:
        """Greedy forward selection.

        Returns list of dicts with strategy_id, marginal_dr_contribution, order.
        """
        ids = list(equity_curves.keys())
        n = len(ids)
        if n == 0:
            return []

        # Align lengths
        min_len = min(len(equity_curves[s]) for s in ids)
        if min_len < 3:
            logger.warning("Equity curves too short ({}) for selection", min_len)
            return []

        # Build returns matrix, filter out constant equity curves
        returns_dict: dict[str, np.ndarray] = {}
        sharpe_dict: dict[str, float] = {}
        for sid in ids:
            eq = np.asarray(equity_curves[sid][:min_len], dtype=np.float64)
            ret = np.diff(eq) / np.where(eq[:-1] != 0, eq[:-1], 1.0)
            std = float(np.std(ret, ddof=1))
            if std < 1e-12:
                continue  # Skip constant/zero-variance strategies
            returns_dict[sid] = ret
            sharpe_dict[sid] = float(np.mean(ret)) / std

        if len(returns_dict) < 2:
            logger.warning("Fewer than 2 non-constant strategies for selection")
            return []

        # Filter by minimum Sharpe
        if self._min_sharpe > -999:
            returns_dict = {k: v for k, v in returns_dict.items() if sharpe_dict.get(k, 0) >= self._min_sharpe}
            sharpe_dict = {k: v for k, v in sharpe_dict.items() if k in returns_dict}
            if len(returns_dict) < 2:
                logger.warning("Fewer than 2 strategies with Sharpe >= {:.4f}", self._min_sharpe)
                return []

        # Seed: strategy with highest standalone Sharpe
        valid_ids = list(returns_dict.keys())
        seed_id = max(sharpe_dict, key=lambda k: sharpe_dict[k])
        selected: list[str] = [seed_id]
        remaining = set(valid_ids) - {seed_id}

        # Track constraint counters
        arch_count: dict[str, int] = {}
        asset_tf_count: dict[str, int] = {}
        self._increment_counters(seed_id, metadata, arch_count, asset_tf_count)

        dr_history: dict[str, float] = {seed_id: 1.0}  # seed DR = 1 by definition

        while len(selected) < self._target and remaining:
            best_id: str | None = None
            best_dr = -np.inf
            current_returns = np.column_stack([returns_dict[s] for s in selected])

            for candidate in remaining:
                # Check archetype constraint
                arch = metadata.get(candidate, {}).get("archetype", "unknown")
                if arch_count.get(arch, 0) >= self._max_per_arch:
                    continue

                # Check asset x timeframe constraint
                sym = metadata.get(candidate, {}).get("symbol", "?")
                tf = metadata.get(candidate, {}).get("timeframe", "?")
                key = f"{sym}_{tf}"
                if asset_tf_count.get(key, 0) >= self._max_per_asset_tf:
                    continue

                # Check avg correlation constraint
                trial_returns = np.column_stack([current_returns, returns_dict[candidate][:current_returns.shape[0]]])
                corr_mat = np.corrcoef(trial_returns, rowvar=False)
                corr_mat[np.isnan(corr_mat)] = 0.0
                upper = corr_mat[np.triu_indices(corr_mat.shape[0], k=1)]
                if len(upper) > 0 and float(np.mean(np.abs(upper))) > self._max_corr:
                    continue

                # Compute DR with candidate added
                trial_dr = DiversificationRatio.compute(trial_returns)
                if trial_dr > best_dr:
                    best_dr = trial_dr
                    best_id = candidate

            if best_id is None:
                logger.info(
                    "No more valid candidates after {} selections", len(selected),
                )
                break

            selected.append(best_id)
            remaining.discard(best_id)
            self._increment_counters(best_id, metadata, arch_count, asset_tf_count)
            dr_history[best_id] = best_dr

        # Build result list
        result: list[dict[str, Any]] = []
        # Compute baseline DR for marginal contribution
        prev_dr = 0.0
        for order, sid in enumerate(selected):
            current_dr = dr_history.get(sid, 0.0)
            result.append({
                "strategy_id": sid,
                "marginal_dr_contribution": round(current_dr - prev_dr, 6),
                "order": order,
            })
            prev_dr = current_dr

        logger.info(
            "Selected {}/{} strategies, final DR={:.3f}, avg_corr within budget",
            len(selected), n, prev_dr,
        )
        return result

    @staticmethod
    def _increment_counters(
        sid: str,
        metadata: dict[str, dict[str, str]],
        arch_count: dict[str, int],
        asset_tf_count: dict[str, int],
    ) -> None:
        meta = metadata.get(sid, {})
        arch = meta.get("archetype", "unknown")
        arch_count[arch] = arch_count.get(arch, 0) + 1
        sym = meta.get("symbol", "?")
        tf = meta.get("timeframe", "?")
        key = f"{sym}_{tf}"
        asset_tf_count[key] = asset_tf_count.get(key, 0) + 1
