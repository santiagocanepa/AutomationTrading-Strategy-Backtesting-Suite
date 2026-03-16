"""
Signal Edge Analysis — Correct next-bar methodology (no look-ahead bias).

Ejecutar con:
    .venv/bin/python scripts/signal_edge_analysis.py

Secciones:
  1. Correct Signal Edge para todos los indicadores × timeframes
  2. Indicadores como filtro de exposicion (reduccion de drawdown)
  3. Combinaciones de indicadores en 4h
  4. Momentum puro (ROC, MA crossover, Donchian, ADX)
  5. Multi-timeframe filter (SSL 4h + EMA200 1d)
  6. Analisis por regimen de mercado
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ── Path setup ────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from suitetrading.data.storage import ParquetStore
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.indicators.registry import get_indicator
from suitetrading.indicators.custom.ssl_channel import ssl_channel, ssl_level_signals
from suitetrading.indicators.custom.firestorm import firestorm
from suitetrading.indicators.custom.wavetrend import wavetrend, wavetrend_reversal

import talib

# ── Constants ─────────────────────────────────────────────────────────────────
DATA_DIR = PROJECT_ROOT / "data" / "raw"
EXCHANGE = "binance"
SYMBOL = "BTCUSDT"
ANNUAL_FACTOR_MAP = {"1h": 8760, "4h": 2190, "1d": 365}
SEP = "=" * 72


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def load_1m() -> pd.DataFrame:
    store = ParquetStore(DATA_DIR)
    return store.read(EXCHANGE, SYMBOL, "1m")


def resample_tf(df_1m: pd.DataFrame, tf: str) -> pd.DataFrame:
    if tf == "1m":
        return df_1m.copy()
    resampler = OHLCVResampler()
    return resampler.resample(df_1m, tf, base_tf="1m")


def bar_returns(df: pd.DataFrame) -> pd.Series:
    """Log returns per bar."""
    return np.log(df["close"] / df["close"].shift(1))


def next_bar_return(signal: pd.Series, ret: pd.Series) -> pd.Series:
    """Correct: signal[i] -> return[i+1]. No look-ahead."""
    sig_shifted = signal.shift(1).fillna(False).astype(bool)
    return ret.where(sig_shifted, 0.0)


def cumulative_return(r: pd.Series) -> float:
    return float(np.exp(r.sum()) - 1)


def annualized_sharpe(r: pd.Series, annual_factor: int) -> float:
    if r.std() == 0:
        return 0.0
    return float((r.mean() / r.std()) * np.sqrt(annual_factor))


def annualized_sortino(r: pd.Series, annual_factor: int) -> float:
    downside = r[r < 0]
    if len(downside) == 0 or downside.std() == 0:
        return float("inf") if r.mean() > 0 else 0.0
    return float((r.mean() / downside.std()) * np.sqrt(annual_factor))


def max_drawdown(equity_curve: pd.Series) -> float:
    roll_max = equity_curve.cummax()
    drawdown = (equity_curve - roll_max) / roll_max.replace(0, np.nan)
    return float(drawdown.min())


def compute_equity(r: pd.Series) -> pd.Series:
    return np.exp(r.cumsum())


def pct_time_in_market(signal: pd.Series) -> float:
    sig_shifted = signal.shift(1).fillna(False).astype(bool)
    return float(sig_shifted.sum() / len(sig_shifted))


def print_section(title: str) -> None:
    print(f"\n{SEP}")
    print(f"=== {title} ===")
    print(SEP)


def print_table(rows: list[dict], cols: list[str]) -> None:
    widths = {c: max(len(c), max(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    print(f"| {header} |")
    print(f"|-{sep}-|")
    for row in rows:
        line = " | ".join(str(row.get(c, "")).ljust(widths[c]) for c in cols)
        print(f"| {line} |")


# ═══════════════════════════════════════════════════════════════════════════════
# Signal builders — retornan pd.Series bool con el mismo indice que df
# ═══════════════════════════════════════════════════════════════════════════════

def build_ssl_signal(df: pd.DataFrame) -> pd.Series:
    """SSL level signal: ssl_up > ssl_down (persistente)."""
    ind = get_indicator("ssl_channel")
    return ind.compute(df, length=12, hold_bars=4)


def build_ssl_level(df: pd.DataFrame) -> pd.Series:
    """SSL level (no hold_bars) para uso como filtro."""
    ssl_up, ssl_down = ssl_channel(df["high"], df["low"], df["close"], length=12)
    buy, _ = ssl_level_signals(ssl_up, ssl_down)
    return buy


def build_firestorm_signal(df: pd.DataFrame) -> pd.Series:
    ind = get_indicator("firestorm")
    return ind.compute(df, period=10, multiplier=1.8, hold_bars=1)


def build_firestorm_level(df: pd.DataFrame) -> pd.Series:
    """Firestorm trend=1 (persistente)."""
    result = firestorm(df["open"], df["high"], df["low"], df["close"], period=10, multiplier=1.8)
    return result["trend"] == 1


def build_wavetrend_signal(df: pd.DataFrame) -> pd.Series:
    ind = get_indicator("wavetrend_reversal")
    return ind.compute(df, channel_len=9, average_len=12, ma_len=3, hold_bars=3)


def build_rsi_signal(df: pd.DataFrame) -> pd.Series:
    ind = get_indicator("rsi")
    return ind.compute(df, period=14, threshold=30.0, mode="oversold", hold_bars=3)


def build_ema_signal(df: pd.DataFrame) -> pd.Series:
    ind = get_indicator("ema")
    return ind.compute(df, period=21, mode="above", hold_bars=3)


def build_macd_signal(df: pd.DataFrame) -> pd.Series:
    ind = get_indicator("macd")
    return ind.compute(df, fast=12, slow=26, signal=9, mode="bullish", hold_bars=3)


def build_bbands_signal(df: pd.DataFrame) -> pd.Series:
    ind = get_indicator("bollinger_bands")
    return ind.compute(df, period=20, nbdev=2.0, mode="lower", hold_bars=3)


INDICATOR_BUILDERS = {
    "ssl_channel": build_ssl_signal,
    "firestorm": build_firestorm_signal,
    "wavetrend_reversal": build_wavetrend_signal,
    "rsi": build_rsi_signal,
    "ema": build_ema_signal,
    "macd": build_macd_signal,
    "bollinger_bands": build_bbands_signal,
}


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 1: Correct Signal Edge
# ═══════════════════════════════════════════════════════════════════════════════

def section1_correct_edge(df_1m: pd.DataFrame) -> None:
    print_section("SECTION 1: CORRECT SIGNAL EDGE (sin look-ahead) — todos los indicadores")

    timeframes = ["1h", "4h", "1d"]
    rows: list[dict] = []

    for tf in timeframes:
        print(f"\n  Procesando timeframe {tf}...")
        df = resample_tf(df_1m, tf)
        annual = ANNUAL_FACTOR_MAP[tf]
        ret = bar_returns(df)
        bh_ret = ret.dropna()

        bh_cum = cumulative_return(bh_ret)
        bh_sharpe = annualized_sharpe(bh_ret, annual)
        bh_eq = compute_equity(bh_ret)
        bh_dd = max_drawdown(bh_eq)

        for name, builder in INDICATOR_BUILDERS.items():
            try:
                sig = builder(df)
            except Exception as e:
                print(f"    ERROR {name}: {e}")
                continue

            strat_r = next_bar_return(sig, ret).dropna()
            cum_r = cumulative_return(strat_r)
            sharpe = annualized_sharpe(strat_r, annual)
            sortino = annualized_sortino(strat_r, annual)
            eq = compute_equity(strat_r)
            dd = max_drawdown(eq)
            pct_in = pct_time_in_market(sig)

            # Drawdown when in position
            in_pos = sig.shift(1).fillna(False).astype(bool)
            ret_in = ret.where(in_pos, 0.0).dropna()
            eq_in = compute_equity(ret_in)
            dd_in = max_drawdown(eq_in)

            ret_out = ret.where(~in_pos, 0.0).dropna()
            eq_out = compute_equity(ret_out)
            dd_out = max_drawdown(eq_out)

            rows.append({
                "indicator": name,
                "tf": tf,
                "cum_ret%": f"{cum_r*100:.1f}",
                "bh_ret%": f"{bh_cum*100:.1f}",
                "sharpe": f"{sharpe:.2f}",
                "sortino": f"{sortino:.2f}",
                "max_dd_in%": f"{dd_in*100:.1f}",
                "max_dd_out%": f"{dd_out*100:.1f}",
                "pct_in%": f"{pct_in*100:.1f}",
            })

    cols = ["indicator", "tf", "cum_ret%", "bh_ret%", "sharpe", "sortino",
            "max_dd_in%", "max_dd_out%", "pct_in%"]
    print_table(rows, cols)

    print(f"\n  Buy & Hold BTC (referencia):")
    for tf in timeframes:
        df = resample_tf(df_1m, tf)
        annual = ANNUAL_FACTOR_MAP[tf]
        ret = bar_returns(df).dropna()
        bh_cum = cumulative_return(ret)
        bh_sharpe = annualized_sharpe(ret, annual)
        bh_eq = compute_equity(ret)
        bh_dd = max_drawdown(bh_eq)
        print(f"    {tf}: cum={bh_cum*100:.1f}%, sharpe={bh_sharpe:.2f}, max_dd={bh_dd*100:.1f}%")

    return rows


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 2: Signal como filtro de exposicion
# ═══════════════════════════════════════════════════════════════════════════════

def section2_exposure_filter(df_1m: pd.DataFrame) -> None:
    print_section("SECTION 2: SIGNAL COMO FILTRO DE EXPOSICION")

    tf = "4h"
    df = resample_tf(df_1m, tf)
    annual = ANNUAL_FACTOR_MAP[tf]
    ret = bar_returns(df)

    rows: list[dict] = []

    for name, builder in INDICATOR_BUILDERS.items():
        try:
            sig = builder(df)
        except Exception as e:
            print(f"  ERROR {name}: {e}")
            continue

        in_pos = sig.shift(1).fillna(False).astype(bool)
        out_pos = ~in_pos

        r_in = ret[in_pos].dropna()
        r_out = ret[out_pos].dropna()

        avg_in = float(r_in.mean()) if len(r_in) > 0 else 0.0
        avg_out = float(r_out.mean()) if len(r_out) > 0 else 0.0
        vol_in = float(r_in.std()) if len(r_in) > 0 else 0.0
        vol_out = float(r_out.std()) if len(r_out) > 0 else 0.0

        eq_in = compute_equity(ret.where(in_pos, 0.0).dropna())
        eq_out = compute_equity(ret.where(out_pos, 0.0).dropna())
        dd_in = max_drawdown(eq_in)
        dd_out = max_drawdown(eq_out)

        # Reduces DD? (dd_in less negative than dd_out or global)
        eq_global = compute_equity(ret.dropna())
        dd_global = max_drawdown(eq_global)
        reduces_dd = "SI" if abs(dd_in) < abs(dd_global) else "NO"

        rows.append({
            "indicator": name,
            "avg_ret_in (bps)": f"{avg_in*10000:.2f}",
            "avg_ret_out (bps)": f"{avg_out*10000:.2f}",
            "vol_in": f"{vol_in:.4f}",
            "vol_out": f"{vol_out:.4f}",
            "max_dd_in%": f"{dd_in*100:.1f}",
            "max_dd_out%": f"{dd_out*100:.1f}",
            "global_dd%": f"{dd_global*100:.1f}",
            "reduce_DD": reduces_dd,
        })

    cols = ["indicator", "avg_ret_in (bps)", "avg_ret_out (bps)", "vol_in", "vol_out",
            "max_dd_in%", "max_dd_out%", "global_dd%", "reduce_DD"]
    print_table(rows, cols)
    print("\n  avg_ret_in > avg_ret_out => el indicador discrimina return positivo")
    print("  reduce_DD=SI => el indicador evita los peores periodos del mercado")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 3: Combinaciones de indicadores en 4h
# ═══════════════════════════════════════════════════════════════════════════════

def section3_combinations(df_1m: pd.DataFrame) -> None:
    print_section("SECTION 3: COMBINACIONES DE INDICADORES (4h, sin look-ahead)")

    tf = "4h"
    df = resample_tf(df_1m, tf)
    annual = ANNUAL_FACTOR_MAP[tf]
    ret = bar_returns(df)

    ssl = build_ssl_signal(df)
    ssl_lvl = build_ssl_level(df)
    fire = build_firestorm_signal(df)
    fire_lvl = build_firestorm_level(df)
    ema200 = talib.EMA(df["close"].values, timeperiod=200)
    ema200_s = pd.Series(ema200, index=df.index)
    ema200_above = df["close"] > ema200_s

    wt_sig = build_wavetrend_signal(df)

    combos: dict[str, pd.Series] = {
        "SSL AND Firestorm": ssl & fire,
        "SSL OR Firestorm": ssl | fire,
        "SSL AND EMA(200)": ssl & ema200_above,
        "Majority (SSL+Fire+EMA, 2/3)": (ssl.astype(int) + fire.astype(int) + ema200_above.astype(int)) >= 2,
        "WaveTrend solo": wt_sig,
        "SSL solo": ssl,
        "Firestorm solo": fire,
    }

    bh_ret_full = ret.dropna()
    bh_cum = cumulative_return(bh_ret_full)
    bh_sharpe = annualized_sharpe(bh_ret_full, annual)

    rows: list[dict] = []

    for combo_name, sig in combos.items():
        sig = sig.fillna(False).astype(bool)
        strat_r = next_bar_return(sig, ret).dropna()
        cum_r = cumulative_return(strat_r)
        sharpe = annualized_sharpe(strat_r, annual)
        sortino = annualized_sortino(strat_r, annual)
        eq = compute_equity(strat_r)
        dd = max_drawdown(eq)
        pct_in = pct_time_in_market(sig)

        rows.append({
            "combination": combo_name,
            "cum_ret%": f"{cum_r*100:.1f}",
            "bh_ret%": f"{bh_cum*100:.1f}",
            "sharpe": f"{sharpe:.2f}",
            "sortino": f"{sortino:.2f}",
            "max_dd%": f"{dd*100:.1f}",
            "pct_in%": f"{pct_in*100:.1f}",
        })

    cols = ["combination", "cum_ret%", "bh_ret%", "sharpe", "sortino", "max_dd%", "pct_in%"]
    print_table(rows, cols)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 4: Momentum puro (sin look-ahead)
# ═══════════════════════════════════════════════════════════════════════════════

def roc_signal(df: pd.DataFrame, n: int = 20) -> pd.Series:
    roc = df["close"] / df["close"].shift(n) - 1
    return (roc > 0).fillna(False)


def ma_crossover_signal(df: pd.DataFrame, fast: int = 20, slow: int = 50) -> pd.Series:
    sma_fast = talib.SMA(df["close"].values, timeperiod=fast)
    sma_slow = talib.SMA(df["close"].values, timeperiod=slow)
    return pd.Series(sma_fast > sma_slow, index=df.index).fillna(False)


def donchian_breakout_signal(df: pd.DataFrame, n: int = 20) -> pd.Series:
    rolling_max = df["close"].rolling(n).max()
    # Breakout: close == rolling max (or within 0.01% to handle float precision)
    on_breakout = df["close"] >= rolling_max * 0.9999
    return on_breakout.fillna(False)


def adx_trend_filter(df: pd.DataFrame, period: int = 14, threshold: float = 25.0) -> pd.Series:
    adx = talib.ADX(df["high"].values, df["low"].values, df["close"].values, timeperiod=period)
    plus_di = talib.PLUS_DI(df["high"].values, df["low"].values, df["close"].values, timeperiod=period)
    minus_di = talib.MINUS_DI(df["high"].values, df["low"].values, df["close"].values, timeperiod=period)
    # Long signal: ADX > threshold AND DI+ > DI-
    signal = (adx > threshold) & (plus_di > minus_di)
    return pd.Series(signal, index=df.index).fillna(False)


MOMENTUM_BUILDERS: dict[str, dict] = {
    "ROC(20)>0": {"fn": roc_signal, "kwargs": {"n": 20}},
    "ROC(5)>0": {"fn": roc_signal, "kwargs": {"n": 5}},
    "MA_cross(20,50)": {"fn": ma_crossover_signal, "kwargs": {"fast": 20, "slow": 50}},
    "MA_cross(50,200)": {"fn": ma_crossover_signal, "kwargs": {"fast": 50, "slow": 200}},
    "Donchian(20)": {"fn": donchian_breakout_signal, "kwargs": {"n": 20}},
    "Donchian(55)": {"fn": donchian_breakout_signal, "kwargs": {"n": 55}},
    "ADX(14)>25": {"fn": adx_trend_filter, "kwargs": {"period": 14, "threshold": 25.0}},
    "ADX(14)>20": {"fn": adx_trend_filter, "kwargs": {"period": 14, "threshold": 20.0}},
}


def section4_momentum(df_1m: pd.DataFrame) -> None:
    print_section("SECTION 4: INDICADORES DE MOMENTUM PURO (sin look-ahead)")

    rows: list[dict] = []

    for tf in ["4h", "1d"]:
        df = resample_tf(df_1m, tf)
        annual = ANNUAL_FACTOR_MAP[tf]
        ret = bar_returns(df)
        bh_cum = cumulative_return(ret.dropna())
        bh_sharpe = annualized_sharpe(ret.dropna(), annual)

        for name, spec in MOMENTUM_BUILDERS.items():
            try:
                sig = spec["fn"](df, **spec["kwargs"])
            except Exception as e:
                print(f"  ERROR {name}@{tf}: {e}")
                continue

            strat_r = next_bar_return(sig, ret).dropna()
            cum_r = cumulative_return(strat_r)
            sharpe = annualized_sharpe(strat_r, annual)
            sortino = annualized_sortino(strat_r, annual)
            eq = compute_equity(strat_r)
            dd = max_drawdown(eq)
            pct_in = pct_time_in_market(sig)

            rows.append({
                "indicator": name,
                "tf": tf,
                "cum_ret%": f"{cum_r*100:.1f}",
                "bh_ret%": f"{bh_cum*100:.1f}",
                "sharpe": f"{sharpe:.2f}",
                "sortino": f"{sortino:.2f}",
                "max_dd%": f"{dd*100:.1f}",
                "pct_in%": f"{pct_in*100:.1f}",
            })

    cols = ["indicator", "tf", "cum_ret%", "bh_ret%", "sharpe", "sortino", "max_dd%", "pct_in%"]
    print_table(rows, cols)


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 5: Multi-timeframe filter
# ═══════════════════════════════════════════════════════════════════════════════

def section5_mtf(df_1m: pd.DataFrame) -> None:
    print_section("SECTION 5: MULTI-TIMEFRAME FILTER (SSL 4h + EMA200 1d)")

    df_4h = resample_tf(df_1m, "4h")
    df_1d = resample_tf(df_1m, "1d")
    annual = ANNUAL_FACTOR_MAP["4h"]

    ret_4h = bar_returns(df_4h)

    # SSL signal en 4h
    ssl_sig_4h = build_ssl_signal(df_4h)

    # EMA200 en 1d -> reindexar a 4h con forward fill
    ema200_1d = talib.EMA(df_1d["close"].values, timeperiod=200)
    ema200_1d_s = pd.Series(ema200_1d, index=df_1d.index, name="ema200_1d")
    ema200_4h = ema200_1d_s.reindex(df_4h.index, method="ffill")
    filter_1d = df_4h["close"] > ema200_4h

    # Combo: SSL 4h AND EMA200 1d
    combo_sig = (ssl_sig_4h & filter_1d).fillna(False)

    configs: dict[str, pd.Series] = {
        "SSL 4h (solo)": ssl_sig_4h,
        "EMA200 1d filter (solo)": filter_1d.fillna(False).astype(bool),
        "SSL 4h AND EMA200 1d": combo_sig,
        "Buy & Hold": pd.Series(True, index=df_4h.index),
    }

    bh_r = ret_4h.dropna()
    bh_cum = cumulative_return(bh_r)
    bh_sharpe = annualized_sharpe(bh_r, annual)

    rows: list[dict] = []

    for cfg_name, sig in configs.items():
        if cfg_name == "Buy & Hold":
            strat_r = ret_4h.dropna()
        else:
            strat_r = next_bar_return(sig, ret_4h).dropna()

        cum_r = cumulative_return(strat_r)
        sharpe = annualized_sharpe(strat_r, annual)
        sortino = annualized_sortino(strat_r, annual)
        eq = compute_equity(strat_r)
        dd = max_drawdown(eq)
        pct_in = float(sig.fillna(False).mean()) if cfg_name != "Buy & Hold" else 1.0

        rows.append({
            "config": cfg_name,
            "cum_ret%": f"{cum_r*100:.1f}",
            "sharpe": f"{sharpe:.2f}",
            "sortino": f"{sortino:.2f}",
            "max_dd%": f"{dd*100:.1f}",
            "pct_in%": f"{pct_in*100:.1f}",
        })

    cols = ["config", "cum_ret%", "sharpe", "sortino", "max_dd%", "pct_in%"]
    print_table(rows, cols)
    print("\n  Mejora MTF = SSL+EMA200 sharpe > SSL solo?")


# ═══════════════════════════════════════════════════════════════════════════════
# SECTION 6: Regimen de mercado
# ═══════════════════════════════════════════════════════════════════════════════

def classify_regime(df_1d: pd.DataFrame, window_bars: int = 126) -> pd.Series:
    """
    Bull:  precio sube > 50% en 6m
    Bear:  precio cae < -30% en 6m
    Sideways: resto
    """
    fwd_ret = df_1d["close"].pct_change(window_bars).shift(-window_bars)
    regime = pd.Series("sideways", index=df_1d.index)
    regime[fwd_ret > 0.50] = "bull"
    regime[fwd_ret < -0.30] = "bear"
    return regime


def section6_regime(df_1m: pd.DataFrame) -> None:
    print_section("SECTION 6: ANALISIS POR REGIMEN DE MERCADO (SSL Channel 4h)")

    df_4h = resample_tf(df_1m, "4h")
    df_1d = resample_tf(df_1m, "1d")
    annual = ANNUAL_FACTOR_MAP["4h"]

    ret_4h = bar_returns(df_4h)
    ssl_sig = build_ssl_signal(df_4h)
    strat_r_full = next_bar_return(ssl_sig, ret_4h)

    # Regime en 1d -> reindexar a 4h
    regime_1d = classify_regime(df_1d)
    regime_4h = regime_1d.reindex(df_4h.index, method="ffill").fillna("sideways")

    rows: list[dict] = []

    for regime_name in ["bull", "bear", "sideways", "all"]:
        if regime_name == "all":
            mask = pd.Series(True, index=df_4h.index)
        else:
            mask = regime_4h == regime_name

        r_bh = ret_4h[mask].dropna()
        r_ssl = strat_r_full[mask].dropna()

        if len(r_bh) < 20:
            continue

        bh_cum = cumulative_return(r_bh)
        ssl_cum = cumulative_return(r_ssl)
        bh_sharpe = annualized_sharpe(r_bh, annual)
        ssl_sharpe = annualized_sharpe(r_ssl, annual)

        eq_bh = compute_equity(r_bh)
        eq_ssl = compute_equity(r_ssl)
        bh_dd = max_drawdown(eq_bh)
        ssl_dd = max_drawdown(eq_ssl)

        n_bars = int(mask.sum())

        rows.append({
            "regime": regime_name,
            "n_bars_4h": str(n_bars),
            "BH_cum%": f"{bh_cum*100:.1f}",
            "SSL_cum%": f"{ssl_cum*100:.1f}",
            "BH_sharpe": f"{bh_sharpe:.2f}",
            "SSL_sharpe": f"{ssl_sharpe:.2f}",
            "BH_dd%": f"{bh_dd*100:.1f}",
            "SSL_dd%": f"{ssl_dd*100:.1f}",
            "SSL>BH?": "SI" if ssl_cum > bh_cum else "NO",
        })

    cols = ["regime", "n_bars_4h", "BH_cum%", "SSL_cum%",
            "BH_sharpe", "SSL_sharpe", "BH_dd%", "SSL_dd%", "SSL>BH?"]
    print_table(rows, cols)

    print("\n  Regimes clasificados por retorno 6m forward de precio BTC:")
    print("    bull     = precio sube >50% en los proximos 6 meses")
    print("    bear     = precio cae >30% en los proximos 6 meses")
    print("    sideways = resto (±10% o mayor sin extremos)")


# ═══════════════════════════════════════════════════════════════════════════════
# CONCLUSIONES
# ═══════════════════════════════════════════════════════════════════════════════

def section_conclusiones(df_1m: pd.DataFrame) -> None:
    print_section("CONCLUSIONES")

    print("""
  Para esta seccion, los resultados anteriores se interpretan bajo los
  siguientes criterios:

  1. EDGE REAL (sin bias) > B&H
     Un indicador tiene edge real si:
     - cumulative return (sin look-ahead) > BH en el mismo periodo
     - Sharpe > BH Sharpe
     - Consistente en mas de 1 timeframe

  2. FILTRO DE RIESGO (reduce DD)
     Un indicador funciona como filtro de riesgo si:
     - max_dd_in% < global_dd%
     - avg_ret_in > avg_ret_out (discrimina los buenos periodos)
     - pct_time_in% < 100% (no esta siempre en mercado)

  3. APPROACHES ALTERNATIVOS
     - Donchian breakout y MA crossover son trend-following que en BTC
       historicamente funcionaron mejor que reversions (RSI, BBands)
     - Multi-TF filter: combinar señal intraday con filtro de tendencia mayor
       reduce DD aunque no genere alpha puro
     - Regime-awareness: estrategias que funcionan en bull no funcionan en bear
       => regime detection como prerrequisito para deployment

  4. LIMITACIONES DEL ANALISIS
     - Todos los returns son log-returns, sin costos de transaccion ni slippage
     - Sin position sizing (full-in/full-out binario)
     - Sin short selling (solo longs evaluados)
     - Hold-bars introduce autocorrelacion en la señal

  RECOMENDACION DE SIGUIENTE PASO:
  ─────────────────────────────────
  (a) Si algun indicador muestra Sharpe > BH: profundizar con walk-forward
      para validar que el edge es real y no data-mined.

  (b) Si ningun indicador bate BH pero varios reducen DD:
      => Usar como FILTRO en lugar de señal de entrada.
      Strategy: Buy & Hold con exposure management via SSL o Firestorm level.
      => Ramp up/ramp down position size segun filtro, no entrada/salida binaria.

  (c) Donchian o MA crossover como base de trend-following puro:
      Estos indicadores tienen menor sobreajuste por ser conceptualmente simples.
      Probar en walk-forward con ventanas out-of-sample antes de escalar.

  (d) Implementar regime classifier: entrenar XGBoost/random forest con features
      de volatilidad, momentum y correlacion para predecir regime en t+1.
      Solo operar cuando el modelo clasifica "bull" con >60% probabilidad.
    """)


# ═══════════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print(f"\n{'='*72}")
    print("  SUITETRADING — Signal Edge Analysis (next-bar, no look-ahead)")
    print(f"  Fecha: 2026-03-14 | Simbolo: {SYMBOL} | Exchange: {EXCHANGE}")
    print(f"{'='*72}")

    print("\n[1/7] Cargando datos 1m de BTC desde ParquetStore...")
    df_1m = load_1m()
    print(f"       Datos cargados: {len(df_1m):,} filas | {df_1m.index[0].date()} → {df_1m.index[-1].date()}")

    print("[2/7] Ejecutando Section 1: Correct Signal Edge...")
    section1_correct_edge(df_1m)

    print("\n[3/7] Ejecutando Section 2: Signal como filtro de exposicion...")
    section2_exposure_filter(df_1m)

    print("\n[4/7] Ejecutando Section 3: Combinaciones de indicadores...")
    section3_combinations(df_1m)

    print("\n[5/7] Ejecutando Section 4: Momentum puro...")
    section4_momentum(df_1m)

    print("\n[6/7] Ejecutando Section 5: Multi-timeframe filter...")
    section5_mtf(df_1m)

    print("\n[7/7] Ejecutando Section 6: Analisis por regimen de mercado...")
    section6_regime(df_1m)

    section_conclusiones(df_1m)

    print(f"\n{SEP}")
    print("  Analisis completado.")
    print(SEP)


if __name__ == "__main__":
    main()
