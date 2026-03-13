"""Abstract base class for all indicators."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np
import pandas as pd


class IndicatorState(StrEnum):
    """How an indicator participates in signal combination."""

    EXCLUYENTE = "Excluyente"
    OPCIONAL = "Opcional"
    DESACTIVADO = "Desactivado"


@dataclass(frozen=True)
class IndicatorConfig:
    """Validated configuration for a single indicator instance."""

    name: str
    state: IndicatorState
    params: dict[str, int | float | str | bool] = field(default_factory=dict)
    timeframes: list[str] | None = None


class Indicator(ABC):
    """Interface that every indicator must implement.

    - ``compute`` receives a DataFrame with OHLCV columns and returns a
      boolean Series where True means "signal active on this bar".
    - ``params_schema`` describes the tuneable parameters with their
      types, ranges, and defaults so the optimisation engine can build
      parameter grids automatically.
    """

    @abstractmethod
    def compute(self, df: pd.DataFrame, **params: int | float | str | bool) -> pd.Series:
        """Return a boolean Series (True = signal active)."""
        ...

    @abstractmethod
    def params_schema(self) -> dict[str, dict]:
        """Return parameter schema.

        Example::

            {
                "period": {"type": "int", "min": 5, "max": 50, "default": 14},
                "multiplier": {"type": "float", "min": 0.5, "max": 5.0, "default": 1.8},
            }
        """
        ...

    # ------------------------------------------------------------------
    # Helpers available to all indicators
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_ohlcv(df: pd.DataFrame) -> None:
        required = {"open", "high", "low", "close", "volume"}
        missing = required - {c.lower() for c in df.columns}
        if missing:
            raise ValueError(f"DataFrame missing OHLCV columns: {missing}")

    @staticmethod
    def _hold_bars(signal: pd.Series, n_bars: int) -> pd.Series:
        """Replicate Pine Script hold-bars pattern.

        After a True pulse, keep the signal True for *n_bars* consecutive
        bars (including the trigger bar).
        """
        out = np.zeros(len(signal), dtype=np.bool_)
        counter = 0
        for i in range(len(signal)):
            if signal.iat[i]:
                counter = n_bars
            if counter > 0:
                out[i] = True
                counter -= 1
        return pd.Series(out, index=signal.index, name=signal.name)
