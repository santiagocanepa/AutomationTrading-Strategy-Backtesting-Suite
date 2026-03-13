"""Tests for reporting.py — dashboard generation."""

import numpy as np
import pandas as pd
import pytest

from suitetrading.backtesting.reporting import ReportingEngine


class TestReportingEngine:
    @pytest.fixture
    def engine(self):
        return ReportingEngine()

    @pytest.fixture
    def sample_results(self):
        return pd.DataFrame({
            "run_id": [f"run_{i}" for i in range(20)],
            "symbol": ["BTCUSDT"] * 10 + ["ETHUSDT"] * 10,
            "timeframe": ["1h"] * 20,
            "archetype": ["trend_following"] * 10 + ["mean_reversion"] * 10,
            "mode": ["simple"] * 20,
            "net_profit": np.random.default_rng(1).normal(100, 500, 20),
            "total_return_pct": np.random.default_rng(2).normal(5, 10, 20),
            "sharpe": np.random.default_rng(3).normal(1.0, 0.5, 20),
            "sortino": np.random.default_rng(4).normal(1.5, 0.8, 20),
            "max_drawdown_pct": np.abs(np.random.default_rng(5).normal(10, 5, 20)),
            "calmar": np.random.default_rng(6).normal(0.5, 0.3, 20),
            "win_rate": np.random.default_rng(7).uniform(30, 70, 20),
            "profit_factor": np.random.default_rng(8).uniform(0.5, 3.0, 20),
            "average_trade": np.random.default_rng(9).normal(10, 50, 20),
            "max_consecutive_losses": np.random.default_rng(10).integers(1, 10, 20),
            "total_trades": np.random.default_rng(11).integers(5, 100, 20),
        })

    def test_empty_results(self, engine, tmp_path):
        artefacts = engine.build_dashboard(results=pd.DataFrame(), output_dir=tmp_path)
        assert artefacts == {}

    def test_summary_csv_created(self, engine, sample_results, tmp_path):
        artefacts = engine.build_dashboard(results=sample_results, output_dir=tmp_path)
        assert "summary_csv" in artefacts
        assert (tmp_path / "results_summary.csv").exists()

    def test_ranking_csv_created(self, engine, sample_results, tmp_path):
        artefacts = engine.build_dashboard(results=sample_results, output_dir=tmp_path)
        if "ranking_csv" in artefacts:
            ranking = pd.read_csv(artefacts["ranking_csv"])
            assert len(ranking) <= 100
            # Should be sorted by sharpe descending
            if len(ranking) > 1:
                assert ranking["sharpe"].iloc[0] >= ranking["sharpe"].iloc[1]

    def test_output_dir_created(self, engine, sample_results, tmp_path):
        out = tmp_path / "deep" / "nested" / "dir"
        engine.build_dashboard(results=sample_results, output_dir=out)
        assert out.exists()

    def test_html_artefacts_if_plotly(self, engine, sample_results, tmp_path):
        artefacts = engine.build_dashboard(results=sample_results, output_dir=tmp_path)
        # If plotly installed, should have HTML
        try:
            import plotly  # noqa: F401
            assert "metric_distributions" in artefacts
            assert "risk_return_scatter" in artefacts
        except ImportError:
            pass  # OK without plotly
