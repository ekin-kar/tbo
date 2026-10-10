"""Different ways to read the breakout range, re-tested on the live v2.6 rules (Oct 2026): ATR buffer above / below the
20-candle level, range width (channel height in ATRs: skip tight or wide ranges), RSI(14) zone at the order candle,
entering only after a 1h / 4h candle CLOSES beyond the level, and an efficiency-ratio (clean trend into the range) filter.
Same engine and costs; open-interest filter and profit lock as live. Scored per period on the fixed-size R account
(BTC 2, ETH 1, alts 1/3, shorts x0.5) and on the bot (ladder + cap) from $200."""
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
import grid_v25 as G
import botsim as BS
from wf2 import V21

I = C.I
COINS = BS.COINS
WT = np.array([2, 1, 1 / 3, 1 / 3, 1 / 3])


def skip_fn(sym, extra):
    oi = G.oi_skip(sym, 240)
    def f(c, a, hi, lo, s):
        out = oi(c, a, hi, lo, s)
        if "width" in extra:
            w = (hi - lo) / np.maximum(a, 1e-12); lo_w, hi_w = extra["width"]
            out = out | (w < lo_w) | (w > hi_w)
        if "rsi" in extra:
            r = I.rsi_wilder(c["c"], 14); rs = r if s > 0 else 100 - r; lo_r, hi_r = extra["rsi"]
            out = out | (rs < lo_r) | (rs > hi_r)
        return out
    return f


def trades(args):
    sym, extra = args
    m = C.load(sym)
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    kw = dict(V21, tf=240, n=20, hold_h=120, sl_mode="atr", sl_atr=1.0, be_R=1.5, lock_R=5.0, lock_to=1.5)
    kw.update({k: v for k, v in extra.items() if k in ("buffer_atr", "confirm_tf", "er_n", "er_min")})
    kw["skip_fn"] = skip_fn(sym, extra)
    x = C.between(F.channel_breakout(m, **kw), "2020-03-01", "2026-10-01").reset_index(drop=True)
    t = m["t"]; e = x.entry_time.values.astype("datetime64[m]").astype(np.int64); xm = x.exit_time.values.astype("datetime64[m]").astype(np.int64)
    be = np.empty(len(x), np.int64)
    for k in range(len(x)):
        j0 = int(np.searchsorted(t, e[k])); j1 = int(np.searchsorted(t, xm[k]))
        lvl = x.entry[k] + x.dir[k] * 1.5 * x.sl_dist[k]
        seg = m["h"][j0 + 1:j1 + 1] >= lvl if x.dir[k] > 0 else m["l"][j0 + 1:j1 + 1] <= lvl
        h = np.nonzero(seg)[0]; be[k] = t[j0 + 1 + h[0]] if len(h) else xm[k]
    return np.c_[e, xm, be, x.dir.to_numpy(), x.R.to_numpy(), np.full(len(x), COINS.index(sym))]


VARS = {"bot now": {}}
for b in (0.1, 0.25, 0.5):
    VARS[f"ATR buffer {b}: level + {b} ATR"] = dict(buffer_atr=b)
for lo_w, hi_w, lab in ((0, 6, "skip ranges wider than 6 ATR"), (0, 8, "skip ranges wider than 8 ATR"), (3, 99, "skip ranges tighter than 3 ATR"),
                        (4, 99, "skip ranges tighter than 4 ATR")):
    VARS[f"width: {lab}"] = dict(width=(lo_w, hi_w))
for lo_r, hi_r in ((50, 100), (55, 100), (0, 75), (0, 80), (45, 75)):
    VARS[f"RSI(14) at the order {lo_r}-{hi_r} (side-adjusted)"] = dict(rsi=(lo_r, hi_r))
VARS["enter after a 1h close beyond the level"] = dict(confirm_tf=60)
VARS["enter after a 4h close beyond the level"] = dict(confirm_tf=240)
for n_, er in ((20, 0.2), (20, 0.3)):
    VARS[f"efficiency ratio({n_}) >= {er}"] = dict(er_n=n_, er_min=er)


def job(name):
    extra = VARS[name]
    x = np.concatenate([trades((s, extra)) for s in COINS]); x = x[np.lexsort((x[:, 5], x[:, 0]))]
    out = []
    for a, b in (("2020-03-01", "2024-01-01"), ("2024-01-01", "2026-10-01")):
        t0, t1 = pd.Timestamp(a).value // BS.MIN, pd.Timestamp(b).value // BS.MIN
        xs = x[(x[:, 0] >= t0) & (x[:, 0] < t1)]
        w = WT[xs[:, 5].astype(int)] * np.where(xs[:, 3] < 0, 0.5, 1); o = np.argsort(xs[:, 1]); e = np.cumsum((xs[:, 4] * w)[o])
        dd = (np.maximum.accumulate(np.r_[0, e])[1:] - e).max()
        r = BS.run(xs, BS.bot_policy(), 200.0)
        out.append((e[-1], dd, len(xs), (xs[:, 4] >= 5).sum(), r["final"], r["dd"]))
    return name, out


if __name__ == "__main__":
    with Pool(3) as p:
        res = p.map(job, list(VARS))
    b = res[0][1]; q = lambda o: o[0] / o[1]
    print(f"{'variant':52s} | fixed R acct 2020-23: net, maxDD, net/DD (x bot), trades | 2024-26 same | >=5R 24-26 | bot $200 2020-23 | 2024-26")
    for n, o in res:
        print(f"{n:52s} | {o[0][0]:5.0f} {o[0][1]:5.1f} {q(o[0]):5.2f} (x{q(o[0])/q(b[0]):.2f}) {o[0][2]:4d} | "
              f"{o[1][0]:5.0f} {o[1][1]:5.1f} {q(o[1]):5.2f} (x{q(o[1])/q(b[1]):.2f}) {o[1][2]:4d} | {o[1][3]:3d} | "
              f"${o[0][4]:>9,.0f} {o[0][5]:4.1f}% | ${o[1][4]:>7,.0f} {o[1][5]:4.1f}%", flush=True)
