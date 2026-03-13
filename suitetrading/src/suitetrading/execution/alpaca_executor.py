"""Alpaca paper/live execution via alpaca-py TradingClient.

Wraps ``alpaca.trading.client.TradingClient`` with a clean interface
focused on crypto bracket orders (entry + SL + TP).

Configuration
-------------
Requires ``APCA_API_KEY_ID`` and ``APCA_API_SECRET_KEY`` environment
variables, or explicit key/secret arguments.  Paper mode (default)
routes to the Alpaca paper-trading endpoint automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from loguru import logger

try:
    from alpaca.trading.client import TradingClient
    from alpaca.trading.enums import OrderSide, OrderType, TimeInForce
    from alpaca.trading.requests import (
        GetAssetsRequest,
        LimitOrderRequest,
        MarketOrderRequest,
    )

    _ALPACA_AVAILABLE = True
except ImportError:
    _ALPACA_AVAILABLE = False


@dataclass(frozen=True)
class OrderResult:
    """Simplified order outcome."""

    order_id: str
    symbol: str
    side: str
    qty: float
    status: str
    filled_avg_price: float | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class AccountInfo:
    """Simplified account snapshot."""

    equity: float
    cash: float
    buying_power: float
    currency: str


@dataclass(frozen=True)
class PositionInfo:
    """Simplified position snapshot."""

    symbol: str
    qty: float
    side: str
    avg_entry_price: float
    market_value: float
    unrealized_pl: float


def _require_alpaca() -> None:
    if not _ALPACA_AVAILABLE:
        raise ImportError(
            "alpaca-py is required for AlpacaExecutor. "
            "Install with: pip install 'alpaca-py>=0.43'"
        )


class AlpacaExecutor:
    """Thin wrapper around alpaca-py TradingClient.

    Parameters
    ----------
    api_key
        Alpaca API key (or set ``APCA_API_KEY_ID`` env var).
    secret_key
        Alpaca secret key (or set ``APCA_API_SECRET_KEY`` env var).
    paper
        Use paper trading endpoint (default True).
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        *,
        paper: bool = True,
    ) -> None:
        _require_alpaca()
        self._client = TradingClient(
            api_key=api_key,
            secret_key=secret_key,
            paper=paper,
        )
        self._paper = paper
        logger.info(
            "AlpacaExecutor initialized (paper={})", paper,
        )

    @property
    def paper(self) -> bool:
        return self._paper

    def get_account(self) -> AccountInfo:
        """Fetch current account equity and cash."""
        acct = self._client.get_account()
        return AccountInfo(
            equity=float(acct.equity),
            cash=float(acct.cash),
            buying_power=float(acct.buying_power),
            currency=str(acct.currency),
        )

    def get_positions(self) -> list[PositionInfo]:
        """Fetch all open positions."""
        positions = self._client.get_all_positions()
        result = []
        for p in positions:
            result.append(PositionInfo(
                symbol=str(p.symbol),
                qty=float(p.qty),
                side=str(p.side),
                avg_entry_price=float(p.avg_entry_price),
                market_value=float(p.market_value),
                unrealized_pl=float(p.unrealized_pl),
            ))
        return result

    def get_position(self, symbol: str) -> PositionInfo | None:
        """Fetch position for a single symbol, or None if flat."""
        try:
            p = self._client.get_open_position(symbol)
            return PositionInfo(
                symbol=str(p.symbol),
                qty=float(p.qty),
                side=str(p.side),
                avg_entry_price=float(p.avg_entry_price),
                market_value=float(p.market_value),
                unrealized_pl=float(p.unrealized_pl),
            )
        except Exception as exc:
            # 404-style "no position" is expected — anything else deserves logging
            exc_name = type(exc).__name__
            if "not found" in str(exc).lower() or "404" in str(exc):
                return None
            logger.warning("get_position({}) failed ({}): {}", symbol, exc_name, exc)
            return None

    def submit_market_order(
        self,
        symbol: str,
        qty: float,
        side: str,
    ) -> OrderResult:
        """Submit a market order.

        Parameters
        ----------
        symbol
            Asset symbol (e.g. ``"BTC/USD"`` for crypto, ``"AAPL"`` for stock).
        qty
            Order quantity.
        side
            ``"buy"`` or ``"sell"``.
        """
        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        request = MarketOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.GTC,
        )
        order = self._client.submit_order(request)
        result = OrderResult(
            order_id=str(order.id),
            symbol=str(order.symbol),
            side=side,
            qty=float(order.qty) if order.qty else qty,
            status=str(order.status),
            filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
        )
        logger.info(
            "Order submitted: {} {} {} @ market → {}",
            side.upper(), qty, symbol, result.status,
        )
        return result

    def submit_limit_order(
        self,
        symbol: str,
        qty: float,
        side: str,
        limit_price: float,
    ) -> OrderResult:
        """Submit a limit order."""
        order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
        request = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=order_side,
            time_in_force=TimeInForce.GTC,
            limit_price=limit_price,
        )
        order = self._client.submit_order(request)
        result = OrderResult(
            order_id=str(order.id),
            symbol=str(order.symbol),
            side=side,
            qty=float(order.qty) if order.qty else qty,
            status=str(order.status),
            filled_avg_price=float(order.filled_avg_price) if order.filled_avg_price else None,
        )
        logger.info(
            "Limit order: {} {} {} @ {:.2f} → {}",
            side.upper(), qty, symbol, limit_price, result.status,
        )
        return result

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an open order. Returns True if cancelled."""
        try:
            self._client.cancel_order_by_id(order_id)
            logger.info("Order {} cancelled", order_id)
            return True
        except Exception as exc:
            logger.warning("Failed to cancel order {}: {}", order_id, exc)
            return False

    def close_position(self, symbol: str) -> OrderResult | None:
        """Close all shares/contracts for a symbol."""
        try:
            order = self._client.close_position(symbol)
            result = OrderResult(
                order_id=str(order.id) if hasattr(order, "id") else "",
                symbol=symbol,
                side="sell",
                qty=float(order.qty) if hasattr(order, "qty") and order.qty else 0.0,
                status=str(order.status) if hasattr(order, "status") else "submitted",
            )
            logger.info("Position closed: {}", symbol)
            return result
        except Exception as exc:
            logger.error("Failed to close position {} ({}): {}", symbol, type(exc).__name__, exc)
            raise

    def close_all_positions(self) -> int:
        """Close all open positions. Returns count of close orders sent."""
        try:
            responses = self._client.close_all_positions(cancel_orders=True)
            n = len(responses) if responses else 0
            logger.info("Closed all positions: {} orders sent", n)
            return n
        except Exception as exc:
            logger.error("Failed to close all positions ({}): {}", type(exc).__name__, exc)
            raise
