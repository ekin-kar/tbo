"""The chosen 'quality' setting vs v2.2 on the 8 coins never used for any choice."""
import pickle
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
from wf2 import V21

OTHER = ["SOLUSDT", "BNBUSDT", "XRPUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT", "TRXUSDT", "DOTUSDT"]
best = pickle.load(open(C.D.CACHE / "quality_choice.pkl", "rb"))["best"]


def job(args):
    sym, lab, kw = args
    C.SLIP = 0.0003
    x = C.between(F.channel_breakout(C.load(sym), **dict(V21, **kw)), "2020-03-01", "2026-10-01")
    x = x.assign(Rs=x.R * np.where(x.dir < 0, 0.5, 1.0))
    return sym, lab, x[["entry_time", "exit_time", "Rs"]]


def met(x):
    x = x.sort_values("exit_time"); r = x.Rs.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    yrs = (x.entry_time.max() - x.entry_time.min()).days / 365.25
    return r.sum() / yrs / max(dd, 3), r.sum() / yrs, dd, len(r) / yrs / 12


if __name__ == "__main__":
    with Pool(4) as p:
        res = p.map(job, [(s, lab, kw) for s in OTHER for lab, kw in (("v2.2", {}), ("chosen", best))])
    R = {(s, l): x for s, l, x in res}
    print("8 other coins (never used to choose), shorts at half size, 2020-26:")
    better = 0
    for s in OTHER:
        a = met(R[(s, "v2.2")]); b = met(R[(s, "chosen")]); better += b[0] > a[0]
        print(f"   {s[:-4]:5s} v2.2 ret/DD {a[0]:5.2f} ({a[1]:4.0f}R/yr, {a[3]:.1f} tr/mo)   chosen {b[0]:5.2f} ({b[1]:4.0f}R/yr, {b[3]:.1f} tr/mo)")
    for lab in ("v2.2", "chosen"):
        x = pd.concat([R[(s, lab)] for s in OTHER]); m = met(x)
        print(f"   ALL 8 pooled {lab:6s}: ret/DD {m[0]:.2f}  {m[1]:.0f}R/yr  DD {m[2]:.1f}R  {m[3]:.1f} trades/month")
    print(f"   chosen better on {better} of 8 coins")
