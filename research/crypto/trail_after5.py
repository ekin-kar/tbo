"""Trail only AFTER day 5: losing/flat trades still close at day 5; trades in profit continue with a trailing stop."""
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
from wf2 import V21
from hold_weekend import W, met

VARS = [("v2.2: close everything at day 5", {})]
for ext, k, minR in [(240, 2.0, 0.0), (240, 3.0, 0.0), (240, 4.0, 0.0), (360, 3.0, 0.0), (360, 4.0, 0.0), (240, 3.0, 2.0), (360, 4.0, 3.0)]:
    VARS.append((f"day5+: in profit > {minR:g}R -> trail {k:g}R, max {ext // 24}d",
                 dict(ext_h=ext, ext_R=minR, trail_k=k, trail_start=0.0, trail_after_h=120)))
DATA = {}


def job(a):
    sym, i = a
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    if sym not in DATA:
        DATA[sym] = C.load(sym)
    x = C.between(F.channel_breakout(DATA[sym], **dict(V21, **VARS[i][1])), "2020-03-01", "2026-10-01")
    return sym, i, x.assign(u=x.R * W[sym] * np.where(x.dir < 0, 0.5, 1.0))[["entry_time", "exit_time", "u", "hours"]]


if __name__ == "__main__":
    with Pool(4) as p:
        res = p.map(job, [(s, i) for s in W for i in range(len(VARS))], chunksize=len(VARS))
    print(f"{'':46s} | {'2020-23: ret/DD  R/yr   DD':>28s} | {'2024-26: ret/DD  R/yr   DD':>28s} | avg hold")
    for i, (lab, _) in enumerate(VARS):
        x = pd.concat([r for s, j, r in res if j == i])
        a = met(x, "2020-03-01", "2024-01-01"); b = met(x, "2024-01-01", "2026-10-01")
        print(f"{lab:46s} | {a[0]:12.2f} {a[1]:6.0f} {a[2]:5.1f} | {b[0]:12.2f} {b[1]:6.0f} {b[2]:5.1f} | {x.hours.mean()/24:.1f} d")
