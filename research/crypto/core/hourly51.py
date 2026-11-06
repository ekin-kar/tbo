"""Hourly bars for all 51 study coins (DEV12 + HOLD39) in one format, for the v2.9 sleeve studies (U4, S1-S4).

Columns (index = hour open, UTC): o h l c (futures 1h klines, data/extra2/<SYM>_1h.csv.gz from fetch_extend.py), v (quote
volume), oi (open interest value, last 5-minute sample of the hour, as panic_sleeve.hourly), prem (premium index 1h close),
fund (last funding rate known at the hour), spot_v4 (spot quote volume of the 4h candle that CLOSED last, NaN if none),
perp_v4 (the same for the perpetual). From 2021-11 (OI history starts Dec 2021). Cached in cache/h51/<SYM>.pkl."""
from pathlib import Path
import numpy as np, pandas as pd
import common as C

EX, EX2 = C.ROOT / "data" / "extra", C.ROOT / "data" / "extra2"
OUR5 = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
DEV12 = OUR5 + ["XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "DOTUSDT", "LTCUSDT", "TRXUSDT"]
HOLD_BIG = ["BCHUSDT", "XLMUSDT", "SUIUSDT", "HBARUSDT", "1000SHIBUSDT", "1000PEPEUSDT", "NEARUSDT", "UNIUSDT", "ETCUSDT",
            "APTUSDT", "AAVEUSDT", "ATOMUSDT", "FILUSDT", "ICPUSDT"]
HOLD_SMALL = ["ALGOUSDT", "ARBUSDT", "AXSUSDT", "CRVUSDT", "ENAUSDT", "EOSUSDT", "FETUSDT", "GRTUSDT", "IMXUSDT", "INJUSDT",
              "LDOUSDT", "MANAUSDT", "OPUSDT", "ORDIUSDT", "RUNEUSDT", "SANDUSDT", "SEIUSDT", "STXUSDT", "THETAUSDT", "TIAUSDT",
              "VETUSDT", "WIFUSDT", "WLDUSDT", "XTZUSDT", "ZECUSDT"]
HOLD39 = HOLD_BIG + HOLD_SMALL
ALL51 = DEV12 + HOLD39
CACHE = C.D.CACHE / "h51"
_H = {}


def _f(sym, name):
    a = EX / f"{sym}_{name}.csv.gz"
    return a if a.exists() else EX2 / f"{sym}_{name}.csv.gz"


def hourly(sym):
    if sym in _H:
        return _H[sym]
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / f"{sym}.pkl"
    if f.exists():
        _H[sym] = pd.read_pickle(f); return _H[sym]
    k = pd.read_csv(EX2 / f"{sym}_1h.csv.gz")
    df = pd.DataFrame({"o": k.o.values, "h": k.h.values, "l": k.l.values, "c": k.c.values, "v": k.quote_volume.values},
                      index=pd.to_datetime(k.open_ms, unit="ms"))
    df = df[~df.index.duplicated()].sort_index()
    df = df.reindex(pd.date_range(df.index[0], df.index[-1], freq="1h"))
    gap = df.c.isna()
    df[["o", "h", "l", "c"]] = df[["o", "h", "l", "c"]].ffill()          # (missing hours: flat bar at the last close)
    for col in ("o", "h", "l"):
        df.loc[gap, col] = df.loc[gap, "c"]
    df["v"] = df.v.fillna(0.0)
    oi = pd.read_csv(_f(sym, "metrics_1h"), usecols=["create_time", "sum_open_interest_value"], parse_dates=["create_time"])
    oi = oi[oi.sum_open_interest_value > 0]
    df["oi"] = oi.set_index(oi.create_time.dt.floor("1h")).sum_open_interest_value.groupby(level=0).last().reindex(df.index)
    pr = pd.read_csv(_f(sym, "premium_1h")); pr.index = pd.to_datetime(pr.open_ms, unit="ms")
    df["prem"] = pr.c.groupby(level=0).last().reindex(df.index)
    fu = pd.read_csv(_f(sym, "funding")); fu.index = pd.DatetimeIndex(pd.to_datetime(fu.time_ms.values, unit="ms")).floor("1h")
    df["fund"] = fu.rate.groupby(level=0).last().reindex(df.index).ffill()
    df["perp_v4"] = df.v.resample("4h").sum().shift(1).reindex(df.index, method="ffill")       # last CLOSED 4h candle
    sp = _f(sym, "spot_4h")
    if sp.exists():
        s = pd.read_csv(sp); s.index = pd.to_datetime(s.open_ms, unit="ms")
        s4 = s.quote_volume.groupby(level=0).last()
        df["spot_v4"] = s4.shift(1, freq="4h").reindex(df.index, method="ffill", tolerance=pd.Timedelta("4h"))
    else:
        df["spot_v4"] = np.nan
    df = df[df.index >= "2021-11-01"]
    df.to_pickle(f)
    _H[sym] = df
    return df
