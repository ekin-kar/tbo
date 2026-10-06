"""Full parameter grid on the 4-coin portfolio (BTC, ETH, DOGE, ADA) as ONE system. Stores compact trade lists."""
import itertools, pickle, sys, time
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
from wf2 import V21

COINS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]
GRID = dict(n=[15, 20, 30, 40], sl_atr=[0.75, 1.0, 1.25, 1.5], be_R=[0.0, 1.0, 1.5, 2.0], hold_h=[72, 120, 168],
            ema_n=[30, 50, 100], slope_d=[0, 5, 10])
DATA = {}


def job(args):
    sym, i, kw = args
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    if sym not in DATA:
        DATA[sym] = C.load(sym)
    x = C.between(F.channel_breakout(DATA[sym], **dict(V21, **kw)), "2020-03-01", "2026-10-01")
    return sym, i, (x.exit_time.values.astype("datetime64[m]").astype(np.int64), x.entry_time.values.astype("datetime64[m]").astype(np.int64),
                    x.R.to_numpy(np.float32), x.dir.to_numpy(np.int8))


if __name__ == "__main__":
    cfgs = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    jobs = [(s, i, c) for s in COINS for i, c in enumerate(cfgs)]           # coin-major: each worker keeps 1-2 coins
    t0 = time.time(); out = {}
    with Pool(4) as p:
        for k, (s, i, tr) in enumerate(p.imap_unordered(job, jobs, chunksize=48)):
            out[(s, i)] = tr
            if k % 500 == 0:
                print(k, "of", len(jobs), round(time.time() - t0), "s", flush=True)
    pickle.dump(dict(cfgs=cfgs, trades=out), open(C.D.CACHE / "portfolio_grid.pkl", "wb"))
    print("saved", len(out), round(time.time() - t0), "s")
