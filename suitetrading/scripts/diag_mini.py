#!/usr/bin/env python3
"""Quick diagnostic: 50 trials, 1 symbol, 1 TF, 1 archetype.
Inspects each pipeline stage to identify where finalists are lost.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import optuna
optuna.logging.set_verbosity(optuna.logging.WARNING)

from suitetrading.backtesting._internal.datasets import build_dataset_from_df
from suitetrading.backtesting.engine import BacktestEngine
from suitetrading.backtesting.metrics import MetricsEngine
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.optimization import (
    WalkForwardEngine, CSCVValidator, deflated_sharpe_ratio,
    OptunaOptimizer,
)
from suitetrading.optimization._internal.objective import BacktestObjective
from suitetrading.optimization._internal.schemas import WFOConfig
from suitetrading.config.archetypes import (
    get_entry_indicators, get_auxiliary_indicators,
)

# ── Config ────────────────────────────────────────────────────────────
SYMBOL = "BTCUSDT"
TF = "1h"
ARCH = "momentum"       # majority voting, 3 TA-Lib indicators → more trades
TRIALS = 50
TOP_N = 10
WFO_SPLITS = 5
WFO_MIN_IS = 500
WFO_MIN_OOS = 100
WFO_GAP = 20
CSCV_SUB = 16
DSR_ALPHA = 0.05
PBO_THRESHOLD = 0.55

# ── Load data ─────────────────────────────────────────────────────────
store = ParquetStore(base_dir=ROOT / "data" / "raw")
df_1m = store.read("binance", SYMBOL, "1m")
cutoff = df_1m.index.max() - pd.DateOffset(months=36)
df_1m = df_1m.loc[df_1m.index >= cutoff]
ohlcv = OHLCVResampler().resample(df_1m, TF, base_tf="1m")

print(f"Data: {SYMBOL} {TF} — {len(ohlcv)} bars")
print(f"Range: {ohlcv.index[0]} → {ohlcv.index[-1]}")

dataset = build_dataset_from_df(
    ohlcv, exchange="binance", symbol=SYMBOL, base_timeframe=TF,
)

entry_inds = get_entry_indicators(ARCH)
aux_inds = get_auxiliary_indicators(ARCH)
all_inds = entry_inds + aux_inds
print(f"Archetype: {ARCH}, entry={entry_inds}, aux={aux_inds}")

# ── Phase A: Optuna ───────────────────────────────────────────────────
db_path = ROOT / "artifacts" / "discovery" / "diag_test.db"
db_path.unlink(missing_ok=True)

objective = BacktestObjective(
    dataset=dataset,
    indicator_names=all_inds,
    auxiliary_indicators=aux_inds,
    archetype=ARCH,
    metric="sharpe",
    mode="fsm",
)

optimizer = OptunaOptimizer(
    objective=objective,
    study_name="diag_test",
    storage=f"sqlite:///{db_path}",
    sampler="tpe",
    direction="maximize",
    seed=42,
)
optimizer.optimize(n_trials=TRIALS)
top = optimizer.get_top_n(TOP_N)

# Analyze
print(f"\n{'='*60}")
print(f"  PHASE A: OPTUNA ({TRIALS} trials)")
print(f"{'='*60}")

for i, t in enumerate(top):
    m = eval(t["metrics"]) if isinstance(t["metrics"], str) else t["metrics"]
    print(
        f"  #{i+1}: sharpe={t['value']:+.4f}  trades={m.get('total_trades', 0):>3d}  "
        f"ret={m.get('total_return_pct', 0):+.2f}%  PF={m.get('profit_factor', 0):.3f}  "
        f"maxDD={m.get('max_drawdown_pct', 0):.2f}%"
    )

positive = sum(1 for t in top if t["value"] > 0)
print(f"\n  Positive Sharpe: {positive}/{len(top)}")
avg_trades = np.mean([
    (eval(t["metrics"]) if isinstance(t["metrics"], str) else t["metrics"]).get("total_trades", 0)
    for t in top
])
print(f"  Avg trades (top-{TOP_N}): {avg_trades:.1f}")

if positive == 0:
    print("\n  ⚠ NO positive Sharpe found. Cannot produce finalists.")
    print("  Root cause is at Optuna/strategy level — not anti-overfit pipeline.")
    sys.exit(1)

# ── Phase B: WFO ──────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  PHASE B: WALK-FORWARD ({WFO_SPLITS} splits)")
print(f"{'='*60}")

wfo_config = WFOConfig(
    n_splits=WFO_SPLITS,
    min_is_bars=WFO_MIN_IS,
    min_oos_bars=WFO_MIN_OOS,
    gap_bars=WFO_GAP,
    mode="rolling",
)

wfo = WalkForwardEngine(
    config=wfo_config, metric="sharpe", auxiliary_indicators=aux_inds,
)

# Use only top candidates with positive Sharpe
pos_top = [t for t in top if t["value"] > 0][:TOP_N]
indicator_names = all_inds

candidates = []
for trial in pos_top:
    flat = eval(trial["params"]) if isinstance(trial["params"], str) else trial["params"]
    ind_params = {}
    risk_overrides = {}
    for key, value in flat.items():
        parts = key.split("__", 1)
        if len(parts) == 2:
            prefix, param_name = parts
            if prefix in indicator_names:
                ind_params.setdefault(prefix, {})[param_name] = value
            else:
                risk_overrides[key] = value
        else:
            risk_overrides[key] = value
    candidates.append({
        "indicator_params": ind_params,
        "risk_overrides": risk_overrides,
        "trial_number": trial.get("trial_number"),
        "optuna_value": trial.get("value"),
    })

wfo_candidates = [
    {"indicator_params": c["indicator_params"], "risk_overrides": c["risk_overrides"]}
    for c in candidates
]

wfo_result = wfo.run(
    dataset=dataset,
    candidate_params=wfo_candidates,
    archetype=ARCH,
    mode="fsm",
)

# Analyze WFO
print(f"\n  Degradation (IS→OOS):")
for pid, deg in sorted(wfo_result.degradation.items())[:5]:
    oos_met = wfo_result.oos_metrics.get(pid, {})
    oos_sharpe = oos_met.get("sharpe", float("nan"))
    print(f"    {pid[:12]}...: deg={deg:.3f}, OOS sharpe={oos_sharpe:.4f}")

oos_curves = {
    k: v for k, v in wfo_result.oos_equity_curves.items()
    if isinstance(v, np.ndarray) and len(v) > 0
}
print(f"\n  OOS curves: {len(oos_curves)}")
for pid, curve in sorted(oos_curves.items())[:3]:
    rets = np.diff(curve) / np.maximum(curve[:-1], 1e-10)
    rets_clean = rets[np.isfinite(rets)]
    std = float(np.std(rets_clean, ddof=1)) if len(rets_clean) > 1 else 0
    sr_per_bar = float(np.mean(rets_clean)) / std if std > 1e-12 else 0
    sr_annual = sr_per_bar * np.sqrt(365 * 24)  # 1h bars
    print(
        f"    {pid[:12]}...: {len(curve)} bars, "
        f"ret/bar={np.mean(rets_clean)*100:.4f}%, "
        f"SR/bar={sr_per_bar:.6f}, SR_ann={sr_annual:.4f}"
    )

# ── Phase C: CSCV ────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  PHASE C: CSCV (PBO threshold={PBO_THRESHOLD})")
print(f"{'='*60}")

if len(oos_curves) < 2:
    print("  ⚠ <2 OOS curves — cannot compute CSCV")
    sys.exit(1)

cscv = CSCVValidator(n_subsamples=CSCV_SUB, metric="sharpe")
curve_ids = sorted(oos_curves.keys())
min_len = min(len(oos_curves[k]) for k in curve_ids)
max_len = max(len(oos_curves[k]) for k in curve_ids)
print(f"  Curves: {len(curve_ids)}, min_len={min_len}, max_len={max_len}")

if min_len < CSCV_SUB * 2:
    print(f"  ⚠ Curves too short ({min_len}) for {CSCV_SUB} subsamples")
    sys.exit(1)

truncated = {k: oos_curves[k][:min_len] for k in curve_ids}
cscv_result = cscv.compute_pbo(truncated)
print(f"  PBO = {cscv_result.pbo:.4f}")
passed_cscv = cscv_result.pbo < PBO_THRESHOLD
print(f"  CSCV pass (PBO < {PBO_THRESHOLD}): {'YES ✓' if passed_cscv else 'NO ✗'}")

# ── Phase D: DSR ──────────────────────────────────────────────────────
print(f"\n{'='*60}")
print(f"  PHASE D: DSR (alpha={DSR_ALPHA}, n_trials={TRIALS})")
print(f"{'='*60}")

for cid in curve_ids[:5]:
    curve = oos_curves[cid]
    rets = np.diff(curve) / np.maximum(curve[:-1], 1e-10)
    rets_clean = rets[np.isfinite(rets)]

    std_r = float(np.std(rets_clean, ddof=1)) if len(rets_clean) > 1 else 0.0
    obs_sr = float(np.mean(rets_clean)) / std_r if std_r > 1e-12 else 0.0
    skew = float(stats.skew(rets_clean)) if len(rets_clean) > 2 else 0.0
    kurt = float(stats.kurtosis(rets_clean, fisher=False)) if len(rets_clean) > 3 else 3.0

    dsr = deflated_sharpe_ratio(
        observed_sharpe=obs_sr,
        n_trials=TRIALS,
        sample_length=len(rets_clean),
        skewness=skew,
        kurtosis=kurt,
    )
    print(
        f"  {cid[:12]}...: SR/bar={obs_sr:.6f}, T={len(rets_clean)}, "
        f"skew={skew:.2f}, kurt={kurt:.2f}, DSR={dsr.dsr:.4f}, sig={dsr.is_significant}"
    )

# ── Summary ───────────────────────────────────────────────────────────
print(f"\n{'='*60}")
print("  SUMMARY — Where finalists are lost")
print(f"{'='*60}")

n_pos = sum(1 for t in top if t["value"] > 0)
n_oos = len(oos_curves)

# Count DSR passes
dsr_pass = 0
for cid in curve_ids:
    curve = oos_curves[cid]
    rets = np.diff(curve) / np.maximum(curve[:-1], 1e-10)
    rets_clean = rets[np.isfinite(rets)]
    std_r = float(np.std(rets_clean, ddof=1)) if len(rets_clean) > 1 else 0.0
    obs_sr = float(np.mean(rets_clean)) / std_r if std_r > 1e-12 else 0.0
    skew = float(stats.skew(rets_clean)) if len(rets_clean) > 2 else 0.0
    kurt = float(stats.kurtosis(rets_clean, fisher=False)) if len(rets_clean) > 3 else 3.0
    d = deflated_sharpe_ratio(
        observed_sharpe=obs_sr, n_trials=TRIALS,
        sample_length=len(rets_clean), skewness=skew, kurtosis=kurt,
    )
    if d.is_significant:
        dsr_pass += 1

finalists = dsr_pass if passed_cscv else 0

print(f"  Optuna top-{TOP_N} positive: {n_pos}/{TOP_N}")
print(f"  WFO OOS curves: {n_oos}")
print(f"  CSCV PBO: {cscv_result.pbo:.4f} → {'PASS' if passed_cscv else 'FAIL'}")
print(f"  DSR significant: {dsr_pass}/{len(curve_ids)}")
print(f"  → FINALISTS: {finalists}")

# Cleanup
db_path.unlink(missing_ok=True)
