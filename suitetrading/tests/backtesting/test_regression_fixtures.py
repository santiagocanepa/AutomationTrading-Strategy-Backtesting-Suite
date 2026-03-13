"""Parametrized regression tests that replay frozen fixtures.

Each JSON fixture in ``tests/fixtures/backtest_regressions/`` contains
deterministic bar data, signals, config and expected results. Any change
to the FSM or runner that alters these results constitutes a regression.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from suitetrading.backtesting._internal.runners import run_fsm_backtest
from suitetrading.backtesting._internal.schemas import BacktestDataset, StrategySignals
from suitetrading.risk.contracts import RiskConfig

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "backtest_regressions"


def _load_fixtures() -> list[dict]:
    fixtures = []
    for p in sorted(FIXTURES_DIR.glob("*.json")):
        with p.open() as f:
            fixtures.append(json.load(f))
    return fixtures


def _build_dataset(fix: dict) -> BacktestDataset:
    bars = fix["bars"]
    idx = pd.date_range("2025-01-01", periods=len(bars), freq="h", tz="UTC")
    ohlcv = pd.DataFrame(bars, columns=["open", "high", "low", "close"], index=idx)
    ohlcv["volume"] = 1000.0
    return BacktestDataset(exchange="test", symbol="TEST", base_timeframe="1h", ohlcv=ohlcv)


def _build_signals(fix: dict) -> StrategySignals:
    n = fix["n_bars"]
    idx = pd.date_range("2025-01-01", periods=n, freq="h", tz="UTC")
    entry = pd.Series(False, index=idx)
    exit_s = pd.Series(False, index=idx)
    trail = pd.Series(False, index=idx)
    for b in fix.get("entry_bars", []):
        entry.iat[b] = True
    for b in fix.get("exit_bars", []):
        exit_s.iat[b] = True
    for b in fix.get("trailing_bars", []):
        trail.iat[b] = True
    return StrategySignals(entry_long=entry, exit_long=exit_s, trailing_long=trail)


_FIXTURES = _load_fixtures()


@pytest.mark.parametrize("fixture", _FIXTURES, ids=[f["name"] for f in _FIXTURES])
class TestRegressionFixtures:
    def test_trade_count(self, fixture: dict) -> None:
        ds = _build_dataset(fixture)
        sigs = _build_signals(fixture)
        cfg = RiskConfig(**fixture["config"])
        result = run_fsm_backtest(dataset=ds, signals=sigs, risk_config=cfg, direction=fixture["direction"])
        assert len(result.trades) == fixture["expected_trades"], (
            f"Expected {fixture['expected_trades']} trades, got {len(result.trades)}"
        )

    def test_final_equity(self, fixture: dict) -> None:
        ds = _build_dataset(fixture)
        sigs = _build_signals(fixture)
        cfg = RiskConfig(**fixture["config"])
        result = run_fsm_backtest(dataset=ds, signals=sigs, risk_config=cfg, direction=fixture["direction"])
        np.testing.assert_almost_equal(result.final_equity, fixture["expected_final_equity"], decimal=2)

    def test_trade_details(self, fixture: dict) -> None:
        ds = _build_dataset(fixture)
        sigs = _build_signals(fixture)
        cfg = RiskConfig(**fixture["config"])
        result = run_fsm_backtest(dataset=ds, signals=sigs, risk_config=cfg, direction=fixture["direction"])
        for i, expected in enumerate(fixture["trade_details"]):
            actual = result.trades[i]
            assert actual.entry_bar == expected["entry_bar"]
            assert actual.exit_bar == expected["exit_bar"]
            assert actual.exit_reason == expected["exit_reason"]
            np.testing.assert_almost_equal(float(actual.pnl), expected["pnl"], decimal=2)
