"""$250 -> $10k-20k in 24 months? Block bootstrap (random 4-week blocks of real v2.4 trades, 5 coins) at several risk levels."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import pickle, sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C

ALL = pickle.load(open(C.D.CACHE / "portfolio_trades_v24.pkl", "rb"))
COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
RISK = {"BTCUSDT": 5.0, "ETHUSDT": 2.5, "BNBUSDT": 0.83, "SOLUSDT": 0.83, "ADAUSDT": 0.83}
T = pd.concat([ALL[(s, 0.0003)] for s in COINS]).sort_values("entry_time")
MIN = 60_000_000_000
BLK = 28 * 24 * 60
mins = lambda col: T[col].values.astype("datetime64[m]").astype(np.int64)
tr = np.c_[mins("entry_time"), mins("exit_time"), mins("be_time"), T.dir.values, T.R.values, T.sym.map({s: i for i, s in enumerate(COINS)}).values]
RV = np.array([RISK[s] for s in COINS]) / 100


def journey(args):
    seed, a, b, mult, months, start = args
    r = np.random.default_rng(seed)
    t0, t1 = pd.Timestamp(a).value // MIN, pd.Timestamp(b).value // MIN
    pool = tr[(tr[:, 0] >= t0) & (tr[:, 0] < t1)]
    nb = int(np.ceil(months * 30.44 * 1440 / BLK)); rows = []
    for k in range(nb):
        u = t0 + r.random() * (t1 - BLK - t0)
        sel = pool[(pool[:, 0] >= u) & (pool[:, 0] < u + BLK)].copy()
        sel[:, :3] += k * BLK - u
        rows.append(sel)
    x = np.concatenate(rows); end = months * 30.44 * 1440
    ev = []
    for i, (e, xx, be, d, R, c) in enumerate(x):
        ev += [(e, 1, i), (max(be, e + 1e-3), 0, i), (max(xx, e + 2e-3), 2, i)]
    ev.sort(key=lambda z: (z[0], -z[1]))
    eq = start; opn = {}; pk = start; dd = 0; low = start
    for t, kind, i in ev:
        if t > end:
            break
        e, xx, be, d, R, c = x[i]
        if kind == 1:
            opn[i] = [eq * RV[int(c)] * mult * (0.5 if d < 0 else 1), False]
        elif kind == 0 and i in opn:
            opn[i][1] = True
        elif kind == 2 and i in opn:
            eq += opn.pop(i)[0] * R; low = min(low, eq)
        w = eq - sum(v[0] for v in opn.values() if not v[1]); pk = max(pk, w); dd = max(dd, 1 - w / pk)
    return eq, dd, low


if __name__ == "__main__":
    N = 1500
    for lab, a, b in (("trades from 2022-26 (no 2020-21 bull run)", "2022-01-01", "2026-10-01"), ("trades from 2024-26", "2024-01-01", "2026-10-01")):
        print(f"\n=== $250 for 24 months, {N} journeys, {lab} ===")
        print(f"{'risk (BTC / ETH / each alt)':30s} median    10% worst  10% best   reach $10k  reach $20k  end < $100  end < $50  median worst drop")
        for mult in (0.5, 1.0, 1.5, 2.0):
            with Pool(4) as p:
                res = np.array(p.map(journey, [(s, a, b, mult, 24, 250.0) for s in range(N)]))
            f, dd, lo = res[:, 0], res[:, 1], res[:, 2]
            rk = f"{5*mult:g}% / {2.5*mult:g}% / {0.83*mult:.2f}%"
            print(f"{rk:30s} ${np.median(f):>9,.0f} ${np.percentile(f,10):>9,.0f} ${np.percentile(f,90):>10,.0f}   {(f>=1e4).mean()*100:5.0f}%     {(f>=2e4).mean()*100:5.0f}%     "
                  f"{(f<100).mean()*100:5.0f}%      {(f<50).mean()*100:5.0f}%     {np.median(dd)*100:4.0f}%", flush=True)
