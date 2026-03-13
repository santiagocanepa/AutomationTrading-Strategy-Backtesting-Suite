#!/usr/bin/env python3
"""Quick multi-archetype diagnostic: 30 trials per archetype, single symbol+TF.
Goal: identify which archetypes produce positive Sharpe at all.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

from loguru import logger
logger.remove()
logger.add(sys.stderr, level="WARNING")

from suitetrading.backtesting._internal.datasets import build_dataset_from_df
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.optimization._internal.objective import BacktestObjective
from suitetrading.optimization import OptunaOptimizer
from suitetrading.config.archetypes import (
    ARCHETYPE_INDICATORS,
    get_entry_indicators,
    get_auxiliary_indicators,
)

SYMBOL = "BTCUSDT"
TF = "1h"
TRIALS = 30
TOP_N = 5

store = ParquetStore(base_dir=ROOT / "data" / "raw")
df_1m = store.read("binance", SYMBOL, "1m")
cutoff = df_1m.index.max() - pd.DateOffset(months=36)
df_1m = df_1m.loc[df_1m.index >= cutoff]
ohlcv = OHLCVResampler().resample(df_1m, TF, base_tf="1m")
dataset = build_dataset_from_df(ohlcv, exchange="binance", symbol=SYMBOL, base_timeframe=TF)

print(f"Data: {SYMBOL} {TF} — {len(ohlcv)} bars\n")
print(f"{'Archetype':<20} {'Best SR':>8} {'#2 SR':>8} {'#3 SR':>8} {'Trades':>7} {'Ret%':>8} {'PF':>6}")
print("-" * 70)

for arch in ARCHETYPE_INDICATORS:
    entry = get_entry_indicators(arch)
    aux = get_auxiliary_indicators(arch)
    all_inds = entry + aux

    db = ROOT / "artifacts" / "discovery" / f"diag_{arch}.db"
    db.unlink(missing_ok=True)

    obj = BacktestObjective(
        dataset=dataset,
        indicator_names=all_inds,
        auxiliary_indicators=aux,
        archetype=arch,
        metric="sharpe",
        mode="fsm",
    )

    opt = OptunaOptimizer(
        objective=obj,
        study_name=f"diag_{arch}",
        storage=f"sqlite:///{db}",
        sampler="tpe",
        direction="maximize",
        seed=42,
    )
    opt.optimize(n_trials=TRIALS)
    top = opt.get_top_n(TOP_N)

    values = [t["value"] for t in top]
    best_m = eval(top[0]["metrics"]) if isinstance(top[0]["metrics"], str) else top[0]["metrics"]
    trades = best_m.get("total_trades", 0)
    ret = best_m.get("total_return_pct", 0)
    pf = best_m.get("profit_factor", 0)

    v2 = values[1] if len(values) > 1 else float("nan")
    v3 = values[2] if len(values) > 2 else float("nan")

    marker = " ✓" if values[0] > 0 else " ✗"
    print(f"{arch:<20} {values[0]:>+8.4f} {v2:>+8.4f} {v3:>+8.4f} {trades:>7d} {ret:>+8.2f} {pf:>6.3f}{marker}")

    db.unlink(missing_ok=True)

print("\n✓ = positive Sharpe found, ✗ = all negative")
