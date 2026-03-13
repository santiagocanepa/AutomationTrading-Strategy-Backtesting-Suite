"""Fast single-indicator audit — lean version."""
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

engine = BacktestEngine()
metrics_engine = MetricsEngine()


def load_ohlcv(symbol, timeframe, months=36):
    store = ParquetStore(base_dir=Path("data/raw"))
    df_1m = store.read("binance", symbol, "1m")
    cutoff = df_1m.index.max() - pd.DateOffset(months=months)
    df_1m = df_1m.loc[df_1m.index >= cutoff]
    if timeframe != "1m":
        resampler = OHLCVResampler()
        return resampler.resample(df_1m, timeframe, base_tf="1m")
    return df_1m


def test_indicator(ohlcv, ind_name, timeframe, n_trials=40):
    indicator = get_indicator(ind_name)
    schema = indicator.params_schema()

    risk_config = RiskConfig(
        initial_capital=10_000.0,
        commission_pct=0.0,
        slippage_pct=0.0,
    )
    dataset = BacktestDataset(
        exchange="binance", symbol="BTCUSDT",
        base_timeframe=timeframe, ohlcv=ohlcv,
    )

    best_sharpe = -999.0
    best_metrics = None
    best_params = None
    valid_count = 0

    def objective(trial):
        nonlocal best_sharpe, best_metrics, best_params, valid_count
        params = {}
        for pn, ps in schema.items():
            pt = ps["type"]
            if pt == "int":
                params[pn] = trial.suggest_int(pn, ps["min"], ps["max"])
            elif pt == "float":
                params[pn] = trial.suggest_float(pn, ps["min"], ps["max"], step=ps.get("step"))
            elif pt == "str":
                params[pn] = trial.suggest_categorical(pn, ps["choices"])
            elif pt == "bool":
                params[pn] = trial.suggest_categorical(pn, [True, False])

        sig = indicator.compute(ohlcv, **params)
        signals = StrategySignals(entry_long=sig)

        result = engine.run(
            dataset=dataset, signals=signals,
            risk_config=risk_config, mode="simple", direction="long",
        )
        metrics = metrics_engine.compute(
            equity_curve=result["equity_curve"],
            trades=result.get("trades"),
            initial_capital=risk_config.initial_capital,
            context={"timeframe": timeframe},
        )

        tc = int(metrics.get("total_trades", 0))
        sh = float(metrics.get("sharpe", 0.0))
        if np.isnan(sh) or np.isinf(sh):
            sh = 0.0

        if tc >= 10:
            valid_count += 1
            if sh > best_sharpe:
                best_sharpe = sh
                best_metrics = metrics
                best_params = params
            return sh
        return -10.0

    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)
    return best_sharpe, best_metrics, best_params, valid_count


def main():
    # Key indicators used in archetypes
    key_indicators = [
        "ssl_channel", "firestorm", "wavetrend_reversal",
        "rsi", "ema", "macd", "bollinger_bands", "atr",
    ]

    for tf in ["1h", "4h"]:
        ohlcv = load_ohlcv("BTCUSDT", tf, months=36)
        print(f"\n{'='*60}")
        print(f"  {tf}: {len(ohlcv)} bars ({ohlcv.index[0].date()} to {ohlcv.index[-1].date()})")
        print(f"  Commission=0% — testing pure signal quality")
        print(f"{'='*60}")
        print(f"{'Indicator':<22} {'Sharpe':>8} {'Trades':>7} {'WR%':>6} {'PF':>7} {'Ret%':>8} {'MDD%':>7} {'Valid':>6}")
        print("-" * 75)

        for ind in key_indicators:
            try:
                bs, bm, bp, vc = test_indicator(ohlcv, ind, tf, n_trials=40)
                if bm:
                    print(f"{ind:<22} {bm['sharpe']:>8.3f} {bm['total_trades']:>7} "
                          f"{bm['win_rate']:>6.1f} {bm['profit_factor']:>7.3f} "
                          f"{bm['total_return_pct']:>8.2f} {bm['max_drawdown_pct']:>7.2f} "
                          f"{vc:>4}/40")
                    if bs > 0:
                        print(f"  ** POSITIVE SHARPE ** params={bp}")
                else:
                    print(f"{ind:<22} {'N/A':>8} {'0':>7} {'-':>6} {'-':>7} {'-':>8} {'-':>7} {vc:>4}/40")
            except Exception as e:
                print(f"{ind:<22} ERROR: {e}")

    print("\n\nDone.")


if __name__ == "__main__":
    main()
