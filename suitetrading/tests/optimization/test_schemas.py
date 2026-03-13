"""Tests for optimization schemas."""

import numpy as np
import pytest

from suitetrading.optimization._internal.schemas import (
    AntiOverfitResult,
    CSCVResult,
    DSRResult,
    ObjectiveResult,
    OptimizationResult,
    PipelineResult,
    SPAResult,
    StrategyReport,
    WFOConfig,
    WFOResult,
)


class TestObjectiveResult:
    def test_creation(self):
        r = ObjectiveResult(
            run_id="abc123",
            params={"period": 14},
            metrics={"sharpe": 1.5},
            equity_curve=np.array([10_000, 10_100]),
            trades=[],
        )
        assert r.run_id == "abc123"
        assert r.is_error is False
        assert r.error_msg is None

    def test_error_state(self):
        r = ObjectiveResult(
            run_id="err",
            params={},
            metrics={},
            equity_curve=np.array([]),
            trades=[],
            is_error=True,
            error_msg="boom",
        )
        assert r.is_error
        assert r.error_msg == "boom"


class TestOptimizationResult:
    def test_creation(self):
        r = OptimizationResult(
            study_name="test_study",
            n_trials=100,
            n_completed=95,
            n_pruned=5,
            best_value=2.1,
            best_params={"period": 20},
            best_run_id="best123",
            wall_time_sec=12.5,
            trials_per_sec=8.0,
        )
        assert r.n_trials == 100
        assert r.best_value == 2.1


class TestWFOConfig:
    def test_defaults(self):
        cfg = WFOConfig()
        assert cfg.n_splits == 5
        assert cfg.mode == "rolling"

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError, match="rolling.*anchored"):
            WFOConfig(mode="invalid")

    def test_ratio_overflow_raises(self):
        with pytest.raises(ValueError, match="<= 1.0"):
            WFOConfig(is_ratio=0.8, oos_ratio=0.3)

    def test_min_splits_raises(self):
        with pytest.raises(ValueError, match=">= 2"):
            WFOConfig(n_splits=1)


class TestWFOResult:
    def test_creation(self):
        r = WFOResult(
            config=WFOConfig(),
            n_candidates=10,
            splits=[],
            oos_equity_curves={},
            oos_metrics={},
            degradation={},
        )
        assert r.n_candidates == 10


class TestCSCVResult:
    def test_overfit_flag(self):
        r = CSCVResult(
            pbo=0.75,
            n_subsamples=16,
            n_combinations=12870,
            omega_values=np.zeros(10),
            is_overfit=True,
        )
        assert r.is_overfit

    def test_not_overfit(self):
        r = CSCVResult(
            pbo=0.2,
            n_subsamples=16,
            n_combinations=12870,
            omega_values=np.ones(10),
            is_overfit=False,
        )
        assert not r.is_overfit


class TestDSRResult:
    def test_significant(self):
        r = DSRResult(dsr=0.97, expected_max_sharpe=0.8, observed_sharpe=2.0, is_significant=True)
        assert r.is_significant

    def test_not_significant(self):
        r = DSRResult(dsr=0.3, expected_max_sharpe=1.2, observed_sharpe=0.5, is_significant=False)
        assert not r.is_significant


class TestSPAResult:
    def test_superior(self):
        r = SPAResult(p_value=0.01, is_superior=True, statistic=3.5, benchmark="buy_hold")
        assert r.is_superior


class TestAntiOverfitResult:
    def test_creation(self):
        r = AntiOverfitResult(
            total_candidates=20,
            passed_cscv=15,
            passed_dsr=8,
            passed_spa=5,
            finalists=["a", "b", "c"],
        )
        assert len(r.finalists) == 3


class TestStrategyReport:
    def test_creation(self):
        r = StrategyReport(
            run_id="abc",
            params={},
            archetype="trend_following",
            symbol="BTCUSDT",
            timeframe="1h",
            is_metrics={"sharpe": 2.0},
            oos_metrics={"sharpe": 1.5},
            degradation_ratio=1.33,
            pbo=0.2,
            dsr=0.97,
            spa_p_value=0.03,
            passed_all_filters=True,
        )
        assert r.passed_all_filters


class TestPipelineResult:
    def test_creation(self):
        opt = OptimizationResult(
            study_name="s", n_trials=10, n_completed=10, n_pruned=0,
            best_value=1.0, best_params={}, best_run_id="x",
            wall_time_sec=1.0, trials_per_sec=10.0,
        )
        wfo = WFOResult(
            config=WFOConfig(), n_candidates=1, splits=[],
            oos_equity_curves={}, oos_metrics={}, degradation={},
        )
        aof = AntiOverfitResult(
            total_candidates=1, passed_cscv=1, passed_dsr=1,
            passed_spa=1, finalists=["x"],
        )
        sr = StrategyReport(
            run_id="x", params={}, archetype="trend_following",
            symbol="BTCUSDT", timeframe="1h",
            is_metrics={}, oos_metrics={}, degradation_ratio=1.0,
            pbo=0.1, dsr=0.99, spa_p_value=0.01, passed_all_filters=True,
        )
        r = PipelineResult(
            optimizer_result=opt,
            wfo_result=wfo,
            anti_overfit_result=aof,
            finalists=[sr],
            total_wall_time_sec=5.0,
        )
        assert r.total_wall_time_sec == 5.0
        assert len(r.finalists) == 1
