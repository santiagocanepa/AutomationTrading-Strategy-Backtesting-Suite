"""Tests for _internal/schemas.py — data contracts."""

import json

import pandas as pd
import pytest

from suitetrading.backtesting._internal.schemas import (
    BacktestCheckpoint,
    BacktestDataset,
    GridRequest,
    RESULT_COLUMNS,
    RunConfig,
    StrategySignals,
)


class TestRunConfig:
    def test_run_id_deterministic(self):
        a = RunConfig(symbol="BTCUSDT", timeframe="1h", archetype="trend_following",
                      indicator_params={"firestorm": {"period": 10}}, risk_overrides={})
        b = RunConfig(symbol="BTCUSDT", timeframe="1h", archetype="trend_following",
                      indicator_params={"firestorm": {"period": 10}}, risk_overrides={})
        assert a.run_id == b.run_id

    def test_run_id_changes_with_params(self):
        a = RunConfig(symbol="BTCUSDT", timeframe="1h", archetype="trend_following",
                      indicator_params={"firestorm": {"period": 10}}, risk_overrides={})
        b = RunConfig(symbol="BTCUSDT", timeframe="1h", archetype="trend_following",
                      indicator_params={"firestorm": {"period": 20}}, risk_overrides={})
        assert a.run_id != b.run_id

    def test_run_id_changes_with_symbol(self):
        a = RunConfig(symbol="BTCUSDT", timeframe="1h", archetype="a",
                      indicator_params={}, risk_overrides={})
        b = RunConfig(symbol="ETHUSDT", timeframe="1h", archetype="a",
                      indicator_params={}, risk_overrides={})
        assert a.run_id != b.run_id

    def test_run_id_is_hex_string(self):
        rc = RunConfig(symbol="X", timeframe="1h", archetype="a",
                       indicator_params={}, risk_overrides={})
        assert len(rc.run_id) == 16
        int(rc.run_id, 16)  # valid hex

    def test_custom_run_id_preserved(self):
        rc = RunConfig(symbol="X", timeframe="1h", archetype="a",
                       indicator_params={}, risk_overrides={}, run_id="custom123")
        assert rc.run_id == "custom123"


class TestBacktestDataset:
    def test_basic_creation(self, sample_ohlcv):
        ds = BacktestDataset(
            exchange="binance", symbol="BTCUSDT",
            base_timeframe="1h", ohlcv=sample_ohlcv,
        )
        assert ds.exchange == "binance"
        assert ds.aligned_frames == {}
        assert ds.metadata == {}


class TestStrategySignals:
    def test_defaults_are_none(self, sample_ohlcv):
        entry = pd.Series([True, False, True], index=sample_ohlcv.index[:3])
        sigs = StrategySignals(entry_long=entry)
        assert sigs.entry_short is None
        assert sigs.exit_long is None
        assert sigs.trailing_long is None


class TestBacktestCheckpoint:
    def test_default_fields(self):
        cp = BacktestCheckpoint(run_id="abc", chunk_id=0, status="pending")
        assert cp.started_at == ""
        assert cp.error == ""


class TestGridRequest:
    def test_creation(self):
        gr = GridRequest(
            symbols=["BTCUSDT"],
            timeframes=["1h"],
            indicator_space={"rsi": {"period": [14, 21]}},
            risk_space={"stop__atr_multiple": [2.0, 3.0]},
            archetypes=["trend_following"],
        )
        assert len(gr.symbols) == 1


class TestResultColumns:
    EXPECTED = [
        "run_id", "symbol", "timeframe", "archetype", "mode",
        "net_profit", "total_return_pct", "sharpe", "sortino",
        "max_drawdown_pct", "calmar", "win_rate", "profit_factor",
        "average_trade", "max_consecutive_losses", "total_trades",
    ]

    def test_exact_columns(self):
        assert RESULT_COLUMNS == self.EXPECTED

    def test_column_count(self):
        assert len(RESULT_COLUMNS) == 16

    def test_all_non_empty_strings(self):
        for col in RESULT_COLUMNS:
            assert isinstance(col, str) and col.strip() != ""


@pytest.fixture
def sample_ohlcv():
    idx = pd.date_range("2024-01-01", periods=100, freq="h", tz="UTC")
    return pd.DataFrame({
        "open": range(100, 200),
        "high": range(101, 201),
        "low": range(99, 199),
        "close": range(100, 200),
        "volume": [1000] * 100,
    }, index=idx)
