"""
TBO v2.1 on 12 coins (no per-coin tuning) and a one-account portfolio simulation.
Alts pay 0.03% slippage per taker fill (BTC/ETH 0.01%); stress test with 0.05%.
Portfolio: risk per trade = r x equity at entry; total open risk cap; same-direction position cap.
A trade's risk is released once its stop is at breakeven (+1.5R reached). Drawdowns are measured on
'equity minus all open risk' (= every open trade stopped at the same moment): a worst-case curve.
"""
import sys, pickle
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
import ideas10 as X
from wf2 import V21

COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "LINKUSDT", "AVAXUSDT",
         "LTCUSDT", "TRXUSDT", "DOTUSDT"]
A, B = "2020-03-01", "2026-10-01"


def trades(args):
    sym, slip = args
    C.SLIP = slip if sym not in ("BTCUSDT", "ETHUSDT") else 0.0001
    m = C.load(sym)
    x = C.between(F.channel_breakout(m, **V21), A, B).copy()
    e = X.idx(m, x.entry_time); xi = X.idx(m, x.exit_time)
    be = X.first_reach(m["h"], m["l"], e, xi, x.dir.to_numpy(), x.entry.to_numpy(), x.sl_dist.to_numpy(), V21["be_R"])
    x["be_time"] = pd.to_datetime(np.where(be >= 0, m["t"][np.clip(be, 0, None)], m["t"][xi]) * 60, unit="s")
    x["sym"] = sym
    return sym, slip, x[["sym", "entry_time", "exit_time", "be_time", "dir", "R", "hours"]]


def simulate(T, risk=0.004, cap=0.03, dir_cap=99, start=A, end=B, eq0=1000.0, short_mult=1.0, weights=None):
    """Event simulation over all coins' trades. Returns daily curve (closed equity, worst-case equity), taken trades."""
    tr = T[(T.entry_time >= start) & (T.entry_time < end)].sort_values("entry_time").reset_index(drop=True)
    ev = []
    eps = pd.Timedelta(microseconds=1)
    for i, r in tr.iterrows():
        # a trade's own breakeven / exit always come after its entry (zero-length trades: + 1 microsecond)
        be_t = max(r.be_time, r.entry_time + eps); ex_t = max(r.exit_time, r.entry_time + 2 * eps)
        ev += [(r.entry_time, 1, i), (be_t, 0, i), (ex_t, 2, i)]
    ev.sort(key=lambda z: (z[0], -z[1]))          # other trades' exits / BE before entries at the same timestamp
    eq = eq0; open_ = {}; taken = []; curve = []; pnl = {}; risk_amt = {}
    for t, kind, i in ev:
        if kind == 1:
            if i in open_:
                continue
            at_risk = sum(v["amt"] for v in open_.values() if not v["be"])
            same = sum(1 for v in open_.values() if v["dir"] == tr.dir[i])
            amt = risk * eq * (short_mult if tr.dir[i] < 0 else 1.0) * (weights[tr.sym[i]] if weights else 1.0)
            if at_risk + amt > cap * eq or same >= dir_cap:
                continue
            open_[i] = dict(amt=amt, be=False, dir=tr.dir[i]); taken.append(i)
        elif kind == 0 and i in open_:
            open_[i]["be"] = True
        elif kind == 2 and i in open_:
            v = open_.pop(i); pnl[i] = v["amt"] * tr.R[i]; risk_amt[i] = v["amt"]
            eq += pnl[i]
        worst = eq - sum(v["amt"] for v in open_.values() if not v["be"])
        curve.append((t, eq, worst, len(open_)))
    assert not open_ or max(tr.exit_time[i] for i in open_) >= ev[-1][0] - pd.Timedelta(seconds=1), "stuck trade"
    cv = pd.DataFrame(curve, columns=["t", "equity", "worst", "n_open"]).set_index("t")
    assert cv.n_open.max() <= tr.sym.nunique(), "more open trades than coins"
    out = tr.loc[taken].copy()
    out["pnl"] = [pnl.get(i, np.nan) for i in taken]; out["risk_usd"] = [risk_amt.get(i, np.nan) for i in taken]
    return cv, out


def report(cv, taken, label, months):
    pk = cv.worst.cummax(); dd = ((pk - cv.worst) / pk).max()
    pk2 = cv.equity.cummax(); dd2 = ((pk2 - cv.equity) / pk2).max()
    final = cv.equity.iloc[-1]
    mo = cv.equity.resample("ME").last().ffill().pct_change().dropna()
    hw = cv.equity.cummax(); newhigh = cv.index[cv.equity >= hw]
    gaps = np.diff(newhigh.values).astype("timedelta64[D]").astype(int)
    wk = len(taken) / (months * 4.345)
    print(f"  {label:34s} ${final:>10,.0f} {((final/1000)**(1/months)-1)*100:5.1f}%/mo | DD closed {dd2*100:4.1f}% worst-case {dd*100:4.1f}% | "
          f"months+ {(mo>0).mean()*100:3.0f}% worst month {mo.min()*100:5.1f}% | trades/wk {wk:4.1f} | new high: median {np.median(gaps) if len(gaps) else 0:.0f}d longest {gaps.max() if len(gaps) else 0}d")


if __name__ == "__main__":
    jobs = [(s, sl) for s in COINS for sl in (0.0003, 0.0005)]
    with Pool(4) as p:
        res = p.map(trades, jobs)
    ALL = {(s, sl): x for s, sl, x in res}
    pickle.dump(ALL, open(C.D.CACHE / "portfolio_trades.pkl", "wb"))
    print("Per coin, TBO v2.1 untouched (R per trade; alts 0.03% slippage; stress = 0.05%):")
    print(f"{'coin':9s} {'trades':>6s} {'PF':>5s} {'R':>6s} {'DD R':>6s} {'R/yr':>5s} | {'2020-23 R':>9s} {'2024-26 R':>9s} | {'stress R':>8s} | by year")
    rows = []
    for s in COINS:
        x = ALL[(s, 0.0003)].sort_values("exit_time"); r = x.R.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
        yrs = (x.exit_time.max() - x.entry_time.min()).days / 365.25
        pf = r[r > 0].sum() / -r[r <= 0].sum()
        dev = C.between(x, *C.DEV).R.sum(); new = C.between(x, *C.HOLDOUT).R.sum()
        rows.append(dict(sym=s, dev=dev, new=new))
        print(f"{s:9s} {len(r):6d} {pf:5.2f} {r.sum():6.0f} {dd:6.1f} {r.sum()/yrs:5.0f} | {dev:9.0f} {new:9.0f} | {ALL[(s,0.0005)].R.sum():8.0f} | "
              f"{x.groupby(x.entry_time.dt.year).R.sum().round(0).astype(int).to_dict()}")
    mo = pd.concat({s: ALL[(s, 0.0003)].groupby(ALL[(s, 0.0003)].exit_time.dt.to_period('M')).R.sum() for s in COINS}, axis=1).fillna(0)
    cm = mo.corr().values; off = cm[~np.eye(len(COINS), dtype=bool)]
    print(f"\nmonthly R correlation between coins: average {off.mean():.2f} (min {off.min():.2f}, max {off.max():.2f}); "
          f"with BTC: " + ", ".join(f"{s[:-4]} {mo.corr()['BTCUSDT'][s]:.2f}" for s in COINS[1:]))
    dev_ok = [r["sym"] for r in rows if r["dev"] > 0]
    print("coins positive in 2020-23 (selection uses ONLY these years):", [s[:-4] for s in dev_ok])
    pickle.dump(dict(dev_ok=dev_ok), open(C.D.CACHE / "portfolio_sel.pkl", "wb"))
