#!/usr/bin/env python3
"""Diagnostic: measure signal density per indicator and combined."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from suitetrading.data.storage import ParquetStore
from suitetrading.data.resampler import OHLCVResampler
from suitetrading.indicators.registry import get_indicator


def main() -> None:
    store = ParquetStore(base_dir=ROOT / "data" / "raw")
    resampler = OHLCVResampler()

    df_1m = store.read("binance", "BTCUSDT", "1m")
    cutoff = df_1m.index.max() - pd.DateOffset(months=6)
    df_1m = df_1m.loc[df_1m.index >= cutoff]
    df_1h = resampler.resample(df_1m, "1h", base_tf="1m")
    n = len(df_1h)

    print(f"=== BTCUSDT 1h, 6 months ({n} bars) ===\n")

    ssl = get_indicator("ssl_channel")
    fire = get_indicator("firestorm")
    fire_tm = get_indicator("firestorm_tm")

    # --- Individual signals ---
    print("--- SSL Channel (cross + hold_bars) ---")
    for length in [12, 50, 104]:
        for hb in [1, 4, 12, 20]:
            sig = ssl.compute(df_1h, length=length, hold_bars=hb)
            print(f"  SSL(len={length:3d}, hb={hb:2d}): {sig.sum():4d}/{n} True ({sig.sum()/n*100:.1f}%)")

    print("\n--- Firestorm (trend reversal + hold_bars) ---")
    for period in [6, 10, 50]:
        for mult in [1.5, 6.0, 9.5]:
            for hb in [1, 4]:
                sig = fire.compute(df_1h, period=period, multiplier=mult, hold_bars=hb)
                print(f"  Fire(per={period:2d}, mult={mult:.1f}, hb={hb}): {sig.sum():4d}/{n} True ({sig.sum()/n*100:.1f}%)")

    print("\n--- FirestormTM (returns band values, not boolean) ---")
    for period in [8, 20]:
        for mult in [1.8, 9.5]:
            sig = fire_tm.compute(df_1h, period=period, multiplier=mult)
            is_bool = sig.dtype == bool
            n_true = sig.astype(bool).sum()
            print(f"  FireTM(per={period:2d}, mult={mult:.1f}): dtype={sig.dtype}, range=[{sig.min():.1f}, {sig.max():.1f}], as_bool={n_true}/{n}")

    # --- Combined AND (the actual discovery config) ---
    print("\n--- Combined AND (3 excluyente) ---")
    # Use params similar to trial 3 from the smoke test
    params_sets = [
        {"ssl_len": 104, "ssl_hb": 12, "fire_per": 6, "fire_mult": 6.11, "fire_hb": 4, "ftm_per": 8, "ftm_mult": 9.49},
        {"ssl_len": 12, "ssl_hb": 4, "fire_per": 10, "fire_mult": 1.8, "fire_hb": 1, "ftm_per": 9, "ftm_mult": 1.8},
        {"ssl_len": 50, "ssl_hb": 4, "fire_per": 10, "fire_mult": 3.0, "fire_hb": 4, "ftm_per": 20, "ftm_mult": 3.0},
    ]

    for ps in params_sets:
        sig_ssl = ssl.compute(df_1h, length=ps["ssl_len"], hold_bars=ps["ssl_hb"])
        sig_fire = fire.compute(df_1h, period=ps["fire_per"], multiplier=ps["fire_mult"], hold_bars=ps["fire_hb"])
        sig_ftm = fire_tm.compute(df_1h, period=ps["ftm_per"], multiplier=ps["ftm_mult"])

        # FirestormTM is NOT boolean — it returns price band values!
        ftm_as_bool = sig_ftm.astype(bool)

        combined = sig_ssl & sig_fire & ftm_as_bool
        print(f"\n  Params: {ps}")
        print(f"    SSL:     {sig_ssl.sum():4d} True bars")
        print(f"    Fire:    {sig_fire.sum():4d} True bars")
        print(f"    FireTM:  {ftm_as_bool.sum():4d} True bars (from float→bool, dtype={sig_ftm.dtype})")
        print(f"    AND:     {combined.sum():4d} True bars = potential entries")

    # --- What if we only AND ssl+fire (2 indicators)? ---
    print("\n--- SSL + Fire only (2 excluyente, no FireTM) ---")
    sig_ssl = ssl.compute(df_1h, length=12, hold_bars=4)
    sig_fire = fire.compute(df_1h, period=10, multiplier=1.8, hold_bars=4)
    combined_2 = sig_ssl & sig_fire
    print(f"  SSL(12,4):  {sig_ssl.sum():4d} True")
    print(f"  Fire(10,1.8,4): {sig_fire.sum():4d} True")
    print(f"  AND: {combined_2.sum():4d} True")

    # -- Rising edge (new entries only) --
    entries_2 = combined_2 & ~combined_2.shift(1, fill_value=False)
    print(f"  Rising edges (actual new entries): {entries_2.sum()}")


if __name__ == "__main__":
    main()
