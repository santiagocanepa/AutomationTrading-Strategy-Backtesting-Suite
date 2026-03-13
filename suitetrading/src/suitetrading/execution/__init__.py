"""Execution module — bridges backtesting signals to live/paper trading.

Public API
----------
- ``AlpacaExecutor`` — Alpaca paper/live order execution via alpaca-py.
- ``SignalBridge`` — Translates StrategySignals + RiskConfig into orders.
"""

from suitetrading.execution.alpaca_executor import AlpacaExecutor
from suitetrading.execution.signal_bridge import Executor, SignalBridge

__all__ = ["AlpacaExecutor", "SignalBridge"]
