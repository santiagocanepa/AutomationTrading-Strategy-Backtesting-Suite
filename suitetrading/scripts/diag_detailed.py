#!/usr/bin/env python3
"""Detailed diagnostic: 100 trials per archetype with exit-mechanism stats."""
import sys
from collections import Counter
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
TRIALS = 100
TOP_N = 5

store = ParquetStore(base_dir=ROOT / "data" / "raw")
df_1m = store.read("binance", SYMBOL, "1m")
cutoff = df_1m.index.max() - pd.DateOffset(months=36)
df_1m = df_1m.loc[df_1m.index >= cutoff]
ohlcv = OHLCVResampler().resample(df_1m, TF, base_tf="1m")
dataset = build_dataset_from_df(ohlcv, exchange="binance", symbol=SYMBOL, base_timeframe=TF)

print(f"Data: {SYMBOL} {TF} — {len(ohlcv)} bars, 100 trials/archetype\n")

# --- Quick signal rate check for best mixed params ---
for arch in ARCHETYPE_INDICATORS:
    entry = get_entry_indicators(arch)
    aux = get_auxiliary_indicators(arch)
    all_inds = entry + aux

    db = ROOT / "artifacts" / "discovery" / f"diag100_{arch}.db"
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
        study_name=f"diag100_{arch}",
        storage=f"sqlite:///{db}",
        sampler="tpe",
        direction="maximize",
        seed=42,
    )
    opt.optimize(n_trials=TRIALS)
    top = opt.get_top_n(TOP_N)

    # Get best trial's detailed metrics
    best = top[0]
    m = eval(best["metrics"]) if isinstance(best["metrics"], str) else best["metrics"]

    # Run single to get trade list
    result = obj.run_single(best["params"])
    trades_data = result.get("trades")

    # Handle both DataFrame and list of TradeRecord
    if trades_data is None:
        trade_list = []
    elif isinstance(trades_data, pd.DataFrame):
        trade_list = trades_data.to_dict("records") if not trades_data.empty else []
    elif isinstance(trades_data, list):
        trade_list = [
            {"pnl": t.pnl, "commission": t.commission, "exit_reason": t.exit_reason}
            if hasattr(t, "pnl") else t
            for t in trades_data
        ]
    else:
        trade_list = []

    # Exit reason distribution
    reasons = Counter(t.get("exit_reason", t.get("reason", "?")) if isinstance(t, dict) else t.exit_reason for t in trade_list) if trade_list else Counter()

    # Win/loss stats
    def _pnl(t):
        return t["pnl"] if isinstance(t, dict) else t.pnl
    def _comm(t):
        return t.get("commission", 0) if isinstance(t, dict) else getattr(t, "commission", 0)

    wins = [t for t in trade_list if _pnl(t) > 0]
    losses = [t for t in trade_list if _pnl(t) <= 0]
    n_trades = len(trade_list)
    win_rate = len(wins) / n_trades * 100 if n_trades else 0
    avg_win = np.mean([_pnl(t) for t in wins]) if wins else 0
    avg_loss = np.mean([abs(_pnl(t)) for t in losses]) if losses else 0
    total_comm = sum(_comm(t) for t in trade_list)
    gross_pnl = sum(_pnl(t) for t in trade_list)

    vals = [t["value"] for t in top]
    pos_count = sum(1 for v in vals if v > 0)

    print(f"═══ {arch.upper()} ═══")
    print(f"  Best Sharpe: {vals[0]:+.4f}  |  Top-5: {[f'{v:+.4f}' for v in vals]}")
    print(f"  Positive in top-5: {pos_count}/5")
    print(f"  Trades: {n_trades}  |  Win rate: {win_rate:.1f}%  |  PF: {m.get('profit_factor', 0):.3f}")
    print(f"  Avg win: ${avg_win:.2f}  |  Avg loss: ${avg_loss:.2f}  |  R:R: {avg_win/avg_loss:.2f}" if avg_loss > 0 else "")
    print(f"  Gross PnL: ${gross_pnl:.2f}  |  Commissions: ${total_comm:.2f}  |  Net: ${gross_pnl - total_comm:.2f}")
    print(f"  Exit reasons: {dict(reasons)}")
    print()

    db.unlink(missing_ok=True)
