"""Robustness of the open-interest filter (idea 6): lookback x threshold x measure (USD value vs contracts),
per coin, per year, longs vs shorts. Skips the order when OI changed by <= threshold over the lookback."""
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import filter_test as FT
import filter_test2 as F2
from portfolio import simulate

EX = C.ROOT / "data" / "extra"
_OI = {}


def series(sym, col):
    if (sym, col) not in _OI:
        g = pd.read_csv(EX / f"{sym}_metrics_1h.csv.gz")
        t = pd.to_datetime(g.create_time).values.astype("datetime64[m]").astype(np.int64)
        o = np.argsort(t); v = g[col].to_numpy()[o]
        _OI[(sym, col)] = (t[o], pd.Series(np.where(v > 0, v, np.nan)).ffill().to_numpy())
    return _OI[(sym, col)]


def oi_chg(c, sym, col, hours):
    t, oi = series(sym, col)
    to = c["t"] + 240
    q = np.searchsorted(t, to, side="left") - 1
    ok = (q >= hours) & (to - t[np.clip(q, 0, None)] < 180)
    qq = np.clip(q, 0, None)
    return np.where(ok, oi[qq] / oi[np.clip(qq - hours, 0, None)] - 1, np.nan)


def make(col, hours, thr, sides="both"):
    def f(c, a, hi, lo, s):
        if sides != "both" and ((sides == "long") != (s > 0)):
            return np.zeros(len(a), bool)
        return oi_chg(c, F2.CUR["sym"], col, hours) <= thr
    return f


CFG = {"none": None}
for col, cn in (("sum_open_interest_value", "USD"), ("sum_open_interest", "contracts")):
    for hours, hn in ((24, "1d"), (72, "3d"), (168, "7d"), (336, "14d")):
        for thr in (-0.01, -0.03, -0.06, -0.10):
            CFG[f"{cn} {hn} <= {thr:.0%}"] = (col, hours, thr)
CFG["USD 7d <= -3% longs only"] = ("sum_open_interest_value", 168, -0.03, "long")
CFG["USD 7d <= -3% shorts only"] = ("sum_open_interest_value", 168, -0.03, "short")
CFG["contracts 7d <= -3% longs only"] = ("sum_open_interest", 168, -0.03, "long")
CFG["contracts 7d <= -3% shorts only"] = ("sum_open_interest", 168, -0.03, "short")


def job(args):
    sym, name = args
    F2.CUR["sym"] = sym
    FT.FILTERS[name] = None if CFG[name] is None else make(*CFG[name])
    return name, sym, FT.job((sym, name))[2]


def acct(TT, a, b):
    cv, tk = simulate(TT, risk=0.05, cap=99, short_mult=0.5, start=a, end=b, eq0=200.0, weights=FT.W)
    mo = (pd.Timestamp(b) - pd.Timestamp(a)).days / 30.44
    pk = cv.worst.cummax()
    return len(tk), ((cv.equity.iloc[-1] / 200) ** (1 / mo) - 1) * 100, ((pk - cv.worst) / pk).max() * 100, cv.equity.iloc[-1]


if __name__ == "__main__":
    with Pool(4) as p:
        res = p.map(job, [(s, n) for s in FT.COINS for n in CFG], chunksize=len(CFG))
    by = {}
    for n, s, x in res:
        by.setdefault(n, {})[s] = x
    pd.to_pickle(by, C.D.CACHE / "oi_filter_trades.pkl")
    print(f"{'filter (acts from 2022)':34s} | 2022-23 trades %/mo DD | 2024-26 trades %/mo DD $200->")
    for n in CFG:
        TT = pd.concat(by[n].values())
        a = acct(TT, "2022-01-01", "2024-01-01"); b = acct(TT, "2024-01-01", "2026-10-01")
        print(f"{n:34s} | {a[0]:4d} {a[1]:6.2f}% {a[2]:5.1f}% | {b[0]:4d} {b[1]:6.2f}% {b[2]:5.1f}% ${b[3]:,.0f}", flush=True)
    # per coin and per year, R units, for the main candidates
    for n in ("USD 7d <= -3%", "contracts 7d <= -3%"):
        print(f"\n{n}: net R per coin and year (filter vs none), 2022+")
        for s in FT.COINS:
            x0 = by["none"][s]; x1 = by[n][s]
            cells = []
            for y in (2022, 2023, 2024, 2025, 2026):
                r0 = x0[x0.entry_time.dt.year == y].R.sum(); r1 = x1[x1.entry_time.dt.year == y].R.sum()
                cells.append(f"{y}: {r0:+5.1f}->{r1:+5.1f}")
            print(f"  {s[:-4]:5s} " + "  ".join(cells))
