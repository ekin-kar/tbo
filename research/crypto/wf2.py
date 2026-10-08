"""
Walk-forward tuning round 2 around TBO v2 (BTC only).
    python wf2.py run  <grid> [SYMBOL]   # compute all configs over the full history (causal), cache trades
    python wf2.py eval <grid> [SYMBOL]   # anchored walk-forward 2022..2026 vs the fixed base, + parameter marginals
Grids: core (stage A), filt (stage B: filters on top of the core winner(s)).
"""
import itertools, pickle, sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F

V2 = dict(tf=240, n=20, sl_atr=1.0, hold_h=120, ema_n=50, sides="both", slope_d=5, no_weekend=True,
          be_R=1.5, be_off=0.0, tp_R=0.0, vol_lo=0.0, vol_hi=1.0, max_ext=99.0, buffer_atr=0.0, ema2_n=0,
          trail_m=0, trail_atr=0.0)
V21 = dict(V2, max_ext=4.0)                  # BTC live settings (TBO v2.1)
SYM = sys.argv[3] if len(sys.argv) > 3 else "BTCUSDT"
GRIDS = {
    "core": dict(n=[15, 20, 25, 30], sl_atr=[0.75, 1.0, 1.25], be_R=[1.0, 1.5, 2.0, 3.0], be_off=[0.0, 0.2],
                 hold_h=[72, 120, 168], ema_n=[30, 50, 75], slope_d=[3, 5, 10]),
    "eth": dict(tf=[240, 120], n=[15, 20, 30, 40], sl_atr=[0.75, 1.0, 1.5], be_R=[0.0, 1.5, 2.5],
                hold_h=[72, 120, 168], ema_n=[30, 50, 100], slope_d=[0, 5], sides=["long", "both"], max_ext=[99.0, 4.0]),
    "ethf": dict(no_weekend=[True, False], tp_R=[0.0, 5.0], trail=[(0, 0.0), (12, 2.0)], vol_lo=[0.0, 0.2],
                 vol_hi=[1.0, 0.8], buffer_atr=[0.0, 0.1], ema2_n=[0, 200], be_off=[0.0, 0.2]),
    "filt": dict(tp_R=[0.0, 5.0, 8.0], vol_lo=[0.0, 0.2], vol_hi=[1.0, 0.8], max_ext=[99.0, 4.0, 2.5],
                 buffer_atr=[0.0, 0.1], ema2_n=[0, 200], no_weekend=[True, False]),
}
TESTS = [2022, 2023, 2024, 2025, 2026]
M = None


def configs(grid):
    base = dict(V21 if grid.startswith("eth") else V2)
    if grid == "ethf":
        try:
            base.update(pickle.load(open(C.D.CACHE / "wf2_eth_choice.pkl", "rb")))
        except FileNotFoundError:
            pass
    if grid == "filt":                       # stage B starts from the stage-A choice if it exists
        try:
            base.update(pickle.load(open(C.D.CACHE / "wf2_core_choice.pkl", "rb")))
        except FileNotFoundError:
            pass
    g = GRIDS[grid]
    out = []
    for v in itertools.product(*g.values()):
        c = dict(base, **dict(zip(g, v)))
        if "trail" in c:
            c["trail_m"], c["trail_atr"] = c.pop("trail")
        out.append(c)
    return out


def init():
    global M
    M = C.load(SYM)


def one(args):
    i, kw = args
    tr = F.channel_breakout(M, **kw)
    tr = tr[tr.entry_time >= "2020-03-01"]
    return i, tr[["entry_time", "exit_time", "dir", "R"]].reset_index(drop=True)


def stream(tr, a, b):
    return tr[(tr.entry_time >= a) & (tr.entry_time < b)].sort_values("exit_time")


def mar(x, years):
    if len(x) < 25 * years:
        return -np.inf
    r = x.R.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    if (x.groupby(x.entry_time.dt.year).R.sum() < 0).sum() > 1:
        return -np.inf
    return r.sum() / years / max(dd, 3.0)


def summary(x, label, yrs=4.75):
    r = x.R.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    e = 1000 * np.cumprod(1 + 0.02 * r); pk = np.maximum.accumulate(e)
    mo = x.groupby(x.exit_time.dt.to_period("M")).R.sum()
    print(f"{label:38s} trades {len(r):4d}  R/yr {r.sum()/yrs:5.1f}  DD {dd:5.1f}R  MAR {r.sum()/yrs/dd:4.2f}  "
          f"2%: {((e[-1]/1000)**(1/(yrs*12))-1)*100:4.1f}%/mo DD {((pk-e)/pk).max()*100:3.0f}%  months+ {(mo>0).mean()*100:3.0f}%  "
          f"{x.groupby(x.entry_time.dt.year).R.sum().round(0).to_dict()}")


if __name__ == "__main__":
    mode, grid = sys.argv[1], sys.argv[2]
    cfgs = configs(grid)
    path = C.D.CACHE / f"wf2_{grid}_{SYM}.pkl"
    if mode == "run":
        if V2 not in cfgs and grid == "core":
            cfgs.append(dict(V2))
        if grid == "eth" and V21 not in cfgs:
            cfgs.append(dict(V21))
        out = {}
        with Pool(4, initializer=init) as p:
            for i, tr in p.imap_unordered(one, list(enumerate(cfgs)), chunksize=8):
                out[i] = tr
        pickle.dump(dict(cfgs=cfgs, trades=out), open(path, "wb"))
        print("saved", len(cfgs))
    else:
        z = pickle.load(open(path, "rb")); cfgs, T = z["cfgs"], z["trades"]
        sc_cache = {}

        def score(i, y):
            if (i, y) not in sc_cache:
                yrs = (pd.Timestamp(f"{y}-01-01") - pd.Timestamp("2020-03-01")).days / 365.25
                sc_cache[(i, y)] = mar(stream(T[i], "2020-03-01", f"{y}-01-01"), yrs)
            return sc_cache[(i, y)]

        ref = V21 if grid.startswith("eth") else V2
        base_i = next((i for i, c in enumerate(cfgs) if c == ref), None)
        if base_i is not None:
            summary(pd.concat([stream(T[base_i], f"{y}-01-01", f"{y+1}-01-01") for y in TESTS]),
                    ("BTC v2.1 settings" if grid.startswith("eth") else "v2") + " fixed (2022-26)")
        picks = []
        for y in TESTS:
            sc = np.array([score(i, y) for i in range(len(cfgs))])
            picks.append(int(np.argmax(sc)))
        summary(pd.concat([stream(T[i], f"{y}-01-01", f"{y+1}-01-01") for y, i in zip(TESTS, picks)]), "walk-forward pick (out of sample)")
        keys = [k if k != "trail" else "trail_m" for k in GRIDS[grid]]
        for y, i in zip(TESTS, picks):
            print("  ", y, {k: cfgs[i][k] for k in keys})
        # marginals on all data: median MAR per value (plateau view)
        yrs = (pd.Timestamp("2026-10-01") - pd.Timestamp("2020-03-01")).days / 365.25
        full = np.array([mar(stream(T[i], "2020-03-01", "2026-10-01"), yrs) for i in range(len(cfgs))])
        df = pd.DataFrame([{k: c[k] for k in keys} for c in cfgs]); df["MAR"] = np.where(np.isfinite(full), full, np.nan)
        for k in keys:
            print(f"   {k:11s}", df.groupby(k).MAR.median().round(2).to_dict())
        top = np.argsort(-np.nan_to_num(full, nan=-9))[:5]
        print("top 5 on all data:")
        for i in top:
            print("  ", round(full[i], 2), {k: cfgs[i][k] for k in keys})
