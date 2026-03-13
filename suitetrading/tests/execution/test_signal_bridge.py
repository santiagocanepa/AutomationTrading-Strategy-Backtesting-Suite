"""Tests for SignalBridge (mocked AlpacaExecutor)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from suitetrading.execution.alpaca_executor import AccountInfo, OrderResult, PositionInfo
from suitetrading.execution.signal_bridge import BridgeState, SignalBridge
from suitetrading.risk.contracts import RiskConfig


@pytest.fixture()
def mock_executor() -> MagicMock:
    executor = MagicMock()
    executor.paper = True
    executor.get_account.return_value = AccountInfo(
        equity=100_000.0, cash=50_000.0, buying_power=200_000.0, currency="USD",
    )
    executor.get_position.return_value = None
    executor.submit_market_order.return_value = OrderResult(
        order_id="order-001", symbol="BTC/USD", side="buy",
        qty=0.1, status="accepted",
    )
    executor.close_position.return_value = OrderResult(
        order_id="order-002", symbol="BTC/USD", side="sell",
        qty=0.1, status="accepted",
    )
    return executor


@pytest.fixture()
def risk_config() -> RiskConfig:
    from suitetrading.risk.archetypes import get_archetype
    return get_archetype("trend_following").build_config()


@pytest.fixture()
def bridge(mock_executor: MagicMock, risk_config: RiskConfig) -> SignalBridge:
    return SignalBridge(
        executor=mock_executor,
        risk_config=risk_config,
        symbol="BTC/USD",
    )


def make_bar(close: float = 50000.0, high: float = 50500.0, low: float = 49500.0) -> dict:
    return {
        "open": close - 100,
        "high": high,
        "low": low,
        "close": close,
        "volume": 1000.0,
        "timestamp": "2026-01-01T00:00:00Z",
    }


class TestEntrySignal:
    def test_entry_long_when_flat(self, bridge: SignalBridge) -> None:
        action = bridge.on_bar(make_bar(), {"entry_long": True})
        assert action == "entry"
        assert bridge.state.position == "long"
        assert bridge.state.entry_price == 50000.0

    def test_no_entry_when_no_signal(self, bridge: SignalBridge) -> None:
        action = bridge.on_bar(make_bar(), {"entry_long": False})
        assert action is None
        assert bridge.state.position == "flat"

    def test_no_double_entry(self, bridge: SignalBridge) -> None:
        bridge.on_bar(make_bar(), {"entry_long": True})
        # Second entry signal while already long → no action
        action = bridge.on_bar(make_bar(), {"entry_long": True})
        assert action is None  # already long, SL/TP not hit, no exit signal


class TestExitSignal:
    def test_exit_on_signal(self, bridge: SignalBridge) -> None:
        bridge.on_bar(make_bar(), {"entry_long": True})
        action = bridge.on_bar(make_bar(), {"exit_long": True})
        assert action == "exit_signal"
        assert bridge.state.position == "flat"

    def test_exit_on_stop_loss(self, bridge: SignalBridge) -> None:
        bridge.on_bar(make_bar(close=50000.0), {"entry_long": True})
        # Bar where low hits below SL
        sl = bridge.state.stop_loss
        action = bridge.on_bar(make_bar(low=sl - 100), {})
        assert action == "exit_sl"
        assert bridge.state.position == "flat"

    def test_exit_on_take_profit(self, bridge: SignalBridge) -> None:
        bridge.on_bar(make_bar(close=50000.0), {"entry_long": True})
        # Bar where high hits above TP
        tp = bridge.state.take_profit
        action = bridge.on_bar(make_bar(high=tp + 100), {})
        assert action == "exit_tp"
        assert bridge.state.position == "flat"


class TestReconcile:
    def test_reconcile_detects_lost_position(self, bridge: SignalBridge) -> None:
        bridge.on_bar(make_bar(), {"entry_long": True})
        assert bridge.state.position == "long"
        # Executor says no position
        bridge._executor.get_position.return_value = None
        bridge.reconcile()
        assert bridge.state.position == "flat"

    def test_reconcile_detects_unexpected_position(
        self, bridge: SignalBridge, mock_executor: MagicMock,
    ) -> None:
        assert bridge.state.position == "flat"
        mock_executor.get_position.return_value = PositionInfo(
            symbol="BTC/USD", qty=0.5, side="long",
            avg_entry_price=50000.0, market_value=25000.0, unrealized_pl=0.0,
        )
        # Should log warning but not crash
        bridge.reconcile()


class TestTradeLog:
    def test_trade_logged_after_round_trip(self, bridge: SignalBridge) -> None:
        bridge.on_bar(make_bar(), {"entry_long": True})
        bridge.on_bar(make_bar(), {"exit_long": True})
        assert len(bridge.trades) == 1
        trade = bridge.trades[0]
        assert trade.side == "long"
        assert trade.exit_reason == "exit_signal"
