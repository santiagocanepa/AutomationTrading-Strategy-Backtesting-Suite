"""Tests for suitetrading.data.timeframes — the single source of truth for TFs."""

from __future__ import annotations

import pytest

from suitetrading.data.timeframes import (
    TIMEFRAME_MAP,
    VALID_TIMEFRAMES,
    is_intraday,
    normalize_timeframe,
    partition_scheme,
    tf_to_binance,
    tf_to_ccxt,
    tf_to_pandas_offset,
    tf_to_pine,
    tf_to_seconds,
)

ALL_KEYS = sorted(VALID_TIMEFRAMES)


# ── normalize_timeframe ─────────────────────────────────────────────────────


class TestNormalizeTimeframe:
    """All 11 canonical keys round-trip, plus Pine Script & Binance aliases."""

    @pytest.mark.parametrize("key", ALL_KEYS)
    def test_identity(self, key: str) -> None:
        assert normalize_timeframe(key) == key

    @pytest.mark.parametrize(
        ("alias", "expected"),
        [
            ("1", "1m"),
            ("3", "3m"),
            ("5", "5m"),
            ("15", "15m"),
            ("30", "30m"),
            ("45", "45m"),
            ("60", "1h"),
            ("240", "4h"),
            ("D", "1d"),
            ("W", "1w"),
            ("M", "1M"),
        ],
    )
    def test_pine_aliases(self, alias: str, expected: str) -> None:
        assert normalize_timeframe(alias) == expected

    @pytest.mark.parametrize(
        ("alias", "expected"),
        [
            ("1min", "1m"),
            ("3min", "3m"),
            ("15min", "15m"),
            ("45min", "45m"),
        ],
    )
    def test_pandas_aliases(self, alias: str, expected: str) -> None:
        assert normalize_timeframe(alias) == expected

    def test_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown timeframe"):
            normalize_timeframe("2h")


# ── tf_to_pandas_offset ─────────────────────────────────────────────────────


class TestTfToPandasOffset:
    @pytest.mark.parametrize("key", ALL_KEYS)
    def test_returns_string(self, key: str) -> None:
        result = tf_to_pandas_offset(key)
        assert isinstance(result, str) and len(result) > 0

    def test_1h(self) -> None:
        assert tf_to_pandas_offset("1h") == "1h"

    def test_1d(self) -> None:
        assert tf_to_pandas_offset("1d") == "1D"

    def test_1w(self) -> None:
        assert tf_to_pandas_offset("1w") == "1W-MON"

    def test_1M(self) -> None:
        assert tf_to_pandas_offset("1M") == "1ME"


# ── tf_to_seconds ────────────────────────────────────────────────────────────


class TestTfToSeconds:
    def test_1m(self) -> None:
        assert tf_to_seconds("1m") == 60

    def test_4h(self) -> None:
        assert tf_to_seconds("4h") == 14400

    def test_1d(self) -> None:
        assert tf_to_seconds("1d") == 86400

    def test_1M_is_none(self) -> None:
        assert tf_to_seconds("1M") is None


# ── tf_to_binance ────────────────────────────────────────────────────────────


class TestTfToBinance:
    def test_1h(self) -> None:
        assert tf_to_binance("1h") == "1h"

    def test_45m_is_none(self) -> None:
        assert tf_to_binance("45m") is None

    @pytest.mark.parametrize("key", ALL_KEYS)
    def test_type(self, key: str) -> None:
        result = tf_to_binance(key)
        assert result is None or isinstance(result, str)


# ── tf_to_ccxt ───────────────────────────────────────────────────────────────


class TestTfToCcxt:
    def test_45m_is_none(self) -> None:
        assert tf_to_ccxt("45m") is None

    def test_1d(self) -> None:
        assert tf_to_ccxt("1d") == "1d"


# ── tf_to_pine ───────────────────────────────────────────────────────────────


class TestTfToPine:
    def test_1h(self) -> None:
        assert tf_to_pine("1h") == "60"

    def test_4h(self) -> None:
        assert tf_to_pine("4h") == "240"

    def test_1d(self) -> None:
        assert tf_to_pine("1d") == "D"


# ── is_intraday ──────────────────────────────────────────────────────────────


class TestIsIntraday:
    @pytest.mark.parametrize("key", ["1m", "3m", "5m", "15m", "30m", "45m", "1h", "4h"])
    def test_intraday(self, key: str) -> None:
        assert is_intraday(key) is True

    @pytest.mark.parametrize("key", ["1d", "1w", "1M"])
    def test_not_intraday(self, key: str) -> None:
        assert is_intraday(key) is False


# ── partition_scheme ─────────────────────────────────────────────────────────


class TestPartitionScheme:
    @pytest.mark.parametrize("key", ["1m", "3m", "5m", "15m", "30m", "45m", "1h", "4h"])
    def test_monthly(self, key: str) -> None:
        assert partition_scheme(key) == "monthly"

    @pytest.mark.parametrize("key", ["1d", "1w", "1M"])
    def test_yearly(self, key: str) -> None:
        assert partition_scheme(key) == "yearly"


# ── Consistency ──────────────────────────────────────────────────────────────


class TestConsistency:
    def test_map_has_11_entries(self) -> None:
        assert len(TIMEFRAME_MAP) == 11

    def test_valid_set_matches_map(self) -> None:
        assert set(VALID_TIMEFRAMES) == set(TIMEFRAME_MAP)

    @pytest.mark.parametrize("key", ALL_KEYS)
    def test_every_key_has_all_fields(self, key: str) -> None:
        entry = TIMEFRAME_MAP[key]
        for field in ("pine", "binance", "ccxt", "pandas", "seconds"):
            assert field in entry
