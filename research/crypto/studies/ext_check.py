"""Plateau check of the 'max distance from the daily EMA' filter and a volume filter on top of v2 (BTC)."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
from wf2 import V2, summary, stream

def one(kw):
    m = C.load("BTCUSDT")
    tr = F.channel_breakout(m, **kw)
    return kw, tr[tr.entry_time >= "2020-03-01"]

if __name__ == "__main__":
    cfgs = [dict(V2, max_ext=e) for e in (99.0, 6.0, 5.0, 4.5, 4.0, 3.5, 3.0, 2.5)] + \
           [dict(V2, vratio=v) for v in (0.8, 1.0, 1.2, 1.5)]
    with Pool(4) as p:
        res = p.map(one, cfgs)
    for kw, tr in res:
        lab = f"max_ext {kw['max_ext']}" if kw.get("vratio", 0) == 0 else f"volume >= {kw['vratio']}x avg"
        x = stream(tr, "2020-03-01", "2026-10-01")
        summary(x, lab + " (2020-26)", yrs=6.58)
