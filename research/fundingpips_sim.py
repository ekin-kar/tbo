"""Funding Pips 1-Step Flex ($10k, 2% daily option) evaluation simulator for the live bots (gold PDAYT + USDJPY VOLC).

Minute-level: every open position's floating P&L is tracked from the m1 bars, because the firm measures the daily loss on live
equity against max(balance, equity) at its 00:00 platform reset (21:00 UTC), and ~26% of USDJPY trades are open across that reset.
Rules: target +12% realised, static floor 88% (equity), daily loss 2% of the reset baseline (equity, real time), no per-trade limit.
The bots' own account-wide daily stop (reset hour 21 UTC) closes everything at `guard` (+ `slip` slippage) and stands down until
the next reset. Risk is a % of balance at entry (as the bots size it).

Two tests:
  * real sequence: a fresh account starts on every trading week, takes the actual trades in actual order;
  * bootstrap: 10,000 paths built from random 4-week blocks (Saturday-aligned, so time of day / weekday stay real).
Usage:  TRADING_DATA=<folder with data> python research/fundingpips_sim.py
"""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent), str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, numba as nb
import R, ideas as X

RESET = 21 * 60          # firm reset minute of day, UTC
TARGET, FLOOR, DAILY = 1.12, 0.88, 0.02

def clean(sym, tr, adj):
    t = R.get(sym)["t"]; gap = np.r_[0, np.diff(t)]
    holes = pd.to_datetime(t[np.flatnonzero(gap > 120)] * 60, unit="s").values.astype("datetime64[m]")
    a = tr.entry_time.values.astype("datetime64[m]"); b = tr.exit_time.values.astype("datetime64[m]"); bad = np.zeros(len(tr), bool)
    for x in holes: bad |= (a < x) & (b >= x)
    tr = tr[~bad].copy(); tr["R"] = tr.R - adj; return tr

def floats(sym, tr):
    """Per-minute floating R (close and adverse extreme) for every trade, flat array + offsets. Minute 0 = entry minute."""
    m = R.get(sym); t = m["t"]; sp = m["sp_main"]
    ent = (tr.entry_time.values.astype("datetime64[m]").astype(np.int64)); ext = (tr.exit_time.values.astype("datetime64[m]").astype(np.int64))
    fc, fw, off = [], [], []; n = 0
    for e0, e1, d, px, sl, r in zip(ent, ext, tr.dir.values, tr.entry.values, tr.sl_dist.values, tr.R.values):
        i0, i1 = np.searchsorted(t, e0), np.searchsorted(t, e1, side="right")
        L = e1 - e0 + 1; c = np.full(L, np.nan); w = np.full(L, np.nan); k = t[i0:i1] - e0
        if d > 0: c[k] = (m["c"][i0:i1] - px) / sl; w[k] = (m["l"][i0:i1] - px) / sl
        else:     c[k] = (px - m["c"][i0:i1] - sp[i0:i1]) / sl; w[k] = (px - m["h"][i0:i1] - sp[i0:i1]) / sl
        c = pd.Series(c).ffill().fillna(0).to_numpy().copy(); w = pd.Series(w).ffill().fillna(0).to_numpy().copy()
        w = np.maximum(w, min(-1.0, r) - 0.05); c[-1] = r; w[-1] = min(w[-1], r)
        fc.append(c); fw.append(w); off.append(n); n += L
    return ent, ext, np.concatenate(fc), np.concatenate(fw), np.array(off)

@nb.njit(cache=True)
def sim(ent, ext, sym, Rr, off, fc, fw, rg, rv, guard, slip, horizon, daily=DAILY, cap=0.0, minm=1.0, dz=0.0):
    """minm < 1: risk scaling below the start (bots v1.4 / v5.5): full risk while bal >= 1 - dz, below that risk x
    max(minm, (bal - FLOOR) / ((1 - dz) - FLOOR)). dz = "shrink from" as a fraction (0 = shrink from the start).
    cap > 0: size-to-room - a new trade's risk is cut so that it plus every open trade stopped out cannot take equity
    below baseline x (1 - cap); skipped if less than 10% of its normal risk is left."""
    """One account over one trade list (sorted by entry, minutes). Returns (status, minutes to finish); status 1 pass, -1 fail, 0 open."""
    n = len(ent)
    if n == 0: return 0, 0
    t0 = ent[0]; bal = 1.0; base = 1.0; halted = False
    op = np.empty(64, np.int64); sz = np.empty(64); no = 0; j = 0
    m = t0 - (t0 - RESET) % 1440                                    # last reset before the first trade
    while True:
        if m - t0 > horizon: return 0, m - t0
        if no == 0:                                                  # jump to the next entry or reset
            if j >= n: return 0, m - t0
            nr = m + 1440 - ((m - RESET) % 1440) if (m - RESET) % 1440 != 0 else m
            m = min(ent[j], nr)
        # equity before anything happens this minute
        eq = bal
        for q in range(no):
            i = op[q]; eq += sz[q] * fc[off[i] + min(m - 1 - ent[i], ext[i] - ent[i])] if m > ent[i] else 0.0
        if (m - RESET) % 1440 == 0:
            base = max(bal, eq); halted = False
        while j < n and ent[j] == m:
            if not halted:
                want = (rg if sym[j] == 0 else rv) * bal
                if minm < 1.0 and bal < 1.0 - dz: want *= max(minm, (bal - FLOOR) / ((1.0 - dz) - FLOOR))
                if cap > 0:
                    room = eq - base * (1 - cap)
                    for q in range(no):
                        i = op[q]; room -= sz[q] * (1.0 + (fc[off[i] + min(m - 1 - ent[i], ext[i] - ent[i])] if m > ent[i] else 0.0))
                    room /= 1.05                                 # stop slippage allowance
                    if room < want: want = room if room >= 0.1 * want else 0.0
                if want > 0:
                    op[no] = j; sz[no] = want; no += 1
            j += 1
        ew = bal
        for q in range(no):
            i = op[q]; ew += sz[q] * fw[off[i] + m - ent[i]]
        if no > 0 and ew <= base * (1 - guard):                     # bot daily stop: close all, stand down
            lvl = base * (1 - guard) - slip * base
            if lvl <= base * (1 - daily) or lvl <= FLOOR: return -1, m - t0
            bal = lvl; no = 0; halted = True
        elif ew <= base * (1 - daily) or ew <= FLOOR:
            return -1, m - t0
        q = 0
        while q < no:                                                # exits this minute
            i = op[q]
            if ext[i] == m:
                bal += sz[q] * Rr[i]; op[q] = op[no - 1]; sz[q] = sz[no - 1]; no -= 1
            else: q += 1
        if bal >= TARGET: return 1, m - t0
        m += 1

def load():
    G = clean("XAUUSD", R.run("XAUUSD", X.pday_trend(R.get("XAUUSD")), "main"), 0.02)
    V = clean("USDJPY", R.run("USDJPY", X.volc_f(R.get("USDJPY")), "main", max_bars=20 * 60), 0.002)
    parts = []; base = 0
    for s, tr in ((0, G), (1, V)):
        e0, e1, c, w, o = floats("XAUUSD" if s == 0 else "USDJPY", tr)
        parts.append((e0, e1, np.full(len(tr), s), tr.R.values, o + base, c, w)); base += len(c)
    ent, ext, sym, Rr, off = (np.concatenate([p[k] for p in parts]) for k in range(5))
    fc = np.concatenate([p[5] for p in parts]); fw = np.concatenate([p[6] for p in parts])
    o = np.lexsort((ext, ent)); return ent[o], ext[o], sym[o], Rr[o], off[o], fc, fw

WEEK = 7 * 1440
def sat(ts): return int(pd.Timestamp(ts).to_period("W-FRI").start_time.value // 60_000_000_000)   # Saturday 00:00 on/before

def rolling(D, rg, rv, guard, slip, a, b, horizon_m=24, daily=DAILY, cap=0.0, minm=1.0, dz=0.0):
    ent, ext, sym, Rr, off, fc, fw = D; out = []
    for s in range(sat(a), sat(b), WEEK):
        k = np.searchsorted(ent, s); st, dt = sim(ent[k:], ext[k:], sym[k:], Rr[k:], off[k:], fc, fw, rg, rv, guard, slip, horizon_m * 30 * 1440, daily, cap, minm, dz)
        out.append((st, dt / 1440))
    return np.array(out)

def boot(D, rg, rv, guard, slip, a, b, N=10000, blocks=26, seed=7, daily=DAILY, cap=0.0, minm=1.0, dz=0.0):
    """Paths of `blocks` x 4 weeks (~24 months) from random Saturday-aligned 4-week windows of [a, b)."""
    ent, ext, sym, Rr, off, fc, fw = D; rng = np.random.default_rng(seed)
    starts = np.arange(sat(a), sat(b) - 4 * WEEK, WEEK); lo = np.searchsorted(ent, starts); hi = np.searchsorted(ent, starts + 4 * WEEK)
    out = np.empty((N, 2))
    for p in range(N):
        pick = rng.integers(0, len(starts), blocks); idx = np.concatenate([np.arange(lo[q], hi[q]) for q in pick])
        shift = np.repeat(np.arange(blocks) * 4 * WEEK - starts[pick] + starts[0], hi[pick] - lo[pick])
        st, dt = sim(ent[idx] + shift, ext[idx] + shift, sym[idx], Rr[idx], off[idx], fc, fw, rg, rv, guard, slip, 24 * 30 * 1440, daily, cap, minm, dz)
        out[p] = st, dt / 1440
    return out

def summ(o):
    ok = o[:, 0] == 1; d = o[ok, 1] / 30.4
    q = lambda x: np.percentile(d, x) if ok.any() else np.nan
    return dict(passp=100 * ok.mean(), fail=100 * (o[:, 0] == -1).mean(), open_=100 * (o[:, 0] == 0).mean(),
                p25=q(25), med=q(50), p75=q(75), in6=100 * (ok & (o[:, 1] <= 182)).mean(), in12=100 * (ok & (o[:, 1] <= 365)).mean())

if __name__ == "__main__":
    D = load(); print("trades", len(D[0]), flush=True)
    # (gold, USDJPY, shrink minimum, shrink from): fixed rows, then the risk-scaling rows
    # (4 Oct 2026: chosen 0.7 / 0.9, full risk until -4%, then shrinking to min 0.3x)
    RISKS = [(0.4, 0.5, 1.0, 0.0), (0.5, 0.6, 1.0, 0.0), (0.6, 0.8, 1.0, 0.0), (0.7, 0.9, 1.0, 0.0), (0.8, 1.0, 1.0, 0.0), (1.0, 1.2, 1.0, 0.0),
             (0.6, 0.8, 0.5, 0.0), (0.7, 0.9, 0.6, 0.0), (0.7, 0.9, 0.5, 0.03), (0.7, 0.9, 0.4, 0.04), (0.7, 0.9, 0.3, 0.04),
             (0.7, 0.9, 0.3, 0.05), (0.8, 1.0, 0.3, 0.04), (0.6, 0.8, 0.3, 0.04)]
    GUARD = 1.5
    WIN = {"2y": ("2024-09-21", "2026-09-19"), "3y": ("2023-09-23", "2026-09-19"), "10y": ("2016-01-09", "2026-09-19")}
    rows = []
    for rg, rv, mm, dz in RISKS:
        r = dict(gold=rg, jpy=rv, minm=mm, dz=dz, guard=GUARD)
        for w, (a, b) in WIN.items():
            s = summ(boot(D, rg / 100, rv / 100, GUARD / 100, 0.0005, a, b, N=4000, minm=mm, dz=dz))
            r.update({f"{w}_{k}": v for k, v in s.items()})
        s = summ(rolling(D, rg / 100, rv / 100, GUARD / 100, 0.0005, "2016-01-09", "2024-09-21", minm=mm, dz=dz))
        r.update({f"roll_{k}": v for k, v in s.items()})
        rows.append(r); print({k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items()}, flush=True)
    pd.DataFrame(rows).round(2).to_csv(pathlib.Path(__file__).resolve().parent / "results" / "fundingpips_results.csv", index=False)
