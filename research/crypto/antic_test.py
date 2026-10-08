"""Anticipation (pre-breakout) entries on top of TBO v2.1, and on their own. 4 coins, R units, both periods + walk-forward."""
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
from wf2 import V21, stream, mar, TESTS

COINS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]
A, B = "2020-03-01", "2026-10-01"
VARS = [("v2.1", {})]
VARS += [(f"+early d<={d} {c}", dict(antic_d=d, antic_cond=c)) for d, c in
         itertools.product((0.25, 0.5, 1.0), ("none", "rsi60", "rsi70", "obv_hl", "volb", "rsi60_volb"))]
VARS += [(f"early ONLY d<={d} {c}", dict(antic_d=d, antic_cond=c, antic_only=True)) for d, c in
         itertools.product((0.5, 1.0), ("rsi70", "obv_hl", "volb"))]


DATA = {}


def job(args):
    sym, i = args
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    if sym not in DATA:                                  # load once per worker (the resample cache keys on the array)
        DATA[sym] = C.load(sym)
    x = C.between(F.channel_breakout(DATA[sym], **dict(V21, **VARS[i][1])), A, B)
    return sym, i, x[["entry_time", "exit_time", "dir", "R"]]


def st(x, a, b):
    x = x[(x.entry_time >= a) & (x.entry_time < b)].sort_values("exit_time"); r = x.R.to_numpy()
    eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
    return r.sum() / yrs, dd, r.sum() / yrs / dd, len(r) / yrs / 12


if __name__ == "__main__":
    with Pool(4) as p:
        res = p.map(job, [(s, i) for s in COINS for i in range(len(VARS))], chunksize=len(VARS))
    T = {(s, i): x for s, i, x in res}
    P = {i: pd.concat([T[(s, i)] for s in COINS]) for i in range(len(VARS))}
    print(f"{'4 coins pooled, R units':34s} | {'2020-23: R/yr  DD  ret/DD tr/mo':>32s} | {'2024-26: R/yr  DD  ret/DD tr/mo':>32s} | 2024-26 ret/DD BTC ETH DOGE ADA")
    for i, (lab, _) in enumerate(VARS):
        a = st(P[i], *C.DEV); b = st(P[i], *C.HOLDOUT)
        pc = [st(T[(s, i)], *C.HOLDOUT)[2] for s in COINS]
        print(f"{lab:34s} | {a[0]:7.0f} {a[1]:6.1f} {a[2]:6.2f} {a[3]:5.1f} | {b[0]:7.0f} {b[1]:6.1f} {b[2]:6.2f} {b[3]:5.1f} | " + " ".join(f"{v:5.2f}" for v in pc))
    picks = []; oos = []
    for y in TESTS:
        ty = (pd.Timestamp(f"{y}-01-01") - pd.Timestamp(A)).days / 365.25
        sc = [mar(stream(P[i], A, f"{y}-01-01"), ty) for i in range(len(VARS))]
        bi = int(np.argmax(sc)); picks.append(VARS[bi][0]); oos.append(stream(P[bi], f"{y}-01-01", f"{y+1}-01-01"))
    w = st(pd.concat(oos), "2022-01-01", "2026-10-01"); b0 = st(P[0], "2022-01-01", "2026-10-01")
    print(f"\nwalk-forward picks: {dict(zip(TESTS, picks))}")
    print(f"walk-forward 2022-26 out of sample: {w[0]:.0f}R/yr DD {w[1]:.1f} ret/DD {w[2]:.2f}   vs v2.1: {b0[0]:.0f}R/yr DD {b0[1]:.1f} ret/DD {b0[2]:.2f}")
