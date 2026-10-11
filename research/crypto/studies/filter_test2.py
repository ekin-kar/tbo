"""Ideas 6/7 inside the backtest: skip the order when open interest fell over the last 7 days (or sits below its
30-day average), or when the last 4h candle's aggressive-buyer share dropped below its 20-candle average.
OI data starts Dec 2021, so the OI filters only act from 2022. Random-skip benchmark over the same years."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import filter_test as FT
from portfolio import simulate

EX = C.ROOT / "data" / "extra"
CUR = {}


def oi_series(sym):
    g = pd.read_csv(EX / f"{sym}_metrics_1h.csv.gz")
    t = pd.to_datetime(g.create_time).values.astype("datetime64[m]").astype(np.int64)
    o = np.argsort(t); t = t[o]; oi = g.sum_open_interest_value.to_numpy()[o]
    oi = pd.Series(np.where(oi > 0, oi, np.nan)).ffill().to_numpy()
    return t, oi


def oi_at(c, sym, kind):
    t, oi = oi_series(sym)
    to = c["t"] + 240                                   # order time = candle close (minutes)
    q = np.searchsorted(t, to, side="left") - 1
    ok = (q >= 720) & (to - t[np.clip(q, 0, None)] < 180)
    qq = np.clip(q, 0, None)
    if kind == "chg7d":
        v = oi[qq] / oi[np.clip(qq - 168, 0, None)] - 1
    else:
        v = oi[qq] / pd.Series(oi).rolling(720).mean().to_numpy()[qq]
    return np.where(ok, v, np.nan)


def tb_drop(c, sym, side):
    k = pd.read_csv(EX / f"{sym}_4h.csv.gz")
    kt = (k.open_ms // 60000).to_numpy(); sh = (k.taker_buy_quote / k.quote_volume).to_numpy()
    sh = np.where(side > 0, sh, 1 - sh)
    d = sh - pd.Series(sh).rolling(20).mean().to_numpy()
    i = np.searchsorted(kt, c["t"])                     # same candle (open time)
    ok = (i < len(kt)) & (kt[np.clip(i, 0, len(kt) - 1)] == c["t"])
    return np.where(ok, d[np.clip(i, 0, len(kt) - 1)], np.nan)


EXTRA = {
    "OI 7d change <= -3.2%": lambda c, a, hi, lo, s: oi_at(c, CUR["sym"], "chg7d") <= -0.0322,
    "OI 7d change <= -8.3%": lambda c, a, hi, lo, s: oi_at(c, CUR["sym"], "chg7d") <= -0.0831,
    "OI below 0.88x its 30d avg": lambda c, a, hi, lo, s: oi_at(c, CUR["sym"], "vs30") <= 0.8829,
    "buyer share drop <= -0.0097": lambda c, a, hi, lo, s: tb_drop(c, CUR["sym"], s) <= -0.009655,
}
T0 = int(pd.Timestamp("2022-01-01").value // 60_000_000_000)


def rnd(seed, share):
    def f(c, a, hi, lo, s):
        r = np.random.default_rng(seed * 2 + (s > 0)).random(len(a))
        return (r < share) & (c["t"] >= T0)
    return f


def job(args):
    sym, name, seed, share = args
    CUR["sym"] = sym
    FT.FILTERS[name] = EXTRA.get(name) if seed is None else rnd(seed, share)
    return name, seed, sym, FT.job((sym, name))[2]


def evaluate(TT):
    out = []
    for a, b, mo in (("2022-01-01", "2024-01-01", 24), ("2024-01-01", "2026-10-01", 33)):
        cv, tk = simulate(TT, risk=0.05, cap=99, short_mult=0.5, start=a, end=b, eq0=200.0, weights=FT.W)
        pk = cv.worst.cummax()
        out += [len(tk), ((cv.equity.iloc[-1] / 200) ** (1 / mo) - 1) * 100, ((pk - cv.worst) / pk).max() * 100, cv.equity.iloc[-1]]
    return out


if __name__ == "__main__":
    jobs = [(s, n, None, 0) for n in ["none"] + list(EXTRA) for s in FT.COINS]
    jobs += [(s, f"rnd{sd}_{sh}", sd, sh) for sh in (0.15, 0.3) for s in FT.COINS for sd in range(25)]
    with Pool(4) as p:
        res = p.map(job, jobs, chunksize=8)
    by = {}
    for name, seed, sym, x in res:
        by.setdefault(name, []).append(x)
    print(f"{'filter (from 2022)':30s} | 2022-23: trades %/mo  DD    | 2024-26: trades %/mo  DD   $200->")
    for n in ["none"] + list(EXTRA):
        r = evaluate(pd.concat(by[n]))
        print(f"{n:30s} | {r[0]:5d} {r[1]:6.2f}% {r[2]:5.1f}% | {r[4]:5d} {r[5]:6.2f}% {r[6]:5.1f}% ${r[7]:,.0f}", flush=True)
    for sh in (0.15, 0.3):
        R = np.array([evaluate(pd.concat(by[f"rnd{sd}_{sh}"])) for sd in range(25)])
        print(f"random skip {sh:.0%} of orders: trades {R[:,0].mean():.0f}/{R[:,4].mean():.0f}; "
              f"2022-23 %/mo median {np.median(R[:,1]):.2f} (90th {np.percentile(R[:,1],90):.2f}), DD median {np.median(R[:,2]):.1f} (10th {np.percentile(R[:,2],10):.1f}); "
              f"2024-26 %/mo median {np.median(R[:,5]):.2f} (90th {np.percentile(R[:,5],90):.2f}), DD median {np.median(R[:,6]):.1f} (10th {np.percentile(R[:,6],10):.1f}), $ 90th {np.percentile(R[:,7],90):,.0f}")
