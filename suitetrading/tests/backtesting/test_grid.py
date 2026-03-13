"""Tests for grid.py — parameter grid generation."""

import pytest

from suitetrading.backtesting._internal.schemas import GridRequest, RunConfig
from suitetrading.backtesting.grid import (
    ParameterGridBuilder,
    build_indicator_space_from_registry,
)


class TestParameterGridBuilder:
    @pytest.fixture
    def builder(self):
        return ParameterGridBuilder()

    def test_single_combination(self, builder):
        req = GridRequest(
            symbols=["BTCUSDT"],
            timeframes=["1h"],
            indicator_space={},
            risk_space={},
            archetypes=["trend_following"],
        )
        configs = builder.build(req)
        assert len(configs) == 1
        assert configs[0].symbol == "BTCUSDT"
        assert configs[0].archetype == "trend_following"

    def test_cartesian_product(self, builder):
        req = GridRequest(
            symbols=["BTCUSDT", "ETHUSDT"],
            timeframes=["1h", "4h"],
            indicator_space={"rsi": {"period": [14, 21]}},
            risk_space={"stop_mult": [2.0, 3.0]},
            archetypes=["trend_following"],
        )
        configs = builder.build(req)
        # 2 symbols × 2 tfs × 1 archetype × 2 rsi periods × 2 risk = 16
        assert len(configs) == 16

    def test_estimate_matches_actual(self, builder):
        req = GridRequest(
            symbols=["BTCUSDT", "ETHUSDT"],
            timeframes=["1h"],
            indicator_space={"rsi": {"period": [14, 21, 28]}, "ema": {"period": [9, 21]}},
            risk_space={"stop_mult": [2.0]},
            archetypes=["trend_following", "mean_reversion"],
        )
        estimated = builder.estimate_size(req)
        actual = len(builder.build(req))
        assert estimated == actual

    def test_ids_are_unique(self, builder):
        req = GridRequest(
            symbols=["BTCUSDT"],
            timeframes=["1h", "4h"],
            indicator_space={"rsi": {"period": [14, 21]}},
            risk_space={},
            archetypes=["trend_following"],
        )
        configs = builder.build(req)
        ids = [c.run_id for c in configs]
        assert len(ids) == len(set(ids))

    def test_chunking_deterministic(self, builder):
        req = GridRequest(
            symbols=["BTCUSDT"],
            timeframes=["1h"],
            indicator_space={"rsi": {"period": list(range(10, 30))}},
            risk_space={},
            archetypes=["trend_following"],
        )
        configs = builder.build(req)
        chunks = builder.chunk(configs, chunk_size=5)
        assert len(chunks) == 4  # 20 / 5
        assert all(len(c) == 5 for c in chunks)

    def test_chunking_last_chunk_smaller(self, builder):
        configs = [
            RunConfig(symbol="X", timeframe="1h", archetype="a",
                      indicator_params={}, risk_overrides={"v": i})
            for i in range(7)
        ]
        chunks = builder.chunk(configs, chunk_size=3)
        assert len(chunks) == 3
        assert len(chunks[-1]) == 1

    def test_chunking_invalid_size(self, builder):
        with pytest.raises(ValueError, match="positive"):
            builder.chunk([], chunk_size=0)

    def test_deduplication(self, builder):
        rc = RunConfig(symbol="X", timeframe="1h", archetype="a",
                       indicator_params={}, risk_overrides={})
        configs = [rc, rc]
        deduped = builder.deduplicate(configs)
        assert len(deduped) == 1

    def test_empty_grid(self, builder):
        req = GridRequest(
            symbols=[], timeframes=["1h"],
            indicator_space={}, risk_space={},
            archetypes=["a"],
        )
        assert builder.build(req) == []

    def test_multi_indicator_space(self, builder):
        req = GridRequest(
            symbols=["X"],
            timeframes=["1h"],
            indicator_space={
                "rsi": {"period": [14, 21]},
                "ema": {"period": [9, 21, 50]},
            },
            risk_space={},
            archetypes=["a"],
        )
        configs = builder.build(req)
        # 1 × 1 × 1 × (2 rsi × 3 ema) = 6
        assert len(configs) == 6


class TestBuildIndicatorSpaceFromRegistry:
    def test_known_indicator(self):
        space = build_indicator_space_from_registry(["rsi"], resolution=3)
        assert "rsi" in space
        assert "period" in space["rsi"]
        assert len(space["rsi"]["period"]) >= 3

    def test_unknown_indicator_skipped(self):
        space = build_indicator_space_from_registry(["nonexistent"], resolution=3)
        assert space == {}

    def test_default_included(self):
        space = build_indicator_space_from_registry(["rsi"], resolution=3)
        assert 14 in space["rsi"]["period"]
