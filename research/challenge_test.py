"""Rolling-start challenge test on the REAL trade sequence (no resampling).
For every trading day from 2016 to Sep 2025 a fresh account starts, takes the live bots' actual trades in their actual order at the
chosen risk (compounding on balance), and is checked after every trade: target reached -> pass; static drawdown floor, daily loss
limit or per-trade limit broken -> fail. The bots' own daily stop is modelled (closes everything at that level, +0.05% slippage).
Usage:  python research/challenge_test.py            (prints the table)"""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent), str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd
import R, ideas as X

def clean(sym, tr, adj):
    t = R.get(sym)["t"]; gap = np.r_[0, np.diff(t)]
    holes = pd.to_datetime(t[np.flatnonzero(gap > 120)] * 60, unit="s").values.astype("datetime64[m]")
    a = tr.entry_time.values.astype("datetime64[m]"); b = tr.exit_time.values.astype("datetime64[m]"); bad = np.zeros(len(tr), bool)
    for x in holes: bad |= (a < x) & (b >= x)
    tr = tr[~bad].copy(); tr["R"] = tr.R - adj; return tr

G = clean("XAUUSD", R.run("XAUUSD", X.pday_trend(R.get("XAUUSD")), "main"), 0.02)[["exit_time", "R"]]; G["s"] = 0
V = clean("USDJPY", R.run("USDJPY", X.volc_f(R.get("USDJPY")), "main"), 0.002)[["exit_time", "R"]]; V["s"] = 1
days = pd.bdate_range("2016-01-04", "2026-09-18"); pos = {d: i for i, d in enumerate(days)}
tr = pd.concat([G, V]).sort_values("exit_time"); tr["day"] = tr.exit_time.dt.normalize()
tr["i"] = tr.day.map(lambda d: pos.get(d, pos.get(d - pd.offsets.BDay(1)))); tr = tr.dropna(subset=["i"]); tr["i"] = tr.i.astype(int)
tr["k"] = tr.groupby("i").cumcount(); K = tr.k.max() + 1
M = np.zeros((len(days), K)); S = np.zeros((len(days), K), int); M[tr.i, tr.k] = tr.R.values; S[tr.i, tr.k] = tr.s.values

def run(starts, rg, rv, targets, floor, daily=0.05, pt=0.03, guard=0.03, H=700, slip=0.0005):
    n = len(starts); bal = np.ones(n); ph = np.zeros(n, int); fail = np.zeros(n, bool); dn = np.full(n, -1)
    for t in range(H):
        di = starts + t; act = (~fail) & (ph < len(targets)) & (di < len(days))
        if not act.any(): break
        dic = np.minimum(di, len(days) - 1); Rr = M[dic]; Ss = S[dic]; day0 = bal.copy(); halted = np.zeros(n, bool)
        for k in range(K):
            x = Rr[:, k]; rr = np.where(Ss[:, k] == 0, rg, rv) / 100; live = act & ~halted & (x != 0); pnl = np.where(live, rr * x * bal, 0.0)
            fl = day0 * (1 - guard) - slip * day0; cap = live & (bal + pnl < fl); pnl = np.where(cap, fl - bal, pnl)
            f = live & (-pnl > pt * bal); bal = bal + pnl
            fail |= f | (live & (bal <= day0 * (1 - daily))) | (live & (bal <= floor)); halted |= cap | (live & (bal <= day0 * (1 - guard)))
        for p, tg in enumerate(targets):
            hit = act & ~fail & (ph == p) & (bal >= 1 + tg); ph[hit] += 1; bal[hit] = 1.0
        fin = act & ~fail & (ph == len(targets)); dn[fin & (dn < 0)] = t
    return ph == len(targets), dn

TYPES = {"1-step 10% target, 10% DD": ((0.10,), 0.90), "1-step 10% target, 8% DD": ((0.10,), 0.92), "1-step 10% target, 6% DD": ((0.10,), 0.94),
         "2-step 8%+6%, 10% DD": ((0.08, 0.06), 0.90), "2-step 8%+6%, 8% DD": ((0.08, 0.06), 0.92)}
RISKS = [(0.5, 0.6), (0.6, 0.8), (0.8, 1.0), (1.0, 1.2)]
SETS = {"all starts 2016-2025": ("2016-01-04", "2025-09-19"), "starts since Sep 2023": ("2023-09-19", "2025-09-19")}
if __name__ == "__main__":
  for tn, (tg, fl) in TYPES.items():
      print(f"\n{tn}")
      for rg, rv in RISKS:
          line = f"  gold {rg}% / USDJPY {rv}%:"
          for sn, (a, b) in SETS.items():
              st = np.arange(np.searchsorted(days, pd.Timestamp(a)), np.searchsorted(days, pd.Timestamp(b)))
              ok, dn = run(st, rg, rv, tg, fl)
              line += f"  | {sn}: pass {100*ok.mean():5.1f}%, median {np.median(dn[ok])/21:.1f} months"
          print(line)
