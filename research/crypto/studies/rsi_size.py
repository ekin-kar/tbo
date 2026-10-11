"""Do TBO breakouts with strong RSI / volume build-up / OBV lead at order placement run better? Sizing test."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import numpy as np, pandas as pd
import common as C, families as F
import ideas10 as X
from wf2 import V21

rows = []
for sym in ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]:
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    m = C.load(sym); tr = C.between(F.channel_breakout(m, **V21), "2020-03-01", "2026-10-01").reset_index(drop=True)
    c = F.resample(m, 240); cl, v = c["c"], c["v"]
    k = np.searchsorted(c["act"], X.idx(m, tr.entry_time), side="right") - 1
    r = C.I.rsi_wilder(cl, 14); obv = np.cumsum(np.sign(np.r_[0, np.diff(cl)]) * v)
    vb = pd.Series(v).rolling(3).mean().to_numpy() / pd.Series(v).rolling(20).mean().to_numpy()
    s = tr.dir.to_numpy()
    rows.append(pd.DataFrame(dict(sym=sym[:-4], t=tr.entry_time, R=tr.R, side=s, rsi=np.where(s > 0, r[k], 100 - r[k]), vb=vb[k],
                                  obv_lead=np.where(s > 0, obv[k] >= C.I.rolling_max(obv, 20)[k], obv[k] <= C.I.rolling_min(obv, 20)[k]))))
D = pd.concat(rows, ignore_index=True); D["period"] = np.where(D.t < "2024-01-01", "2020-23", "2024-26")
print("avg R per trade by condition at order placement (2020-23 | 2024-26):")
for name, msk in [("all", D.R == D.R), ("RSI >= 70", D.rsi >= 70), ("RSI 60-70", (D.rsi >= 60) & (D.rsi < 70)), ("RSI < 60", D.rsi < 60),
                  ("volume build > 1.3", D.vb > 1.3), ("volume build <= 1.3", D.vb <= 1.3), ("OBV leading", D.obv_lead), ("OBV not leading", ~D.obv_lead)]:
    g = D[msk].groupby("period").R.agg(["mean", "size"])
    print(f"  {name:22s} " + " | ".join(f"{p}: {g.loc[p,'mean']:+.2f}R (n={int(g.loc[p,'size'])})" for p in g.index))


def st(d):
    d = d.sort_values("t"); r = d.Rs.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    yrs = (d.t.max() - d.t.min()).days / 365.25; return r.sum() / yrs / dd
print("\nsizing (4 coins, return/DD 2020-23 | 2024-26), all with shorts at half size:")
base = np.where(D.side < 0, 0.5, 1.0)
for name, mult in [("v2.2 (shorts half)", base), ("1.5x when RSI >= 70", base * np.where(D.rsi >= 70, 1.5, 1.0)),
                   ("0.5x when RSI < 60", base * np.where(D.rsi < 60, 0.5, 1.0)), ("1.5x when OBV leads", base * np.where(D.obv_lead, 1.5, 1.0)),
                   ("1.5x when volume builds", base * np.where(D.vb > 1.3, 1.5, 1.0))]:
    D["Rs"] = D.R * mult
    print(f"  {name:26s} {st(D[D.period=='2020-23']):5.2f} | {st(D[D.period=='2024-26']):5.2f}")

print("\nOBV leading vs not, per coin (avg R, 2020-23 | 2024-26):")
for s in ["BTC", "ETH", "DOGE", "ADA"]:
    d = D[D.sym == s]
    f = lambda p, l: d[(d.period == p) & (d.obv_lead == l)].R.mean()
    print(f"  {s:5s} leading {f('2020-23', True):+.2f} | {f('2024-26', True):+.2f}   not leading {f('2020-23', False):+.2f} | {f('2024-26', False):+.2f}")
for name, mult in [("0.5x when OBV leads", base * np.where(D.obv_lead, 0.5, 1.0)), ("skip when OBV leads", base * np.where(D.obv_lead, 0.0, 1.0))]:
    D["Rs"] = D.R * mult
    print(f"  {name:26s} {st(D[D.period=='2020-23']):5.2f} | {st(D[D.period=='2024-26']):5.2f}")
