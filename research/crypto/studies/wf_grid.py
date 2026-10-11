"""Stage 1 of the walk-forward study: run every config of the grid over the full history (causal), save trades."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import itertools, sys, pickle
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F

SYM = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
GRID = dict(tf=[240, 120], n=[20, 30, 40], sl_atr=[1.0, 1.5, 2.5], hold_h=[72, 120], ema_n=[50, 100],
            sides=["long", "both"], trail=[(0, 0.0), (12, 2.0), (6, 2.0)], slope_d=[0, 5], no_weekend=[False, True],
            be_R=[0.0, 1.5])
M = None


def init():
    global M
    M = C.load(SYM)


def one(args):
    i, kw = args
    kw = dict(kw); tm, ta = kw.pop("trail")
    tr = F.channel_breakout(M, trail_m=tm, trail_atr=ta, **kw)
    tr = tr[tr.entry_time >= "2020-03-01"]
    return i, tr[["entry_time", "exit_time", "dir", "R"]].reset_index(drop=True)


if __name__ == "__main__":
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    print(len(combos), flush=True)
    out = {}
    with Pool(4, initializer=init) as p:
        for k, (i, tr) in enumerate(p.imap_unordered(one, list(enumerate(combos)), chunksize=8)):
            out[i] = tr
            if k % 500 == 0:
                print(k, flush=True)
    with open(C.D.CACHE / f"wf_{SYM}.pkl", "wb") as f:
        pickle.dump(dict(combos=combos, trades=out), f)
    print("saved")
