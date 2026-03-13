#!/usr/bin/env python3
"""Reproducible benchmark of the backtesting pipeline.

Loads real Binance 1m data, resamples to 1h, generates a grid of 1000+
combinations, and executes the full pipeline: grid → signals → engine →
metrics → Parquet serialisation.  Reports throughput, memory and phase
timings.

Usage
-----
    cd suitetrading
    .venv/bin/python scripts/benchmark_backtesting.py [--combos 1024] [--chunk 64]

Output
------
    data/benchmark_results.json   — raw numeric results
    stdout                        — human-readable summary
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# ── Ensure project root on sys.path ──────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.backtesting._internal.checkpoints import CheckpointManager
from suitetrading.backtesting._internal.datasets import build_dataset_from_df
from suitetrading.backtesting._internal.schemas import GridRequest, StrategySignals
from suitetrading.backtesting.engine import BacktestEngine
from suitetrading.backtesting.grid import ParameterGridBuilder
from suitetrading.backtesting.metrics import MetricsEngine
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.risk.archetypes.mean_reversion import MeanReversion
from suitetrading.risk.archetypes.trend_following import TrendFollowing


# ── CLI ───────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Backtesting pipeline benchmark")
    p.add_argument("--combos", type=int, default=1024,
                    help="Target number of grid combinations (default 1024)")
    p.add_argument("--chunk", type=int, default=64,
                    help="Chunk size for batch execution (default 64)")
    p.add_argument("--months", type=int, default=3,
                    help="Months of 1m data to load (default 3)")
    p.add_argument("--output", type=str, default="data/benchmark_results.json",
                    help="Path for JSON output")
    return p.parse_args()


# ── Data loading ──────────────────────────────────────────────────────

def load_and_resample(months: int) -> pd.DataFrame:
    """Load BTCUSDT 1m from Parquet, slice last *months*, resample to 1h."""
    store = ParquetStore(base_dir=ROOT / "data" / "raw")
    resampler = OHLCVResampler()

    df_1m = store.read("binance", "BTCUSDT", "1m")
    cutoff = df_1m.index.max() - pd.DateOffset(months=months)
    df_1m = df_1m.loc[df_1m.index >= cutoff]

    df_1h = resampler.resample(df_1m, "1h", base_tf="1m")
    return df_1h


# ── Signal generation ─────────────────────────────────────────────────

def make_momentum_signals(ohlcv: pd.DataFrame, period: int = 20) -> StrategySignals:
    """Simple SMA crossover: long when close crosses above SMA."""
    close = ohlcv["close"]
    sma = close.rolling(period, min_periods=period).mean()
    prev_close = close.shift(1)
    prev_sma = sma.shift(1)
    entry = ((close > sma) & (prev_close <= prev_sma)).fillna(False)
    return StrategySignals(entry_long=entry)


# ── Grid construction ─────────────────────────────────────────────────

def build_grid(target_combos: int) -> list:
    """Build a GridRequest that produces approximately *target_combos* configs."""
    # Use 2 symbols × 2 timeframes × 2 archetypes = 8 base combos.
    # To reach target_combos we expand the indicator space.
    # 8 * n_indicator_combos ≈ target_combos → n ≈ target/8 = 128
    # With 2 indicators × sqrt(128) ≈ 12 values each → 12*11 = 132 → 1056
    n_per_param = max(2, int(np.ceil(np.sqrt(target_combos / 8))))

    sma_periods = list(range(10, 10 + n_per_param))
    rsi_periods = list(range(7, 7 + n_per_param))

    req = GridRequest(
        symbols=["BTCUSDT", "ETHUSDT"],
        timeframes=["1h", "4h"],
        indicator_space={
            "sma": {"period": sma_periods},
            "rsi": {"period": rsi_periods},
        },
        risk_space={},
        archetypes=["trend_following", "mean_reversion"],
    )

    builder = ParameterGridBuilder()
    configs = builder.build(req)
    return configs[:target_combos]


# ── Benchmark execution ──────────────────────────────────────────────

def run_benchmark(args: argparse.Namespace) -> dict:
    results: dict = {"environment": _env_info(), "config": {}}

    # ── Phase 0: Data load ────────────────────────────────────────────
    t0 = time.perf_counter()
    tracemalloc.start()
    df_1h = load_and_resample(args.months)
    t_data = time.perf_counter() - t0
    mem_data = tracemalloc.get_traced_memory()[1] / 1024 / 1024
    tracemalloc.stop()

    results["data"] = {
        "bars": len(df_1h),
        "date_range": f"{df_1h.index[0]} → {df_1h.index[-1]}",
        "load_resample_sec": round(t_data, 3),
        "peak_memory_mb": round(mem_data, 1),
    }
    print(f"[Data] {len(df_1h)} bars loaded ({args.months}mo), {t_data:.2f}s, {mem_data:.1f} MB peak")

    # ── Phase 1: Grid generation ──────────────────────────────────────
    t1 = time.perf_counter()
    configs = build_grid(args.combos)
    t_grid = time.perf_counter() - t1

    results["config"] = {
        "target_combos": args.combos,
        "actual_combos": len(configs),
        "chunk_size": args.chunk,
    }
    results["grid"] = {"generation_sec": round(t_grid, 4), "combos": len(configs)}
    print(f"[Grid] {len(configs)} configs generated in {t_grid:.4f}s")

    # ── Phase 2: Chunked execution ────────────────────────────────────
    engine = BacktestEngine()
    metrics_engine = MetricsEngine()

    # Pre-build dataset/signals (shared across all configs — benchmark
    # measures engine throughput, not data I/O per run)
    dataset = build_dataset_from_df(df_1h, symbol="BTCUSDT", base_timeframe="1h")
    signals = make_momentum_signals(df_1h, period=20)

    chunks = ParameterGridBuilder.chunk(configs, args.chunk)

    all_metrics: list[dict] = []
    tracemalloc.start()
    t2 = time.perf_counter()

    for chunk_idx, chunk in enumerate(chunks):
        for cfg in chunk:
            archetype = cfg.archetype
            rc = (TrendFollowing().build_config()
                  if archetype == "trend_following"
                  else MeanReversion().build_config())

            res = engine.run(
                dataset=dataset,
                signals=signals,
                risk_config=rc,
                mode="auto",
            )

            m = metrics_engine.compute(
                equity_curve=res["equity_curve"],
                trades=res["trades"],
                initial_capital=rc.initial_capital,
            )
            m["run_id"] = cfg.run_id
            m["symbol"] = cfg.symbol
            m["timeframe"] = cfg.timeframe
            m["archetype"] = cfg.archetype
            all_metrics.append(m)

        if (chunk_idx + 1) % 4 == 0 or chunk_idx == len(chunks) - 1:
            elapsed = time.perf_counter() - t2
            done = (chunk_idx + 1) * args.chunk
            done = min(done, len(configs))
            rate = done / elapsed if elapsed > 0 else 0
            print(f"  [{done}/{len(configs)}] {rate:.1f} backtests/sec  ({elapsed:.1f}s)")

    t_exec = time.perf_counter() - t2
    mem_exec_peak = tracemalloc.get_traced_memory()[1] / 1024 / 1024
    tracemalloc.stop()

    throughput = len(configs) / t_exec if t_exec > 0 else 0
    results["execution"] = {
        "total_sec": round(t_exec, 3),
        "throughput_per_sec": round(throughput, 1),
        "throughput_per_min": round(throughput * 60, 0),
        "peak_memory_mb": round(mem_exec_peak, 1),
        "chunks": len(chunks),
        "errors": sum(1 for m in all_metrics if "error" in m),
    }
    print(f"[Exec] {len(configs)} runs in {t_exec:.2f}s — {throughput:.1f}/sec, {mem_exec_peak:.1f} MB peak")

    # ── Phase 3: Serialisation ────────────────────────────────────────
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        t3 = time.perf_counter()
        cm = CheckpointManager(Path(tmpdir) / "checkpoints")
        for i, chunk_metrics in enumerate(_ichunked(all_metrics, args.chunk)):
            cm.save_chunk_results(i, chunk_metrics)
        t_serial = time.perf_counter() - t3

        # Load back to verify
        df_results = cm.load_all_results()

    results["serialisation"] = {
        "parquet_write_sec": round(t_serial, 4),
        "parquet_write_pct_of_exec": round(t_serial / max(t_exec, 0.001) * 100, 2),
        "rows_written": len(df_results),
    }
    print(f"[Parquet] {len(df_results)} rows written in {t_serial:.4f}s ({results['serialisation']['parquet_write_pct_of_exec']:.1f}% of exec)")

    # ── Phase 4: Projection ───────────────────────────────────────────
    ratio_100k = 100_000 / len(configs) if len(configs) > 0 else 0
    results["projection_100k"] = {
        "estimated_sec": round(t_exec * ratio_100k, 1),
        "estimated_min": round(t_exec * ratio_100k / 60, 2),
        "estimated_memory_mb": round(mem_exec_peak * ratio_100k, 1),
        "note": "Linear extrapolation — actual may vary with dataset diversity and GC pressure",
    }
    est_min = results["projection_100k"]["estimated_min"]
    print(f"[Projection] 100K combos ≈ {est_min:.1f} min (linear extrapolation)")

    # ── Summary ───────────────────────────────────────────────────────
    total = t_data + t_grid + t_exec + t_serial
    results["total_wall_sec"] = round(total, 3)
    results["timestamp"] = datetime.now(timezone.utc).isoformat()

    return results


# ── Helpers ───────────────────────────────────────────────────────────

def _env_info() -> dict:
    import multiprocessing
    return {
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "machine": platform.machine(),
        "cpu_count": multiprocessing.cpu_count(),
    }


def _ichunked(lst: list, n: int):
    for i in range(0, len(lst), n):
        yield lst[i : i + n]


# ── Main ──────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    print(f"=== Backtesting Pipeline Benchmark ===")
    print(f"Target: {args.combos} combos, chunk_size={args.chunk}, data={args.months}mo\n")

    results = run_benchmark(args)

    out_path = ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2, default=str))
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
