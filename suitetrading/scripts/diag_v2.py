import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import optuna
import pandas as pd

from suitetrading.backtesting._internal.datasets import build_dataset_from_df
from suitetrading.config.archetypes import (
    get_entry_indicators,
    get_auxiliary_indicators,
    get_all_indicators,
    get_combination_mode,
)
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.indicators.base import IndicatorState
from suitetrading.indicators.registry import get_indicator
from suitetrading.indicators.signal_combiner import combine_signals
from suitetrading.optimization._internal.objective import BacktestObjective

optuna.logging.set_verbosity(optuna.logging.WARNING)
ROOT = Path(__file__).resolve().parent.parent

store = ParquetStore(base_dir=ROOT / "data" / "raw")
df = store.read("binance", "BTCUSDT", "1m")
cutoff = df.index.max() - pd.DateOffset(months=36)
df = df.loc[df.index >= cutoff]
resampler = OHLCVResampler()
ohlcv = resampler.resample(df, "1h", base_tf="1m")
dataset = build_dataset_from_df(
    ohlcv, exchange="binance", symbol="BTCUSDT", base_timeframe="1h",
)
print(f"Dataset: {len(dataset.ohlcv)} bars")

STUDIES = [
    ("BTCUSDT_1h_trend_following", "trend_following"),
    ("BTCUSDT_1h_mean_reversion", "mean_reversion"),
    ("BTCUSDT_1h_mixed", "mixed"),
    ("BTCUSDT_1h_momentum", "momentum"),
    ("BTCUSDT_1h_breakout", "breakout"),
]

for sname, archetype in STUDIES:
    db = ROOT / "artifacts" / "discovery" / "studies" / f"{sname}.db"
    if not db.exists():
        continue
    study = optuna.load_study(study_name=sname, storage=f"sqlite:///{db}")
    trials = sorted(
        [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE],
        key=lambda t: t.value if t.value is not None else -999,
        reverse=True,
    )
    best = trials[0]
    m = best.user_attrs.get("metrics", {})
    entry_inds = get_entry_indicators(archetype)
    all_inds = get_all_indicators(archetype)
    aux_inds = get_auxiliary_indicators(archetype)
    comb_mode, comb_threshold = get_combination_mode(archetype)

    print(f"\n{'='*60}")
    print(f"{sname}")
    print(f"  Entry: {entry_inds}, Aux: {aux_inds}, Mode: {comb_mode}")
    print(f"  Best #{best.number}: value={best.value:.4f}")
    print(f"  sharpe={m.get('sharpe')}, trades={m.get('total_trades')}, "
          f"WR={m.get('win_rate')}, ret={m.get('total_return_pct')}%, "
          f"PF={m.get('profit_factor')}")

    # Split params into indicator and risk
    ind_params = {}
    for key, value in best.params.items():
        parts = key.split("__", 1)
        if len(parts) == 2 and parts[0] in all_inds:
            ind_params.setdefault(parts[0], {})[parts[1]] = value

    # Per-indicator signal counts
    for ind_name in entry_inds:
        if ind_name in ind_params:
            indicator = get_indicator(ind_name)
            sig = indicator.compute(dataset.ohlcv, **ind_params[ind_name])
            pct = sig.sum() / len(sig) * 100
            print(f"  {ind_name}: {sig.sum()} signals ({pct:.2f}%)")

    # Combined signal
    signals = {}
    for ind_name in entry_inds:
        if ind_name in ind_params:
            indicator = get_indicator(ind_name)
            signals[ind_name] = indicator.compute(
                dataset.ohlcv, **ind_params[ind_name],
            )
    if signals:
        states = {k: IndicatorState.EXCLUYENTE for k in signals}
        combined = combine_signals(signals, states, combination_mode=comb_mode, majority_threshold=comb_threshold)
        print(f"  COMBINED ({comb_mode}): {combined.sum()} entries")

    # Full replay
    obj = BacktestObjective(
        dataset=dataset,
        indicator_names=all_inds,
        auxiliary_indicators=aux_inds if aux_inds else None,
        archetype=archetype,
        mode="fsm",
    )
    result = obj.run_single(dict(best.params))
    rm = result["metrics"]
    print(f"  REPLAY: sharpe={rm.get('sharpe'):.4f}, "
          f"trades={rm.get('total_trades')}, "
          f"WR={rm.get('win_rate')}, "
          f"ret={rm.get('total_return_pct')}%, "
          f"PF={rm.get('profit_factor')}")

    # Trade distribution
    trades = result.get("trades")
    if trades is not None and len(trades) > 0:
        tdf = pd.DataFrame(trades) if isinstance(trades, list) else trades
        if "pnl" in tdf.columns:
            wins = tdf[tdf["pnl"] > 0]
            losses = tdf[tdf["pnl"] <= 0]
            if len(wins) > 0:
                print(f"  Winners: {len(wins)}, avg={wins['pnl'].mean():.2f}")
            if len(losses) > 0:
                print(f"  Losers:  {len(losses)}, avg={losses['pnl'].mean():.2f}")
            if "exit_reason" in tdf.columns:
                for reason in tdf["exit_reason"].unique():
                    sub = tdf[tdf["exit_reason"] == reason]
                    print(f"    {reason}: {len(sub)}, avg_pnl={sub['pnl'].mean():+.2f}")

print("\nDone.")
