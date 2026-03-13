"""Quick test: verify simple runner trade outcomes."""
import optuna
import numpy as np
import pandas as pd
from pathlib import Path
from loguru import logger
import ast

optuna.logging.set_verbosity(optuna.logging.WARNING)
logger.disable("suitetrading")

from suitetrading.backtesting._internal.schemas import BacktestDataset, StrategySignals
from suitetrading.backtesting.engine import BacktestEngine
from suitetrading.backtesting.metrics import MetricsEngine
from suitetrading.data.storage import ParquetStore
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.indicators.registry import get_indicator
from suitetrading.risk.archetypes import get_archetype
from suitetrading.optimization._internal.objective import BacktestObjective
from suitetrading.config.archetypes import ARCHETYPE_INDICATORS, get_combination_mode
from suitetrading.indicators.signal_combiner import combine_signals
from suitetrading.indicators.base import IndicatorState


def main():
    # Load data
    store = ParquetStore(base_dir=Path("data/raw"))
    df_1m = store.read("binance", "BTCUSDT", "1m")
    cutoff = df_1m.index.max() - pd.DateOffset(months=36)
    df_1m = df_1m.loc[df_1m.index >= cutoff]
    resampler = OHLCVResampler()
    ohlcv = resampler.resample(df_1m, "1h", base_tf="1m")

    # Load best trend_following trial params
    db = Path("artifacts/discovery/studies/BTCUSDT_1h_trend_following.db")
    study = optuna.load_study(study_name=db.stem, storage=f"sqlite:///{db}")
    best = None
    for t in study.trials:
        if t.state.name == "COMPLETE" and t.value is not None and t.value > -5:
            if best is None or t.value > best.value:
                best = t

    print(f"Trial {best.number}, original Sharpe={best.value:.4f}")
    print(f"Params: {best.params}")

    # Check what mode would be selected
    from suitetrading.backtesting.engine import _select_mode
    risk_config_tf = get_archetype("trend_following").build_config()
    mode = _select_mode(risk_config_tf.archetype, "auto")
    print(f"Risk archetype: {risk_config_tf.archetype}")
    print(f"Selected mode: {mode}")

    # Build signals manually
    arch_cfg = ARCHETYPE_INDICATORS["trend_following"]
    indicator_names = arch_cfg["entry"]

    obj = BacktestObjective(
        dataset=BacktestDataset(exchange="binance", symbol="BTCUSDT",
                                base_timeframe="1h", ohlcv=ohlcv),
        indicator_names=indicator_names,
        archetype="trend_following",
        direction="long",
        metric="sharpe",
        mode="auto",
    )

    indicator_params, risk_overrides = obj._split_params(best.params)
    signals = obj.build_signals(indicator_params)
    risk_config = obj.build_risk_config(risk_overrides)

    print(f"\nRisk config archetype: {risk_config.archetype}")
    print(f"Stop model: {risk_config.stop.model}, ATR mult: {risk_config.stop.atr_multiple}")
    
    # Check signal density
    entry = signals.entry_long
    signal_pct = entry.sum() / len(entry) * 100
    print(f"\nSignal density: {entry.sum()} signals / {len(entry)} bars = {signal_pct:.2f}%")

    engine = BacktestEngine()
    metrics_engine = MetricsEngine()

    # Run in auto mode (should pick simple for trend_following)
    result_auto = engine.run(
        dataset=BacktestDataset(exchange="binance", symbol="BTCUSDT",
                                base_timeframe="1h", ohlcv=ohlcv),
        signals=signals,
        risk_config=risk_config,
        mode="auto",
        direction="long",
    )

    print(f"\n=== AUTO MODE (resolves to: {_select_mode(risk_config.archetype, 'auto')}) ===")
    print(f"Total trades: {result_auto['total_trades']}")
    trades_auto = result_auto.get("trades")
    if trades_auto is not None and not trades_auto.empty:
        print(f"Trade PnLs: {trades_auto['pnl'].tolist()[:10]}")
        print(f"Exit reasons: {trades_auto['exit_reason'].value_counts().to_dict()}")
        wins = (trades_auto['pnl'] > 0).sum()
        losses = (trades_auto['pnl'] < 0).sum()
        zeros = (trades_auto['pnl'] == 0).sum()
        print(f"Wins: {wins}, Losses: {losses}, Break-even: {zeros}")

    metrics_auto = metrics_engine.compute(
        equity_curve=result_auto["equity_curve"],
        trades=trades_auto,
        initial_capital=risk_config.initial_capital,
        context={"timeframe": "1h"},
    )
    print(f"Sharpe: {metrics_auto['sharpe']:.4f}")
    print(f"WinRate: {metrics_auto['win_rate']:.2f}%")
    print(f"Trades: {metrics_auto['total_trades']}")

    # Now run in FSM mode explicitly
    result_fsm = engine.run(
        dataset=BacktestDataset(exchange="binance", symbol="BTCUSDT",
                                base_timeframe="1h", ohlcv=ohlcv),
        signals=signals,
        risk_config=risk_config,
        mode="fsm",
        direction="long",
    )

    print(f"\n=== FSM MODE ===")
    print(f"Total trades: {result_fsm['total_trades']}")
    trades_fsm = result_fsm.get("trades")
    if trades_fsm is not None and not trades_fsm.empty:
        print(f"Trade PnLs: {trades_fsm['pnl'].tolist()[:10]}")
        print(f"Exit reasons: {trades_fsm['exit_reason'].value_counts().to_dict()}")
        wins = (trades_fsm['pnl'] > 0).sum()
        losses = (trades_fsm['pnl'] < 0).sum()
        zeros = (trades_fsm['pnl'] == 0).sum()
        print(f"Wins: {wins}, Losses: {losses}, Break-even: {zeros}")

    metrics_fsm = metrics_engine.compute(
        equity_curve=result_fsm["equity_curve"],
        trades=trades_fsm,
        initial_capital=risk_config.initial_capital,
        context={"timeframe": "1h"},
    )
    print(f"Sharpe: {metrics_fsm['sharpe']:.4f}")
    print(f"WinRate: {metrics_fsm['win_rate']:.2f}%")
    print(f"Trades: {metrics_fsm['total_trades']}")


if __name__ == "__main__":
    main()
