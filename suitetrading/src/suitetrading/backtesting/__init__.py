"""Backtesting engine: grid generation, metrics and reporting.

Public surface:

- ``BacktestEngine``  — single / batch run orchestrator
- ``MetricsEngine``   — vectorised performance metrics
- ``ParameterGridBuilder`` — parameter grid expansion + chunking
- ``ReportingEngine``      — Plotly dashboard generator
- ``BacktestDataset`` / ``StrategySignals`` / ``RunConfig`` — contracts
"""

from suitetrading.backtesting._internal.schemas import (  # noqa: F401
    BacktestCheckpoint,
    BacktestDataset,
    GridRequest,
    RunConfig,
    StrategySignals,
)
from suitetrading.backtesting.engine import BacktestEngine  # noqa: F401
from suitetrading.backtesting.grid import ParameterGridBuilder  # noqa: F401
from suitetrading.backtesting.metrics import MetricsEngine  # noqa: F401
from suitetrading.backtesting.reporting import ReportingEngine  # noqa: F401
