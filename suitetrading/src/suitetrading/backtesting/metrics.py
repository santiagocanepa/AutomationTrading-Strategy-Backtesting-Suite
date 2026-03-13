"""Metrics engine — vectorised computation of backtest performance stats.

All metrics are computed from equity curves and/or trade lists using
NumPy for speed.  No external metrics library required.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


class MetricsEngine:
    """Compute standardised performance metrics for a backtest run."""

    TRADING_DAYS_YEAR = 365  # crypto markets run 24/7

    def compute(
        self,
        *,
        equity_curve: pd.Series | np.ndarray,
        trades: pd.DataFrame | None = None,
        initial_capital: float = 10_000.0,
        context: dict[str, Any] | None = None,
    ) -> dict[str, float | int]:
        """Return the full metrics dict for a single run.

        ``equity_curve`` is an array of equity values at each bar.
        ``trades`` is a DataFrame with at least a ``pnl`` column.
        ``context`` may contain ``"timeframe"`` (e.g. ``"15m"``) to
        select the correct annualisation factor for Sharpe / Sortino.
        """
        eq = np.asarray(equity_curve, dtype=np.float64)
        if len(eq) == 0:
            return self._empty_metrics()

        returns = _safe_returns(eq)
        net_profit = float(eq[-1] - initial_capital)
        total_return_pct = (eq[-1] / initial_capital - 1.0) * 100.0

        tf = (context or {}).get("timeframe")
        ann = _annualisation_factor(tf) if tf else np.sqrt(365 * 24)

        sharpe = _sharpe(returns, annualisation=ann)
        sortino = _sortino(returns, annualisation=ann)
        max_dd_pct = _max_drawdown_pct(eq)
        calmar = _calmar(total_return_pct, max_dd_pct)

        trade_metrics = self._trade_metrics(trades)

        result: dict[str, float | int] = {
            "net_profit": round(net_profit, 4),
            "total_return_pct": round(total_return_pct, 4),
            "sharpe": round(sharpe, 4),
            "sortino": round(sortino, 4),
            "max_drawdown_pct": round(max_dd_pct, 4),
            "calmar": round(calmar, 4),
            **trade_metrics,
        }
        return result

    @staticmethod
    def _trade_metrics(trades: pd.DataFrame | None) -> dict[str, float | int]:
        if trades is None or trades.empty:
            return {
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "average_trade": 0.0,
                "max_consecutive_losses": 0,
                "total_trades": 0,
            }

        pnl = trades["pnl"].values.astype(np.float64)
        comm = trades["commission"].values.astype(np.float64) if "commission" in trades.columns else np.zeros(len(pnl))
        net = pnl - comm
        n = len(net)
        wins = net > 0
        losses = net < 0

        win_rate = float(np.sum(wins) / n * 100.0) if n > 0 else 0.0
        gross_profit = float(np.sum(net[wins])) if np.any(wins) else 0.0
        gross_loss = float(np.abs(np.sum(net[losses]))) if np.any(losses) else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
        average_trade = float(np.mean(net)) if n > 0 else 0.0
        max_consec_losses = _max_consecutive(~wins & (net != 0))

        return {
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else 999.99,
            "average_trade": round(average_trade, 4),
            "max_consecutive_losses": int(max_consec_losses),
            "total_trades": n,
        }

    @staticmethod
    def _empty_metrics() -> dict[str, float | int]:
        return {
            "net_profit": 0.0,
            "total_return_pct": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown_pct": 0.0,
            "calmar": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "average_trade": 0.0,
            "max_consecutive_losses": 0,
            "total_trades": 0,
        }


# ── Annualisation helpers ──────────────────────────────────────────────

_BARS_PER_YEAR: dict[str, int] = {
    "1m": 365 * 24 * 60,
    "5m": 365 * 24 * 12,
    "15m": 365 * 24 * 4,
    "30m": 365 * 24 * 2,
    "1h": 365 * 24,
    "2h": 365 * 12,
    "4h": 365 * 6,
    "6h": 365 * 4,
    "8h": 365 * 3,
    "12h": 365 * 2,
    "1d": 365,
    "1w": 52,
}


def _annualisation_factor(timeframe: str | None) -> float:
    """Return sqrt(bars_per_year) for the given timeframe string."""
    if timeframe is None:
        return float(np.sqrt(365 * 24))
    bpy = _BARS_PER_YEAR.get(timeframe)
    if bpy is None:
        return float(np.sqrt(365 * 24))
    return float(np.sqrt(bpy))


# ── Vectorised metric functions ───────────────────────────────────────

def _safe_returns(equity: np.ndarray) -> np.ndarray:
    """Bar-to-bar returns, handling zeros gracefully."""
    prev = np.roll(equity, 1)
    prev[0] = equity[0]
    mask = prev != 0
    returns = np.zeros_like(equity)
    returns[mask] = (equity[mask] - prev[mask]) / prev[mask]
    return returns


def _sharpe(returns: np.ndarray, annualisation: float = np.sqrt(365 * 24)) -> float:
    """Annualised Sharpe ratio (assuming hourly bars as default)."""
    if len(returns) < 2:
        return 0.0
    std = float(np.std(returns, ddof=1))
    if std == 0:
        return 0.0
    return float(np.mean(returns) / std * annualisation)


def _sortino(returns: np.ndarray, annualisation: float = np.sqrt(365 * 24)) -> float:
    """Annualised Sortino ratio (downside deviation only)."""
    if len(returns) < 2:
        return 0.0
    downside = returns[returns < 0]
    if len(downside) < 2:
        return float("nan")
    dd = float(np.std(downside, ddof=1))
    if dd == 0:
        return 0.0
    return float(np.mean(returns) / dd * annualisation)


def _max_drawdown_pct(equity: np.ndarray) -> float:
    """Maximum drawdown as a percentage of the peak."""
    if len(equity) == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    drawdown = (peak - equity) / np.where(peak > 0, peak, 1.0)
    return float(np.max(drawdown) * 100.0)


def _calmar(total_return_pct: float, max_dd_pct: float) -> float:
    """Calmar ratio: total return / max drawdown."""
    if max_dd_pct == 0.0:
        return 0.0
    return total_return_pct / max_dd_pct


def _max_consecutive(mask: np.ndarray) -> int:
    """Longest consecutive streak of True values."""
    if len(mask) == 0:
        return 0
    max_streak = 0
    current = 0
    for val in mask:
        if val:
            current += 1
            if current > max_streak:
                max_streak = current
        else:
            current = 0
    return max_streak
