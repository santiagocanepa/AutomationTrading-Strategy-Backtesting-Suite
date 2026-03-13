"""Reporting engine — exploratory dashboard and result export.

Generates interactive Plotly HTML reports from backtest results stored
in Parquet.  Designed for local exploration, not as a web application.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False


class ReportingEngine:
    """Build exploratory HTML dashboards from backtest results."""

    def build_dashboard(
        self,
        *,
        results: pd.DataFrame,
        output_dir: str | Path,
    ) -> dict[str, str]:
        """Generate dashboard artefacts and return paths.

        Returns a dict mapping artefact name → file path.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        artefacts: dict[str, str] = {}

        if results.empty:
            logger.warning("No results to report")
            return artefacts

        # Always export summary CSV for inspection
        summary_path = output_dir / "results_summary.csv"
        results.to_csv(summary_path, index=False)
        artefacts["summary_csv"] = str(summary_path)

        if not HAS_PLOTLY:
            logger.warning("plotly not installed — skipping HTML dashboard")
            return artefacts

        artefacts.update(self._build_html_reports(results, output_dir))
        return artefacts

    def _build_html_reports(
        self,
        df: pd.DataFrame,
        output_dir: Path,
    ) -> dict[str, str]:
        artefacts: dict[str, str] = {}

        # 1. Metric distributions
        if _has_numeric_cols(df):
            fig = self._metric_distributions(df)
            path = output_dir / "metric_distributions.html"
            fig.write_html(str(path))
            artefacts["metric_distributions"] = str(path)

        # 2. Risk vs Return scatter
        if {"sharpe", "max_drawdown_pct", "total_return_pct"}.issubset(df.columns):
            fig = self._risk_return_scatter(df)
            path = output_dir / "risk_return_scatter.html"
            fig.write_html(str(path))
            artefacts["risk_return_scatter"] = str(path)

        # 3. Breakdown by symbol/timeframe
        if {"symbol", "total_return_pct"}.issubset(df.columns):
            fig = self._breakdown_by_group(df, "symbol")
            path = output_dir / "breakdown_by_symbol.html"
            fig.write_html(str(path))
            artefacts["breakdown_by_symbol"] = str(path)

        if {"timeframe", "total_return_pct"}.issubset(df.columns):
            fig = self._breakdown_by_group(df, "timeframe")
            path = output_dir / "breakdown_by_timeframe.html"
            fig.write_html(str(path))
            artefacts["breakdown_by_timeframe"] = str(path)

        # 4. Ranking table
        ranking = self._build_ranking(df)
        path = output_dir / "ranking.csv"
        ranking.to_csv(path, index=False)
        artefacts["ranking_csv"] = str(path)

        logger.info("Dashboard generated → {}", output_dir)
        return artefacts

    # ── Chart builders ────────────────────────────────────────────────

    @staticmethod
    def _metric_distributions(df: pd.DataFrame) -> go.Figure:
        metrics = [c for c in ["sharpe", "sortino", "win_rate", "profit_factor", "max_drawdown_pct"] if c in df.columns]
        fig = make_subplots(rows=1, cols=len(metrics), subplot_titles=metrics)
        for i, m in enumerate(metrics, 1):
            fig.add_trace(
                go.Histogram(x=df[m].dropna(), name=m, nbinsx=30),
                row=1, col=i,
            )
        fig.update_layout(title="Metric Distributions", showlegend=False, height=400)
        return fig

    @staticmethod
    def _risk_return_scatter(df: pd.DataFrame) -> go.Figure:
        color_col = "archetype" if "archetype" in df.columns else None
        fig = px.scatter(
            df,
            x="max_drawdown_pct",
            y="total_return_pct",
            color=color_col,
            hover_data=["symbol", "timeframe", "sharpe"] if {"symbol", "timeframe", "sharpe"}.issubset(df.columns) else None,
            title="Risk vs Return",
            labels={"max_drawdown_pct": "Max Drawdown %", "total_return_pct": "Total Return %"},
        )
        return fig

    @staticmethod
    def _breakdown_by_group(df: pd.DataFrame, group_col: str) -> go.Figure:
        fig = px.box(
            df,
            x=group_col,
            y="total_return_pct",
            title=f"Return Distribution by {group_col.title()}",
        )
        return fig

    @staticmethod
    def _build_ranking(df: pd.DataFrame) -> pd.DataFrame:
        sort_col = "sharpe" if "sharpe" in df.columns else "total_return_pct"
        ranking = df.sort_values(sort_col, ascending=False).head(100)
        return ranking


def _has_numeric_cols(df: pd.DataFrame) -> bool:
    return any(df[c].dtype.kind in "iuf" for c in df.columns)
