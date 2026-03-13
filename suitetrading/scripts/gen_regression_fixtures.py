"""Generate regression fixture JSON files."""
import json
import numpy as np
import pandas as pd

from suitetrading.backtesting._internal.runners import run_fsm_backtest
from suitetrading.backtesting._internal.schemas import BacktestDataset, StrategySignals
from suitetrading.risk.contracts import RiskConfig


def make_dataset(prices):
    idx = pd.date_range("2025-01-01", periods=len(prices), freq="h", tz="UTC")
    ohlcv = pd.DataFrame(prices, columns=["open", "high", "low", "close"], index=idx)
    ohlcv["volume"] = 1000.0
    return BacktestDataset(exchange="test", symbol="TEST", base_timeframe="1h", ohlcv=ohlcv)


def make_signals(n, entry_bars=None, exit_bars=None, trailing_bars=None):
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    entry = pd.Series(False, index=idx)
    exit_s = pd.Series(False, index=idx)
    trail = pd.Series(False, index=idx)
    for b in (entry_bars or []):
        entry.iat[b] = True
    for b in (exit_bars or []):
        exit_s.iat[b] = True
    for b in (trailing_bars or []):
        trail.iat[b] = True
    return StrategySignals(entry_long=entry, exit_long=exit_s, trailing_long=trail)


def gen_fixture(name, n, bars, entry_bars, exit_bars, trailing_bars, cfg_dict, direction="long"):
    ds = make_dataset(bars[:n])
    sigs = make_signals(n, entry_bars=entry_bars, exit_bars=exit_bars, trailing_bars=trailing_bars)
    cfg = RiskConfig(**cfg_dict)
    r = run_fsm_backtest(dataset=ds, signals=sigs, risk_config=cfg, direction=direction)
    fix = {
        "name": name,
        "config": cfg.model_dump(),
        "direction": direction,
        "entry_bars": entry_bars,
        "exit_bars": exit_bars,
        "trailing_bars": trailing_bars,
        "n_bars": n,
        "bars": [list(b) for b in bars[:n]],
        "expected_trades": len(r.trades),
        "expected_final_equity": round(float(r.final_equity), 6),
        "trade_details": [
            {"entry_bar": t.entry_bar, "exit_bar": t.exit_bar, "exit_reason": t.exit_reason, "pnl": round(float(t.pnl), 6)}
            for t in r.trades
        ],
    }
    path = f"tests/fixtures/backtest_regressions/{name}.json"
    with open(path, "w") as f:
        json.dump(fix, f, indent=2)
    print(f"  {name}: {len(r.trades)} trades, equity={r.final_equity:.2f}")
    for t in r.trades:
        print(f"    trade: bar {t.entry_bar}->{t.exit_bar} reason={t.exit_reason} pnl={t.pnl:.4f}")
    return fix


if __name__ == "__main__":
    # Fixture 1: basic_long_sl — entry, then price drops to trigger SL
    bars1 = []
    for i in range(30):
        c = 100 + i * 2
        bars1.append((c - 1, c + 3, c - 3, c))
    for i in range(30):
        c = 158 - i * 4
        bars1.append((c + 1, c + 3, c - 3, c))
    print("Fixture 1: basic_long_sl")
    gen_fixture("basic_long_sl", 60, bars1, [15], [], [],
                {"pyramid": {"enabled": False, "max_adds": 0}, "partial_tp": {"enabled": False},
                 "break_even": {"enabled": False}, "stop": {"atr_multiple": 2.0}})

    # Fixture 2: long_with_tp1_trailing — entry, TP1 fires, then trailing exit
    bars2 = []
    for i in range(40):
        c = 100 + i * 3
        bars2.append((c - 1, c + 4, c - 4, c))
    for i in range(40):
        c = 217 + i * 0.5
        bars2.append((c - 1, c + 4, c - 4, c))
    print("Fixture 2: long_with_tp1_trailing")
    gen_fixture("long_with_tp1_trailing", 80, bars2, [15], [25], [50],
                {"partial_tp": {"enabled": True, "close_pct": 35.0, "trigger": "signal", "profit_distance_factor": 1.001},
                 "break_even": {"enabled": True, "buffer": 1.0007},
                 "pyramid": {"enabled": False, "max_adds": 0}, "stop": {"atr_multiple": 3.0}})

    # Fixture 3: time_exit — entry, time_exit triggers after 20 bars
    bars3 = []
    for i in range(60):
        c = 100 + i * 0.5
        bars3.append((c - 0.5, c + 2, c - 2, c))
    print("Fixture 3: time_exit")
    gen_fixture("time_exit", 60, bars3, [15], [], [],
                {"time_exit": {"enabled": True, "max_bars": 20},
                 "pyramid": {"enabled": False, "max_adds": 0}, "partial_tp": {"enabled": False},
                 "break_even": {"enabled": False}, "stop": {"atr_multiple": 20.0}})

    # Fixture 4: long_with_r_multiple_tp1 — TP1 via r_multiple trigger
    bars4 = []
    for i in range(40):
        c = 100 + i * 2
        bars4.append((c - 1, c + 3, c - 3, c))
    for i in range(40):
        c = 178 - i * 3
        bars4.append((c + 1, c + 3, c - 3, c))
    print("Fixture 4: long_with_r_multiple_tp1")
    gen_fixture("long_with_r_multiple_tp1", 80, bars4, [5], [], [],
                {"partial_tp": {"enabled": True, "close_pct": 50.0, "trigger": "r_multiple", "r_multiple": 0.5},
                 "break_even": {"enabled": True, "buffer": 1.0007, "activation": "after_tp1"},
                 "pyramid": {"enabled": False, "max_adds": 0}, "stop": {"atr_multiple": 2.0}})

    print("\nDone! All fixtures generated.")
