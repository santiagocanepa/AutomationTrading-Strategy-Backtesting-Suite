"""Tests for suitetrading.data.validator — OHLCV quality checks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from suitetrading.data.validator import DataValidator, ValidationIssue


@pytest.fixture
def validator() -> DataValidator:
    return DataValidator()


@pytest.fixture
def valid_1m(sample_1m_1day: pd.DataFrame) -> pd.DataFrame:
    """Return the shared fixture — it's already valid OHLCV."""
    return sample_1m_1day


# ── Schema checks ────────────────────────────────────────────────────────────


class TestSchemaValidation:
    def test_valid_ohlcv_passes(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        issues = validator.validate(valid_1m, "1m")
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) == 0

    def test_missing_column_fails(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        df = valid_1m.drop(columns=["volume"])
        issues = validator.validate(df, "1m")
        errors = [i for i in issues if i.severity == "error"]
        assert any("volume" in i.description for i in errors)

    def test_wrong_dtype_fails(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        df = valid_1m.copy()
        df["close"] = df["close"].astype(str)
        issues = validator.validate(df, "1m")
        errors = [i for i in issues if i.severity == "error"]
        assert any("close" in i.description for i in errors)

    def test_no_timezone_fails(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        df = valid_1m.copy()
        df.index = df.index.tz_localize(None)
        issues = validator.validate(df, "1m")
        errors = [i for i in issues if i.severity == "error"]
        assert any("timezone" in i.description.lower() or "UTC" in i.description for i in errors)

    def test_non_datetime_index_fails(self, validator: DataValidator) -> None:
        df = pd.DataFrame(
            {"open": [1.0], "high": [2.0], "low": [0.5], "close": [1.5], "volume": [10.0]},
            index=[0],
        )
        issues = validator.validate(df, "1m")
        errors = [i for i in issues if i.severity == "error"]
        assert len(errors) > 0


# ── Timestamp checks ─────────────────────────────────────────────────────────


class TestTimestampValidation:
    def test_unsorted_timestamps(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        df = valid_1m.iloc[::-1]  # Reverse order
        issues = validator.validate(df, "1m")
        errors = [i for i in issues if i.severity == "error" and i.issue_type == "timestamp"]
        assert any("sorted" in i.description.lower() for i in errors)

    def test_duplicate_timestamps(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        df = pd.concat([valid_1m.iloc[:5], valid_1m.iloc[:5]])
        df = df.sort_index()
        issues = validator.validate(df, "1m")
        errors = [i for i in issues if i.severity == "error" and i.issue_type == "timestamp"]
        assert any("duplicate" in i.description.lower() for i in errors)


# ── OHLCV logic checks ──────────────────────────────────────────────────────


class TestOHLCVLogic:
    def test_high_less_than_low(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        df = valid_1m.copy()
        df.iloc[10, df.columns.get_loc("high")] = df.iloc[10]["low"] - 10
        issues = validator.validate(df, "1m")
        errors = [i for i in issues if i.severity == "error" and i.issue_type == "ohlcv"]
        assert len(errors) > 0

    def test_negative_volume(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        df = valid_1m.copy()
        df.iloc[0, df.columns.get_loc("volume")] = -5.0
        issues = validator.validate(df, "1m")
        errors = [i for i in issues if i.severity == "error" and "volume" in i.description.lower()]
        assert len(errors) > 0


# ── Gap detection ────────────────────────────────────────────────────────────


class TestGapDetection:
    def test_detect_gaps_finds_missing(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        # Drop 5 bars in the middle
        df = pd.concat([valid_1m.iloc[:100], valid_1m.iloc[105:]])
        gaps = validator.detect_gaps(df, "1m")
        assert len(gaps) == 1
        assert gaps.iloc[0]["missing_bars"] >= 4

    def test_detect_gaps_no_false_positive(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        gaps = validator.detect_gaps(valid_1m, "1m")
        assert len(gaps) == 0


# ── Gap filling ──────────────────────────────────────────────────────────────


class TestGapFilling:
    def test_fill_gaps_ffill(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        df = pd.concat([valid_1m.iloc[:100], valid_1m.iloc[105:]])
        filled, count = validator.fill_gaps(df, "1m", method="ffill")
        assert count == 5
        assert not filled["close"].isna().any()
        # Filled volume should be 0
        filled_only = filled.iloc[100:105]
        assert (filled_only["volume"] == 0.0).all()

    def test_fill_gaps_mark(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        df = pd.concat([valid_1m.iloc[:100], valid_1m.iloc[105:]])
        filled, count = validator.fill_gaps(df, "1m", method="mark")
        assert count == 5
        # Mark leaves NaN
        assert filled["close"].isna().any()


# ── Warnings ─────────────────────────────────────────────────────────────────


class TestWarnings:
    def test_outlier_warning(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        df = valid_1m.copy()
        # Create a 200% jump
        df.iloc[50, df.columns.get_loc("close")] = df.iloc[49]["close"] * 3
        issues = validator.validate(df, "1m")
        warnings = [i for i in issues if i.severity == "warning" and i.issue_type == "outlier"]
        assert len(warnings) > 0

    def test_zero_volume_warning(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        df = valid_1m.copy()
        # Set >1% of volume to 0
        n_zero = int(len(df) * 0.02)
        df.iloc[:n_zero, df.columns.get_loc("volume")] = 0.0
        issues = validator.validate(df, "1m")
        warnings = [i for i in issues if i.severity == "warning" and i.issue_type == "volume"]
        assert len(warnings) > 0


# ── Report ───────────────────────────────────────────────────────────────────


class TestReport:
    def test_generate_report_structure(self, validator: DataValidator, valid_1m: pd.DataFrame) -> None:
        report = validator.generate_report("binance", "BTCUSDT", "1m", valid_1m)
        assert report["exchange"] == "binance"
        assert report["symbol"] == "BTCUSDT"
        assert report["timeframe"] == "1m"
        assert "total_rows" in report
        assert "completeness_pct" in report
        assert "ohlcv_valid_pct" in report
        assert "volume_zero_pct" in report
        assert isinstance(report["issues"], list)
        assert isinstance(report["gaps"], list)
