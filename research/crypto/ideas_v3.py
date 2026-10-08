"""10 improvement ideas (Oct 2026), the ones testable with our data: 1 partial take-profit, 2 earlier breakeven,
3 failed-breakout exit, 4 re-entry after a fake breakout, 5 adding to winners, 8 trend-strength sizing,
9 several channel lengths. Exits are replayed minute by minute (tradesim.py, matches the engine on 1472/1474 trades).
Account in R: BTC 2, ETH 1, DOGE/ADA 0.5, shorts x0.5 (the bot's weights); dev = 2020-23, holdout = 2024-26."""
import sys, pickle
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
import tradesim as T

COINS = T.COINS
CACHE = C.D.CACHE / "ideas_v3_base.pkl"


def base(sym):
    x = T.base_trades(sym)
    x["reason2"] = [T.path(sym, r.e, r.dir, r.entry, r.sl_dist)[2] for r in x.itertuples()]
    return x


def out(sym, r, R, size=1.0, e_time=None, x_idx=None):
    m = T.data(sym)
    return dict(sym=sym, entry_time=e_time if e_time is not None else r.entry_time,
                exit_time=pd.Timestamp(int(m["t"][x_idx]) * 60, unit="s"), dir=r.dir, R=R, size=size)


# ── variants: each returns a list of result rows for one coin ──
def v_base(sym, X, **k):
    rows = []
    for r in X.itertuples():
        xi, xp, _, _ = T.path(sym, r.e, r.dir, r.entry, r.sl_dist)
        rows.append(out(sym, r, T.R_of(sym, r.dir, r.entry, r.sl_dist, xi, xp, r.e)[0], x_idx=xi))
    return rows


def v_partial(sym, X, frac=0.5, tp=1.0, be_rest=False, **k):
    """frac of the position takes profit at +tp R (resting limit, maker fee); the rest runs as usual
    (be_rest: the rest's stop moves to entry when the take-profit fills)."""
    m = T.data(sym); rows = []
    for r in X.itertuples():
        P, D, s, e = r.entry, r.sl_dist, r.dir, r.e
        xi, xp, _, _ = T.path(sym, e, s, P, D)
        Rb = T.R_of(sym, s, P, D, xi, xp, e)[0]
        j1 = min(e + T.HOLD, len(m["t"]) - 1)
        H, L = m["h"][e:j1], m["l"][e:j1]
        fav = (H - P) if s > 0 else (P - L)
        ti = T.first(fav >= tp * D)
        stop_hit = T.first((L <= P - D) if s > 0 else (H >= P + D))
        if ti >= 0 and (stop_hit < 0 or ti < stop_hit):
            tpx = P + s * tp * D
            Ra = T.R_of(sym, s, P, D, e + ti, tpx, e, taker_exit=False)[0]
            if be_rest:
                x2, p2, _, _ = T.path(sym, e, s, P, D, be_R=tp)
                Rb = T.R_of(sym, s, P, D, x2, p2, e)[0]; xi = max(xi, x2) if True else xi
                xi = x2
            R = frac * Ra + (1 - frac) * Rb
            rows.append(out(sym, r, R, x_idx=max(xi, e + ti)))
        else:
            rows.append(out(sym, r, Rb, x_idx=xi))
    return rows


def v_be(sym, X, be_R=1.5, be_off=0.0, **k):
    rows = []
    for r in X.itertuples():
        xi, xp, _, _ = T.path(sym, r.e, r.dir, r.entry, r.sl_dist, be_R=be_R, be_off=be_off)
        rows.append(out(sym, r, T.R_of(sym, r.dir, r.entry, r.sl_dist, xi, xp, r.e)[0], x_idx=xi))
    return rows


def v_failed(sym, X, tf=60, k_atr=0.0, within_h=24, **k):
    """Before breakeven: exit at the next open if a tf-candle closes back beyond the entry by k_atr x stop distance,
    within the first within_h hours."""
    m = T.data(sym); c = F.resample(m, tf); rows = []
    for r in X.itertuples():
        P, D, s, e = r.entry, r.sl_dist, r.dir, r.e
        xi, xp, why, b = T.path(sym, e, s, P, D)
        lim = min(xi, b if b >= 0 else xi, e + int(within_h * 60))
        a0 = np.searchsorted(c["act"], e, side="right"); a1 = np.searchsorted(c["act"], lim, side="right")
        acts = c["act"][a0:a1]; cl = c["c"][a0:a1]
        bad = (cl < P - k_atr * D) if s > 0 else (cl > P + k_atr * D)
        f = T.first(bad)
        if f >= 0 and acts[f] < xi:
            j = int(acts[f]); xp2 = m["o"][j]
            rows.append(out(sym, r, T.R_of(sym, s, P, D, j, xp2, e)[0], x_idx=j))
        else:
            rows.append(out(sym, r, T.R_of(sym, s, P, D, xi, xp, e)[0], x_idx=xi))
    return rows


def v_reentry(sym, X, within_h=48, max_re=1, **k):
    """After a full stop-out (before breakeven), buy (sell) again if price trades back through the original entry
    within within_h hours; same stop distance and exits. Skipped if another trade on the coin overlaps."""
    m = T.data(sym); rows = v_base(sym, X)
    spans = [(r.e, T.path(sym, r.e, r.dir, r.entry, r.sl_dist)[0]) for r in X.itertuples()]
    extra = []
    for r in X.itertuples():
        P, D, s, e = r.entry, r.sl_dist, r.dir, r.e
        xi, xp, why, b = T.path(sym, e, s, P, D)
        n_re = 0
        while why == "SL" and n_re < max_re:
            j0 = xi + 1; j1 = min(xi + int(within_h * 60), len(m["t"]) - 1)
            H, L = m["h"][j0:j1], m["l"][j0:j1]
            f = T.first((H >= P) if s > 0 else (L <= P))
            if f < 0:
                break
            e2 = j0 + f
            P2 = max(P, m["o"][e2]) if s > 0 else min(P, m["o"][e2])
            x2, p2, why2, _ = T.path(sym, e2, s, P2, D)
            if any(a < x2 and bb > e2 for a, bb in spans):
                break
            extra.append(out(sym, r, T.R_of(sym, s, P2, D, x2, p2, e2)[0], e_time=pd.Timestamp(int(m["t"][e2]) * 60, unit="s"), x_idx=x2))
            spans.append((e2, x2)); xi, why = x2, why2; n_re += 1
    return rows + extra


def v_pyramid(sym, X, add=0.5, levels=(1.0, 2.0), **k):
    """Add `add` x the starting size at +1R (all stops -> entry) and at +2R (all stops -> entry + 1R)."""
    m = T.data(sym); rows = []
    sl_cost = T.C.TAKER + T.slip(sym)
    for r in X.itertuples():
        P, D, s, e = r.entry, r.sl_dist, r.dir, r.e
        n = len(m["t"]); j1 = min(e + T.HOLD, n - 1)
        H, L, O = m["h"][e:j1], m["l"][e:j1], m["o"]
        fav = (H - P) if s > 0 else (P - L)
        pieces = [(1.0, P, e)]; stop = P - s * D; i = 0; xi = None; xp = None
        stops = [P, P + s * D]
        for li, lv in enumerate(levels + (None,)):
            seg_fav = fav[i:]
            hit = T.first((L[i:] <= stop) if s > 0 else (H[i:] >= stop))
            be = T.first(seg_fav >= T.BE_R * D) if li == 0 else -1
            nxt = T.first(seg_fav >= lv * D) if lv is not None else -1
            # breakeven of the base rules (only before the first add)
            if li == 0 and be >= 0 and (hit < 0 or be < hit) and (nxt < 0 or be < nxt):
                stop_be = P
                hit2 = T.first((L[i + be + 1:] <= stop_be) if s > 0 else (H[i + be + 1:] >= stop_be))
                nxt2 = T.first(fav[i + be + 1:] >= lv * D)
                if hit2 >= 0 and (nxt2 < 0 or hit2 < nxt2):
                    xi, xp = e + i + be + 1 + hit2, stop_be; break
                if nxt2 < 0:
                    xi, xp = j1, O[j1]; break
                i = i + be + 1 + nxt2; stop = stop_be
                pieces.append((add, P + s * lv * D, e + i)); stop = stops[li]; i += 1
                continue
            if hit >= 0 and (nxt < 0 or hit <= nxt):
                xi, xp = e + i + hit, stop; break
            if nxt < 0:
                xi, xp = j1, O[j1]; break
            i = i + nxt
            pieces.append((add, P + s * lv * D, e + i)); stop = stops[li]; i += 1
        hours = (m["t"][xi] - m["t"][e]) / 60
        R = 0.0
        for sz, px, ei in pieces:
            h_ = (m["t"][xi] - m["t"][ei]) / 60
            R += sz * (((xp - px) * s - sl_cost * px - sl_cost * xp - T.C.FUNDING_8H * h_ / 8 * px) / D)
        rows.append(out(sym, r, R, x_idx=xi))
    return rows


VARIANTS = {"base": (v_base, {})}
for frac in (1 / 3, 0.5):
    for tp in (1.0, 1.5, 2.0):
        VARIANTS[f"1 partial {frac:.0%} at +{tp}R"] = (v_partial, dict(frac=frac, tp=tp))
    VARIANTS[f"1 partial {frac:.0%} at +1R, rest to BE"] = (v_partial, dict(frac=frac, tp=1.0, be_rest=True))
for be_R in (0.5, 0.75, 1.0, 1.25, 1.5, 2.0):
    for be_off in (0.0, 0.1, 0.25):
        if be_off < be_R:
            VARIANTS[f"2 BE at +{be_R}R, stop +{be_off}R"] = (v_be, dict(be_R=be_R, be_off=be_off))
for tf in (60, 240):
    for k_atr in (0.0, 0.3):
        for wh in (12, 24, 120):
            VARIANTS[f"3 fail exit {tf//60}h close <entry-{k_atr}R in {wh}h"] = (v_failed, dict(tf=tf, k_atr=k_atr, within_h=wh))
for wh in (24, 48, 96):
    for mr in (1, 2):
        VARIANTS[f"4 re-entry within {wh}h, max {mr}"] = (v_reentry, dict(within_h=wh, max_re=mr))
for add in (0.5, 1.0):
    VARIANTS[f"5 add {add}x at +1R"] = (v_pyramid, dict(add=add, levels=(1.0,)))
    VARIANTS[f"5 add {add}x at +1R and +2R"] = (v_pyramid, dict(add=add, levels=(1.0, 2.0)))


def job(args):
    sym, name = args
    if sym not in BASE:
        BASE[sym] = pd.read_pickle(CACHE)[sym]
    f, kw = VARIANTS[name]
    return name, f(sym, BASE[sym], **kw)


BASE = {}


def score(df):
    df = df.copy()
    df["w"] = df.sym.map(T.WT) * np.where(df.dir < 0, 0.5, 1) * df["size"]
    res = {}
    for pn, a, b in (("dev", "2020-03-01", "2024-01-01"), ("ho", "2024-01-01", "2026-10-01")):
        d = df[(df.entry_time >= a) & (df.entry_time < b)].sort_values("exit_time")
        pr = (d.R * d.w).to_numpy(); e = np.cumsum(pr); dd = np.max(np.maximum.accumulate(np.r_[0, e])[1:] - e)
        st = mx = 0
        for R in d.R.to_numpy():
            st = st + 1 if R < -0.5 else 0; mx = max(mx, st)
        res[pn] = dict(net=e[-1], dd=dd, ratio=e[-1] / dd, n=len(d), profit=(d.R > 0.05).mean() * 100,
                       full=(d.R < -0.5).mean() * 100, streak=mx)
    return res


if __name__ == "__main__":
    if not CACHE.exists():
        with Pool(4) as p:
            bs = p.map(base, COINS)
        pd.to_pickle({s: b for s, b in zip(COINS, bs)}, CACHE)
    names = list(VARIANTS)
    jobs = [(s, n) for s in COINS for n in names]
    with Pool(4) as p:
        res = p.map(job, jobs, chunksize=len(names))
    by = {}
    for n, rows in res:
        by.setdefault(n, []).extend(rows)
    S = {n: score(pd.DataFrame(by[n])) for n in names}
    pickle.dump(dict(rows=by, S=S), open(C.D.CACHE / "ideas_v3_results.pkl", "wb"))
    b = S["base"]
    print(f"{'variant':44s} | {'2020-23: net/DD (x base)  profit% full-loss% streak':52s} | 2024-26 same")
    for n in names:
        s = S[n]
        line = f"{n:44s}"
        for pn in ("dev", "ho"):
            q = s[pn]
            line += f" | {q['net']:6.0f}R {q['dd']:5.1f} {q['ratio']:5.2f} (x{q['ratio']/b[pn]['ratio']:.2f}) {q['profit']:4.0f}% {q['full']:4.0f}% {q['streak']:3d}"
        print(line)
