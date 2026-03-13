"""Quick diagnostic of smoke test v2 results."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import optuna
import pandas as pd as pd

from suitetrading.backtesting._internal.datasets import build_dataset_from_dffrom suitetrading.backtesting._internal.datasets import build_dataset_from_df
from suitetrading.config.archetypes import get_entry_indicators, get_auxiliary_indicators, get_all_indicators, get_combination_mode
from suitetrading.data.resampler import OHLCVResampler























































































    main()if __name__ == "__main__":    print("\nDone.", flush=True)                        print(f"    {reason}: {len(sub)}, avg_pnl={sub['pnl'].mean():+.2f}", flush=True)                        sub = tdf[tdf["exit_reason"] == reason]                    for reason in tdf["exit_reason"].unique():                if "exit_reason" in tdf.columns:                    print(f"  Losers:  {len(losses)}, avg={losses['pnl'].mean():.2f}", flush=True)                if len(losses) > 0:                    print(f"  Winners: {len(wins)}, avg={wins['pnl'].mean():.2f}", flush=True)                if len(wins) > 0:                losses = tdf[tdf["pnl"] <= 0]                wins = tdf[tdf["pnl"] > 0]            if "pnl" in tdf.columns:            tdf = pd.DataFrame(trades) if isinstance(trades, list) else trades        if trades is not None and len(trades) > 0:        trades = result.get("trades")        print(f"  REPLAY: sharpe={rm.get('sharpe'):.4f}, trades={rm.get('total_trades')}, WR={rm.get('win_rate')}, ret={rm.get('total_return_pct')}%, PF={rm.get('profit_factor')}", flush=True)        rm = result["metrics"]        result = obj.run_single(dict(best.params))        obj = BacktestObjective(dataset=dataset, indicator_names=all_inds, auxiliary_indicators=aux_inds if aux_inds else None, archetype=archetype, mode="fsm")            print(f"  COMBINED ({comb_mode}): {combined.sum()} entries", flush=True)            combined = combine_signals(signals, states, combination_mode=comb_mode)            states = {k: IndicatorState.EXCLUYENTE for k in signals}        if signals:                signals[ind_name] = indicator.compute(dataset.ohlcv, **ind_params[ind_name])                indicator = get_indicator(ind_name)            if ind_name in ind_params:        for ind_name in entry_inds:        signals = {}                print(f"  {ind_name}: {sig.sum()} signals ({sig.sum()/len(sig)*100:.2f}%)", flush=True)                sig = indicator.compute(dataset.ohlcv, **ind_params[ind_name])                indicator = get_indicator(ind_name)            if ind_name in ind_params:        for ind_name in entry_inds:                ind_params.setdefault(parts[0], {})[parts[1]] = value            if len(parts) == 2 and parts[0] in all_inds:            parts = key.split("__", 1)        for key, value in best.params.items():        ind_params = {}        print(f"  sharpe={m.get('sharpe')}, trades={m.get('total_trades')}, WR={m.get('win_rate')}, ret={m.get('total_return_pct')}%, MDD={m.get('max_drawdown_pct')}%, PF={m.get('profit_factor')}", flush=True)        m = best.user_attrs.get("metrics", {})        print(f"  Best trial #{best.number}: value={best.value:.4f}", flush=True)        print(f"  Entry: {entry_inds}, Aux: {aux_inds}, Mode: {comb_mode}", flush=True)        print(f"{sname}", flush=True)        print(f"\n{'='*60}", flush=True)        comb_mode = get_combination_mode(archetype)        all_inds = get_all_indicators(archetype)        aux_inds = get_auxiliary_indicators(archetype)        entry_inds = get_entry_indicators(archetype)        best = trials[0]        trials.sort(key=lambda t: t.value if t.value is not None else -999, reverse=True)        trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]        study = optuna.load_study(study_name=sname, storage=f"sqlite:///{db_path}")            continue            print(f"\n{sname}: DB not found", flush=True)        if not db_path.exists():        db_path = ROOT / "artifacts" / "discovery" / "studies" / f"{sname}.db"    for sname, archetype in studies:    ]        ("BTCUSDT_1h_breakout", "breakout"),        ("BTCUSDT_1h_momentum", "momentum"),        ("BTCUSDT_1h_mixed", "mixed"),        ("BTCUSDT_1h_mean_reversion", "mean_reversion"),        ("BTCUSDT_1h_trend_following", "trend_following"),    studies = [    print(f"Dataset: {len(dataset.ohlcv)} bars", flush=True)    dataset = build_dataset_from_df(ohlcv, exchange="binance", symbol="BTCUSDT", base_timeframe="1h")    ohlcv = resampler.resample(df, "1h", base_tf="1m")    resampler = OHLCVResampler()    df = df.loc[df.index >= cutoff]    cutoff = df.index.max() - pd.DateOffset(months=36)    df = store.read("binance", "BTCUSDT", "1m")    store = ParquetStore(base_dir=ROOT / "data" / "raw")    print("Loading data...", flush=True)def main():ROOT = Path(__file__).resolve().parent.parentoptuna.logging.set_verbosity(optuna.logging.WARNING)from suitetrading.optimization._internal.objective import BacktestObjectivefrom suitetrading.indicators.signal_combiner import combine_signalsfrom suitetrading.indicators.registry import get_indicatorfrom suitetrading.indicators.base import IndicatorStatefrom suitetrading.data.storage import ParquetStore


































































































































































    main()if __name__ == "__main__":    print("\nDone.", flush=True)                        )                            flush=True,                            f"avg_pnl={sub['pnl'].mean():+.2f}",                            f"    {reason}: {len(sub)}, "                        print(                        sub = tdf[tdf["exit_reason"] == reason]                    for reason in tdf["exit_reason"].unique():                if "exit_reason" in tdf.columns:                    )                        flush=True,                        f"  Losers:  {len(losses)}, avg={losses['pnl'].mean():.2f}",                    print(                if len(losses) > 0:                    )                        flush=True,                        f"  Winners: {len(wins)}, avg={wins['pnl'].mean():.2f}",                    print(                if len(wins) > 0:                losses = tdf[tdf["pnl"] <= 0]                wins = tdf[tdf["pnl"] > 0]            if "pnl" in tdf.columns:            tdf = pd.DataFrame(trades) if isinstance(trades, list) else trades        if trades is not None and len(trades) > 0:        trades = result.get("trades")        # Trade analysis        )            flush=True,            f"PF={rm.get('profit_factor')}",            f"ret={rm.get('total_return_pct')}%, "            f"WR={rm.get('win_rate')}, "            f"trades={rm.get('total_trades')}, "            f"  REPLAY: sharpe={rm.get('sharpe'):.4f}, "        print(        rm = result["metrics"]        result = obj.run_single(dict(best.params))        )            mode="fsm",            archetype=archetype,            auxiliary_indicators=aux_inds if aux_inds else None,            indicator_names=all_inds,            dataset=dataset,        obj = BacktestObjective(        # Full backtest            )                flush=True,                f"  COMBINED ({comb_mode}): {combined.sum()} entries",            print(            )                signals, states, combination_mode=comb_mode,            combined = combine_signals(            states = {k: IndicatorState.EXCLUYENTE for k in signals}        if signals:                )                    dataset.ohlcv, **ind_params[ind_name],                signals[ind_name] = indicator.compute(                indicator = get_indicator(ind_name)            if ind_name in ind_params:        for ind_name in entry_inds:        signals = {}        # Combined                )                    flush=True,                    f"({sig.sum()/len(sig)*100:.2f}%)",                    f"  {ind_name}: {sig.sum()} signals "                print(                sig = indicator.compute(dataset.ohlcv, **ind_params[ind_name])                indicator = get_indicator(ind_name)            if ind_name in ind_params:        for ind_name in entry_inds:        # Signal counts                ind_params.setdefault(parts[0], {})[parts[1]] = value            if len(parts) == 2 and parts[0] in all_inds:            parts = key.split("__", 1)        for key, value in best.params.items():        ind_params = {}        # Split params        )            flush=True,            f"MDD={m.get('max_drawdown_pct')}%, PF={m.get('profit_factor')}",            f"WR={m.get('win_rate')}, ret={m.get('total_return_pct')}%, "            f"  sharpe={m.get('sharpe')}, trades={m.get('total_trades')}, "        print(        m = best.user_attrs.get("metrics", {})        print(f"  Best trial #{best.number}: value={best.value:.4f}", flush=True)        )            flush=True,            f"  Entry: {entry_inds}, Aux: {aux_inds}, Mode: {comb_mode}",        print(        print(f"{sname}", flush=True)        print(f"\n{'='*60}", flush=True)        comb_mode = get_combination_mode(archetype)        all_inds = get_all_indicators(archetype)        aux_inds = get_auxiliary_indicators(archetype)        entry_inds = get_entry_indicators(archetype)        best = trials[0]        )            reverse=True,            key=lambda t: t.value if t.value is not None else -999,        trials.sort(        ]            if t.state == optuna.trial.TrialState.COMPLETE            t for t in study.trials        trials = [        )            study_name=sname, storage=f"sqlite:///{db_path}",        study = optuna.load_study(            continue            print(f"\n{sname}: DB not found", flush=True)        if not db_path.exists():        db_path = ROOT / "artifacts" / "discovery" / "studies" / f"{sname}.db"    for sname, archetype in studies:    ]        ("BTCUSDT_1h_breakout", "breakout"),        ("BTCUSDT_1h_momentum", "momentum"),        ("BTCUSDT_1h_mixed", "mixed"),        ("BTCUSDT_1h_mean_reversion", "mean_reversion"),        ("BTCUSDT_1h_trend_following", "trend_following"),    studies = [    print(f"Dataset: {len(dataset.ohlcv)} bars", flush=True)    )        ohlcv, exchange="binance", symbol="BTCUSDT", base_timeframe="1h",    dataset = build_dataset_from_df(    ohlcv = resampler.resample(df, "1h", base_tf="1m")    resampler = OHLCVResampler()    df = df.loc[df.index >= cutoff]    cutoff = df.index.max() - pd.DateOffset(months=36)    df = store.read("binance", "BTCUSDT", "1m")    store = ParquetStore(base_dir=ROOT / "data" / "raw")    print("Loading data...", flush=True)def main():ROOT = Path(__file__).resolve().parent.parentoptuna.logging.set_verbosity(optuna.logging.WARNING)from suitetrading.optimization._internal.objective import BacktestObjectivefrom suitetrading.indicators.signal_combiner import combine_signalsfrom suitetrading.indicators.registry import get_indicatorfrom suitetrading.indicators.base import IndicatorStatefrom suitetrading.data.storage import ParquetStorefrom suitetrading.data.resampler import OHLCVResampler)    get_combination_mode,    get_all_indicators,    get_auxiliary_indicators,    get_entry_indicators,from suitetrading.config.archetypes import get_entry_indicators, get_auxiliary_indicators, get_all_indicators, get_combination_mode
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.indicators.base import IndicatorState
from suitetrading.indicators.registry import get_indicator
from suitetrading.indicators.signal_combiner import combine_signals
from suitetrading.optimization._internal.objective import BacktestObjective

optuna.logging.set_verbosity(optuna.logging.WARNING)

ROOT = Path(__file__).resolve().parent.parent

print("Step 2: load data", flush=True)
store = ParquetStore(base_dir=ROOT / "data" / "raw")
df = store.read("binance", "BTCUSDT", "1m")
cutoff = df.index.max() - pd.DateOffset(months=36)
df = df.loc[df.index >= cutoff]
print(f"  1m bars: {len(df)}", flush=True)

resampler = OHLCVResampler()
ohlcv = resampler.resample(df, "1h", base_tf="1m")
print(f"  1h bars: {len(ohlcv)}", flush=True)

dataset = build_dataset_from_df(ohlcv, exchange="binance", symbol="BTCUSDT", base_timeframe="1h")

studies = [
    ("BTCUSDT_1h_trend_following", "trend_following"),
    ("BTCUSDT_1h_mean_reversion", "mean_reversion"),
    ("BTCUSDT_1h_mixed", "mixed"),
    ("BTCUSDT_1h_momentum", "momentum"),
    ("BTCUSDT_1h_breakout", "breakout"),
]

for sname, archetype in studies:
    db_path = ROOT / "artifacts" / "discovery" / "studies" / f"{sname}.db"
    if not db_path.exists():
        print(f"\n{sname}: DB not found", flush=True)
        continue

    study = optuna.load_study(study_name=sname, storage=f"sqlite:///{db_path}")
    trials = [t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE]
    trials.sort(key=lambda t: t.value if t.value is not None else -999, reverse=True)
    best = trials[0]

    entry_inds = get_entry_indicators(archetype)
    aux_inds = get_auxiliary_indicators(archetype)
    all_inds = get_all_indicators(archetype)
    comb_mode, comb_threshold = get_combination_mode(archetype)

    print(f"\n{'='*60}", flush=True)
    print(f"{sname}", flush=True)
    print(f"  Entry: {entry_inds}, Aux: {aux_inds}, Mode: {comb_mode}", flush=True)
    print(f"  Best trial #{best.number}: value={best.value:.4f}", flush=True)
    m = best.user_attrs.get("metrics", {})
    print(f"  Metrics: sharpe={m.get('sharpe')}, trades={m.get('total_trades')}, "
          f"WR={m.get('win_rate')}, ret={m.get('total_return_pct')}%, "
          f"MDD={m.get('max_drawdown_pct')}%, PF={m.get('profit_factor')}", flush=True)
    print(f"  Params: {dict(best.params)}", flush=True)

    # Split params
    ind_params = {}
    risk_ov = {}
    for key, value in best.params.items():
        parts = key.split("__", 1)
        if len(parts) == 2 and parts[0] in all_inds:
            ind_params.setdefault(parts[0], {})[parts[1]] = value
        else:
            risk_ov[key] = value

    # Individual signal counts
    print(f"  Signal counts:", flush=True)
    for ind_name in entry_inds:
        if ind_name in ind_params:
            indicator = get_indicator(ind_name)
            sig = indicator.compute(dataset.ohlcv, **ind_params[ind_name])
            print(f"    {ind_name}: {sig.sum()} signals ({sig.sum()/len(sig)*100:.2f}%)", flush=True)

    # Combined signals
    signals = {}
    for ind_name in entry_inds:
        if ind_name in ind_params:
            indicator = get_indicator(ind_name)
            signals[ind_name] = indicator.compute(dataset.ohlcv, **ind_params[ind_name])
    if signals:
        states = {k: IndicatorState.EXCLUYENTE for k in signals}
        combined = combine_signals(signals, states, combination_mode=comb_mode, majority_threshold=comb_threshold)
        print(f"    COMBINED ({comb_mode}): {combined.sum()} entries", flush=True)

    # Full backtest replay
    obj = BacktestObjective(
        dataset=dataset,
        indicator_names=all_inds,
        auxiliary_indicators=aux_inds if aux_inds else None,
        archetype=archetype,
        mode="fsm",
    )
    result = obj.run_single(dict(best.params))
    rm = result["metrics"]
    print(f"  Replay: sharpe={rm.get('sharpe'):.4f}, trades={rm.get('total_trades')}, "
          f"WR={rm.get('win_rate')}, ret={rm.get('total_return_pct')}%, "
          f"MDD={rm.get('max_drawdown_pct')}%, PF={rm.get('profit_factor')}", flush=True)

    # Trade analysis
    trades = result.get("trades")
    if trades is not None and len(trades) > 0:
        tdf = pd.DataFrame(trades) if isinstance(trades, list) else trades
        if "pnl" in tdf.columns:
            wins = tdf[tdf["pnl"] > 0]
            losses = tdf[tdf["pnl"] <= 0]
            print(f"  Trades: {len(wins)} wins (avg={wins['pnl'].mean():.2f}), "
                  f"{len(losses)} losses (avg={losses['pnl'].mean():.2f})" if len(wins) > 0 and len(losses) > 0
                  else f"  Trades: {len(wins)} wins, {len(losses)} losses", flush=True)
            if "exit_reason" in tdf.columns:
                for reason, count in tdf["exit_reason"].value_counts().items():
                    sub = tdf[tdf["exit_reason"] == reason]
                    avg_pnl = sub["pnl"].mean()
                    print(f"    {reason}: {count} ({avg_pnl:+.2f} avg PnL)", flush=True)

print("\nDone.", flush=True)
