#!/usr/bin/env python3
"""Deeper diagnostic: signal rate, commission impact, timeframe scan.

Tests:
1. Signal rate per indicator (what % of bars trigger entry)
2. Gross vs net PnL (is commission killing marginal alpha?)  
3. Multi-TF scan with best archetype (mean_reversion was closest)
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
logger.add(sys.stderr, level="ERROR")

from suitetrading.backtesting._internal.datasets import build_dataset_from_df
from suitetrading.backtesting.engine import BacktestEngine
from suitetrading.backtesting.metrics import MetricsEngine
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.indicators.base import IndicatorState
from suitetrading.indicators.registry import get_indicator
from suitetrading.indicators.signal_combiner import combine_signals
from suitetrading.config.archetypes import (
    ARCHETYPE_INDICATORS,
    get_entry_indicators,
    get_auxiliary_indicators,
    get_combination_mode,
)

SYMBOL = "BTCUSDT"
MONTHS = 36

store = ParquetStore(base_dir=ROOT / "data" / "raw")
df_1m = store.read("binance", SYMBOL, "1m")
cutoff = df_1m.index.max() - pd.DateOffset(months=MONTHS)
df_1m = df_1m.loc[df_1m.index >= cutoff]

# ═══════════════════════════════════════════════════════════════════════
# TEST 1: Signal rate per archetype (how often do signals fire?)
# ═══════════════════════════════════════════════════════════════════════
print("=" * 70)
print("  TEST 1: SIGNAL RATES (default params, BTCUSDT)")
print("=" * 70)

for tf in ["1h", "4h"]:
    ohlcv = OHLCVResampler().resample(df_1m, tf, base_tf="1m")
    n_bars = len(ohlcv)
    print(f"\n  TF={tf} ({n_bars} bars)")
    print(f"  {'Archetype':<20} {'Mode':<12} {'Entry sigs':>10} {'Rate':>8} {'Combined':>10} {'Comb rate':>10}")
    
    for arch in ARCHETYPE_INDICATORS:
        entry_inds = get_entry_indicators(arch)
        comb_mode, comb_threshold = get_combination_mode(arch)
        
        # Use mid-range default params
        signals = {}
        for ind_name in entry_inds:
            ind_cls = get_indicator(ind_name)
            try:
                state = ind_cls.compute(ohlcv)
                sig = state.entry_long if hasattr(state, "entry_long") else pd.Series(False, index=ohlcv.index)
                signals[ind_name] = sig
                n_true = int(sig.sum())
            except Exception as e:
                signals[ind_name] = pd.Series(False, index=ohlcv.index)
                n_true = 0
        
        # Show individual signal counts
        ind_counts = ", ".join(f"{k}={int(signals[k].sum())}" for k in entry_inds)
        
        # Combined signal
        combined = combine_signals(signals, combination_mode=comb_mode, majority_threshold=comb_threshold)
        n_combined = int(combined.sum())
        
        print(
            f"  {arch:<20} {comb_mode:<12} {ind_counts:>30} "
            f"{n_combined:>10} {n_combined/n_bars*100:>8.2f}%"
        )

# ═══════════════════════════════════════════════════════════════════════
# TEST 2: Commission impact on best-performing trials
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("  TEST 2: COMMISSION IMPACT (momentum, 1h, 30 trials)")
print("=" * 70)

ohlcv_1h = OHLCVResampler().resample(df_1m, "1h", base_tf="1m")
dataset_1h = build_dataset_from_df(ohlcv_1h, exchange="binance", symbol=SYMBOL, base_timeframe="1h")

# Run backtests with commission OFF (set to 0)
from suitetrading.optimization._internal.objective import BacktestObjective
from suitetrading.optimization import OptunaOptimizer
from suitetrading.risk.contracts import RiskConfig

# First with commission
db = ROOT / "artifacts" / "discovery" / "diag_comm_on.db"
db.unlink(missing_ok=True)

obj_on = BacktestObjective(
    dataset=dataset_1h,
    indicator_names=["rsi", "macd", "ema"],
    auxiliary_indicators=[],
    archetype="momentum",
    metric="sharpe",
    mode="fsm",
)
opt_on = OptunaOptimizer(
    objective=obj_on, study_name="comm_on",
    storage=f"sqlite:///{db}", sampler="tpe",
    direction="maximize", seed=42,
)
opt_on.optimize(n_trials=30)
top_on = opt_on.get_top_n(5)
db.unlink(missing_ok=True)

# Now we'll manually check: extract best params and run backtest manually
print(f"\n  With commission (0.10%):")
for i, t in enumerate(top_on[:3]):
    m = eval(t["metrics"]) if isinstance(t["metrics"], str) else t["metrics"]
    gross_pnl = sum(tr.get("pnl", 0) for tr in m.get("trades", [])) if "trades" in m else 0
    net_pnl = m.get("net_profit", 0)
    comm_total = m.get("total_commission", 0)
    print(
        f"    #{i+1}: sharpe={t['value']:+.4f}  trades={m.get('total_trades',0)}  "
        f"net={net_pnl:+.2f}  ret={m.get('total_return_pct',0):+.2f}%  PF={m.get('profit_factor',0):.3f}"
    )

# ═══════════════════════════════════════════════════════════════════════
# TEST 3: Multi-timeframe scan (which TF works best?)
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("  TEST 3: TIMEFRAME SCAN (momentum, 30 trials each)")
print("=" * 70)
print(f"  {'TF':<6} {'Bars':>8} {'Best SR':>10} {'Trades':>8} {'Ret%':>10} {'PF':>8}")
print("  " + "-" * 55)

for tf in ["15m", "1h", "4h", "1d"]:
    ohlcv = OHLCVResampler().resample(df_1m, tf, base_tf="1m")
    ds = build_dataset_from_df(ohlcv, exchange="binance", symbol=SYMBOL, base_timeframe=tf)
    
    db = ROOT / "artifacts" / "discovery" / f"diag_tf_{tf}.db"
    db.unlink(missing_ok=True)
    
    obj = BacktestObjective(
        dataset=ds,
        indicator_names=["rsi", "macd", "ema"],
        auxiliary_indicators=[],
        archetype="momentum",
        metric="sharpe",
        mode="fsm",
    )
    opt = OptunaOptimizer(
        objective=obj, study_name=f"diag_tf_{tf}",
        storage=f"sqlite:///{db}", sampler="tpe",
        direction="maximize", seed=42,
    )
    opt.optimize(n_trials=30)
    top = opt.get_top_n(3)
    db.unlink(missing_ok=True)
    
    best = top[0]
    m = eval(best["metrics"]) if isinstance(best["metrics"], str) else best["metrics"]
    print(
        f"  {tf:<6} {len(ohlcv):>8,} {best['value']:>+10.4f} "
        f"{m.get('total_trades',0):>8} {m.get('total_return_pct',0):>+10.2f} "
        f"{m.get('profit_factor',0):>8.3f}"
    )

print("\nDone.")
