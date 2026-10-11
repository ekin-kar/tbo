"""Loser filters from loser_eval.py, run inside the backtest (skipped orders, not removed trades) and
through the account simulation at the bot's settings. Thresholds are 2020-23 quantiles."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F, ideas10 as X
from wf2 import V21
from portfolio import simulate

I = C.I
COINS = ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]
W = {"BTCUSDT": 1.0, "ETHUSDT": 0.5, "DOGEUSDT": 0.25, "ADAUSDT": 0.25}


def touches(c, a, hi, lo, side, n=20, k=0.5):
    H, L = c["h"], c["l"]
    out = np.zeros(len(a))
    lvl = hi if side > 0 else lo
    for j in range(n):
        Hj = np.r_[np.full(j, np.nan), H[:len(H) - j]]; Lj = np.r_[np.full(j, np.nan), L[:len(L) - j]]
        out += (Hj >= lvl - k * a) if side > 0 else (Lj <= lvl + k * a)
    return out


def quiet(c, a):
    return pd.Series(c["c"]).rolling(10).std().to_numpy() / a


def minor(c, a, hi, lo, side, n=120):
    return ((I.rolling_max(c["h"], n) - hi) if side > 0 else (lo - I.rolling_min(c["l"], n))) / a


def age(c, hi, lo, side):
    s = pd.Series(c["h"] if side > 0 else -c["l"])
    return s.rolling(20).apply(lambda x: 19 - int(np.argmax(x[::-1] == x.max())), raw=True).to_numpy()


FILTERS = {
    "none": None,
    "touches>=6": lambda c, a, hi, lo, s: touches(c, a, hi, lo, s) >= 6,
    "touches>=7": lambda c, a, hi, lo, s: touches(c, a, hi, lo, s) >= 7,
    "quiet<=0.44": lambda c, a, hi, lo, s: quiet(c, a) <= 0.441,
    "quiet<=0.37": lambda c, a, hi, lo, s: quiet(c, a) <= 0.374,
    "minor level (120)>=5.6": lambda c, a, hi, lo, s: minor(c, a, hi, lo, s) >= 5.61,
    "old level age>=16": lambda c, a, hi, lo, s: age(c, hi, lo, s) >= 16,
    "touches>=6 OR quiet<=0.44": lambda c, a, hi, lo, s: (touches(c, a, hi, lo, s) >= 6) | (quiet(c, a) <= 0.441),
    "2+ of 4 'tired setup' signs": lambda c, a, hi, lo, s: ((touches(c, a, hi, lo, s) >= 6).astype(int) + (quiet(c, a) <= 0.441)
                                                         + (minor(c, a, hi, lo, s) >= 5.61) + (age(c, hi, lo, s) >= 16)) >= 2,
}


_DATA = {}


def job(args):
    sym, fname = args
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    if sym not in _DATA:
        _DATA[sym] = C.load(sym)
    m = _DATA[sym]
    x = C.between(F.channel_breakout(m, **dict(V21, skip_fn=FILTERS[fname])), "2020-03-01", "2026-10-01").copy()
    e = X.idx(m, x.entry_time); xi = X.idx(m, x.exit_time)
    be = X.first_reach(m["h"], m["l"], e, xi, x.dir.to_numpy(), x.entry.to_numpy(), x.sl_dist.to_numpy(), V21["be_R"])
    x["be_time"] = pd.to_datetime(np.where(be >= 0, m["t"][np.clip(be, 0, None)], m["t"][xi]) * 60, unit="s")
    x["sym"] = sym
    return fname, sym, x[["sym", "entry_time", "exit_time", "be_time", "dir", "R", "hours"]]


if __name__ == "__main__":
    with Pool(4) as p:
        res = p.map(job, [(s, f) for f in FILTERS for s in COINS])
    T = {}
    for f, s, x in res:
        T.setdefault(f, []).append(x)
    print(f"{'filter':30s} | {'2020-23: trades  %/mo  DD':28s} | {'2024-26: trades  %/mo  DD  $200->':36s} | net R per coin 2024-26 (BTC ETH DOGE ADA)")
    for f, xs in T.items():
        TT = pd.concat(xs); line = f"{f:30s}"
        for a, b, mo in (("2020-03-01", "2024-01-01", 46), ("2024-01-01", "2026-10-01", 33)):
            cv, tk = simulate(TT, risk=0.05, cap=99, short_mult=0.5, start=a, end=b, eq0=200.0, weights=W)
            pk = cv.worst.cummax(); dd = ((pk - cv.worst) / pk).max() * 100
            fin = cv.equity.iloc[-1]
            line += f" | {len(tk):5d} {((fin/200)**(1/mo)-1)*100:6.2f}% {dd:5.1f}%" + (f" ${fin:,.0f}" if a == "2024-01-01" else "")
        h = TT[TT.entry_time >= "2024-01-01"]
        line += " | " + " ".join(f"{h[h.sym == s].R.sum():+6.1f}" for s in COINS)
        print(line, flush=True)
