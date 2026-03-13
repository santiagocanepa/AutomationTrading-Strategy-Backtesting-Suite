"""Replay best trials from smoke test with variable commission.

Compares Sharpe with 0.07% commission vs 0% commission to isolate
the impact of execution costs on signal quality.
"""
import optuna
import ast
from pathlib import Path

import pandas as pd
from loguru import logger

optuna.logging.set_verbosity(optuna.logging.WARNING)
logger.disable("suitetrading")

from suitetrading.backtesting._internal.schemas import BacktestDataset
from suitetrading.optimization._internal.objective import BacktestObjective
from suitetrading.config.archetypes import ARCHETYPE_INDICATORS
from suitetrading.data.storage import ParquetStore
from suitetrading.data.resampler import OHLCVResampler


def load_dataset(symbol: str, timeframe: str, months: int = 36) -> BacktestDataset:
    store = ParquetStore(base_dir=Path("data/raw"))
    df_1m = store.read("binance", symbol, "1m")
    cutoff = df_1m.index.max() - pd.DateOffset(months=months)
    df_1m = df_1m.loc[df_1m.index >= cutoff]

    if timeframe != "1m":
        resampler = OHLCVResampler()
        ohlcv = resampler.resample(df_1m, timeframe, base_tf="1m")
    else:
        ohlcv = df_1m

    return BacktestDataset(
        exchange="binance",
        symbol=symbol,
        base_timeframe=timeframe,
        ohlcv=ohlcv,
    )


def replay_trial(
    dataset: BacktestDataset,
    archetype: str,
    trial_params: dict,
    commission_override: float | None = None,
) -> dict:
    """Re-run a trial, optionally overriding commission."""
    arch_cfg = ARCHETYPE_INDICATORS[archetype]
    indicator_names = arch_cfg["entry"]

    obj = BacktestObjective(
        dataset=dataset,
        indicator_names=indicator_names,
        archetype=archetype,
        direction="long",
        metric="sharpe",
        mode="auto",
    )

    indicator_params, risk_overrides = obj._split_params(trial_params)
    signals = obj.build_signals(indicator_params)
    risk_config = obj.build_risk_config(risk_overrides)

    if commission_override is not None:
        risk_config = risk_config.model_copy(update={"commission_pct": commission_override})

    from suitetrading.backtesting.engine import BacktestEngine
    from suitetrading.backtesting.metrics import MetricsEngine

    engine = BacktestEngine()
    metrics_engine = MetricsEngine()

    result = engine.run(
        dataset=dataset,
        signals=signals,
        risk_config=risk_config,
        mode="auto",
        direction="long",
    )

    metrics = metrics_engine.compute(
        equity_curve=result["equity_curve"],
        trades=result.get("trades"),
        initial_capital=risk_config.initial_capital,
        context={"timeframe": dataset.base_timeframe},
    )
    return metrics


def main():
    dataset = load_dataset("BTCUSDT", "1h")
    print(f"Dataset: {len(dataset.ohlcv)} bars, {dataset.ohlcv.index[0]} to {dataset.ohlcv.index[-1]}")

    studies_dir = Path("artifacts/discovery/studies")

    for db in sorted(studies_dir.glob("*.db")):
        sname = db.stem
        archetype = sname.split("_", 2)[-1]  # BTCUSDT_1h_momentum -> momentum
        study = optuna.load_study(study_name=sname, storage=f"sqlite:///{db}")

        # Find best non-penalty trial
        best = None
        for t in study.trials:
            if t.state.name != "COMPLETE":
                continue
            if t.value is not None and t.value > -5:
                if best is None or t.value > best.value:
                    best = t

        if not best:
            print(f"\n=== {sname}: No non-penalty trials ===")
            continue

        print(f"\n{'='*60}")
        print(f"=== {sname} (Trial {best.number}, original Sharpe={best.value:.4f}) ===")
        print(f"{'='*60}")

        # Replay with standard commission (0.07%)
        m1 = replay_trial(dataset, archetype, best.params, commission_override=0.07)
        print(f"\n  Commission=0.07%:")
        print(f"    Sharpe={m1['sharpe']:.4f}  Sortino={m1['sortino']:.4f}")
        print(f"    Return={m1['total_return_pct']:.4f}%  MDD={m1['max_drawdown_pct']:.4f}%")
        print(f"    Trades={m1['total_trades']}  WinRate={m1['win_rate']:.2f}%  PF={m1['profit_factor']:.4f}")
        print(f"    AvgTrade={m1['average_trade']:.4f}  NetProfit={m1['net_profit']:.2f}")

        # Replay with zero commission
        m0 = replay_trial(dataset, archetype, best.params, commission_override=0.0)
        print(f"\n  Commission=0.00%:")
        print(f"    Sharpe={m0['sharpe']:.4f}  Sortino={m0['sortino']:.4f}")
        print(f"    Return={m0['total_return_pct']:.4f}%  MDD={m0['max_drawdown_pct']:.4f}%")
        print(f"    Trades={m0['total_trades']}  WinRate={m0['win_rate']:.2f}%  PF={m0['profit_factor']:.4f}")
        print(f"    AvgTrade={m0['average_trade']:.4f}  NetProfit={m0['net_profit']:.2f}")

        # Delta
        delta_sharpe = m0['sharpe'] - m1['sharpe']
        delta_return = m0['total_return_pct'] - m1['total_return_pct']
        commission_drag = m1['net_profit'] - m0['net_profit']
        print(f"\n  ** IMPACT: dSharpe={delta_sharpe:+.4f}  dReturn={delta_return:+.4f}%  Commission cost={commission_drag:.2f} **")
        if m0['sharpe'] > 0 and m1['sharpe'] <= 0:
            print(f"  ** COMMISSION KILLS PROFITABILITY — edge exists but too thin **")


if __name__ == "__main__":
    main()
