"""Application settings loaded from environment / .env file."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration — values come from env vars or .env file."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # ── General ──────────────────────────────────────────────
    data_dir: str = "./data"
    results_dir: str = "./results"
    log_level: str = "INFO"

    # ── Data directories ─────────────────────────────────────
    raw_data_dir: str = "./data/raw"
    processed_data_dir: str = "./data/processed"

    # ── Exchange config ──────────────────────────────────────
    default_exchange: str = "binance"
    binance_vision_base_url: str = "https://data.binance.vision"

    # ── Download config ──────────────────────────────────────
    download_rate_limit_weight: int = 1200
    download_retry_max: int = 3
    download_retry_backoff: float = 2.0

    # ── Storage config ───────────────────────────────────────
    parquet_compression: str = "zstd"
    parquet_compression_level: int = 3

    # ── Default pairs and timeframes ─────────────────────────
    default_symbols: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    base_timeframe: str = "1m"
    target_timeframes: list[str] = [
        "1m", "3m", "5m", "15m", "30m", "45m",
        "1h", "4h", "1d", "1w", "1M",
    ]

    # ── Alpaca config ────────────────────────────────────────
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_feed: str = "iex"  # "iex" (free) or "sip" (paid)
    alpaca_symbols: list[str] = ["AAPL", "SPY", "QQQ", "MSFT", "AMZN"]
