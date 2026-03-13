#!/usr/bin/env python3
"""Run a practical backtesting batch focused on risk management.

This script is intentionally opinionated:

- it uses a small set of entry triggers,
- it forces ``mode='fsm'`` to exercise the real risk engine,
- it varies only the risk parameters that are clearly wired into the
  current backtesting runner.

The goal is not to find a final strategy. The goal is to start measuring
how much of the edge comes from risk policy instead of endlessly adding
indicators.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.backtesting._internal.datasets import build_dataset_from_df
from suitetrading.backtesting._internal.schemas import StrategySignals
from suitetrading.backtesting.engine import BacktestEngine
from suitetrading.backtesting.metrics import MetricsEngine
from suitetrading.backtesting.reporting import ReportingEngine
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.indicators.custom.firestorm import Firestorm
from suitetrading.indicators.custom.ssl_channel import SSLChannel, SSLChannelLow
from suitetrading.indicators.custom.wavetrend import WaveTrendReversal
from suitetrading.risk.archetypes import get_archetype


@dataclass(frozen=True)
class StrategyPreset:
    name: str
    archetype: str
    family: str
    description: str


@dataclass(frozen=True)
class RiskPreset:
    name: str
    overrides: dict[str, Any]
    note: str


STRATEGIES: dict[str, StrategyPreset] = {
    "ssl_trend": StrategyPreset(
        name="ssl_trend",
        archetype="trend_following",
        family="trend",
        description="SSL Channel entry + SSL low trailing signal",
    ),
    "firestorm_trend": StrategyPreset(
        name="firestorm_trend",
        archetype="trend_following",
        family="trend",
        description="Firestorm trend change as entry/exit",
    ),
    "wavetrend_meanrev": StrategyPreset(
        name="wavetrend_meanrev",
        archetype="mean_reversion",
        family="mean_reversion",
        description="WaveTrend reversal as mean reversion trigger",
    ),
}


TREND_RISK_PRESETS: list[RiskPreset] = [
    RiskPreset("base", {}, "TrendFollowing base preset"),
    RiskPreset(
        "tight_stop",
        {"stop": {"atr_multiple": 2.0}},
        "Closer invalidation, less room for trend noise",
    ),
    RiskPreset(
        "wide_stop",
        {"stop": {"atr_multiple": 4.0}},
        "Wider invalidation, more room for trend continuation",
    ),
    RiskPreset(
        "atr_sizer",
        {"sizing": {"model": "atr", "risk_pct": 0.75, "atr_multiple": 2.0}},
        "Volatility-adjusted position sizing instead of fixed fractional",
    ),
    RiskPreset(
        "no_pyramid",
        {"pyramid": {"enabled": False, "max_adds": 0}},
        "Disable pyramiding to isolate initial-entry quality",
    ),
    RiskPreset(
        "partial_tp_on",
        {
            "partial_tp": {"enabled": True, "close_pct": 35.0, "trigger": "signal", "profit_distance_factor": 1.01},
            "break_even": {"enabled": True, "buffer": 1.0007},
        },
        "Adds partial exit plus break-even after confirmation",
    ),
]


MEANREV_RISK_PRESETS: list[RiskPreset] = [
    RiskPreset(
        "base_safe",
        {"time_exit": {"enabled": False}},
        "Mean reversion base with time exit disabled for now",
    ),
    RiskPreset(
        "tight_stop",
        {"time_exit": {"enabled": False}, "stop": {"atr_multiple": 1.0}},
        "Faster invalidation for failed reversals",
    ),
    RiskPreset(
        "loose_stop",
        {"time_exit": {"enabled": False}, "stop": {"atr_multiple": 2.0}},
        "Give reversals more space before invalidation",
    ),
    RiskPreset(
        "time_exit",
        {"time_exit": {"enabled": True, "max_bars": 20}},
        "Close after 20 bars to limit mean-reversion holding time",
    ),
    RiskPreset(
        "no_partial_tp",
        {"time_exit": {"enabled": False}, "partial_tp": {"enabled": False}},
        "Measure how much expectancy depends on taking partials",
    ),
    RiskPreset(
        "no_break_even",
        {"time_exit": {"enabled": False}, "break_even": {"enabled": False}},
        "Measure whether BE is helping or cutting winners too early",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a practical risk-focused backtesting batch")
    parser.add_argument("--symbol", default=None, help="Single symbol (backward compat)")
    parser.add_argument("--symbols", nargs="+", default=None, help="Multiple symbols")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--timeframe", default=None, help="Single timeframe (backward compat)")
    parser.add_argument("--timeframes", nargs="+", default=None, help="Multiple timeframes")
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--strategies", nargs="+", choices=sorted(STRATEGIES), default=list(STRATEGIES))
    parser.add_argument("--data-dir", default=str(ROOT / "data" / "raw"))
    parser.add_argument("--output-dir", default=str(ROOT / "artifacts" / "risk_lab"))
    args = parser.parse_args()
    # Resolve symbols: --symbols takes precedence, else --symbol, else default
    if args.symbols is None:
        args.symbols = [args.symbol] if args.symbol else ["BTCUSDT"]
    # Resolve timeframes: --timeframes takes precedence, else --timeframe, else default
    if args.timeframes is None:
        args.timeframes = [args.timeframe] if args.timeframe else ["1h"]
    return args


def load_timeframe_data(*, exchange: str, symbol: str, timeframe: str, months: int, data_dir: Path) -> pd.DataFrame:
    store = ParquetStore(base_dir=data_dir)

    if timeframe == "1m":
        df = store.read(exchange, symbol, "1m")
        cutoff = df.index.max() - pd.DateOffset(months=months)
        return df.loc[df.index >= cutoff].copy()

    df_1m = store.read(exchange, symbol, "1m")
    cutoff = df_1m.index.max() - pd.DateOffset(months=months)
    df_1m = df_1m.loc[df_1m.index >= cutoff]
    resampler = OHLCVResampler()
    return resampler.resample(df_1m, timeframe, base_tf="1m")


def build_strategy_signals(strategy_name: str, ohlcv: pd.DataFrame) -> StrategySignals:
    if strategy_name == "ssl_trend":
        entry_long = SSLChannel().compute(ohlcv, length=12, hold_bars=4, direction="long")
        exit_long = SSLChannel().compute(ohlcv, length=12, hold_bars=1, direction="short")
        trailing_long = SSLChannelLow().compute(ohlcv, length=12, direction="long")
        return StrategySignals(entry_long=entry_long, exit_long=exit_long, trailing_long=trailing_long)

    if strategy_name == "firestorm_trend":
        entry_long = Firestorm().compute(ohlcv, period=10, multiplier=1.8, hold_bars=1, direction="long")
        exit_long = Firestorm().compute(ohlcv, period=10, multiplier=1.8, hold_bars=1, direction="short")
        return StrategySignals(entry_long=entry_long, exit_long=exit_long)

    if strategy_name == "wavetrend_meanrev":
        entry_long = WaveTrendReversal().compute(
            ohlcv,
            channel_len=9,
            average_len=12,
            ma_len=3,
            ob_level=60.0,
            os_level=-60.0,
            hold_bars=3,
            direction="long",
        )
        exit_long = WaveTrendReversal().compute(
            ohlcv,
            channel_len=9,
            average_len=12,
            ma_len=3,
            ob_level=60.0,
            os_level=-60.0,
            hold_bars=1,
            direction="short",
        )
        return StrategySignals(entry_long=entry_long, exit_long=exit_long, trailing_long=exit_long)

    raise ValueError(f"Unknown strategy preset: {strategy_name!r}")


def risk_presets_for(strategy: StrategyPreset) -> list[RiskPreset]:
    if strategy.family == "trend":
        return TREND_RISK_PRESETS
    if strategy.family == "mean_reversion":
        return MEANREV_RISK_PRESETS
    raise ValueError(f"Unknown strategy family: {strategy.family!r}")


def run_batch(args: argparse.Namespace) -> tuple[pd.DataFrame, Path]:
    engine = BacktestEngine()
    metrics_engine = MetricsEngine()
    rows: list[dict[str, Any]] = []

    output_root = Path(args.output_dir)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    syms_label = "_".join(args.symbols)
    tfs_label = "_".join(args.timeframes)
    run_dir = output_root / f"{syms_label}_{tfs_label}_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    total_combos = len(args.symbols) * len(args.timeframes) * len(args.strategies)
    print(f"Risk Lab: {len(args.symbols)} symbols × {len(args.timeframes)} TFs × {len(args.strategies)} strategies")

    for symbol in args.symbols:
        for timeframe in args.timeframes:
            print(f"\n{'='*60}")
            print(f"  {symbol} @ {timeframe}")
            print(f"{'='*60}")

            try:
                ohlcv = load_timeframe_data(
                    exchange=args.exchange,
                    symbol=symbol,
                    timeframe=timeframe,
                    months=args.months,
                    data_dir=Path(args.data_dir),
                )
            except (FileNotFoundError, KeyError) as exc:
                print(f"  SKIP: {exc}")
                continue

            dataset = build_dataset_from_df(
                ohlcv, exchange=args.exchange, symbol=symbol, base_timeframe=timeframe,
            )

            for strategy_name in args.strategies:
                strategy = STRATEGIES[strategy_name]
                signals = build_strategy_signals(strategy_name, ohlcv)
                presets = risk_presets_for(strategy)

                print(f"\n  --- {strategy.name} ({strategy.description}) ---")

                for preset in presets:
                    risk_config = get_archetype(strategy.archetype).build_config(**preset.overrides)
                    result = engine.run(
                        dataset=dataset,
                        signals=signals,
                        risk_config=risk_config,
                        mode="fsm",
                        direction="long",
                        context={"strategy": strategy.name, "risk_profile": preset.name},
                    )
                    metrics = metrics_engine.compute(
                        equity_curve=result["equity_curve"],
                        trades=result["trades"],
                        initial_capital=risk_config.initial_capital,
                    )

                    row = {
                        "run_label": f"{symbol}__{timeframe}__{strategy.name}__{preset.name}",
                        "strategy": strategy.name,
                        "strategy_family": strategy.family,
                        "risk_profile": preset.name,
                        "risk_note": preset.note,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "bars": len(ohlcv),
                        "archetype": risk_config.archetype,
                        "mode": result["mode"],
                        "stop_model": risk_config.stop.model,
                        "stop_atr_multiple": risk_config.stop.atr_multiple,
                        "sizing_model": risk_config.sizing.model,
                        "risk_pct": risk_config.sizing.risk_pct,
                        "partial_tp_enabled": risk_config.partial_tp.enabled,
                        "partial_tp_close_pct": risk_config.partial_tp.close_pct,
                        "break_even_enabled": risk_config.break_even.enabled,
                        "pyramid_enabled": risk_config.pyramid.enabled,
                        "pyramid_max_adds": risk_config.pyramid.max_adds,
                        "time_exit_enabled": risk_config.time_exit.enabled,
                        "overrides_json": json.dumps(preset.overrides, sort_keys=True),
                        **metrics,
                    }
                    rows.append(row)

                    print(
                        f"    {preset.name:<16} sharpe={row['sharpe']:>7.3f}  "
                        f"return={row['total_return_pct']:>8.2f}%  "
                        f"dd={row['max_drawdown_pct']:>7.2f}%  trades={row['total_trades']:>4}"
                    )

    results = pd.DataFrame(rows).sort_values(["sharpe", "total_return_pct"], ascending=False)
    results_path = run_dir / "risk_lab_results.csv"
    results.to_csv(results_path, index=False)

    reporting_ready = results[[
        "strategy", "strategy_family", "risk_profile", "symbol", "timeframe", "archetype",
        "net_profit", "total_return_pct", "sharpe", "sortino", "max_drawdown_pct",
        "calmar", "win_rate", "profit_factor", "average_trade", "max_consecutive_losses",
        "total_trades",
    ]].copy()
    ReportingEngine().build_dashboard(results=reporting_ready, output_dir=run_dir)

    notes = [
        "# Risk Lab Notes",
        "",
        f"Symbols: {', '.join(args.symbols)}",
        f"Timeframes: {', '.join(args.timeframes)}",
        f"Total campaigns: {len(rows)}",
        "",
        "This batch forces mode=fsm to exercise the real state machine.",
        "",
        "Included by design:",
        "- stop distance via RiskConfig.stop",
        "- sizing model and risk_pct",
        "- partial TP on/off",
        "- break-even on/off",
        "- pyramiding on/off",
        "- time exit (mean reversion family)",
        "- portfolio limits (feature-flagged, off by default)",
        "- trailing policy mode (signal default, policy available)",
    ]
    (run_dir / "README.md").write_text("\n".join(notes))

    return results, run_dir


def main() -> None:
    args = parse_args()
    results, run_dir = run_batch(args)

    print("\n=== Top 10 by Sharpe ===")
    top = results.head(10)
    for _, row in top.iterrows():
        print(
            f"{row['run_label']:<32} sharpe={row['sharpe']:>7.3f}  "
            f"return={row['total_return_pct']:>8.2f}%  dd={row['max_drawdown_pct']:>7.2f}%"
        )

    print(f"\nResults written to {run_dir}")


if __name__ == "__main__":
    main()