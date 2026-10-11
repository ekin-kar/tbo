"""Stage B: filters on top of the best structures from grid_v25 (plus the live one).
Filters (all at the order candle, side-adjusted): open interest (lookback x threshold, or off), RSI(14) zone, ADX(14)
strength, volume vs its 20-candle average, distance from the daily EMA (max_ext), daily EMA length / slope days.
Usage: python grid_v25b.py "<tf,n,stop_index,be_R,hold_h>;..."   (structures to test)"""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import itertools, sys, time
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import grid_v25 as G

I = C.I
OUT = C.D.CACHE / "grid_v25b.csv"


def adx(h, l, c, n=14):
    up = np.r_[0, np.diff(h)]; dn = np.r_[0, -np.diff(l)]
    pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
    w = lambda x: pd.Series(x).ewm(alpha=1 / n, adjust=False).mean().to_numpy()
    atr = w(I.true_range(h, l, c)); pdi = 100 * w(pdm) / atr; ndi = 100 * w(ndm) / atr
    return w(100 * np.abs(pdi - ndi) / np.maximum(pdi + ndi, 1e-12))


def make_skip(sym, tf, f):
    oi_h, oi_t = f["oi"]
    def skip(c, a, hi, lo, s):
        out = np.zeros(len(a), bool)
        if oi_h:
            out |= G.oi_skip(sym, tf, oi_h, oi_t)(c, a, hi, lo, s)
        if f["rsi"]:
            r = I.rsi_wilder(c["c"], 14); rs = r if s > 0 else 100 - r
            lo_, hi_ = f["rsi"]
            out |= (rs < lo_) | (rs > hi_)
        if f["adx"]:
            out |= adx(c["h"], c["l"], c["c"]) < f["adx"]
        if f["vol"]:
            v20 = pd.Series(c["v"]).rolling(20).mean().to_numpy()
            out |= c["v"] < f["vol"] * v20
        return out
    return skip


FILTERS = []
for oi_ in ((0, 0), (24, -0.02), (72, -0.01), (72, -0.03), (72, -0.06), (168, -0.03), (168, -0.08)):
    FILTERS.append(dict(oi=oi_, rsi=None, adx=0, vol=0, ext=4.0, ema=50, slope=5))
for rsi in ((50, 100), (55, 100), (0, 75), (0, 80), (50, 80)):
    FILTERS.append(dict(oi=(72, -0.03), rsi=rsi, adx=0, vol=0, ext=4.0, ema=50, slope=5))
for a_ in (15, 20, 25, 30):
    FILTERS.append(dict(oi=(72, -0.03), rsi=None, adx=a_, vol=0, ext=4.0, ema=50, slope=5))
for v in (0.8, 1.0, 1.3):
    FILTERS.append(dict(oi=(72, -0.03), rsi=None, adx=0, vol=v, ext=4.0, ema=50, slope=5))
for ext in (2.5, 3.0, 5.0, 99.0):
    FILTERS.append(dict(oi=(72, -0.03), rsi=None, adx=0, vol=0, ext=ext, ema=50, slope=5))
for ema, slope in ((20, 3), (30, 5), (100, 5), (200, 5), (50, 0), (50, 3), (50, 10)):
    FILTERS.append(dict(oi=(72, -0.03), rsi=None, adx=0, vol=0, ext=4.0, ema=ema, slope=slope))


def job(args):
    si, fi, cfg = args
    f = FILTERS[fi]
    X = pd.concat([G.trades(s, cfg, dict(skip_fn=make_skip(s, cfg["tf"], f), max_ext=f["ext"], ema_n=f["ema"], slope_d=f["slope"]))
                   for s in G.COINS])
    return dict(struct=si, filt=fi, **cfg, oi=str(f["oi"]), rsi=str(f["rsi"]), adx=f["adx"], vol=f["vol"], ext=f["ext"],
                ema=f["ema"], slope=f["slope"], **G.score(X))


if __name__ == "__main__":
    structs = [dict(zip(("tf", "n", "stop", "be_R", "hold_h"), (int(v[0]), int(v[1]), int(v[2]), float(v[3]), int(v[4]))))
               for v in (s.split(",") for s in sys.argv[1].split(";"))]
    jobs = [(si, fi, cfg) for si, cfg in enumerate(structs) for fi in range(len(FILTERS))]
    print(f"{len(structs)} structures x {len(FILTERS)} filters = {len(jobs)} runs", flush=True)
    rows = []
    with Pool(4) as p:
        for k, r in enumerate(p.imap_unordered(job, jobs, chunksize=2)):
            rows.append(r)
            if k % 50 == 0:
                print(f"{k}/{len(jobs)}", flush=True)
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print("finished", flush=True)
