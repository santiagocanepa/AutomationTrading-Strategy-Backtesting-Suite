"""Generate an interactive HTML chart for manual indicator validation.

Usage examples::

    .venv/bin/python scripts/plot_indicator_validation.py
    .venv/bin/python scripts/plot_indicator_validation.py --indicator firestorm
    .venv/bin/python scripts/plot_indicator_validation.py --indicator wavetrend_reversal --bars 500

The script reads locally stored 1m data, resamples it to the requested
timeframe, computes the selected indicator, and exports:

- an interactive HTML chart,
- a CSV with timestamps and signal values.

This is meant for a focused, manual comparison against TradingView.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
except ImportError as exc:  # pragma: no cover - runtime guard for local script
    raise SystemExit(
        "plotly is required for this script. Install it in the project venv to generate HTML charts."
    ) from exc


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from suitetrading.data.resampler import OHLCVResampler
from suitetrading.data.storage import ParquetStore
from suitetrading.indicators.custom.firestorm import Firestorm, firestorm
from suitetrading.indicators.custom.ssl_channel import SSLChannel, ssl_channel, ssl_cross_signals, ssl_level_signals
from suitetrading.indicators.custom.wavetrend import WaveTrendReversal, wavetrend, wavetrend_reversal


SUPPORTED_INDICATORS = ("ssl_channel", "firestorm", "wavetrend_reversal")


def load_ohlcv(
    *,
    exchange: str,
    symbol: str,
    timeframe: str,
    bars: int,
    data_dir: Path,
) -> pd.DataFrame:
    """Load OHLCV from local store, resampling from 1m when needed."""
    store = ParquetStore(base_dir=data_dir)

    if timeframe == "1m":
        df = store.read(exchange, symbol, "1m")
        return df.tail(bars).copy()

    df_1m = store.read(exchange, symbol, "1m")
    resampler = OHLCVResampler()
    df_tf = resampler.resample(df_1m, timeframe, base_tf="1m")
    return df_tf.tail(bars).copy()


def build_ssl_payload(df: pd.DataFrame, *, length: int, hold_bars: int) -> dict[str, Any]:
    ssl_up, ssl_down = ssl_channel(df["high"], df["low"], df["close"], length=length)
    cross_buy, cross_sell = ssl_cross_signals(ssl_up, ssl_down)
    level_buy, level_sell = ssl_level_signals(ssl_up, ssl_down)
    entry_long = SSLChannel().compute(df, length=length, hold_bars=hold_bars, direction="long")

    return {
        "name": "ssl_channel",
        "price_lines": {
            "ssl_up": ssl_up,
            "ssl_down": ssl_down,
        },
        "signals": {
            "cross_buy": cross_buy,
            "cross_sell": cross_sell,
            "level_buy": level_buy,
            "level_sell": level_sell,
            "entry_long": entry_long,
        },
        "subtitle": f"SSL Channel length={length}, hold_bars={hold_bars}",
    }


def build_firestorm_payload(df: pd.DataFrame, *, period: int, multiplier: float, hold_bars: int) -> dict[str, Any]:
    result = firestorm(df["open"], df["high"], df["low"], df["close"], period=period, multiplier=multiplier)
    entry_long = Firestorm().compute(
        df,
        period=period,
        multiplier=multiplier,
        hold_bars=hold_bars,
        direction="long",
    )

    return {
        "name": "firestorm",
        "price_lines": {
            "firestorm_up": result["up"],
            "firestorm_dn": result["dn"],
        },
        "signals": {
            "buy": result["buy"],
            "sell": result["sell"],
            "entry_long": entry_long,
            "trend": result["trend"],
        },
        "subtitle": f"Firestorm period={period}, multiplier={multiplier}, hold_bars={hold_bars}",
    }


def build_wavetrend_payload(
    df: pd.DataFrame,
    *,
    channel_len: int,
    average_len: int,
    ma_len: int,
    ob_level: float,
    os_level: float,
    hold_bars: int,
) -> dict[str, Any]:
    wt1, wt2 = wavetrend(
        df["high"],
        df["low"],
        df["close"],
        channel_len=channel_len,
        average_len=average_len,
        ma_len=ma_len,
    )
    buy, sell = wavetrend_reversal(wt1, wt2, ob_level=ob_level, os_level=os_level)
    entry_long = WaveTrendReversal().compute(
        df,
        channel_len=channel_len,
        average_len=average_len,
        ma_len=ma_len,
        ob_level=ob_level,
        os_level=os_level,
        hold_bars=hold_bars,
        direction="long",
    )

    return {
        "name": "wavetrend_reversal",
        "price_lines": {},
        "signals": {
            "buy": buy,
            "sell": sell,
            "entry_long": entry_long,
        },
        "oscillator": {
            "wt1": wt1,
            "wt2": wt2,
            "ob_level": pd.Series(ob_level, index=df.index, name="ob_level"),
            "os_level": pd.Series(os_level, index=df.index, name="os_level"),
        },
        "subtitle": (
            "WaveTrend Reversal "
            f"channel_len={channel_len}, average_len={average_len}, ma_len={ma_len}, "
            f"ob_level={ob_level}, os_level={os_level}, hold_bars={hold_bars}"
        ),
    }


def build_payload(args: argparse.Namespace, df: pd.DataFrame) -> dict[str, Any]:
    if args.indicator == "ssl_channel":
        return build_ssl_payload(df, length=args.length, hold_bars=args.hold_bars)
    if args.indicator == "firestorm":
        return build_firestorm_payload(
            df,
            period=args.period,
            multiplier=args.multiplier,
            hold_bars=args.hold_bars,
        )
    return build_wavetrend_payload(
        df,
        channel_len=args.channel_len,
        average_len=args.average_len,
        ma_len=args.ma_len,
        ob_level=args.ob_level,
        os_level=args.os_level,
        hold_bars=args.hold_bars,
    )


def build_chart(df: pd.DataFrame, payload: dict[str, Any], *, title: str) -> go.Figure:
    has_oscillator = "oscillator" in payload

    if has_oscillator:
        fig = make_subplots(
            rows=2,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.06,
            row_heights=[0.68, 0.32],
        )
    else:
        fig = make_subplots(rows=1, cols=1, shared_xaxes=True)

    fig.add_trace(
        go.Candlestick(
            x=df.index,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="OHLCV",
        ),
        row=1,
        col=1,
    )

    for name, series in payload.get("price_lines", {}).items():
        fig.add_trace(
            go.Scatter(x=series.index, y=series.values, mode="lines", name=name),
            row=1,
            col=1,
        )

    add_signal_markers(fig, df, payload.get("signals", {}), row=1)

    if has_oscillator:
        oscillator = payload["oscillator"]
        for name, series in oscillator.items():
            fig.add_trace(
                go.Scatter(x=series.index, y=series.values, mode="lines", name=name),
                row=2,
                col=1,
            )

    fig.update_layout(
        title=f"{title}<br><sup>{payload['subtitle']}</sup>",
        xaxis_rangeslider_visible=False,
        template="plotly_white",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
        height=950 if has_oscillator else 700,
    )
    return fig


def add_signal_markers(fig: go.Figure, df: pd.DataFrame, signals: dict[str, pd.Series], *, row: int) -> None:
    marker_specs = {
        "cross_buy": {"color": "green", "symbol": "triangle-up", "y": df["low"] * 0.995},
        "buy": {"color": "green", "symbol": "triangle-up", "y": df["low"] * 0.995},
        "entry_long": {"color": "blue", "symbol": "circle", "y": df["low"] * 0.99},
        "cross_sell": {"color": "red", "symbol": "triangle-down", "y": df["high"] * 1.005},
        "sell": {"color": "red", "symbol": "triangle-down", "y": df["high"] * 1.005},
    }

    for name, spec in marker_specs.items():
        series = signals.get(name)
        if series is None:
            continue
        active = series.astype(bool)
        if not active.any():
            continue
        fig.add_trace(
            go.Scatter(
                x=df.index[active],
                y=spec["y"][active],
                mode="markers",
                name=name,
                marker=dict(color=spec["color"], symbol=spec["symbol"], size=9),
            ),
            row=row,
            col=1,
        )


def build_signal_export(df: pd.DataFrame, payload: dict[str, Any]) -> pd.DataFrame:
    export = pd.DataFrame(index=df.index)
    export["open"] = df["open"]
    export["high"] = df["high"]
    export["low"] = df["low"]
    export["close"] = df["close"]

    for name, series in payload.get("price_lines", {}).items():
        export[name] = series
    for name, series in payload.get("oscillator", {}).items():
        if name in {"ob_level", "os_level"}:
            continue
        export[name] = series
    for name, series in payload.get("signals", {}).items():
        export[name] = series

    return export.reset_index(names="timestamp")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate indicator validation HTML for manual TradingView comparison")
    parser.add_argument("--exchange", default="binance")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--timeframe", default="1h")
    parser.add_argument("--bars", type=int, default=300)
    parser.add_argument("--indicator", choices=SUPPORTED_INDICATORS, default="ssl_channel")
    parser.add_argument("--data-dir", type=str, default=str(PROJECT_ROOT / "data" / "raw"))
    parser.add_argument("--output-dir", type=str, default=str(PROJECT_ROOT / "artifacts" / "indicator_validation"))

    parser.add_argument("--length", type=int, default=12)
    parser.add_argument("--period", type=int, default=10)
    parser.add_argument("--multiplier", type=float, default=1.8)
    parser.add_argument("--channel-len", type=int, default=9)
    parser.add_argument("--average-len", type=int, default=12)
    parser.add_argument("--ma-len", type=int, default=3)
    parser.add_argument("--ob-level", type=float, default=60.0)
    parser.add_argument("--os-level", type=float, default=-60.0)
    parser.add_argument("--hold-bars", type=int, default=4)

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    df = load_ohlcv(
        exchange=args.exchange,
        symbol=args.symbol,
        timeframe=args.timeframe,
        bars=args.bars,
        data_dir=data_dir,
    )
    payload = build_payload(args, df)

    stem = f"{args.symbol}_{args.timeframe}_{args.indicator}"
    html_path = output_dir / f"{stem}.html"
    csv_path = output_dir / f"{stem}.csv"

    fig = build_chart(df, payload, title=f"{args.symbol} {args.timeframe} — {args.indicator}")
    fig.write_html(str(html_path))

    export_df = build_signal_export(df, payload)
    export_df.to_csv(csv_path, index=False)

    print(f"HTML written to {html_path}")
    print(f"CSV written to {csv_path}")


if __name__ == "__main__":
    main()