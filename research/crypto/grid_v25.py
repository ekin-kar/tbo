"""Big structure grid for TBO (Oct 2026): timeframe x channel x stop type/size x breakeven x hold, on the bot's 5 coins
with the open-interest filter (OI USD 3-day change <= -3% -> no order; data from 2022). Trend filter as v2.4.
Each config is scored on the bot's weighted account in R (BTC 2, ETH 1, BNB/SOL/ADA 1/3, shorts x0.5):
net R, max drawdown R and net/drawdown for 2020-23 (dev) and 2024-26 (holdout), plus each year's net R.
Results are appended to cache/grid_v25.csv as they come (safe to stop and resume)."""
import itertools, os, sys, time
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
from wf2 import V21

COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
WT = {"BTCUSDT": 2.0, "ETHUSDT": 1.0, "BNBUSDT": 1 / 3, "SOLUSDT": 1 / 3, "ADAUSDT": 1 / 3}
OUT = C.D.CACHE / "grid_v25.csv"
EX = C.ROOT / "data" / "extra"
_D, _OI = {}, {}

STOPS = [("atr", dict(sl_mode="atr", sl_atr=k)) for k in (0.75, 1.0, 1.5, 2.0)] + \
        [("pct", dict(sl_mode="pct", sl_pct=k)) for k in (0.01, 0.02, 0.03, 0.05)] + \
        [("chan", dict(sl_mode="chan", sl_chan=k)) for k in (0.25, 0.5, 0.75)] + [("swing", dict(sl_mode="swing", swing_k=6))]
GRID = [dict(tf=tf, n=n, stop=si, be_R=be, hold_h=h) for tf, n, si, be, h in
        itertools.product((60, 120, 240, 480, 720, 1440), (10, 15, 20, 30, 50), range(len(STOPS)), (0.0, 1.0, 1.5, 2.0), (72, 120, 240))]


def oi(sym):
    if sym not in _OI:
        g = pd.read_csv(EX / f"{sym}_metrics_1h.csv.gz", usecols=["create_time", "sum_open_interest_value"])
        t = pd.to_datetime(g.create_time).values.astype("datetime64[m]").astype(np.int64)
        o = np.argsort(t); v = g.sum_open_interest_value.to_numpy()[o]
        _OI[sym] = (t[o], pd.Series(np.where(v > 0, v, np.nan)).ffill().to_numpy())
    return _OI[sym]


def oi_skip(sym, tf, hours=72, thr=-0.03):
    def f(c, a, hi, lo, s):
        t, v = oi(sym)
        to = c["t"] + tf
        q = np.searchsorted(t, to, side="left") - 1
        ok = (q >= hours) & (to - t[np.clip(q, 0, None)] < 180)
        qq = np.clip(q, 0, None)
        return np.where(ok, v[qq] / v[np.clip(qq - hours, 0, None)] - 1, np.nan) <= thr
    return f


def trades(sym, cfg, extra=None):
    if sym not in _D:
        _D[sym] = C.load(sym)
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    kw = dict(V21, tf=cfg["tf"], n=cfg["n"], be_R=cfg["be_R"], hold_h=cfg["hold_h"], **STOPS[cfg["stop"]][1])
    kw.update(extra or {})
    kw.setdefault("skip_fn", oi_skip(sym, cfg["tf"]))
    x = C.between(F.channel_breakout(_D[sym], **kw), "2020-03-01", "2026-10-01")
    return pd.DataFrame(dict(sym=sym, entry_time=x.entry_time.values, exit_time=x.exit_time.values, dir=x.dir.values, R=x.R.values))


def score(X):
    out = {}
    X = X.sort_values("exit_time")
    w = X.sym.map(WT).to_numpy() * np.where(X.dir < 0, 0.5, 1); pr = X.R.to_numpy() * w
    for nm, a, b in (("dev", "2020-03-01", "2024-01-01"), ("ho", "2024-01-01", "2026-10-01")):
        m = ((X.entry_time >= a) & (X.entry_time < b)).to_numpy()
        e = np.cumsum(pr[m]); dd = np.max(np.maximum.accumulate(np.r_[0, e])[1:] - e) if m.any() else np.nan
        out[f"{nm}_net"] = e[-1] if m.any() else 0.0; out[f"{nm}_dd"] = dd; out[f"{nm}_ratio"] = out[f"{nm}_net"] / dd if dd else np.nan
        out[f"{nm}_n"] = int(m.sum()); out[f"{nm}_win"] = float((X.R[m] > 0).mean() * 100) if m.any() else np.nan
    for y in range(2020, 2027):
        m = (X.entry_time.dt.year == y).to_numpy(); out[f"y{y}"] = float(pr[m].sum())
    return out


def job(i):
    cfg = GRID[i]
    X = pd.concat([trades(s, cfg) for s in COINS])
    return dict(i=i, **cfg, stop_name=STOPS[cfg["stop"]][0], stop_val=list(STOPS[cfg["stop"]][1].values())[-1], **score(X))


if __name__ == "__main__":
    done = set(pd.read_csv(OUT).i) if OUT.exists() else set()
    todo = [i for i in range(len(GRID)) if i not in done]
    print(f"{len(GRID)} configs, {len(todo)} to run", flush=True)
    t0 = time.time(); first = not OUT.exists()
    with Pool(4) as p:
        for k, r in enumerate(p.imap_unordered(job, todo, chunksize=4)):
            pd.DataFrame([r]).to_csv(OUT, mode="a", header=first, index=False); first = False
            if k % 200 == 0:
                print(f"{k}/{len(todo)} done, {(time.time()-t0)/60:.1f} min", flush=True)
    print("finished", flush=True)
