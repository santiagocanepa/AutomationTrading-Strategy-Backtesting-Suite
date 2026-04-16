"""OHLCV data quality validation.

Every DataFrame that enters the storage layer must pass through
``DataValidator.validate()`` first.  Each check is a private method returning
``list[ValidationIssue]``; the public ``validate()`` concatenates them all,
sorted by severity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import numpy as np
import pandas as pd
from suitetrading.data.timeframes import tf_to_pandas_offset, tf_to_seconds


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A single data quality issue found during validation."""

    severity: str  # "error", "warning", "info"
    issue_type: str  # "schema", "timestamp", "ohlcv", "gap", "volume", "outlier"
    timestamp: datetime | None  # Where the issue occurs (None for global)
    description: str
    affected_rows: int


_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

REQUIRED_COLUMNS = frozenset({"open", "high", "low", "close", "volume"})


# ── Validator ────────────────────────────────────────────────────────────────


class DataValidator:
    """Validate OHLCV data quality and generate reports."""

    # ── Public API ───────────────────────────────────────────────────────────

    def validate(self, df: pd.DataFrame, expected_tf: str) -> list[ValidationIssue]:
        """Run all checks and return issues sorted by severity."""
        issues: list[ValidationIssue] = []
        issues.extend(self._validate_schema(df))

        # Only proceed with deeper checks if schema is valid
        if any(i.severity == "error" and i.issue_type == "schema" for i in issues):
            return sorted(issues, key=lambda i: _SEVERITY_ORDER.get(i.severity, 9))

        issues.extend(self._validate_timestamps(df))
        issues.extend(self._validate_ohlcv_logic(df))
        issues.extend(self._validate_volume(df))
        issues.extend(self._validate_outliers(df))
        issues.extend(self._validate_gaps(df, expected_tf))
        return sorted(issues, key=lambda i: _SEVERITY_ORDER.get(i.severity, 9))

    def detect_gaps(
        self,
        df: pd.DataFrame,
        expected_tf: str,
        *,
        ignore_weekends: bool = False,
    ) -> pd.DataFrame:
        """Return a DataFrame describing every gap in the timeseries.

        Columns: ``gap_start``, ``gap_end``, ``duration``, ``missing_bars``.
        """
        if len(df) < 2:
            return pd.DataFrame(columns=["gap_start", "gap_end", "duration", "missing_bars"])

        secs = tf_to_seconds(expected_tf)
        if secs is None:
            # Variable-length TF (1M) — skip gap detection
            return pd.DataFrame(columns=["gap_start", "gap_end", "duration", "missing_bars"])

        expected_delta = pd.Timedelta(seconds=secs)
        diffs = df.index.to_series().diff()
        gap_mask = diffs > expected_delta * 1.5

        if ignore_weekends:
            weekday = df.index.to_series().dt.weekday
            weekend_mask = weekday.shift(1).isin([4, 5])  # Fri/Sat → gap to Mon
            gap_mask = gap_mask & ~weekend_mask

        if not gap_mask.any():
            return pd.DataFrame(columns=["gap_start", "gap_end", "duration", "missing_bars"])

        gap_idx = gap_mask[gap_mask].index
        rows: list[dict] = []
        for ts in gap_idx:
            pos = df.index.get_loc(ts)
            if isinstance(pos, int) and pos > 0:
                gap_start = df.index[pos - 1]
            else:
                continue
            duration = ts - gap_start
            missing = int(duration / expected_delta) - 1
            rows.append(
                {"gap_start": gap_start, "gap_end": ts, "duration": duration, "missing_bars": missing}
            )
        return pd.DataFrame(rows)

    def fill_gaps(
        self,
        df: pd.DataFrame,
        expected_tf: str,
        method: str = "ffill",
    ) -> tuple[pd.DataFrame, int]:
        """Fill detected gaps. Returns ``(filled_df, num_bars_added)``."""
        secs = tf_to_seconds(expected_tf)
        if secs is None:
            return df.copy(), 0

        offset = tf_to_pandas_offset(expected_tf)
        full_idx = pd.date_range(df.index.min(), df.index.max(), freq=offset, tz="UTC")
        missing_mask = ~full_idx.isin(df.index)
        num_missing = int(missing_mask.sum())

        if num_missing == 0:
            return df.copy(), 0

        reindexed = df.reindex(full_idx)
        if method == "ffill":
            reindexed[["open", "high", "low", "close"]] = reindexed[
                ["open", "high", "low", "close"]
            ].ffill()
            reindexed["volume"] = reindexed["volume"].fillna(0.0)
        # "mark" leaves NaN as-is for downstream filtering

        return reindexed, num_missing

    def generate_report(
        self,
        exchange: str,
        symbol: str,
        timeframe: str,
        df: pd.DataFrame,
    ) -> dict:
        """Generate a comprehensive quality report dict."""
        issues = self.validate(df, timeframe)
        gaps_df = self.detect_gaps(df, timeframe)

        secs = tf_to_seconds(timeframe)
        if secs and len(df) >= 2:
            total_seconds = (df.index[-1] - df.index[0]).total_seconds()
            expected_rows = int(total_seconds / secs) + 1
        else:
            expected_rows = len(df)

        completeness = len(df) / expected_rows * 100 if expected_rows else 100.0

        zero_vol = (df["volume"] == 0).sum() if "volume" in df.columns else 0
        zero_vol_pct = zero_vol / len(df) * 100 if len(df) else 0.0

        ohlcv_issues = [i for i in issues if i.issue_type == "ohlcv"]
        ohlcv_valid_pct = 100.0 - (sum(i.affected_rows for i in ohlcv_issues) / len(df) * 100) if len(df) else 100.0

        return {
            "exchange": exchange,
            "symbol": symbol,
            "timeframe": timeframe,
            "date_range": {
                "start": df.index.min().isoformat() if len(df) else None,
                "end": df.index.max().isoformat() if len(df) else None,
            },
            "total_rows": len(df),
            "expected_rows": expected_rows,
            "completeness_pct": round(completeness, 2),
            "gaps": [row.to_dict() for _, row in gaps_df.iterrows()] if len(gaps_df) else [],
            "issues": issues,
            "ohlcv_valid_pct": round(ohlcv_valid_pct, 2),
            "volume_zero_pct": round(zero_vol_pct, 2),
        }

    # ── Private checks ───────────────────────────────────────────────────────

    def _validate_schema(self, df: pd.DataFrame) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        missing = REQUIRED_COLUMNS - set(df.columns)
        if missing:
            issues.append(
                ValidationIssue("error", "schema", None, f"Missing columns: {sorted(missing)}", 0)
            )
            return issues

        for col in REQUIRED_COLUMNS:
            if not pd.api.types.is_float_dtype(df[col]):
                issues.append(
                    ValidationIssue("error", "schema", None, f"Column '{col}' is {df[col].dtype}, expected float64", len(df))
                )

        if not isinstance(df.index, pd.DatetimeIndex):
            issues.append(
                ValidationIssue("error", "schema", None, f"Index is {type(df.index).__name__}, expected DatetimeIndex", len(df))
            )
        elif df.index.tz is None:
            issues.append(
                ValidationIssue("error", "schema", None, "DatetimeIndex has no timezone (expected UTC)", len(df))
            )

        return issues

    def _validate_timestamps(self, df: pd.DataFrame) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        if not df.index.is_monotonic_increasing:
            issues.append(
                ValidationIssue("error", "timestamp", None, "Index is not sorted ascending", len(df))
            )

        dup_count = int(df.index.duplicated().sum())
        if dup_count:
            issues.append(
                ValidationIssue("error", "timestamp", None, f"{dup_count} duplicate timestamps", dup_count)
            )

        now = pd.Timestamp.now("UTC")
        future_count = int((df.index > now).sum())
        if future_count:
            issues.append(
                ValidationIssue("warning", "timestamp", None, f"{future_count} future timestamps", future_count)
            )

        return issues

    def _validate_ohlcv_logic(self, df: pd.DataFrame) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        bad_high = ~((df["high"] >= df["open"]) & (df["high"] >= df["close"]) & (df["high"] >= df["low"]))
        n_bad_high = int(bad_high.sum())
        if n_bad_high:
            first_ts = df.index[bad_high][0]
            issues.append(
                ValidationIssue("error", "ohlcv", first_ts.to_pydatetime(), f"high < open/close/low in {n_bad_high} rows", n_bad_high)
            )

        bad_low = ~((df["low"] <= df["open"]) & (df["low"] <= df["close"]))
        n_bad_low = int(bad_low.sum())
        if n_bad_low:
            first_ts = df.index[bad_low][0]
            issues.append(
                ValidationIssue("error", "ohlcv", first_ts.to_pydatetime(), f"low > open/close in {n_bad_low} rows", n_bad_low)
            )

        neg_vol = df["volume"] < 0
        n_neg = int(neg_vol.sum())
        if n_neg:
            first_ts = df.index[neg_vol][0]
            issues.append(
                ValidationIssue("error", "ohlcv", first_ts.to_pydatetime(), f"Negative volume in {n_neg} rows", n_neg)
            )

        return issues

    def _validate_volume(self, df: pd.DataFrame) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if len(df) == 0:
            return issues

        zero_pct = (df["volume"] == 0).sum() / len(df) * 100
        if zero_pct > 1.0:
            issues.append(
                ValidationIssue(
                    "warning", "volume", None,
                    f"Volume is zero in {zero_pct:.1f}% of rows",
                    int((df["volume"] == 0).sum()),
                )
            )
        return issues

    def _validate_outliers(self, df: pd.DataFrame) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        if len(df) < 2:
            return issues

        pct_change = df["close"].pct_change().abs()
        outliers = pct_change > 0.5  # >50% in one bar
        n_outliers = int(outliers.sum())
        if n_outliers:
            first_ts = df.index[outliers][0]
            issues.append(
                ValidationIssue(
                    "warning", "outlier", first_ts.to_pydatetime(),
                    f"Price change >50% in {n_outliers} bars (possible error or extreme event)",
                    n_outliers,
                )
            )
        return issues

    def _validate_gaps(self, df: pd.DataFrame, expected_tf: str) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []
        gaps_df = self.detect_gaps(df, expected_tf)
        if len(gaps_df):
            total_missing = int(gaps_df["missing_bars"].sum())
            issues.append(
                ValidationIssue(
                    "warning", "gap", None,
                    f"{len(gaps_df)} gaps detected, {total_missing} bars missing total",
                    total_missing,
                )
            )
        return issues
