"""Dataset loading, resampling, alignment and warmup trimming.

Bridges the ``data`` module (ParquetStore, OHLCVResampler) with the
backtesting engine so that every run receives a clean, validated
``BacktestDataset``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger

from suitetrading.backtesting._internal.schemas import BacktestDataset, StrategySignals
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.data.warmup import WarmupCalculator
from suitetrading.indicators.base import IndicatorConfig, IndicatorState
from suitetrading.indicators.mtf import align_to_base
from suitetrading.indicators.registry import get_indicator
from suitetrading.indicators.signal_combiner import combine_signals


def load_dataset(
    *,
    exchange: str,
    symbol: str,
    base_timeframe: str,
    htf_timeframes: list[str] | None = None,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    data_dir: Path | str = Path("data/raw"),
    warmup_indicators: list[dict] | None = None,
) -> BacktestDataset:
    """Load and prepare a dataset from the Parquet store.

    Applies warmup trimming when *warmup_indicators* is supplied.
    Higher-timeframe data is resampled from the base and aligned.
    """
    store = ParquetStore(base_dir=Path(data_dir))
    resampler = OHLCVResampler()

    ohlcv = store.read(exchange, symbol, base_timeframe, start=start, end=end)
    if ohlcv.empty:
        raise ValueError(f"No data for {exchange}/{symbol}/{base_timeframe}")

    aligned: dict[str, pd.DataFrame] = {}
    for tf in htf_timeframes or []:
        resampled = resampler.resample(ohlcv, tf, base_timeframe)
        aligned[tf] = align_to_base(resampled, ohlcv.index)

    if warmup_indicators:
        calc = WarmupCalculator()
        warmup_td = calc.calculate(warmup_indicators, base_timeframe)
        cutoff = ohlcv.index[0] + warmup_td
        ohlcv = ohlcv.loc[ohlcv.index >= cutoff]
        aligned = {tf: df.loc[df.index >= cutoff] for tf, df in aligned.items()}
        logger.debug("Trimmed warmup: {} bars removed (cutoff={})", cutoff, warmup_td)

    return BacktestDataset(
        exchange=exchange,
        symbol=symbol,
        base_timeframe=base_timeframe,
        ohlcv=ohlcv,
        aligned_frames=aligned,
        metadata={"start": str(ohlcv.index[0]), "end": str(ohlcv.index[-1]), "bars": len(ohlcv)},
    )


def build_dataset_from_df(
    ohlcv: pd.DataFrame,
    *,
    exchange: str = "synthetic",
    symbol: str = "TEST",
    base_timeframe: str = "1h",
) -> BacktestDataset:
    """Build a BacktestDataset from an in-memory DataFrame (for tests)."""
    return BacktestDataset(
        exchange=exchange,
        symbol=symbol,
        base_timeframe=base_timeframe,
        ohlcv=ohlcv,
        metadata={"bars": len(ohlcv)},
    )


def compute_signals(
    dataset: BacktestDataset,
    indicator_configs: list[IndicatorConfig],
    num_optional_required: int = 1,
) -> StrategySignals:
    """Compute and combine indicator signals into a StrategySignals bundle.

    Each indicator in *indicator_configs* is instantiated from the
    registry, computed against the appropriate timeframe, and combined
    via ``combine_signals``.
    """
    signals: dict[str, pd.Series] = {}
    states: dict[str, IndicatorState] = {}
    payload: dict[str, Any] = {}

    for cfg in indicator_configs:
        if cfg.state == IndicatorState.DESACTIVADO:
            continue

        indicator = get_indicator(cfg.name)
        df = dataset.ohlcv

        if cfg.timeframes:
            for tf in cfg.timeframes:
                if tf in dataset.aligned_frames:
                    df = dataset.aligned_frames[tf]
                    break

        sig = indicator.compute(df, **cfg.params)
        # Re-align to base if was computed on HTF
        if len(sig) != len(dataset.ohlcv):
            sig = sig.reindex(dataset.ohlcv.index, method="ffill").fillna(False)

        key = f"{cfg.name}_{'_'.join(str(v) for v in cfg.params.values())}"
        signals[key] = sig
        states[key] = cfg.state
        payload[key] = sig

    combined = combine_signals(signals, states, num_optional_required)

    return StrategySignals(
        entry_long=combined,
        indicators_payload=payload,
    )
