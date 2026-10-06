"""Funding Pips 1-Step Flex funded (Master) account: 12 months with bi-weekly payouts, for the live bots.
Same minute-level model as fundingpips_sim.py (static 88% floor, 2% daily from max(balance, equity) at 21:00 UTC, bot daily stop).
Payouts: every 14 calendar days, at the first moment with no open position, if balance >= start x (1 + keep + 1%) the profit above
start x (1 + keep) is withdrawn and the trader receives 80% of it. keep = buffer left in the account (0 = withdraw everything).
Risk scaling (bots v1.4+ / v5.5): minm < 1 -> full risk while bal >= 1 - dz, below that risk x max(minm, (bal - floor) / ((1 - dz) - floor)).
Usage:  TRADING_DATA=<folder with data> python research/fundingpips_funded.py
"""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent), str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, numba as nb
import fundingpips_sim as F

@nb.njit(cache=True)
def fund(ent, ext, sym, Rr, off, fc, fw, rg, rv, guard, slip, horizon, keep, daily=0.02, floor=0.88, split=0.8, minm=1.0, dz=0.0):
    """Returns (lost, paid as fraction of the account, minutes to first payout or -1)."""
    n = len(ent)
    t0 = ent[0]; bal = 1.0; base = 1.0; halted = False; paid = 0.0; first = -1
    nextpay = t0 + 14 * 1440
    op = np.empty(64, np.int64); sz = np.empty(64); no = 0; j = 0
    m = t0 - (t0 - F.RESET) % 1440
    while True:
        if m - t0 > horizon or (j >= n and no == 0): return 0, paid, first
        if no == 0:
            if m >= nextpay:                                          # payout window, flat account
                if bal >= 1.0 + keep + 0.01:
                    paid += split * (bal - 1.0 - keep); bal = 1.0 + keep
                    if first < 0: first = m - t0
                nextpay = m + 14 * 1440
            nr = m + 1440 - ((m - F.RESET) % 1440) if (m - F.RESET) % 1440 != 0 else m
            m = min(ent[j], nr, max(nextpay, m))
            if m - t0 > horizon: return 0, paid, first
        eq = bal
        for q in range(no):
            i = op[q]; eq += sz[q] * fc[off[i] + min(m - 1 - ent[i], ext[i] - ent[i])] if m > ent[i] else 0.0
        if (m - F.RESET) % 1440 == 0:
            base = max(bal, eq); halted = False
        while j < n and ent[j] == m:
            if not halted:
                w = (rg if sym[j] == 0 else rv) * bal
                if minm < 1.0 and bal < 1.0 - dz: w *= max(minm, (bal - floor) / ((1.0 - dz) - floor))
                op[no] = j; sz[no] = w; no += 1
            j += 1
        ew = bal
        for q in range(no):
            i = op[q]; ew += sz[q] * fw[off[i] + m - ent[i]]
        if no > 0 and ew <= base * (1 - guard):
            lvl = base * (1 - guard) - slip * base
            if lvl <= base * (1 - daily) or lvl <= floor: return 1, paid, first
            bal = lvl; no = 0; halted = True
        elif ew <= base * (1 - daily) or ew <= floor:
            return 1, paid, first
        q = 0
        while q < no:
            i = op[q]
            if ext[i] == m:
                bal += sz[q] * Rr[i]; op[q] = op[no - 1]; sz[q] = sz[no - 1]; no -= 1
            else: q += 1
        m += 1

def boot(D, rg, rv, guard, keep, a, b, N=4000, blocks=13, seed=11, minm=1.0, dz=0.0):
    ent, ext, sym, Rr, off, fc, fw = D; rng = np.random.default_rng(seed); W = F.WEEK
    starts = np.arange(F.sat(a), F.sat(b) - 4 * W, W); lo = np.searchsorted(ent, starts); hi = np.searchsorted(ent, starts + 4 * W)
    out = np.empty((N, 3))
    for p in range(N):
        pick = rng.integers(0, len(starts), blocks); idx = np.concatenate([np.arange(lo[q], hi[q]) for q in pick])
        shift = np.repeat(np.arange(blocks) * 4 * W - starts[pick] + starts[0], hi[pick] - lo[pick])
        out[p] = fund(ent[idx] + shift, ext[idx] + shift, sym[idx], Rr[idx], off[idx], fc, fw, rg, rv, guard, 0.0005, blocks * 28 * 1440, keep,
                      0.02, 0.88, 0.8, minm, dz)
    return out

if __name__ == "__main__":
    D = F.load()
    W = {"2y": ("2024-09-21", "2026-09-19"), "3y": ("2023-09-23", "2026-09-19"), "10y": ("2016-01-09", "2026-09-19")}
    rows = []
    for rg, rv in [(0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.8), (0.7, 0.9), (0.8, 1.0), (1.0, 1.2)]:
        for keep, minm, dz in ((0.01, 1.0, 0.0), (0.01, 0.3, 0.04)):        # $100 kept (5 Oct 2026); no scaling / full to -4% then min 0.3x
            r = dict(gold=rg, jpy=rv, keep=keep, minm=minm, dz=dz)
            for w, (a, b) in W.items():
                o = boot(D, rg / 100, rv / 100, 0.015, keep, a, b, minm=minm, dz=dz)
                pay = o[:, 1] * 10000; fp = o[o[:, 2] >= 0, 2] / 1440
                r.update({f"{w}_lost%": round(100 * o[:, 0].mean(), 1), f"{w}_paid_p25": round(np.percentile(pay, 25)),
                          f"{w}_paid_med": round(np.median(pay)), f"{w}_paid_p75": round(np.percentile(pay, 75)),
                          f"{w}_first_pay_days": round(np.median(fp)) if len(fp) else -1})
            rows.append(r); print(r, flush=True)
    pd.DataFrame(rows).to_csv(pathlib.Path(__file__).resolve().parent / "results" / "fundingpips_funded_results.csv", index=False)
