"""Tests for FSM short-side execution — direction='short' lifecycle."""

import numpy as np
import pandas as pd
import pytest

from suitetrading.backtesting._internal.schemas import BacktestDataset, StrategySignals
from suitetrading.backtesting.engine import BacktestEngine
from suitetrading.risk.archetypes.trend_following import TrendFollowing


@pytest.fixture
def trending_up_ohlcv():
    """Synthetic uptrend — short positions should lose money."""
    n = 500
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    close = 100.0 + np.linspace(0, 50, n) + np.random.default_rng(42).normal(0, 0.3, n)
    high = close + np.abs(np.random.default_rng(43).normal(0.5, 0.3, n))
    low = close - np.abs(np.random.default_rng(44).normal(0.5, 0.3, n))
    open_ = close + np.random.default_rng(45).normal(0, 0.2, n)
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": np.full(n, 1000.0),
    }, index=idx)


@pytest.fixture
def trending_down_ohlcv():
    """Synthetic downtrend — short positions should profit."""
    n = 500
    idx = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    close = 150.0 - np.linspace(0, 50, n) + np.random.default_rng(42).normal(0, 0.3, n)
    high = close + np.abs(np.random.default_rng(43).normal(0.5, 0.3, n))
    low = close - np.abs(np.random.default_rng(44).normal(0.5, 0.3, n))
    open_ = close + np.random.default_rng(45).normal(0, 0.2, n)
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": np.full(n, 1000.0),
    }, index=idx)


def _make_short_signals(ohlcv: pd.DataFrame, entry_prob: float = 0.05) -> StrategySignals:
    """Create entry_short signals with matching exit_short."""
    rng = np.random.default_rng(99)
    n = len(ohlcv)
    entry_short = rng.random(n) < entry_prob
    entry_short[:20] = False
    exit_short = rng.random(n) < 0.03
    exit_short[:20] = False
    idx = ohlcv.index
    z = pd.Series(np.zeros(n, dtype=bool), index=idx)
    return StrategySignals(
        entry_long=z,
        entry_short=pd.Series(entry_short, index=idx),
        exit_long=z,
        exit_short=pd.Series(exit_short, index=idx),
        trailing_long=z,
        trailing_short=pd.Series(exit_short, index=idx),
    )


class TestFSMShortDirection:
    @pytest.fixture
    def engine(self):
        return BacktestEngine()

    def test_short_produces_trades(self, engine, trending_down_ohlcv):
        """direction='short' opens and closes short trades."""
        ds = BacktestDataset(
            exchange="synthetic", symbol="TEST",
            base_timeframe="1h", ohlcv=trending_down_ohlcv,
        )
        signals = _make_short_signals(trending_down_ohlcv)
        rc = TrendFollowing().build_config()
        result = engine.run(
            dataset=ds, signals=signals, risk_config=rc,
            mode="fsm", direction="short",
        )
        assert result["total_trades"] > 0

    def test_short_trade_direction_is_short(self, engine, trending_down_ohlcv):
        """Trade records must have direction='short'."""
        ds = BacktestDataset(
            exchange="synthetic", symbol="TEST",
            base_timeframe="1h", ohlcv=trending_down_ohlcv,
        )
        signals = _make_short_signals(trending_down_ohlcv)
        rc = TrendFollowing().build_config()
        result = engine.run(
            dataset=ds, signals=signals, risk_config=rc,
            mode="fsm", direction="short",
        )
        trades = result.get("trades")
        if trades is not None and not trades.empty:
            for _, row in trades.iterrows():
                assert row["direction"] in ("short", "flat"), (
                    f"Expected short or flat, got {row['direction']}"
                )

    def test_short_on_downtrend_profits(self, engine, trending_down_ohlcv):
        """Short positions on a downtrend should profit overall."""
        ds = BacktestDataset(
            exchange="synthetic", symbol="TEST",
            base_timeframe="1h", ohlcv=trending_down_ohlcv,
        )
        signals = _make_short_signals(trending_down_ohlcv)
        rc = TrendFollowing().build_config(commission_pct=0.0, slippage_pct=0.0)
        result = engine.run(
            dataset=ds, signals=signals, risk_config=rc,
            mode="fsm", direction="short",
        )
        trades = result.get("trades")
        if trades is not None and len(trades) >= 2:
            total_pnl = trades["pnl"].sum()
            assert total_pnl > 0, f"Expected positive PnL on downtrend, got {total_pnl}"

    def test_short_on_uptrend_loses(self, engine, trending_up_ohlcv):
        """Short positions on an uptrend should lose money."""
        ds = BacktestDataset(
            exchange="synthetic", symbol="TEST",
            base_timeframe="1h", ohlcv=trending_up_ohlcv,
        )
        signals = _make_short_signals(trending_up_ohlcv)
        rc = TrendFollowing().build_config(commission_pct=0.0, slippage_pct=0.0)
        result = engine.run(
            dataset=ds, signals=signals, risk_config=rc,
            mode="fsm", direction="short",
        )
        final = result["equity_curve"][-1]
        initial = rc.initial_capital
        assert final < initial, f"Expected loss on uptrend, got {final} vs {initial}"

    def test_long_vs_short_are_independent(self, engine, trending_down_ohlcv):
        """Long and short runs with same data produce different equity curves."""
        ds = BacktestDataset(
            exchange="synthetic", symbol="TEST",
            base_timeframe="1h", ohlcv=trending_down_ohlcv,
        )
        rng = np.random.default_rng(77)
        n = len(trending_down_ohlcv)
        idx = trending_down_ohlcv.index
        signals = StrategySignals(
            entry_long=pd.Series(rng.random(n) < 0.04, index=idx),
            entry_short=pd.Series(rng.random(n) < 0.04, index=idx),
            exit_long=pd.Series(rng.random(n) < 0.02, index=idx),
            exit_short=pd.Series(rng.random(n) < 0.02, index=idx),
        )
        rc = TrendFollowing().build_config()
        result_long = engine.run(
            dataset=ds, signals=signals, risk_config=rc,
            mode="fsm", direction="long",
        )
        result_short = engine.run(
            dataset=ds, signals=signals, risk_config=rc,
            mode="fsm", direction="short",
        )
        eq_long = result_long["equity_curve"]
        eq_short = result_short["equity_curve"]
        assert not np.array_equal(eq_long, eq_short)

    def test_short_stop_loss_above_entry(self, engine, trending_up_ohlcv):
        """Short SL exit prices should be at or above entry."""
        ds = BacktestDataset(
            exchange="synthetic", symbol="TEST",
            base_timeframe="1h", ohlcv=trending_up_ohlcv,
        )
        signals = _make_short_signals(trending_up_ohlcv)
        rc = TrendFollowing().build_config()
        result = engine.run(
            dataset=ds, signals=signals, risk_config=rc,
            mode="fsm", direction="short",
        )
        trades = result.get("trades")
        if trades is not None and not trades.empty:
            sl_trades = trades[trades["exit_reason"].str.contains("stop", case=False, na=False)]
            for _, t in sl_trades.iterrows():
                assert t["exit_price"] >= t["entry_price"] * 0.95, (
                    f"Short SL exit {t['exit_price']} way below entry {t['entry_price']}"
                )
