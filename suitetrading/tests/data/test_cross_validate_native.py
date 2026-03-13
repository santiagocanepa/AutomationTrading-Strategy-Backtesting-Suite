from __future__ import annotations

import pandas as pd

from scripts.cross_validate_native import _first_complete_bar_start, _trim_to_complete_bars


def test_first_complete_bar_start_skips_partial_hour() -> None:
    window_start = pd.Timestamp("2026-02-09T17:51:00Z")

    assert _first_complete_bar_start(window_start, "1h") == pd.Timestamp("2026-02-09T18:00:00Z")


def test_first_complete_bar_start_preserves_aligned_day() -> None:
    window_start = pd.Timestamp("2026-02-10T00:00:00Z")

    assert _first_complete_bar_start(window_start, "1d") == pd.Timestamp("2026-02-10T00:00:00Z")


def test_trim_to_complete_bars_drops_leading_partial_day() -> None:
    index = pd.to_datetime(
        ["2026-02-09T00:00:00Z", "2026-02-10T00:00:00Z", "2026-02-11T00:00:00Z"],
        utc=True,
    )
    df = pd.DataFrame(
        {
            "open": [1.0, 2.0, 3.0],
            "high": [1.0, 2.0, 3.0],
            "low": [1.0, 2.0, 3.0],
            "close": [1.0, 2.0, 3.0],
            "volume": [1.0, 2.0, 3.0],
        },
        index=index,
    )

    trimmed = _trim_to_complete_bars(
        df,
        window_start=pd.Timestamp("2026-02-09T17:51:00Z"),
        target_tf="1d",
    )

    assert trimmed.index.tolist() == list(index[1:])