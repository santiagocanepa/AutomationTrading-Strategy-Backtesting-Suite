"""Tests for VBT simulator adapter and vectorizability table."""

from __future__ import annotations

import numpy as np
import pytest

from suitetrading.risk.contracts import RiskConfig
from suitetrading.risk.vbt_simulator import VECTORIZABILITY, VBTSimulatorAdapter


# ═══════════════════════════════════════════════════════════════════════════════
# Vectorizability table
# ═══════════════════════════════════════════════════════════════════════════════


class TestVectorizability:
    def test_known_archetypes(self):
        assert VECTORIZABILITY["trend_following"] == "medium"
        assert VECTORIZABILITY["mean_reversion"] == "medium"
        assert VECTORIZABILITY["momentum"] == "medium"
        assert VECTORIZABILITY["breakout"] == "medium"
        assert VECTORIZABILITY["pyramidal"] == "low"
        assert VECTORIZABILITY["grid_dca"] == "low"

    def test_all_entries_valid(self):
        valid = {"high", "medium", "low"}
        for name, level in VECTORIZABILITY.items():
            assert level in valid, f"{name} has invalid level {level}"


# ═══════════════════════════════════════════════════════════════════════════════
# Adapter
# ═══════════════════════════════════════════════════════════════════════════════


class TestVBTSimulatorAdapter:
    def test_flat_config_keys(self):
        cfg = RiskConfig(archetype="trend_following")
        adapter = VBTSimulatorAdapter(cfg)
        flat = adapter.flat_config
        assert "sizing__risk_pct" in flat
        assert "stop__atr_multiple" in flat
        assert "pyramid__max_adds" in flat
        assert "initial_capital" in flat

    def test_vectorizability_property(self):
        cfg = RiskConfig(archetype="trend_following")
        adapter = VBTSimulatorAdapter(cfg)
        assert adapter.vectorizability == "medium"

    def test_unknown_archetype_defaults_to_low(self):
        cfg = RiskConfig(archetype="custom_unknown")
        adapter = VBTSimulatorAdapter(cfg)
        assert adapter.vectorizability == "low"

    def test_flat_values_match_config(self):
        cfg = RiskConfig(
            initial_capital=5000.0,
            sizing={"risk_pct": 2.0, "max_leverage": 3.0},
        )
        adapter = VBTSimulatorAdapter(cfg)
        flat = adapter.flat_config
        assert flat["initial_capital"] == pytest.approx(5000.0)
        assert flat["sizing__risk_pct"] == pytest.approx(2.0)
        assert flat["sizing__max_leverage"] == pytest.approx(3.0)


# ═══════════════════════════════════════════════════════════════════════════════
# Simple backtest prototype
# ═══════════════════════════════════════════════════════════════════════════════


class TestRunSimpleBacktest:
    @pytest.fixture
    def adapter(self) -> VBTSimulatorAdapter:
        cfg = RiskConfig(
            archetype="trend_following",
            initial_capital=10_000.0,
            sizing={"risk_pct": 1.0},
            stop={"atr_multiple": 2.0},
        )
        return VBTSimulatorAdapter(cfg)

    def test_output_keys(self, adapter: VBTSimulatorAdapter):
        n = 50
        close = np.linspace(100, 110, n)
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        entries[5] = True
        exits[40] = True

        result = adapter.run_simple_backtest(close=close, entries=entries, exits=exits)
        assert "equity_curve" in result
        assert "final_equity" in result
        assert "total_return_pct" in result
        assert len(result["equity_curve"]) == n

    def test_no_trades_flat_equity(self, adapter: VBTSimulatorAdapter):
        n = 30
        close = np.full(n, 100.0)
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)

        result = adapter.run_simple_backtest(close=close, entries=entries, exits=exits)
        assert result["final_equity"] == pytest.approx(10_000.0)
        assert result["total_return_pct"] == pytest.approx(0.0)

    def test_profitable_trade(self, adapter: VBTSimulatorAdapter):
        n = 20
        close = np.concatenate([np.full(5, 100.0), np.linspace(100, 120, 15)])
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        atr = np.full(n, 2.0)
        entries[2] = True
        exits[18] = True

        result = adapter.run_simple_backtest(close=close, entries=entries, exits=exits, atr=atr)
        assert result["final_equity"] > 10_000.0

    def test_stop_loss_fires(self, adapter: VBTSimulatorAdapter):
        n = 20
        # Price drops sharply after entry
        close = np.concatenate([np.full(5, 100.0), np.linspace(100, 80, 15)])
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        atr = np.full(n, 2.0)
        entries[3] = True

        result = adapter.run_simple_backtest(close=close, entries=entries, exits=exits, atr=atr)
        # Should lose money (stopped out)
        assert result["final_equity"] < 10_000.0


# ═══════════════════════════════════════════════════════════════════════════════
# Archetype A — Trend Following
# ═══════════════════════════════════════════════════════════════════════════════


class TestArchetypeATrendFollowing:
    """VBT sim with TrendFollowing config produces coherent results."""

    @pytest.fixture
    def adapter(self) -> VBTSimulatorAdapter:
        from suitetrading.risk.archetypes.trend_following import TrendFollowing
        cfg = TrendFollowing().build_config()
        return VBTSimulatorAdapter(cfg)

    def test_trending_market_profitable(self, adapter: VBTSimulatorAdapter):
        n = 100
        close = np.linspace(100, 150, n)  # steady uptrend
        open_ = close - 0.1
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        atr = np.full(n, 2.0)
        entries[5] = True
        exits[90] = True

        result = adapter.run_simple_backtest(
            open_=open_, close=close, entries=entries, exits=exits, atr=atr,
        )
        assert result["final_equity"] > adapter._cfg.initial_capital
        assert result["total_return_pct"] > 0

    def test_stop_loss_limits_loss(self, adapter: VBTSimulatorAdapter):
        n = 50
        close = np.concatenate([np.full(10, 100.0), np.linspace(100, 70, 40)])
        open_ = close - 0.5
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        atr = np.full(n, 2.0)
        entries[5] = True

        result = adapter.run_simple_backtest(
            open_=open_, close=close, entries=entries, exits=exits, atr=atr,
        )
        assert result["final_equity"] < adapter._cfg.initial_capital
        # Loss is bounded — not catastrophic
        assert result["final_equity"] > adapter._cfg.initial_capital * 0.90

    def test_no_trades_flat(self, adapter: VBTSimulatorAdapter):
        n = 50
        close = np.full(n, 100.0)
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)

        result = adapter.run_simple_backtest(close=close, entries=entries, exits=exits)
        assert result["final_equity"] == pytest.approx(adapter._cfg.initial_capital)

    def test_equity_curve_correct_length(self, adapter: VBTSimulatorAdapter):
        n = 60
        close = np.linspace(100, 120, n)
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        entries[10] = True
        exits[50] = True

        result = adapter.run_simple_backtest(close=close, entries=entries, exits=exits)
        assert len(result["equity_curve"]) == n


# ═══════════════════════════════════════════════════════════════════════════════
# Archetype B — Mean Reversion
# ═══════════════════════════════════════════════════════════════════════════════


class TestArchetypeBMeanReversion:
    """VBT sim with MeanReversion config produces coherent results."""

    @pytest.fixture
    def adapter(self) -> VBTSimulatorAdapter:
        from suitetrading.risk.archetypes.mean_reversion import MeanReversion
        cfg = MeanReversion().build_config()
        return VBTSimulatorAdapter(cfg)

    def test_reversion_trade_profitable(self, adapter: VBTSimulatorAdapter):
        n = 40
        # Price dips then reverts to mean
        close = np.concatenate([
            np.full(5, 100.0),
            np.linspace(100, 95, 10),   # dip
            np.linspace(95, 105, 25),    # recovery
        ])
        open_ = close + 0.1
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        atr = np.full(n, 1.0)
        entries[14] = True   # enter at bottom of dip
        exits[35] = True     # exit after recovery

        result = adapter.run_simple_backtest(
            open_=open_, close=close, entries=entries, exits=exits, atr=atr,
        )
        assert result["final_equity"] > adapter._cfg.initial_capital

    def test_tight_stop_fires_quickly(self, adapter: VBTSimulatorAdapter):
        """Mean reversion has ATR×1.5 — tighter than trend following ATR×3."""
        n = 30
        close = np.concatenate([np.full(10, 100.0), np.linspace(100, 85, 20)])
        open_ = close - 0.3
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        atr = np.full(n, 2.0)  # stop_dist = 2*1.5=3
        entries[5] = True

        result = adapter.run_simple_backtest(
            open_=open_, close=close, entries=entries, exits=exits, atr=atr,
        )
        assert result["final_equity"] < adapter._cfg.initial_capital

    def test_no_trades_flat(self, adapter: VBTSimulatorAdapter):
        n = 30
        close = np.full(n, 100.0)
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)

        result = adapter.run_simple_backtest(close=close, entries=entries, exits=exits)
        assert result["final_equity"] == pytest.approx(adapter._cfg.initial_capital)


# ═══════════════════════════════════════════════════════════════════════════════
# Archetype C — Mixed (Partial TP + Trail)
# ═══════════════════════════════════════════════════════════════════════════════


class TestArchetypeCMixed:
    """VBT sim with Mixed config loads and runs without error."""

    @pytest.fixture
    def adapter(self) -> VBTSimulatorAdapter:
        from suitetrading.risk.archetypes.mixed import Mixed
        cfg = Mixed().build_config()
        return VBTSimulatorAdapter(cfg)

    def test_smoke_run_completes(self, adapter: VBTSimulatorAdapter):
        n = 80
        close = np.linspace(100, 130, n)
        open_ = close - 0.2
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        atr = np.full(n, 2.0)
        entries[10] = True
        exits[70] = True

        result = adapter.run_simple_backtest(
            open_=open_, close=close, entries=entries, exits=exits, atr=atr,
        )
        assert "equity_curve" in result
        assert "final_equity" in result
        assert len(result["equity_curve"]) == n
        assert result["final_equity"] > adapter._cfg.initial_capital

    def test_stop_loss_works(self, adapter: VBTSimulatorAdapter):
        n = 40
        close = np.concatenate([np.full(10, 100.0), np.linspace(100, 80, 30)])
        open_ = close - 0.3
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        atr = np.full(n, 2.0)
        entries[5] = True

        result = adapter.run_simple_backtest(
            open_=open_, close=close, entries=entries, exits=exits, atr=atr,
        )
        assert result["final_equity"] < adapter._cfg.initial_capital


# ═══════════════════════════════════════════════════════════════════════════════
# Transversal: all high-vectorizability archetypes run
# ═══════════════════════════════════════════════════════════════════════════════


class TestTransversalArchetypes:
    """All archetypes with high/medium vectorizability run through VBT sim."""

    @pytest.fixture(params=["trend_following", "mean_reversion", "mixed"])
    def abc_adapter(self, request) -> VBTSimulatorAdapter:
        from suitetrading.risk.archetypes.trend_following import TrendFollowing
        from suitetrading.risk.archetypes.mean_reversion import MeanReversion
        from suitetrading.risk.archetypes.mixed import Mixed

        builders = {
            "trend_following": TrendFollowing,
            "mean_reversion": MeanReversion,
            "mixed": Mixed,
        }
        cfg = builders[request.param]().build_config()
        return VBTSimulatorAdapter(cfg)

    def test_all_produce_valid_equity_curve(self, abc_adapter: VBTSimulatorAdapter):
        n = 50
        close = np.linspace(100, 115, n)
        entries = np.zeros(n, dtype=bool)
        exits = np.zeros(n, dtype=bool)
        entries[5] = True
        exits[45] = True

        result = abc_adapter.run_simple_backtest(close=close, entries=entries, exits=exits)
        assert len(result["equity_curve"]) == n
        assert result["final_equity"] > 0

    def test_flat_config_has_required_keys(self, abc_adapter: VBTSimulatorAdapter):
        flat = abc_adapter.flat_config
        required = [
            "initial_capital", "slippage_pct", "sizing__risk_pct",
            "stop__atr_multiple", "pyramid__enabled",
        ]
        for key in required:
            assert key in flat, f"Missing key: {key}"

    def test_adapter_from_archetype_builder(self, abc_adapter: VBTSimulatorAdapter):
        assert abc_adapter.vectorizability in {"high", "medium", "low"}
        assert abc_adapter._cfg.initial_capital > 0
