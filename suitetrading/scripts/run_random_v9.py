"""V9 Exhaustive Random Search — without Optuna.

Generates random parameter sets, runs backtests via BacktestObjective.run_single(),
and stores results in Parquet (not SQLite).

Usage:
    python scripts/run_random_v9.py \
        --symbol SPY --direction long --timeframe 1h \
        --trials 300000 --step-factor 4 \
        --output-dir artifacts/exhaustive_v9

⚠️  METHODOLOGY: Random sampling WITHOUT optimizer.
    DO NOT change this to use NSGA-II/TPE without explicit user confirmation.
    See DIRECTION.md for full rationale.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from loguru import logger

# ── Paths ────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
SRC_DIR = PROJECT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))

from suitetrading.backtesting._internal.schemas import BacktestDataset
from suitetrading.config.archetypes import get_entry_indicators
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.indicators.registry import get_indicator
from suitetrading.optimization._internal.objective import (
    EXHAUSTIVE_RISK_SPACE,
    BacktestObjective,
    _smart_optional_range,
)

DATA_DIR = PROJECT_DIR / "data" / "raw"


# ── Random parameter generation ─────────────────────────────────────

def _random_value(
    schema: dict, step_factor: int, rng: np.random.Generator,
) -> int | float | str | bool:
    """Generate a single random value matching a param schema."""
    ptype = schema["type"]
    if ptype == "int":
        lo, hi = schema["min"], schema["max"]
        if step_factor > 1:
            step = max(1, (hi - lo) // max(1, (hi - lo) // step_factor))
            values = list(range(lo, hi + 1, step))
        else:
            values = list(range(lo, hi + 1))
        return int(rng.choice(values))
    if ptype == "float":
        lo, hi = schema["min"], schema["max"]
        step = schema.get("step")
        if step:
            n_steps = max(1, int(round((hi - lo) / step)))
            return float(lo + rng.integers(0, n_steps + 1) * step)
        return float(rng.uniform(lo, hi))
    if ptype == "str":
        choices = schema.get("choices", [])
        return str(rng.choice(choices)) if choices else ""
    if ptype == "bool":
        return bool(rng.choice([True, False]))
    raise ValueError(f"Unknown type: {ptype}")


MAX_EXCLUYENTE = 2
STATES = ["Excluyente", "Opcional", "Desactivado"]
TIMEFRAMES = ["grafico", "1_superior", "2_superiores"]


def generate_random_params(
    entry_indicators: list[str],
    indicator_names: list[str],
    risk_space: dict[str, dict],
    step_factor: int,
    rng: np.random.Generator,
) -> dict[str, object]:
    """Generate one complete random parameter set."""
    flat: dict[str, object] = {}
    entry_set = set(entry_indicators)

    # ── Indicator params ─────────────────────────────────────────
    states_assigned: dict[str, str] = {}
    for ind_name in indicator_names:
        indicator = get_indicator(ind_name)
        schema = indicator.params_schema()

        # Dynamic state/TF for entry indicators
        if ind_name in entry_set:
            state = str(rng.choice(STATES))
            states_assigned[ind_name] = state
            flat[f"{ind_name}____state"] = state
            flat[f"{ind_name}____timeframe"] = str(rng.choice(TIMEFRAMES))

        # Indicator params (with step_factor for regularization)
        for param_name, param_schema in schema.items():
            flat[f"{ind_name}__{param_name}"] = _random_value(
                param_schema, step_factor, rng,
            )

    # ── Enforce MAX_EXCLUYENTE ───────────────────────────────────
    excl_names = [n for n, s in states_assigned.items() if s == "Excluyente"]
    if len(excl_names) > MAX_EXCLUYENTE:
        for name in rng.choice(excl_names, len(excl_names) - MAX_EXCLUYENTE, replace=False):
            flat[f"{name}____state"] = "Opcional"
            states_assigned[name] = "Opcional"

    # ── Smart num_optional_required ──────────────────────────────
    excl_count = sum(1 for s in states_assigned.values() if s == "Excluyente")
    opc_count = sum(1 for s in states_assigned.values() if s == "Opcional")
    min_req, max_req = _smart_optional_range(excl_count, opc_count)
    if max_req > 0:
        flat["num_optional_required"] = int(rng.integers(min_req, max_req + 1))
    else:
        flat["num_optional_required"] = 1

    # ── Risk params (NO step_factor — already at designed granularity)
    for key, schema in risk_space.items():
        flat[key] = _random_value(schema, 1, rng)

    return flat


# ── Main runner ──────────────────────────────────────────────────────

FLUSH_EVERY = 5000  # Write parquet every N trials


def run_study(
    symbol: str,
    direction: str,
    timeframe: str,
    n_trials: int,
    step_factor: int,
    output_dir: Path,
    seed: int,
    months: int,
    exchange: str,
    commission: float,
) -> None:
    """Run a single study: random params → backtest → Parquet."""
    study_name = f"{symbol}_{timeframe}_rich_stock_{direction}"
    parquet_dir = output_dir / "parquet"
    parquet_dir.mkdir(parents=True, exist_ok=True)

    # ── Check for existing results (resume) ──────────────────────
    existing_files = sorted(parquet_dir.glob(f"{study_name}_*.parquet"))
    existing_trials = 0
    if existing_files:
        for f in existing_files:
            existing_trials += len(pd.read_parquet(f, columns=["trial_id"]))
        if existing_trials >= n_trials:
            logger.info("{}: already has {} trials, skipping", study_name, existing_trials)
            return
        logger.info("{}: resuming from {} trials", study_name, existing_trials)

    remaining = n_trials - existing_trials

    # ── Load data (1m → resample to target TF) ────────────────────
    store = ParquetStore(base_dir=DATA_DIR)
    df_1m = store.read(exchange, symbol, "1m")
    cutoff = df_1m.index.max() - pd.DateOffset(months=months)
    df_1m = df_1m.loc[df_1m.index >= cutoff]

    if timeframe == "1m":
        ohlcv = df_1m
    else:
        resampler = OHLCVResampler()
        ohlcv = resampler.resample(df_1m, timeframe, base_tf="1m")
    logger.info("{}: {} bars loaded", study_name, len(ohlcv))

    dataset = BacktestDataset(
        exchange=exchange, symbol=symbol,
        base_timeframe=timeframe, ohlcv=ohlcv,
    )

    # ── Build objective (reuse build_signals/build_risk_config) ──
    entry_indicators = get_entry_indicators("rich_stock")
    objective = BacktestObjective(
        dataset=dataset,
        indicator_names=list(entry_indicators),
        auxiliary_indicators=["firestorm_tm"],
        archetype="rich_stock",
        direction=direction,
        metric="sharpe",
        risk_search_space=EXHAUSTIVE_RISK_SPACE,
        mode="fsm",
        commission_pct=commission,
        step_factor=step_factor,
    )

    indicator_names = list(entry_indicators)
    rng = np.random.default_rng(seed + existing_trials)

    # ── Run trials ───────────────────────────────────────────────
    batch: list[dict] = []
    chunk_id = len(existing_files)
    t0 = time.perf_counter()
    completed = 0
    errors = 0

    for i in range(remaining):
        trial_id = existing_trials + i
        params = generate_random_params(
            entry_indicators, indicator_names,
            EXHAUSTIVE_RISK_SPACE, step_factor, rng,
        )

        try:
            result = objective.run_single(params)
            metrics = result["metrics"]
            row = {
                "trial_id": trial_id,
                "sharpe": float(metrics.get("sharpe", 0.0)),
                "sortino": float(metrics.get("sortino", 0.0)),
                "calmar": float(metrics.get("calmar", 0.0)),
                "max_drawdown_pct": float(metrics.get("max_drawdown_pct", 0.0)),
                "net_profit": float(metrics.get("net_profit", 0.0)),
                "total_return_pct": float(metrics.get("total_return_pct", 0.0)),
                "total_trades": int(metrics.get("total_trades", 0)),
                "win_rate": float(metrics.get("win_rate", 0.0)),
                "profit_factor": float(metrics.get("profit_factor", 0.0)),
                "average_trade": float(metrics.get("average_trade", 0.0)),
                "max_consecutive_losses": int(metrics.get("max_consecutive_losses", 0)),
                **params,
            }
            batch.append(row)
            completed += 1
        except Exception as e:
            errors += 1
            if errors <= 5:
                logger.warning("Trial {} error: {}", trial_id, e)
            continue

        # ── Flush to Parquet ─────────────────────────────────────
        if len(batch) >= FLUSH_EVERY:
            chunk_path = parquet_dir / f"{study_name}_{chunk_id:04d}.parquet"
            pd.DataFrame(batch).to_parquet(chunk_path, compression="zstd")
            elapsed = time.perf_counter() - t0
            rate = completed / elapsed
            eta_h = (remaining - completed) / rate / 3600 if rate > 0 else 0
            logger.info(
                "{}: {}/{} trials ({:.1f}/sec), chunk {} saved, ETA {:.1f}h",
                study_name, completed + existing_trials, n_trials,
                rate, chunk_id, eta_h,
            )
            batch = []
            chunk_id += 1

    # ── Final flush ──────────────────────────────────────────────
    if batch:
        chunk_path = parquet_dir / f"{study_name}_{chunk_id:04d}.parquet"
        pd.DataFrame(batch).to_parquet(chunk_path, compression="zstd")

    elapsed = time.perf_counter() - t0
    rate = completed / elapsed if elapsed > 0 else 0
    logger.info(
        "{}: DONE — {} trials in {:.0f}s ({:.1f}/sec), {} errors",
        study_name, completed + existing_trials, elapsed, rate, errors,
    )


# ── CLI ──────────────────────────────────────────────────────────────

def main() -> None:
    p = argparse.ArgumentParser(description="V9 Random Exhaustive Search (no Optuna)")
    p.add_argument("--symbol", required=True)
    p.add_argument("--direction", required=True, choices=["long", "short"])
    p.add_argument("--timeframe", default="1h")
    p.add_argument("--trials", type=int, default=300000)
    p.add_argument("--step-factor", type=int, default=4)
    p.add_argument("--output-dir", type=Path, default=Path("artifacts/exhaustive_v9"))
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--months", type=int, default=60)
    p.add_argument("--exchange", default="alpaca")
    p.add_argument("--commission", type=float, default=0.0)
    args = p.parse_args()

    run_study(
        symbol=args.symbol,
        direction=args.direction,
        timeframe=args.timeframe,
        n_trials=args.trials,
        step_factor=args.step_factor,
        output_dir=args.output_dir,
        seed=args.seed,
        months=args.months,
        exchange=args.exchange,
        commission=args.commission,
    )


if __name__ == "__main__":
    main()
