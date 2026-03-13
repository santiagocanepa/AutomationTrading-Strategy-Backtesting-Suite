"""Tests for AlpacaExecutor (mocked TradingClient)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# Skip all tests if alpaca-py is not installed
pytest.importorskip("alpaca.trading.client")


@dataclass
class FakeAccount:
    equity: str = "100000.00"
    cash: str = "50000.00"
    buying_power: str = "200000.00"
    currency: str = "USD"


@dataclass
class FakePosition:
    symbol: str = "BTC/USD"
    qty: str = "0.5"
    side: str = "long"
    avg_entry_price: str = "50000.00"
    market_value: str = "25000.00"
    unrealized_pl: str = "500.00"


@dataclass
class FakeOrder:
    id: str = "order-123"
    symbol: str = "BTC/USD"
    qty: str = "0.5"
    side: str = "buy"
    status: str = "accepted"
    filled_avg_price: str | None = None


@pytest.fixture()
def mock_trading_client():
    with patch("suitetrading.execution.alpaca_executor.TradingClient") as MockTC:
        client = MagicMock()
        MockTC.return_value = client
        yield client


@pytest.fixture()
def executor(mock_trading_client):
    from suitetrading.execution.alpaca_executor import AlpacaExecutor

    return AlpacaExecutor(api_key="test-key", secret_key="test-secret", paper=True)


class TestGetAccount:
    def test_returns_account_info(self, executor, mock_trading_client):
        mock_trading_client.get_account.return_value = FakeAccount()
        info = executor.get_account()
        assert info.equity == 100_000.0
        assert info.cash == 50_000.0
        assert info.currency == "USD"


class TestGetPositions:
    def test_returns_positions(self, executor, mock_trading_client):
        mock_trading_client.get_all_positions.return_value = [FakePosition()]
        positions = executor.get_positions()
        assert len(positions) == 1
        assert positions[0].symbol == "BTC/USD"
        assert positions[0].qty == 0.5

    def test_empty_positions(self, executor, mock_trading_client):
        mock_trading_client.get_all_positions.return_value = []
        assert executor.get_positions() == []


class TestGetPosition:
    def test_existing_position(self, executor, mock_trading_client):
        mock_trading_client.get_open_position.return_value = FakePosition()
        pos = executor.get_position("BTC/USD")
        assert pos is not None
        assert pos.symbol == "BTC/USD"

    def test_no_position(self, executor, mock_trading_client):
        mock_trading_client.get_open_position.side_effect = Exception("not found")
        pos = executor.get_position("BTC/USD")
        assert pos is None


class TestSubmitMarketOrder:
    def test_buy_order(self, executor, mock_trading_client):
        mock_trading_client.submit_order.return_value = FakeOrder()
        result = executor.submit_market_order("BTC/USD", 0.5, "buy")
        assert result.order_id == "order-123"
        assert result.side == "buy"
        assert result.qty == 0.5

    def test_sell_order(self, executor, mock_trading_client):
        mock_trading_client.submit_order.return_value = FakeOrder(side="sell")
        result = executor.submit_market_order("BTC/USD", 0.5, "sell")
        assert result.side == "sell"


class TestCancelOrder:
    def test_cancel_success(self, executor, mock_trading_client):
        mock_trading_client.cancel_order_by_id.return_value = None
        assert executor.cancel_order("order-123") is True

    def test_cancel_failure(self, executor, mock_trading_client):
        mock_trading_client.cancel_order_by_id.side_effect = Exception("not found")
        assert executor.cancel_order("order-123") is False


class TestClosePosition:
    def test_close_success(self, executor, mock_trading_client):
        mock_trading_client.close_position.return_value = FakeOrder()
        result = executor.close_position("BTC/USD")
        assert result is not None
        assert result.order_id == "order-123"

    def test_close_failure(self, executor, mock_trading_client):
        mock_trading_client.close_position.side_effect = Exception("no position")
        with pytest.raises(Exception, match="no position"):
            executor.close_position("BTC/USD")


class TestCloseAllPositions:
    def test_close_all(self, executor, mock_trading_client):
        mock_trading_client.close_all_positions.return_value = [FakeOrder(), FakeOrder()]
        n = executor.close_all_positions()
        assert n == 2
