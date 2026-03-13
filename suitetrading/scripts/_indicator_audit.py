"""Single-indicator quality audit.

Runs each indicator individually with a range of parameters against BTC 1h,
using the simple backtest runner (no FSM complexity). Shows whether any 
individual indicator has edge.
"""
import optuna
import numpy as np
import pandas as pd
from pathlib import Path
from loguru import logger

optuna.logging.set_verbosity(optuna.logging.WARNING)
logger.disable("suitetrading")

from suitetrading.backtesting._internal.schemas import BacktestDataset, StrategySignals
from suitetrading.backtesting.engine import BacktestEngine
from suitetrading.backtesting.metrics import MetricsEngine
from suitetrading.data.storage import ParquetStore
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.indicators.registry import get_indicator, INDICATOR_REGISTRY
from suitetrading.risk.contracts import RiskConfig


def load_ohlcv(symbol: str, timeframe: str, months: int = 36) -> pd.DataFrame:
    store = ParquetStore(base_dir=Path("data/raw"))
    df_1m = store.read("binance", symbol, "1m")
    cutoff = df_1m.index.max() - pd.DateOffset(months=months)
    df_1m = df_1m.loc[df_1m.index >= cutoff]
    if timeframe != "1m":
        resampler = OHLCVResampler()
        return resampler.resample(df_1m, timeframe, base_tf="1m")
    return df_1m


def run_indicator_audit(
    ohlcv: pd.DataFrame,
    ind_name: str,
    timeframe: str,
    n_trials: int = 100,
    commission: float = 0.0,
) -> dict:
    """Optimize a single indicator and return best metrics."""
    indicator = get_indicator(ind_name)
    schema = indicator.params_schema()
    metrics_engine = MetricsEngine()
    engine = BacktestEngine()

    risk_config = RiskConfig(
        initial_capital=10_000.0,
        commission_pct=commission,
        slippage_pct=0.0,
    )

    dataset = BacktestDataset(
        exchange="binance",
        symbol="BTCUSDT",
        base_timeframe=timeframe,
        ohlcv=ohlcv,
    )

    best_sharpe = -999.0
    best_metrics = None
    best_params = None

    def objective(trial):
        nonlocal best_sharpe, best_metrics, best_params
        
        params = {}
        for param_name, param_schema in schema.items():
            ptype = param_schema["type"]
            if ptype == "int":
                params[param_name] = trial.suggest_int(param_name, param_schema["min"], param_schema["max"])
            elif ptype == "float":
                step = param_schema.get("step")
                params[param_name] = trial.suggest_float(param_name, param_schema["min"], param_schema["max"], step=step)
            elif ptype == "str":
                params[param_name] = trial.suggest_categorical(param_name, param_schema["choices"])
            elif ptype == "bool":
                params[param_name] = trial.suggest_categorical(param_name, [True, False])

        signal = indicator.compute(ohlcv, **params)
        signals = StrategySignals(entry_long=signal)

        result = engine.run(
            dataset=dataset,
            signals=signals,
            risk_config=risk_config,
            mode="simple",
            direction="long",
        )

        metrics = metrics_engine.compute(
            equity_curve=result["equity_curve"],
            trades=result.get("trades"),
            initial_capital=risk_config.initial_capital,
            context={"timeframe": timeframe},
        )

        total_trades = int(metrics.get("total_trades", 0))
        sharpe = float(metrics.get("sharpe", 0.0))
        if np.isnan(sharpe) or np.isinf(sharpe):
            sharpe = 0.0

        if total_trades >= 10 and sharpe > best_sharpe:
            best_sharpe = sharpe
            best_metrics = metrics
            best_params = params

        return sharpe if total_trades >= 10 else -10.0

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    return {
        "best_sharpe": best_sharpe,
        "best_metrics": best_metrics,
        "best_params": best_params,
        "n_valid_trials": sum(1 for t in study.trials if t.value is not None and t.value > -5),
    }


def main():
    for tf in ["1h", "4h"]:
        print(f"\n{'#'*70}")
        print(f"#  TIMEFRAME: {tf}")
        print(f"{'#'*70}")

        ohlcv = load_ohlcv("BTCUSDT", tf, months=36)
        print(f"Data: {len(ohlcv)} bars, {ohlcv.index[0]} to {ohlcv.index[-1]}")

        indicators = list(INDICATOR_REGISTRY.keys())
        print(f"Indicators to test: {indicators}")

        for ind_name in indicators:
            print(f"\n--- {ind_name} ({tf}) ---")
            try:
                # Test with 0% commission (pure signal quality)
                r0 = run_indicator_audit(ohlcv, ind_name, tf, n_trials=80, commission=0.0)
                if r0["best_metrics"]:
                    m = r0["best_metrics"]
                    print(f"  NO COMMISSION: Sharpe={m['sharpe']:.4f} Trades={m['total_trades']} "
                          f"WR={m['win_rate']:.1f}% PF={m['profit_factor']:.3f} "
                          f"Return={m['total_return_pct']:.2f}% MDD={m['max_drawdown_pct']:.2f}%")
                    print(f"  Params: {r0['best_params']}")
                    print(f"  Valid trials: {r0['n_valid_trials']}/80")
                else:
                    print(f"  NO VALID TRIALS (all < 10 trades)")

                # Test with standard commission
                r1 = run_indicator_audit(ohlcv, ind_name, tf, n_trials=80, commission=0.07)
                if r1["best_metrics"]:
                    m = r1["best_metrics"]
                    print(f"  WITH COMMISSION: Sharpe={m['sharpe']:.4f} Trades={m['total_trades']} "
                          f"WR={m['win_rate']:.1f}% PF={m['profit_factor']:.3f} "
                          f"Return={m['total_return_pct']:.2f}% MDD={m['max_drawdown_pct']:.2f}%")

                if r0["best_metrics"] and r1["best_metrics"]:
                    delta = r0["best_metrics"]["sharpe"] - r1["best_metrics"]["sharpe"]
                    if r0["best_metrics"]["sharpe"] > 0:
                        print(f"  ** HAS EDGE (Sharpe > 0 w/o commission) **")
                    if r0["best_metrics"]["sharpe"] > 0 and r1["best_metrics"]["sharpe"] <= 0:
                        print(f"  ** COMMISSION KILLS EDGE **")
            except Exception as e:
                print(f"  ERROR: {e}")


if __name__ == "__main__":
    main()
