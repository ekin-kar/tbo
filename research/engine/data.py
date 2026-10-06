"""
Data layer: loads 1m bars (bid prices, UTC) and builds higher-timeframe candles.

Time is stored as int64 "minutes since 1970-01-01 UTC" everywhere inside the engine.
"""
import json
import lzma
from pathlib import Path

import numpy as np
import pandas as pd

import os
_ROOT = Path(__file__).resolve().parent.parent
if not (_ROOT / "data").exists() and (_ROOT.parent / "data").exists():
    _ROOT = _ROOT.parent   # repo layout: <repo>/data next to <repo>/research
# Data files (*.m1pack, *_SPREAD.csv) live in <repo>/data unless TRADING_DATA points elsewhere;
# intermediate files are cached in <repo>/cache (or TRADING_CACHE).
UPLOADS = Path(os.environ.get("TRADING_DATA", _ROOT / "data"))
CACHE = Path(os.environ.get("TRADING_CACHE", _ROOT / "cache"))
CACHE.mkdir(parents=True, exist_ok=True)

FILES = {
    "XAUUSD": "XAUUSD_M1_bt.m1pack",
    "EURUSD": "EURUSD_M1.m1pack",
    "GBPUSD": "GBPUSD_M1.m1pack",
    "USDJPY": "USDJPY_M1.m1pack",
    "EURJPY": "EURJPY_M1.m1pack",
    "NAS100": "Nasdaq100_M1.m1pack",
    "SP500": "S_P500_M1.m1pack",
    "XAGUSD": "XAGUSD_M1.m1pack",
}

# Spread scenarios in PRICE units (bars are bid; ask = bid + spread).
#   low  = best-case quiet spread, typ = assumed normal, high = stress test.
# Commission: $15 per $1M notional per side (from the user's XAUUSD deal) = 15e-6 of price per unit.
SPECS = {
    # MEASURED from cTrader tick data, Jan-Mar 2025 (validation runs): gold median $0.27, EURUSD 1.0 pip.
    "XAUUSD": dict(digits=2, spread=dict(low=0.20, typ=0.27, high=0.40)),
    "EURUSD": dict(digits=5, spread=dict(low=0.00007, typ=0.00010, high=0.00015)),
    # PLACEHOLDERS (pessimistic guesses) until the spread logger measures them:
    "GBPUSD": dict(digits=5, spread=dict(low=0.00008, typ=0.00013, high=0.00020)),
    "USDJPY": dict(digits=3, spread=dict(low=0.008, typ=0.012, high=0.020)),
    "EURJPY": dict(digits=3, spread=dict(low=0.012, typ=0.018, high=0.030)),
    "NAS100": dict(digits=2, spread=dict(low=0.8, typ=1.5, high=3.0)),
    "SP500": dict(digits=2, spread=dict(low=0.3, typ=0.5, high=1.0)),
    "XAGUSD": dict(digits=3, spread=dict(low=0.02, typ=0.03, high=0.05)),
}
COMMISSION_PER_SIDE = 15e-6

HOLDOUT_START = "2026-01-01"   # sealed final exam: nothing tuned on data from here on


def _unpack(data: bytes) -> pd.DataFrame:
    magic = b"M1PACK1\n"
    assert data.startswith(magic)
    rest = data[len(magic):]
    nl = rest.index(b"\n")
    h = json.loads(rest[:nl])
    arr = np.frombuffer(lzma.decompress(rest[nl + 1:]), dtype=np.int32).reshape(6, h["rows"]).astype(np.int64)
    arr[0, 0] = 0
    arr[1, 0] = 0
    t = h["t0"] + np.cumsum(arr[0])
    o = h["o0"] + np.cumsum(arr[1])
    s = 10 ** h["digits"]
    return pd.DataFrame({"t": t, "o": o / s, "h": (o + arr[2]) / s, "l": (o + arr[3]) / s,
                         "c": (o + arr[4]) / s, "v": arr[5]})


def load_m1(sym: str) -> dict:
    """1m bid bars as numpy arrays: t (int minutes UTC), o, h, l, c, v."""
    CACHE.mkdir(parents=True, exist_ok=True)
    cache = CACHE / f"{sym}.npz"
    if cache.exists():
        z = np.load(cache)
        return {k: z[k] for k in z.files}
    df = _unpack((UPLOADS / FILES[sym]).read_bytes())
    d = {k: df[k].to_numpy() for k in ["t", "o", "h", "l", "c", "v"]}
    np.savez(cache, **d)
    return d


def resample(m1: dict, tf: int) -> dict:
    """
    Build tf-minute candles from 1m bars, aligned to UTC like cTrader (verified for 5m).
    'act' = index of the first 1m bar at/after the candle's close time: the earliest
    moment a decision based on this closed candle can be acted on.
    """
    t = m1["t"]
    b = t - (t % tf)
    starts = np.flatnonzero(np.r_[True, b[1:] != b[:-1]])
    ends = np.r_[starts[1:], len(t)] - 1
    out = {
        "t": b[starts],
        "o": m1["o"][starts],
        "h": np.maximum.reduceat(m1["h"], starts),
        "l": np.minimum.reduceat(m1["l"], starts),
        "c": m1["c"][ends],
        "v": np.add.reduceat(m1["v"], starts),
    }
    out["act"] = np.searchsorted(t, out["t"] + tf, side="left")
    out["tf"] = tf
    return out


SPREAD_FILES = {"EURUSD": "EURUSD_SPREAD.csv", "XAUUSD": "XAUUSD_SPREAD.csv",
                "USDJPY": "USDJPY_SPREAD.csv", "GBPUSD": "GBPUSD_SPREAD.csv",
                "EURJPY": "EURJPY_SPREAD.csv", "NAS100": "NAS100_SPREAD.csv",
                "SP500": "SP500_SPREAD.csv", "XAGUSD": "XAGUSD_SPREAD.csv"}


def load_spread(sym, m1, column="AvgSpread"):
    """
    Real measured spread per minute, aligned to the 1m bars.
    Minutes with no measurement (before tick data starts, or gaps) fall back to the
    median spread for that hour of day, so nothing is ever charged zero cost.
    """
    import pandas as pd
    path = UPLOADS / SPREAD_FILES[sym]
    if not path.exists():
        return None
    df = pd.read_csv(path)
    t = pd.to_datetime(df["Time"]).to_numpy().astype("datetime64[m]").astype(np.int64)
    tick = 10.0 ** (-SPECS[sym]["digits"])
    sp = df[column].to_numpy(dtype=float) * tick
    out = np.full(len(m1["t"]), np.nan)
    idx = np.searchsorted(t, m1["t"])
    ok = (idx < len(t)) & (t[np.clip(idx, 0, len(t) - 1)] == m1["t"])
    out[ok] = sp[idx[ok]]
    hour = (m1["t"] % 1440) // 60
    for h in range(24):
        m = hour == h
        med = np.nanmedian(out[m])
        if np.isnan(med):
            med = np.nanmedian(out)
        out[m & np.isnan(out)] = med
    return out


def to_datetime(t_minutes) -> pd.DatetimeIndex:
    return pd.to_datetime(np.asarray(t_minutes, dtype=np.int64) * 60, unit="s")


def minute_of_day(t):
    return np.asarray(t) % 1440


def day_index(t):
    return np.asarray(t) // 1440


def weekday(t):
    # 1970-01-01 was a Thursday -> Monday=0
    return (np.asarray(t) // 1440 + 3) % 7


def minutes(ts: str) -> int:
    return int(pd.Timestamp(ts).value // 60_000_000_000)
