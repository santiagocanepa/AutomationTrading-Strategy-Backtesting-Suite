"""Slippage models — realistic execution cost estimation for crypto markets.

Provides timeframe-aware and asset-aware slippage estimates based on
empirical spreads and market microstructure data from Binance.

Typical bid-ask spreads on Binance Futures (2024-2025 averages):
    BTC: 0.01%    ETH: 0.01%    SOL: 0.02%
    BNB: 0.02%    AVAX: 0.03%   LINK: 0.03%

On lower timeframes, slippage has proportionally more impact because
the per-bar move is smaller relative to the spread.
"""

from __future__ import annotations

# Empirical half-spread in percent (= one side of bid-ask spread).
# This is the MINIMUM slippage — market orders cross the spread.
_BASE_SPREAD_PCT: dict[str, float] = {
    "BTCUSDT": 0.005,    # ~$0.50 on $100K BTC
    "ETHUSDT": 0.007,
    "SOLUSDT": 0.010,
    "BNBUSDT": 0.010,
    "AVAXUSDT": 0.015,
    "LINKUSDT": 0.015,
}

# Additional impact slippage per timeframe (lower TF = more entries = more impact).
# Empirical: fills on a 15m signal arrive within ~5s → price moves ~0.01% on BTC.
_TF_IMPACT_PCT: dict[str, float] = {
    "1m": 0.020,
    "5m": 0.015,
    "15m": 0.010,
    "30m": 0.008,
    "1h": 0.005,
    "2h": 0.004,
    "4h": 0.003,
    "1d": 0.002,
}

# ── Stock spreads ────────────────────────────────────────────────────
_BASE_SPREAD_PCT_STOCK: dict[str, float] = {
    "SPY": 0.003,    # Ultra-liquid ETF
    "QQQ": 0.003,
    "IWM": 0.005,
    "XLK": 0.005,
    "XLF": 0.005,
    "XLE": 0.008,
    "GLD": 0.005,
    "TLT": 0.005,
    "AAPL": 0.003,
    "MSFT": 0.003,
    "NVDA": 0.005,
    "TSLA": 0.008,
    "AMZN": 0.005,
}

_TF_IMPACT_PCT_STOCK: dict[str, float] = {
    "1m": 0.010,
    "5m": 0.008,
    "15m": 0.005,
    "30m": 0.004,
    "1h": 0.003,
    "4h": 0.002,
    "1d": 0.001,
}

_DEFAULT_SPREAD = 0.010
_DEFAULT_IMPACT = 0.005
_DEFAULT_SPREAD_STOCK = 0.005
_DEFAULT_IMPACT_STOCK = 0.003


def estimate_slippage_pct(
    symbol: str = "BTCUSDT",
    timeframe: str = "1h",
) -> float:
    """Return estimated one-way slippage in percent.

    Auto-detects crypto vs stock based on symbol name (USDT suffix = crypto).

    Total cost per trade = commission + slippage (applied on both entry and exit).
    Stocks via Alpaca are commission-free, so slippage is the main cost.
    """
    is_crypto = symbol.endswith("USDT") or symbol.endswith("USD")
    if is_crypto:
        spread = _BASE_SPREAD_PCT.get(symbol, _DEFAULT_SPREAD)
        impact = _TF_IMPACT_PCT.get(timeframe, _DEFAULT_IMPACT)
    else:
        spread = _BASE_SPREAD_PCT_STOCK.get(symbol, _DEFAULT_SPREAD_STOCK)
        impact = _TF_IMPACT_PCT_STOCK.get(timeframe, _DEFAULT_IMPACT_STOCK)
    return round(spread + impact, 4)


def get_slippage_table() -> dict[str, dict[str, float]]:
    """Return a full table of slippage estimates for all symbol × timeframe combos."""
    symbols = list(_BASE_SPREAD_PCT.keys())
    timeframes = list(_TF_IMPACT_PCT.keys())
    table: dict[str, dict[str, float]] = {}
    for sym in symbols:
        table[sym] = {}
        for tf in timeframes:
            table[sym][tf] = estimate_slippage_pct(sym, tf)
    return table
