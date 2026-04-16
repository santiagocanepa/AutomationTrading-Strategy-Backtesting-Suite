"""Rolling portfolio validation across multiple time windows.

Validates that a long+short portfolio is profitable across diverse market
regimes (bull/bear/sideways/crash) using rolling windows, not a single
holdout period.  Reuses existing BacktestObjective, EnsembleBacktester,
PortfolioOptimizer and RegimeClassifier infrastructure.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats as sp_stats

from suitetrading.backtesting._internal.datasets import build_dataset_from_df
from suitetrading.backtesting.ensemble import EnsembleBacktester
from suitetrading.backtesting.metrics import MetricsEngine
from suitetrading.optimization._internal.objective import BacktestObjective
from suitetrading.risk.portfolio_optimizer import PortfolioOptimizer


# ── Data contracts ────────────────────────────────────────────────────

@dataclass
class StrategySpec:
    """Frozen strategy specification loaded from an evidence card."""

    symbol: str
    timeframe: str
    archetype: str
    direction: str  # "long" | "short"
    indicator_params: dict[str, dict[str, Any]]
    risk_overrides: dict[str, Any]
    pbo: float
    label: str

    @classmethod
    def from_evidence_card(cls, path: Path) -> StrategySpec:
        """Parse an evidence card JSON into a StrategySpec."""
        data = json.loads(path.read_text())
        label = (
            f"{data['symbol']}_{data['timeframe']}"
            f"_{data['archetype']}_{data['direction']}"
        )
        # Disambiguate if multiple candidates share the same study
        cid = data.get("candidate_id", "")
        if cid:
            label = f"{label}_{cid[:8]}"
        return cls(
            symbol=data["symbol"],
            timeframe=data["timeframe"],
            archetype=data["archetype"],
            direction=data["direction"],
            indicator_params=data["indicator_params"],
            risk_overrides=data["risk_overrides"],
            pbo=data.get("pbo", 1.0),
            label=label,
        )


@dataclass
class WindowResult:
    """Metrics for one rolling window."""

    window_id: int
    start: str
    end: str
    n_bars: int
    dominant_regime: str
    is_oos: bool
    strategy_metrics: dict[str, dict[str, float]]
    portfolio_metrics: dict[str, dict[str, float]]
    strategy_directions: dict[str, str] = field(default_factory=dict)


@dataclass
class RollingValidationResult:
    """Aggregated rolling validation output."""

    n_windows: int
    n_oos_windows: int
    windows: list[WindowResult]
    pct_positive_sharpe: dict[str, float]
    regime_performance: dict[str, dict[str, float]]
    alpha_stability: dict[str, dict[str, float]]
    max_drawdown_by_method: dict[str, float]
    long_short_contribution: dict[str, dict[str, float]]
    binomial_p_value: dict[str, float]
    best_method: str
    validation_pass: bool
    timestamp: str


# ── Helpers ───────────────────────────────────────────────────────────

def _align_to_daily(equity: np.ndarray, index: pd.DatetimeIndex) -> pd.Series:
    """Resample an equity curve to daily last-values for multi-TF alignment."""
    eq_series = pd.Series(equity, index=index)
    daily = eq_series.resample("1D").last().ffill()
    return daily


def _flatten_params(
    indicator_params: dict[str, dict[str, Any]],
    risk_overrides: dict[str, Any],
) -> dict[str, Any]:
    """Convert nested params back to the flat format BacktestObjective expects."""
    flat: dict[str, Any] = {}
    for ind_name, params in indicator_params.items():
        for k, v in params.items():
            flat[f"{ind_name}__{k}"] = v
    flat.update(risk_overrides)
    return flat


def _regime_adaptive_weights(
    specs: list[StrategySpec],
    dominant_regime: str,
) -> np.ndarray:
    """Compute weights biased by regime: overweight shorts in bearish regimes."""
    BIAS = {
        "trend_up":  {"long": 1.4, "short": 0.6},
        "trend_down": {"long": 0.6, "short": 1.4},
        "crash":     {"long": 0.3, "short": 1.7},
        "high_vol":  {"long": 0.8, "short": 1.2},
        "range":     {"long": 1.0, "short": 1.0},
    }
    bias = BIAS.get(dominant_regime, {"long": 1.0, "short": 1.0})
    raw = np.array([bias[s.direction] for s in specs], dtype=float)
    return raw / raw.sum()


def _binomial_pvalue(n_positive: int, n_total: int, p0: float = 0.5) -> float:
    """One-sided binomial test: P(X >= n_positive) under H0(p=p0)."""
    if n_total == 0:
        return 1.0
    return float(sp_stats.binomtest(n_positive, n_total, p0, alternative="greater").pvalue)


def _classify_window_regime(
    df: pd.DataFrame,
    *,
    trend_threshold: float = 30.0,
    crash_dd: float = -40.0,
    high_vol_ann: float = 1.0,
) -> str:
    """Classify a window's regime by price return and volatility.

    Thresholds should be calibrated per asset class:
    - Crypto: trend=30%, crash_dd=-40%, high_vol=1.0
    - Stocks: trend=10%, crash_dd=-20%, high_vol=0.30
    """
    if len(df) < 10:
        return "range"

    close = df["close"]
    ret_pct = (close.iloc[-1] / close.iloc[0] - 1) * 100

    # Realized vol: annualized std of log returns
    log_rets = np.log(close / close.shift(1)).dropna()
    vol = float(log_rets.std() * np.sqrt(252 * 6))

    # Max drawdown in window
    peak = close.cummax()
    dd = ((close - peak) / peak * 100).min()

    if dd < crash_dd:
        return "crash"
    if ret_pct > trend_threshold:
        return "trend_up"
    if ret_pct < -trend_threshold:
        return "trend_down"
    if vol > high_vol_ann:
        return "high_vol"
    return "range"


# ── Core evaluator ────────────────────────────────────────────────────

class RollingPortfolioEvaluator:
    """Evaluate a portfolio of strategies across rolling windows."""

    WARMUP_BARS: int = 200

    REGIME_PRESETS: dict[str, dict[str, float]] = {
        "crypto": {"trend_threshold": 30.0, "crash_dd": -40.0, "high_vol_ann": 1.0},
        "stocks": {"trend_threshold": 10.0, "crash_dd": -20.0, "high_vol_ann": 0.30},
    }

    def __init__(
        self,
        *,
        window_months: int = 6,
        slide_months: int = 2,
        weight_methods: tuple[str, ...] = ("equal", "risk_parity", "regime_adaptive"),
        initial_capital: float = 100_000.0,
        commission_pct: float = 0.04,
        mode: str = "fsm",
        holdout_start: str | pd.Timestamp | None = None,
        asset_class: str = "crypto",
    ) -> None:
        self._window_months = window_months
        self._slide_months = slide_months
        self._weight_methods = weight_methods
        self._initial_capital = initial_capital
        self._commission_pct = commission_pct
        self._mode = mode
        self._regime_params = self.REGIME_PRESETS.get(asset_class, self.REGIME_PRESETS["crypto"])
        if holdout_start is not None:
            ts = pd.Timestamp(holdout_start)
            self._holdout_start = ts.tz_localize("UTC") if ts.tzinfo is None else ts
        else:
            self._holdout_start = None
        self._metrics_engine = MetricsEngine()

    # ── Public API ────────────────────────────────────────────────────

    def evaluate(
        self,
        specs: list[StrategySpec],
        ohlcv_cache: dict[str, pd.DataFrame],
    ) -> RollingValidationResult:
        """Run full rolling evaluation and return aggregated results."""
        windows = self._generate_windows(ohlcv_cache)
        logger.info("Generated {} rolling windows", len(windows))

        results: list[WindowResult] = []
        for wid, (start, end) in enumerate(windows):
            wr = self._evaluate_window(specs, ohlcv_cache, start, end, wid)
            results.append(wr)
            tag = "OOS" if wr.is_oos else "IS"
            logger.info(
                "Window {:>2d} [{} → {}] regime={:<10s} {} | {}",
                wid, wr.start[:10], wr.end[:10], wr.dominant_regime, tag,
                {m: f"sharpe={v.get('sharpe', 0):.2f}" for m, v in wr.portfolio_metrics.items()},
            )

        agg = self._aggregate(results)
        return RollingValidationResult(
            n_windows=len(results),
            n_oos_windows=sum(1 for w in results if w.is_oos),
            windows=results,
            timestamp=datetime.now(timezone.utc).isoformat(),
            **agg,
        )

    def save_results(self, result: RollingValidationResult, output_dir: Path) -> Path:
        """Persist results to JSON."""
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        path = output_dir / f"rolling_validation_{ts}.json"
        path.write_text(json.dumps(asdict(result), indent=2, default=str))
        logger.info("Saved results to {}", path)
        return path

    @staticmethod
    def print_report(result: RollingValidationResult) -> None:
        """Pretty-print a validation report to stdout."""
        print("\n" + "=" * 70)
        print("  ROLLING PORTFOLIO VALIDATION REPORT")
        print("=" * 70)
        print(f"  Windows: {result.n_windows} total, {result.n_oos_windows} OOS")
        print(f"  Timestamp: {result.timestamp}")

        print("\n── % Windows with Sharpe > 0 ──")
        for method, pct in result.pct_positive_sharpe.items():
            binom_p = result.binomial_p_value.get(method, 1.0)
            status = "PASS" if pct >= 75.0 and binom_p < 0.05 else "FAIL"
            print(f"  {method:<20s}: {pct:5.1f}%  (binomial p={binom_p:.4f})  [{status}]")

        print("\n── Regime Performance (avg Sharpe) ──")
        for regime, perf in result.regime_performance.items():
            print(f"  {regime:<12s}: sharpe={perf.get('sharpe', 0):.3f}  return={perf.get('total_return_pct', 0):.1f}%")

        print("\n── Alpha Stability ──")
        for method, info in result.alpha_stability.items():
            print(f"  {method:<20s}: slope={info.get('slope', 0):.6f}  status={info.get('status', '?')}")

        print("\n── Max Drawdown ──")
        for method, dd in result.max_drawdown_by_method.items():
            status = "PASS" if dd < 40.0 else "FAIL"
            print(f"  {method:<20s}: {dd:.1f}%  [{status}]")

        print("\n── Long/Short Contribution (avg return) ──")
        for method, contrib in result.long_short_contribution.items():
            print(f"  {method:<20s}: long={contrib.get('long', 0):.2f}%  short={contrib.get('short', 0):.2f}%")

        best = result.best_method
        overall = "PASS" if result.validation_pass else "FAIL"
        print(f"\n  Best method: {best}")
        print(f"  Overall: [{overall}]")
        print("=" * 70 + "\n")

    # ── Internal ──────────────────────────────────────────────────────

    def _generate_windows(
        self,
        ohlcv_cache: dict[str, pd.DataFrame],
    ) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
        """Generate (start, end) pairs covering the full data range."""
        all_starts = []
        all_ends = []
        for df in ohlcv_cache.values():
            all_starts.append(df.index.min())
            all_ends.append(df.index.max())

        global_start = min(all_starts)
        global_end = max(all_ends)

        # Skip initial warmup
        cursor = global_start + pd.DateOffset(months=0)
        window_offset = pd.DateOffset(months=self._window_months)
        slide_offset = pd.DateOffset(months=self._slide_months)

        windows: list[tuple[pd.Timestamp, pd.Timestamp]] = []
        while cursor + window_offset <= global_end:
            w_end = cursor + window_offset
            windows.append((cursor, w_end))
            cursor += slide_offset

        return windows

    def _evaluate_window(
        self,
        specs: list[StrategySpec],
        ohlcv_cache: dict[str, pd.DataFrame],
        start: pd.Timestamp,
        end: pd.Timestamp,
        window_id: int,
    ) -> WindowResult:
        """Run all strategies on a single window and combine into portfolio."""
        # Mark OOS if the window midpoint falls in the holdout period
        midpoint = start + (end - start) / 2
        is_oos = (
            self._holdout_start is not None
            and midpoint >= self._holdout_start
        )

        # Determine dominant regime from lowest-frequency (largest TF) data
        ref_key = min(ohlcv_cache.keys(), key=lambda k: len(ohlcv_cache[k]))
        ref_df = ohlcv_cache[ref_key]
        window_df = ref_df.loc[start:end]
        dominant_str = _classify_window_regime(window_df, **self._regime_params)

        # Run each strategy
        strategy_metrics: dict[str, dict[str, float]] = {}
        daily_equities: dict[str, pd.Series] = {}
        strategy_directions: dict[str, str] = {}

        for spec in specs:
            cache_key = f"{spec.symbol}_{spec.timeframe}"
            ohlcv = ohlcv_cache.get(cache_key)
            if ohlcv is None:
                logger.warning("No data for {}, skipping", cache_key)
                continue

            window_ohlcv = ohlcv.loc[start:end]
            if len(window_ohlcv) < self.WARMUP_BARS:
                logger.debug(
                    "Window too short for {} ({} bars), skipping",
                    spec.label, len(window_ohlcv),
                )
                continue

            dataset = build_dataset_from_df(
                window_ohlcv,
                exchange="binance_futures",
                symbol=spec.symbol,
                base_timeframe=spec.timeframe,
            )

            indicator_names = list(spec.indicator_params.keys())
            objective = BacktestObjective(
                dataset=dataset,
                indicator_names=indicator_names,
                archetype=spec.archetype,
                direction=spec.direction,
                mode=self._mode,
                commission_pct=self._commission_pct,
            )

            flat_params = _flatten_params(spec.indicator_params, spec.risk_overrides)
            try:
                result = objective.run_single(flat_params)
            except Exception:
                logger.exception("Backtest failed for {} in window {}", spec.label, window_id)
                continue

            metrics = result["metrics"]
            strategy_metrics[spec.label] = metrics
            strategy_directions[spec.label] = spec.direction

            equity = result["equity_curve"]
            daily = _align_to_daily(equity, window_ohlcv.index[:len(equity)])
            daily_equities[spec.label] = daily

        if not daily_equities:
            return WindowResult(
                window_id=window_id,
                start=str(start),
                end=str(end),
                n_bars=len(window_df) if len(window_df) > 0 else 0,
                dominant_regime=dominant_str,
                is_oos=is_oos,
                strategy_metrics={},
                portfolio_metrics={},
            )

        # Align all daily equities to a common date index
        common_idx = sorted(
            set().union(*(eq.index for eq in daily_equities.values()))
        )
        common_idx = pd.DatetimeIndex(common_idx)

        aligned: dict[str, np.ndarray] = {}
        for label, eq in daily_equities.items():
            reindexed = eq.reindex(common_idx).ffill().bfill()
            aligned[label] = reindexed.values

        labels = list(aligned.keys())
        n_strats = len(labels)

        # Build returns matrix for PortfolioOptimizer
        equity_matrix = np.column_stack([aligned[l] for l in labels])
        returns_matrix = np.diff(equity_matrix, axis=0) / equity_matrix[:-1]

        # Compute portfolio for each weighting method
        portfolio_metrics: dict[str, dict[str, float]] = {}
        optimizer = PortfolioOptimizer()
        ensemble = EnsembleBacktester()

        for method in self._weight_methods:
            if method == "regime_adaptive":
                active_specs = [s for s in specs if s.label in labels]
                weights = _regime_adaptive_weights(active_specs, dominant_str)
            elif method == "equal":
                weights = np.ones(n_strats) / n_strats
            else:
                # risk_parity via PortfolioOptimizer
                pw = optimizer.optimize(returns_matrix, labels, method=method)
                weights = pw.weights

            ens_result = ensemble.run(
                equity_curves=aligned,
                weights=weights,
                strategy_ids=labels,
            )

            p_metrics = self._metrics_engine.compute(
                equity_curve=ens_result.equity_curve,
                initial_capital=self._initial_capital,
            )
            portfolio_metrics[method] = p_metrics

        return WindowResult(
            window_id=window_id,
            start=str(start),
            end=str(end),
            n_bars=len(window_df) if len(window_df) > 0 else 0,
            dominant_regime=dominant_str,
            is_oos=is_oos,
            strategy_metrics=strategy_metrics,
            portfolio_metrics=portfolio_metrics,
            strategy_directions=strategy_directions,
        )

    def _aggregate(self, windows: list[WindowResult]) -> dict[str, Any]:
        """Compute summary statistics across all windows."""
        methods = list(self._weight_methods)

        # % windows with positive Sharpe
        pct_positive: dict[str, float] = {}
        n_positive: dict[str, int] = {}
        n_total = len([w for w in windows if w.portfolio_metrics])

        for method in methods:
            pos = sum(
                1 for w in windows
                if w.portfolio_metrics.get(method, {}).get("sharpe", -1) > 0
            )
            n_positive[method] = pos
            pct_positive[method] = (pos / n_total * 100) if n_total else 0.0

        # Binomial p-value
        binom_pv: dict[str, float] = {}
        for method in methods:
            binom_pv[method] = _binomial_pvalue(n_positive[method], n_total)

        # Regime performance (average Sharpe and return per regime)
        regime_perf: dict[str, dict[str, float]] = {}
        regime_sharpes: dict[str, list[float]] = {}
        regime_returns: dict[str, list[float]] = {}
        # Use the best method for regime analysis
        best_method = max(methods, key=lambda m: pct_positive.get(m, 0))

        for w in windows:
            regime = w.dominant_regime
            pm = w.portfolio_metrics.get(best_method, {})
            sharpe = pm.get("sharpe", 0)
            ret = pm.get("total_return_pct", 0)
            regime_sharpes.setdefault(regime, []).append(sharpe)
            regime_returns.setdefault(regime, []).append(ret)

        for regime in regime_sharpes:
            regime_perf[regime] = {
                "sharpe": float(np.mean(regime_sharpes[regime])),
                "total_return_pct": float(np.mean(regime_returns[regime])),
            }

        # Alpha stability: linear regression of Sharpe over window order
        alpha_stability: dict[str, dict[str, float]] = {}
        for method in methods:
            sharpes = [
                w.portfolio_metrics.get(method, {}).get("sharpe", 0)
                for w in windows if w.portfolio_metrics
            ]
            if len(sharpes) >= 3:
                x = np.arange(len(sharpes))
                slope, _, r_value, p_value, _ = sp_stats.linregress(x, sharpes)
                if slope < -0.01 and p_value < 0.10:
                    status = "DECAYING"
                elif slope > 0.01 and p_value < 0.10:
                    status = "IMPROVING"
                else:
                    status = "STABLE"
                alpha_stability[method] = {
                    "slope": float(slope),
                    "r_squared": float(r_value**2),
                    "p_value": float(p_value),
                    "status": status,
                }
            else:
                alpha_stability[method] = {"slope": 0.0, "status": "INSUFFICIENT_DATA"}

        # Max drawdown per method
        max_dd: dict[str, float] = {}
        for method in methods:
            dds = [
                w.portfolio_metrics.get(method, {}).get("max_drawdown_pct", 0)
                for w in windows if w.portfolio_metrics
            ]
            max_dd[method] = float(max(dds)) if dds else 0.0

        # Long/short contribution (direction-agnostic across methods)
        long_rets: list[float] = []
        short_rets: list[float] = []
        for w in windows:
            for label, sm in w.strategy_metrics.items():
                direction = w.strategy_directions.get(label, "long")
                ret = sm.get("total_return_pct", 0)
                if direction == "short":
                    short_rets.append(ret)
                else:
                    long_rets.append(ret)
        ls_data = {
            "long": float(np.mean(long_rets)) if long_rets else 0.0,
            "short": float(np.mean(short_rets)) if short_rets else 0.0,
        }
        ls_contrib: dict[str, dict[str, float]] = {m: ls_data for m in methods}

        # Determine best method and overall pass
        n_regimes_positive = sum(
            1 for r in regime_perf.values() if r.get("sharpe", 0) > 0
        )
        best = best_method
        best_pct = pct_positive.get(best, 0)
        best_binom = binom_pv.get(best, 1.0)
        best_alpha = alpha_stability.get(best, {}).get("status", "?")
        best_dd = max_dd.get(best, 100.0)

        validation_pass = (
            best_pct >= 75.0
            and best_binom < 0.05
            and best_alpha != "DECAYING"
            and best_dd < 40.0
            and n_regimes_positive >= 4
        )

        return {
            "pct_positive_sharpe": pct_positive,
            "regime_performance": regime_perf,
            "alpha_stability": alpha_stability,
            "max_drawdown_by_method": max_dd,
            "long_short_contribution": ls_contrib,
            "binomial_p_value": binom_pv,
            "best_method": best,
            "validation_pass": validation_pass,
        }
