"""Breakeven offset and tighter stop (Oct 2026). Live v2.6 rules (OI filter, breakeven at +1.5 ATR, profit lock at +5 ATR
-> +1.5 ATR, 120 h) with:
  be_off  : the breakeven stop at entry + be_off x ATR instead of exactly the entry (covers fees)
  stop    : the initial stop at stop x ATR, the position still sized for 1 ATR (a stop-out costs ~stop x R + fees);
            breakeven / lock price levels unchanged. Results in R of 1 ATR (engine R x stop).
  'sized on the new stop' variants: plain stop x ATR with full risk (= sl_atr change).
Scored on a fixed-size R account (BTC 2, ETH 1, alts 1/3, shorts x0.5) per period, and the bot's ladder + cap from $200."""
import sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
import grid_v25 as G
import botsim as BS
from wf2 import V21

COINS = BS.COINS
WT = np.array([2, 1, 1 / 3, 1 / 3, 1 / 3])


def trades(args):
    sym, stop, be_off, scale = args
    m = C.load(sym)
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    kw = dict(V21, tf=240, n=20, hold_h=120, sl_mode="atr", sl_atr=stop, be_R=1.5 / stop, be_off=be_off / stop,
              lock_R=5.0 / stop, lock_to=1.5 / stop, skip_fn=G.oi_skip(sym, 240))
    x = C.between(F.channel_breakout(m, **kw), "2020-03-01", "2026-10-01").reset_index(drop=True)
    t = m["t"]; e = x.entry_time.values.astype("datetime64[m]").astype(np.int64); xm = x.exit_time.values.astype("datetime64[m]").astype(np.int64)
    be = np.empty(len(x), np.int64)
    for k in range(len(x)):
        j0 = int(np.searchsorted(t, e[k])); j1 = int(np.searchsorted(t, xm[k]))
        lvl = x.entry[k] + x.dir[k] * 1.5 / stop * x.sl_dist[k]
        seg = m["h"][j0 + 1:j1 + 1] >= lvl if x.dir[k] > 0 else m["l"][j0 + 1:j1 + 1] <= lvl
        h = np.nonzero(seg)[0]; be[k] = t[j0 + 1 + h[0]] if len(h) else xm[k]
    R = x.R.to_numpy() * (stop if scale else 1.0)                    # R of the 1-ATR risk unit when sized on 1 ATR
    return sym, np.c_[e, xm, be, x.dir.to_numpy(), R, np.full(len(x), COINS.index(sym))], x.reason.to_numpy()


VARS = {"bot now (stop 1.0 ATR, breakeven at entry)": (1.0, 0.0, True),
        "breakeven +0.05R": (1.0, 0.05, True), "breakeven +0.1R": (1.0, 0.1, True), "breakeven +0.2R": (1.0, 0.2, True),
        "stop 0.9 ATR, sized on 1 ATR": (0.9, 0.0, True), "stop 0.8 ATR, sized on 1 ATR": (0.8, 0.0, True),
        "stop 0.9 + breakeven +0.1R (your idea)": (0.9, 0.1, True),
        "stop 0.9 ATR, sized on 0.9 (full risk)": (0.9, 0.0, False)}


def score(x, reasons):
    out = {}
    for nm, a, b in (("20-23", "2020-03-01", "2024-01-01"), ("24-26", "2024-01-01", "2026-10-01")):
        t0, t1 = pd.Timestamp(a).value // BS.MIN, pd.Timestamp(b).value // BS.MIN
        s = (x[:, 0] >= t0) & (x[:, 0] < t1); xs = x[s]
        w = WT[xs[:, 5].astype(int)] * np.where(xs[:, 3] < 0, 0.5, 1); o = np.argsort(xs[:, 1]); e = np.cumsum((xs[:, 4] * w)[o])
        dd = (np.maximum.accumulate(np.r_[0, e])[1:] - e).max()
        R = xs[:, 4]
        out[nm] = dict(net=e[-1], dd=dd, n=len(xs), stops=(R < -0.5).sum(), avg_stop=R[R < -0.5].mean(),
                       be=((R > -0.5) & (R < 0.5)).sum(), avg_be=R[(R > -0.5) & (R < 0.5)].mean(), big=(R >= 5).sum())
    for nm, a in (("lad20", "2020-03-01"), ("lad24", "2024-01-01")):
        t0 = pd.Timestamp(a).value // BS.MIN
        r = BS.run(x[x[:, 0] >= t0], BS.bot_policy(), 200.0); out[nm] = (r["final"], r["dd"])
    return out


def job(name):
    stop, bo, scale = VARS[name]
    parts = [trades((s, stop, bo, scale)) for s in COINS]
    x = np.concatenate([p[1] for p in parts]); rs = np.concatenate([p[2] for p in parts])
    o = np.lexsort((x[:, 5], x[:, 0])); x = x[o]
    return name, score(x, rs[o])


if __name__ == "__main__":
    base_x = BS.TR.copy()
    with Pool(3) as p:
        res = p.map(job, list(VARS))
    b = res[0][1]
    chk = abs(b["24-26"]["net"] - 308.2) < 1 and abs(b["lad24"][0] - 26688) < 2
    print("baseline reproduces v2.6:", chk, round(b["24-26"]["net"], 1), round(b["lad24"][0]))
    print(f"{'':42s} | fixed R account: net / maxDD / net-per-DD (x bot)  2020-23 | 2024-26 | stops: n, avg R | BE exits: n, avg R | >=5R | ladder $200 from 2020 / from 2024 (final, worst drop)")
    for n, s in res:
        a, h = s["20-23"], s["24-26"]
        print(f"{n:42s} | {a['net']:5.0f} {a['dd']:5.1f} {a['net']/a['dd']:5.2f} (x{(a['net']/a['dd'])/(b['20-23']['net']/b['20-23']['dd']):.2f}) | "
              f"{h['net']:5.0f} {h['dd']:5.1f} {h['net']/h['dd']:5.2f} (x{(h['net']/h['dd'])/(b['24-26']['net']/b['24-26']['dd']):.2f}) | "
              f"{a['stops']+h['stops']:4d} {(a['avg_stop']*a['stops']+h['avg_stop']*h['stops'])/(a['stops']+h['stops']):+.2f} | "
              f"{a['be']+h['be']:4d} {(a['avg_be']*a['be']+h['avg_be']*h['be'])/(a['be']+h['be']):+.2f} | {a['big']+h['big']:3d} | "
              f"${s['lad20'][0]:>10,.0f} {s['lad20'][1]:4.1f}% / ${s['lad24'][0]:>7,.0f} {s['lad24'][1]:4.1f}%", flush=True)
