"""Weekend entries and holding-time sweep on the weighted 4-coin portfolio (BTC 2x, ETH 1x, DOGE/ADA 0.5x, shorts half)."""
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
from wf2 import V21

W = {"BTCUSDT": 2.0, "ETHUSDT": 1.0, "DOGEUSDT": 0.5, "ADAUSDT": 0.5}
VARS = [("v2.2 (no weekend, 5 days)", {})] + [("weekend entries ON", dict(no_weekend=False))] + \
       [(f"hold {h // 24:g} days", dict(hold_h=h)) for h in (48, 72, 96, 144, 168, 240)]
DATA = {}


def job(a):
    sym, i = a
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    if sym not in DATA:
        DATA[sym] = C.load(sym)
    x = C.between(F.channel_breakout(DATA[sym], **dict(V21, **VARS[i][1])), "2020-03-01", "2026-10-01")
    wd = x.entry_time.dt.dayofweek
    return sym, i, x.assign(u=x.R * W[sym] * np.where(x.dir < 0, 0.5, 1.0), wknd=(wd >= 5))[["entry_time", "exit_time", "u", "hours", "reason", "wknd"]]


def met(x, a, b):
    x = x[(x.entry_time >= a) & (x.entry_time < b)].sort_values("exit_time"); r = x.u.to_numpy()
    eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max(); yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
    mo = x.groupby(x.exit_time.dt.to_period("M")).u.sum()
    return r.sum() / yrs / dd, r.sum() / yrs, dd, (mo > 0).mean(), len(r) / yrs / 12


if __name__ == "__main__":
    with Pool(4) as p:
        res = p.map(job, [(s, i) for s in W for i in range(len(VARS))], chunksize=len(VARS))
    P = {i: pd.concat([x for s, j, x in res if j == i]) for i in range(len(VARS))}
    print(f"{'':28s} | {'2020-23: ret/DD  R/yr   DD  months+':>36s} | {'2024-26: ret/DD  R/yr   DD  months+  trades/mo':>48s}")
    for i, (lab, _) in enumerate(VARS):
        a = met(P[i], "2020-03-01", "2024-01-01"); b = met(P[i], "2024-01-01", "2026-10-01")
        print(f"{lab:28s} | {a[0]:12.2f} {a[1]:5.0f} {a[2]:5.1f} {a[3]*100:6.0f}% | {b[0]:12.2f} {b[1]:5.0f} {b[2]:5.1f} {b[3]*100:6.0f}% {b[4]:8.1f}")
    x = P[1]
    print("\nweekend-ON run, trades entered on Sat/Sun vs weekdays (avg weighted R per trade):",
          {k: round(v, 3) for k, v in x.groupby("wknd").u.mean().items()}, "counts", x.wknd.value_counts().to_dict())
    x = P[0]
    print("\nv2.2: where the profit comes from, by how the trade ended / how long it was held:")
    x = x.assign(bucket=pd.cut(x.hours, [-1, 12, 24, 48, 96, 119.9, 121], labels=["<12h", "12-24h", "1-2d", "2-4d", "4-5d", "5-day exit"]))
    print(x.groupby("bucket", observed=True).agg(trades=("u", "size"), total=("u", "sum"), avg=("u", "mean")).round(2).to_string())
