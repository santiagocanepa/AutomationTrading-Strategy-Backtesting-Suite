"""Futures/derivatives-specific indicators.

These indicators use data columns beyond standard OHLCV:
- ``funding_rate``: Binance perpetual futures funding rate (8h updates)
- ``open_interest``: Aggregate open interest (5m-1d resolution)
- ``long_short_ratio``: Global long/short account ratio (5m-1d resolution)

All indicators fall back gracefully to no-signal (all False) when the
required columns are absent, so they can be included in archetypes
without requiring futures data to be downloaded.

Data availability for production:
    funding_rate:      Every 8h — use as regime filter, not entry timing
    open_interest:     5m/15m/1h/4h — fine for any TF >= 15m
    long_short_ratio:  5m/15m/1h/4h — fine for any TF >= 15m
"""
