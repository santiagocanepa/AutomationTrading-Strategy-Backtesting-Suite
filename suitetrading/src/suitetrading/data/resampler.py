"""Multi-timeframe OHLCV resampler.

Resamples a base-timeframe (typically 1m) DataFrame up to any target
timeframe defined in ``timeframes.py``.  Incomplete bars at the tail
are automatically dropped.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from loguru import logger

from suitetrading.data.timeframes import (
    TIMEFRAME_MAP,
    normalize_timeframe,
    tf_to_pandas_offset,
    tf_to_seconds,
)


_AGG_RULES: dict[str, str] = {
    "open": "first",
    "high": "max",
    "low": "min",
    "close": "last",
    "volume": "sum",
}


class OHLCVResampler:
    """Resample OHLCV from a base timeframe to higher timeframes."""

    def resample(self, df_base: pd.DataFrame, target_tf: str, *, base_tf: str = "1m") -> pd.DataFrame:
        """Resample *df_base* from *base_tf* to *target_tf*.

        Raises ``ValueError`` if *target_tf* resolution ≤ *base_tf*.
        Returns a DataFrame with incomplete trailing bar dropped.
        """
        target_tf = normalize_timeframe(target_tf)
        base_tf = normalize_timeframe(base_tf)

        target_secs = tf_to_seconds(target_tf)
        base_secs = tf_to_seconds(base_tf)

        if target_secs is not None and base_secs is not None and target_secs <= base_secs:
            raise ValueError(
                f"target_tf {target_tf!r} ({target_secs}s) must be > base_tf {base_tf!r} ({base_secs}s)"
            )

        offset = tf_to_pandas_offset(target_tf)

        # For weekly, pandas default is Sunday close; we want Monday-based weeks
        # "1W-MON" is already handled by our TIMEFRAME_MAP pandas entry.
        # For 45m and other non-standard offsets, use origin="epoch" for consistent alignment
        resample_kwargs: dict = {"rule": offset, "closed": "left", "label": "left"}
        if target_tf == "45m":
            resample_kwargs["origin"] = "epoch"

        resampled = df_base.resample(**resample_kwargs).agg(_AGG_RULES)
        resampled = resampled.dropna(subset=["open"])

        # Drop incomplete trailing bar
        resampled = self._drop_incomplete_tail(resampled, df_base, target_tf, base_tf)

        return resampled

    def resample_all(
        self,
        df_1m: pd.DataFrame,
        target_tfs: list[str] | None = None,
        *,
        base_tf: str = "1m",
    ) -> dict[str, pd.DataFrame]:
        """Resample to all target timeframes.  Returns ``{tf: df}``."""
        if target_tfs is None:
            base_secs = tf_to_seconds(base_tf) or 0
            target_tfs = [
                tf for tf, info in TIMEFRAME_MAP.items()
                if info["seconds"] is not None and info["seconds"] > base_secs
            ]
            # Also include monthly (seconds=None) — always > any intraday
            if "1M" not in target_tfs:
                target_tfs.append("1M")

        result: dict[str, pd.DataFrame] = {}
        for tf in target_tfs:
            try:
                result[tf] = self.resample(df_1m, tf, base_tf=base_tf)
            except ValueError as exc:
                logger.warning("Skipping {}: {}", tf, exc)
        return result

    @staticmethod
    def validate_against_native(
        resampled: pd.DataFrame,
        native: pd.DataFrame,
        tolerance_pct: float = 0.01,
        volume_tolerance_abs: float = 1e-9,
    ) -> dict:
        """Compare resampled OHLCV against natively-fetched data.

        Returns a report dict with *pass* boolean and per-column max deviation.
        """
        common_idx = resampled.index.intersection(native.index)
        if len(common_idx) == 0:
            return {"pass": False, "reason": "no overlapping timestamps", "bars_compared": 0}

        r = resampled.loc[common_idx]
        n = native.loc[common_idx]

        report: dict = {"bars_compared": len(common_idx), "columns": {}}
        all_pass = True

        for col in ["open", "high", "low", "close"]:
            pct_diff = ((r[col] - n[col]).abs() / n[col].replace(0, np.nan) * 100)
            max_diff = float(pct_diff.max())
            col_pass = max_diff <= tolerance_pct
            report["columns"][col] = {"max_pct_diff": max_diff, "pass": col_pass}
            if not col_pass:
                all_pass = False

        # Volume sums can differ by tiny floating-point noise after transport/parsing.
        vol_diff = (r["volume"] - n["volume"]).abs()
        max_vol_diff = float(vol_diff.max())
        vol_pass = bool(np.isclose(max_vol_diff, 0.0, atol=volume_tolerance_abs, rtol=0.0))
        report["columns"]["volume"] = {"max_abs_diff": max_vol_diff, "pass": vol_pass}
        if not vol_pass:
            all_pass = False

        report["pass"] = all_pass
        return report

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _drop_incomplete_tail(
        resampled: pd.DataFrame,
        df_base: pd.DataFrame,
        target_tf: str,
        base_tf: str,
    ) -> pd.DataFrame:
        """Remove the last bar if it doesn't have enough base bars."""
        if resampled.empty:
            return resampled

        target_secs = tf_to_seconds(target_tf)
        base_secs = tf_to_seconds(base_tf)

        if target_secs is None or base_secs is None:
            # Variable-length (1M) — drop last bar always to be safe
            return resampled.iloc[:-1] if len(resampled) > 1 else resampled

        expected_bars = target_secs // base_secs
        last_ts = resampled.index[-1]
        bars_in_last = len(df_base.loc[df_base.index >= last_ts])

        if bars_in_last < expected_bars:
            return resampled.iloc[:-1]
        return resampled
