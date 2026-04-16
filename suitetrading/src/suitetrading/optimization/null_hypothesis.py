"""Null Hypothesis Permutation Test for the discovery pipeline.

Validates that the Optuna → WFO → CSCV/PBO pipeline does not produce
false positives by running it on data with permuted returns (no signal).

If the pipeline finds few candidates (<3% hit rate) on permuted data
but many (12.6%) on real data, the methodology is statistically valid.

References
----------
- White, H. (2000). "A Reality Check for Data Snooping."
- Bailey, D. H. et al. (2017). "The Probability of Backtest Overfitting."
"""

from __future__ import annotations

import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from loguru import logger
from scipy import stats


# ── OHLCV Permutation ────────────────────────────────────────────────


def permute_ohlcv(df_1m: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Permute OHLCV bar features, destroying temporal structure.

    Preserves
    ---------
    - Distribution of log returns (same values, different order)
    - Intra-bar consistency (ratios + return from same bar stay together)
    - Volume distribution
    - DatetimeIndex (unchanged)

    Destroys
    --------
    - Autocorrelation (trends, mean-reversion, momentum)
    - Any temporal signal or pattern
    """
    rng = np.random.default_rng(seed)

    close = df_1m["close"].values.astype(np.float64)
    high = df_1m["high"].values.astype(np.float64)
    low = df_1m["low"].values.astype(np.float64)
    open_ = df_1m["open"].values.astype(np.float64)
    volume = df_1m["volume"].values.astype(np.float64)

    n = len(close)
    if n < 2:
        return df_1m.copy()

    # Per-bar features
    log_returns = np.log(close[1:] / np.maximum(close[:-1], 1e-12))
    high_ratio = high / np.maximum(close, 1e-12)
    low_ratio = low / np.maximum(close, 1e-12)
    open_ratio = open_ / np.maximum(close, 1e-12)

    # Permute bars 1..n-1 together (bar 0 is anchor point)
    perm = rng.permutation(n - 1)
    shuffled_returns = log_returns[perm]
    shuffled_high_ratio = high_ratio[1:][perm]
    shuffled_low_ratio = low_ratio[1:][perm]
    shuffled_open_ratio = open_ratio[1:][perm]
    shuffled_volume = volume[1:][perm]

    # Reconstruct smooth close from shuffled log returns
    new_close = np.empty(n, dtype=np.float64)
    new_close[0] = close[0]
    new_close[1:] = close[0] * np.exp(np.cumsum(shuffled_returns))

    # Reconstruct OHL from permuted ratios × reconstructed close
    new_open = np.empty(n, dtype=np.float64)
    new_high = np.empty(n, dtype=np.float64)
    new_low = np.empty(n, dtype=np.float64)
    new_volume = np.empty(n, dtype=np.float64)

    # Bar 0: original ratios applied to anchor close
    new_open[0] = open_ratio[0] * new_close[0]
    new_high[0] = high_ratio[0] * new_close[0]
    new_low[0] = low_ratio[0] * new_close[0]
    new_volume[0] = volume[0]

    # Bars 1..n-1: shuffled ratios applied to new close
    new_open[1:] = shuffled_open_ratio * new_close[1:]
    new_high[1:] = shuffled_high_ratio * new_close[1:]
    new_low[1:] = shuffled_low_ratio * new_close[1:]
    new_volume[1:] = shuffled_volume

    # Clamp: high >= max(open, close), low <= min(open, close)
    new_high = np.maximum(new_high, np.maximum(new_open, new_close))
    new_low = np.minimum(new_low, np.minimum(new_open, new_close))

    return pd.DataFrame(
        {
            "open": new_open,
            "high": new_high,
            "low": new_low,
            "close": new_close,
            "volume": new_volume,
        },
        index=df_1m.index,
    )


# ── Data contracts ───────────────────────────────────────────────────


@dataclass
class NullStudyConfig:
    """Configuration for a single null hypothesis study."""

    exchange: str
    symbol: str
    tf: str
    archetype: str
    direction: str
    seed: int
    n_trials: int = 200
    top_n: int = 50
    commission_pct: float = 0.04
    pbo_threshold: float = 0.20
    wfo_splits: int = 5
    wfo_min_is: int = 500
    wfo_min_oos: int = 100
    wfo_gap: int = 20


@dataclass
class NullStudyResult:
    """Result from a single null hypothesis study."""

    pbo: float
    n_passed_pbo: int
    n_passed_dsr: int
    best_optuna_value: float
    wall_time: float
    error: str | None = None
    symbol: str = ""
    tf: str = ""
    archetype: str = ""
    direction: str = ""
    seed: int = 0


@dataclass
class NullHypothesisResult:
    """Aggregated result from the full null hypothesis test."""

    null_hit_rate: float
    real_hit_rate: float
    p_value: float
    is_valid: bool
    n_null_studies: int
    n_null_passed: int
    n_errors: int
    per_seed: dict[int, float]
    per_study: list[dict[str, Any]]
    timestamp: str = ""


# ── Helpers ──────────────────────────────────────────────────────────


def _extract_candidate_params(
    top_trials: list[dict[str, Any]],
    indicator_names: list[str],
) -> list[dict[str, Any]]:
    """Convert flat Optuna params to structured format for WFO.

    Copied from ``scripts/run_discovery.py`` — logic must stay in sync.
    """
    ind_set = set(indicator_names)
    candidates = []
    for trial in top_trials:
        flat = trial["params"]
        ind_params: dict[str, dict[str, Any]] = {}
        risk_overrides: dict[str, Any] = {}

        for key, value in flat.items():
            parts = key.split("__", 1)
            if len(parts) == 2 and parts[0] in ind_set:
                ind_params.setdefault(parts[0], {})[parts[1]] = value
            else:
                risk_overrides[key] = value

        candidates.append({
            "indicator_params": ind_params,
            "risk_overrides": risk_overrides,
            "trial_number": trial.get("trial_number"),
            "optuna_value": trial.get("value"),
        })
    return candidates


def _register_factory_archetypes() -> None:
    """Register factory-generated archetypes (idempotent).

    Required in each worker process when using ProcessPoolExecutor.
    """
    try:
        from suitetrading.config.archetypes import ARCHETYPE_INDICATORS
        from suitetrading.risk.archetypes import ARCHETYPE_REGISTRY
        from suitetrading.risk.archetypes._factory import generate_factory_archetypes

        if any(k.endswith("_fullrisk_pyr") for k in ARCHETYPE_INDICATORS):
            return  # Already registered

        registry_add, indicator_add = generate_factory_archetypes()
        for name, cls in registry_add.items():
            if name not in ARCHETYPE_REGISTRY:
                ARCHETYPE_REGISTRY[name] = cls
        for name, cfg in indicator_add.items():
            if name not in ARCHETYPE_INDICATORS:
                ARCHETYPE_INDICATORS[name] = cfg
    except Exception as e:
        logger.debug("Factory archetype registration skipped: {}", e)


# ── Single study execution (top-level for pickling) ──────────────────


def run_null_study(
    cfg: NullStudyConfig,
    data_dir: Path,
    months: int,
    *,
    _preloaded_1m: pd.DataFrame | None = None,
) -> NullStudyResult:
    """Run one null hypothesis study on permuted data.

    Top-level function, pickleable for ``ProcessPoolExecutor``.
    Pipeline: load 1m → permute → resample → Optuna → WFO → CSCV/PBO.

    Parameters
    ----------
    cfg
        Study configuration.
    data_dir
        Root directory for parquet data store.
    months
        Months of data to use.
    _preloaded_1m
        Pre-loaded 1m DataFrame for testing (skips disk load).
    """
    from suitetrading.backtesting._internal.datasets import build_dataset_from_df
    from suitetrading.config.archetypes import (
        get_auxiliary_indicators,
        get_entry_indicators,
    )
    from suitetrading.data.resampler import OHLCVResampler
    from suitetrading.data.storage import ParquetStore
    from suitetrading.optimization import (
        CSCVValidator,
        OptunaOptimizer,
        WalkForwardEngine,
        deflated_sharpe_ratio,
    )
    from suitetrading.optimization._internal.objective import BacktestObjective
    from suitetrading.optimization._internal.schemas import WFOConfig

    t0 = time.perf_counter()

    def _make_result(
        pbo: float = 1.0,
        n_pbo: int = 0,
        n_dsr: int = 0,
        best_val: float = float("nan"),
        error: str | None = None,
    ) -> NullStudyResult:
        return NullStudyResult(
            pbo=pbo,
            n_passed_pbo=n_pbo,
            n_passed_dsr=n_dsr,
            best_optuna_value=best_val,
            wall_time=time.perf_counter() - t0,
            error=error,
            symbol=cfg.symbol,
            tf=cfg.tf,
            archetype=cfg.archetype,
            direction=cfg.direction,
            seed=cfg.seed,
        )

    try:
        _register_factory_archetypes()

        # ── Load & permute ────────────────────────────────────────
        if _preloaded_1m is not None:
            df_1m = _preloaded_1m
        else:
            store = ParquetStore(base_dir=data_dir)
            df_1m = store.read(cfg.exchange, cfg.symbol, "1m")
            cutoff = df_1m.index.max() - pd.DateOffset(months=months)
            df_1m = df_1m.loc[df_1m.index >= cutoff]

        df_perm = permute_ohlcv(df_1m, cfg.seed)

        # ── Resample to target TF ────────────────────────────────
        if cfg.tf != "1m":
            ohlcv = OHLCVResampler().resample(df_perm, cfg.tf, base_tf="1m")
        else:
            ohlcv = df_perm

        dataset = build_dataset_from_df(
            ohlcv,
            exchange=cfg.exchange,
            symbol=cfg.symbol,
            base_timeframe=cfg.tf,
        )

        # ── Indicator setup ──────────────────────────────────────
        entry_indicators = get_entry_indicators(cfg.archetype)
        auxiliary_indicators = get_auxiliary_indicators(cfg.archetype)
        all_indicators = entry_indicators + auxiliary_indicators

        # ── Optuna search (in-memory, ephemeral) ─────────────────
        objective = BacktestObjective(
            dataset=dataset,
            indicator_names=all_indicators,
            auxiliary_indicators=auxiliary_indicators,
            archetype=cfg.archetype,
            direction=cfg.direction,
            metric="sharpe",
            mode="fsm",
            commission_pct=cfg.commission_pct,
        )

        sname = (
            f"null_{cfg.symbol}_{cfg.tf}_{cfg.archetype}"
            f"_{cfg.direction}_s{cfg.seed}"
        )
        optimizer = OptunaOptimizer(
            objective=objective,
            study_name=sname,
            storage=None,
            sampler="tpe",
            direction="maximize",
            seed=cfg.seed,
        )

        opt_result = optimizer.optimize(n_trials=cfg.n_trials)
        best_val = opt_result.best_value

        # ── Extract top-N for WFO ────────────────────────────────
        top_n = min(cfg.top_n, opt_result.n_completed)
        if top_n < 2:
            return _make_result(best_val=best_val, error="too_few_completed_trials")

        top_trials = optimizer.get_top_n(top_n)
        candidates = _extract_candidate_params(top_trials, all_indicators)

        # ── Walk-Forward Optimization ────────────────────────────
        wfo_config = WFOConfig(
            n_splits=cfg.wfo_splits,
            min_is_bars=cfg.wfo_min_is,
            min_oos_bars=cfg.wfo_min_oos,
            gap_bars=cfg.wfo_gap,
            mode="rolling",
        )

        n_bars = len(dataset.ohlcv)
        min_required = (
            wfo_config.min_is_bars + wfo_config.gap_bars + wfo_config.min_oos_bars
        )
        if n_bars < min_required:
            return _make_result(
                best_val=best_val,
                error=f"insufficient_bars: {n_bars} < {min_required}",
            )

        wfo = WalkForwardEngine(
            config=wfo_config,
            metric="sharpe",
            auxiliary_indicators=auxiliary_indicators,
            commission_pct=cfg.commission_pct,
        )

        wfo_candidates = [
            {
                "indicator_params": c["indicator_params"],
                "risk_overrides": c["risk_overrides"],
            }
            for c in candidates
        ]

        wfo_result = wfo.run(
            dataset=dataset,
            candidate_params=wfo_candidates,
            archetype=cfg.archetype,
            direction=cfg.direction,
            mode="fsm",
        )

        # ── CSCV → PBO ──────────────────────────────────────────
        oos_curves = {
            k: v
            for k, v in wfo_result.oos_equity_curves.items()
            if isinstance(v, np.ndarray) and len(v) > 0
        }

        if len(oos_curves) < 2:
            return _make_result(best_val=best_val, error="insufficient_oos_curves")

        min_len = min(len(v) for v in oos_curves.values())
        cscv_min_bars = 32
        if min_len < cscv_min_bars:
            return _make_result(
                best_val=best_val,
                error=f"oos_curves_too_short: {min_len} < {cscv_min_bars}",
            )

        truncated = {k: v[:min_len] for k, v in oos_curves.items()}
        cscv = CSCVValidator(n_subsamples=16, metric="sharpe")
        cscv_result = cscv.compute_pbo(truncated)

        n_passed_pbo = len(oos_curves) if cscv_result.pbo < cfg.pbo_threshold else 0

        # ── DSR per candidate ────────────────────────────────────
        n_passed_dsr = 0
        total_trials = opt_result.n_completed

        for curve in oos_curves.values():
            rets = np.diff(curve) / np.maximum(curve[:-1], 1e-10)
            rets_clean = rets[np.isfinite(rets)]
            if len(rets_clean) < 30:
                continue

            std_r = float(np.std(rets_clean, ddof=1))
            obs_sharpe = (
                float(np.mean(rets_clean)) / std_r if std_r > 1e-12 else 0.0
            )

            dsr_result = deflated_sharpe_ratio(
                observed_sharpe=obs_sharpe,
                n_trials=total_trials,
                sample_length=len(rets_clean),
                skewness=float(stats.skew(rets_clean)),
                kurtosis=float(stats.kurtosis(rets_clean, fisher=False)),
            )
            if dsr_result.is_significant:
                n_passed_dsr += 1

        return _make_result(
            pbo=cscv_result.pbo,
            n_pbo=n_passed_pbo,
            n_dsr=n_passed_dsr,
            best_val=best_val,
        )

    except Exception as e:
        logger.error("Null study failed ({}): {}", cfg.archetype, e)
        return _make_result(error=str(e))


# ── Full test orchestrator ───────────────────────────────────────────


class NullHypothesisTest:
    """Orchestrates the null hypothesis permutation test.

    Generates ``NullStudyConfig`` → runs in parallel via
    ``ProcessPoolExecutor`` → analyzes with binomial test.
    """

    def __init__(
        self,
        *,
        symbols: list[str],
        timeframes: list[str],
        archetypes: list[str],
        directions: list[str] | tuple[str, ...] = ("long", "short"),
        seeds: list[int] | range,
        n_trials: int = 200,
        top_n: int = 50,
        months: int = 12,
        pbo_threshold: float = 0.20,
        real_hit_rate: float = 0.126,
        real_total: int = 2619,
        max_workers: int = 8,
        data_dir: Path | str = Path("data/raw"),
    ) -> None:
        self._symbols = list(symbols)
        self._timeframes = list(timeframes)
        self._archetypes = list(archetypes)
        self._directions = list(directions)
        self._seeds = list(seeds)
        self._n_trials = n_trials
        self._top_n = top_n
        self._months = months
        self._pbo_threshold = pbo_threshold
        self._real_hit_rate = real_hit_rate
        self._real_total = real_total
        self._real_hits = round(real_hit_rate * real_total)
        self._max_workers = max_workers
        self._data_dir = Path(data_dir)

    def _generate_configs(self) -> list[NullStudyConfig]:
        """Build one NullStudyConfig per (symbol, tf, archetype, dir, seed)."""
        configs: list[NullStudyConfig] = []
        for symbol in self._symbols:
            exchange = "binance" if symbol.endswith("USDT") else "alpaca"
            commission = 0.04 if exchange == "binance" else 0.0
            for tf in self._timeframes:
                for archetype in self._archetypes:
                    for direction in self._directions:
                        for seed in self._seeds:
                            configs.append(
                                NullStudyConfig(
                                    exchange=exchange,
                                    symbol=symbol,
                                    tf=tf,
                                    archetype=archetype,
                                    direction=direction,
                                    seed=seed,
                                    n_trials=self._n_trials,
                                    top_n=self._top_n,
                                    commission_pct=commission,
                                    pbo_threshold=self._pbo_threshold,
                                )
                            )
        return configs

    def run(self) -> NullHypothesisResult:
        """Execute all null studies in parallel and return analysis."""
        _register_factory_archetypes()

        configs = self._generate_configs()
        total = len(configs)
        logger.info(
            "Null hypothesis test: {} studies "
            "({} sym × {} tf × {} arch × {} dir × {} seeds)",
            total,
            len(self._symbols),
            len(self._timeframes),
            len(self._archetypes),
            len(self._directions),
            len(self._seeds),
        )

        results: list[NullStudyResult] = []
        with ProcessPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {
                pool.submit(
                    run_null_study, cfg, self._data_dir, self._months
                ): cfg
                for cfg in configs
            }
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                status = (
                    "PASS"
                    if result.error is None and result.pbo < self._pbo_threshold
                    else f"ERR({result.error[:30]})"
                    if result.error
                    else "FAIL"
                )
                logger.info(
                    "[{}/{}] {}_{}_{}_{}  seed={}: PBO={:.3f} [{}] ({:.1f}s)",
                    len(results),
                    total,
                    result.symbol,
                    result.tf,
                    result.archetype,
                    result.direction,
                    result.seed,
                    result.pbo,
                    status,
                    result.wall_time,
                )

        return self._analyze(results)

    def _analyze(self, results: list[NullStudyResult]) -> NullHypothesisResult:
        """Compute null hit rate, binomial p-value, per-seed breakdown."""
        valid = [r for r in results if r.error is None]
        n_errors = len(results) - len(valid)

        if not valid:
            return NullHypothesisResult(
                null_hit_rate=0.0,
                real_hit_rate=self._real_hit_rate,
                p_value=1.0,
                is_valid=False,
                n_null_studies=len(results),
                n_null_passed=0,
                n_errors=n_errors,
                per_seed={},
                per_study=[],
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        n_passed = sum(1 for r in valid if r.pbo < self._pbo_threshold)
        null_rate = n_passed / len(valid)

        # Per-seed breakdown
        per_seed: dict[int, float] = {}
        for seed in sorted(set(r.seed for r in valid)):
            seed_results = [r for r in valid if r.seed == seed]
            seed_passed = sum(
                1 for r in seed_results if r.pbo < self._pbo_threshold
            )
            per_seed[seed] = seed_passed / len(seed_results)

        # Binomial p-value: P(X >= real_hits | p=null_rate, n=real_total)
        from scipy.stats import binom

        if null_rate > 0:
            p_value = float(
                1.0 - binom.cdf(self._real_hits - 1, self._real_total, null_rate)
            )
        else:
            p_value = 0.0  # null produces nothing → real hits are genuine

        is_valid = null_rate < 0.05

        # Per-study breakdown for export
        per_study = [
            {
                "symbol": r.symbol,
                "tf": r.tf,
                "archetype": r.archetype,
                "direction": r.direction,
                "seed": r.seed,
                "pbo": r.pbo,
                "n_passed_pbo": r.n_passed_pbo,
                "n_passed_dsr": r.n_passed_dsr,
                "best_optuna_value": r.best_optuna_value,
                "wall_time": round(r.wall_time, 1),
                "error": r.error,
                "passed": r.error is None and r.pbo < self._pbo_threshold,
            }
            for r in results
        ]

        return NullHypothesisResult(
            null_hit_rate=null_rate,
            real_hit_rate=self._real_hit_rate,
            p_value=p_value,
            is_valid=is_valid,
            n_null_studies=len(results),
            n_null_passed=n_passed,
            n_errors=n_errors,
            per_seed=per_seed,
            per_study=per_study,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def save_results(
        self, result: NullHypothesisResult, output_dir: Path,
    ) -> Path:
        """Save results to JSON in the output directory."""
        output_dir.mkdir(parents=True, exist_ok=True)
        ts = result.timestamp.replace(":", "-").split(".")[0]
        path = output_dir / f"null_hypothesis_{ts}.json"

        data = asdict(result)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)

        logger.info("Results saved to {}", path)
        return path

    @staticmethod
    def print_report(result: NullHypothesisResult) -> None:
        """Print a formatted summary of the null hypothesis test."""
        sep = "=" * 60
        print(f"\n{sep}")
        print("  NULL HYPOTHESIS PERMUTATION TEST")
        print(sep)
        print(f"  Timestamp:       {result.timestamp}")
        print(f"  Total studies:   {result.n_null_studies}")
        print(f"  Errors:          {result.n_errors}")
        print(f"  Null passed:     {result.n_null_passed}")
        print(
            f"  Null hit rate:   {result.null_hit_rate:.4f} "
            f"({result.null_hit_rate * 100:.1f}%)"
        )
        print(
            f"  Real hit rate:   {result.real_hit_rate:.4f} "
            f"({result.real_hit_rate * 100:.1f}%)"
        )
        print(f"  p-value:         {result.p_value:.6f}")
        print(f"  Pipeline valid:  {'YES' if result.is_valid else 'NO'}")
        print()

        # Interpretation
        print("  Interpretation:")
        if result.null_hit_rate < 0.02:
            print("    Excellent — minimal false positives")
        elif result.null_hit_rate < 0.05:
            print("    Acceptable — real alpha >> null")
        elif result.null_hit_rate < 0.10:
            print("    Questionable — needs review")
        else:
            print("    Pipeline has selection bias — results unreliable")
        print()

        # Per-seed
        if result.per_seed:
            print("  Per-seed hit rates:")
            for seed, rate in sorted(result.per_seed.items()):
                print(f"    seed {seed}: {rate:.3f}")
        print(sep)
