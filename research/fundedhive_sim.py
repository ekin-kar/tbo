"""FundedHive 1-step evaluation and funded-account simulator for the live bots (gold PDAYT + USDJPY VOLC).

Same minute-level live-equity method as fundingpips_sim.py (floating P&L counts, daily loss measured from max(balance, equity)
at the firm's daily reset, the bots' own account-wide daily stop closes everything and stands down until the next reset),
with FundedHive's rules:
  Low       1% per trade, 2% daily, 5% static max loss, +10% target, fee 1% repaid from profits
  Moderate  1.5% per trade, 3% daily, 6% static max loss, +10% target, fee 2% repaid from profits
  B book    equity below 99% of the start at a daily reset -> a flat 1% debt; back at 100% -> A book
The bots never risk more than 0.85% per trade in any setting tested here, so the per-trade rule is never the binding limit.

Evaluation: random 4-week blocks of the real trades (2y / 3y / 10y windows) plus a fresh account started every week 2016-2024
on the real trade sequence. Funded: 12 months from the first funded day with a buffer ladder and the B-book rules.
Writes research/results/fundedhive_results.json (read by make_fundedhive_html.py).
Usage:  TRADING_DATA=<folder with data> python research/fundedhive_sim.py
"""
import sys, pathlib, json; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent), str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, numba as nb
import fundingpips_sim as F

OUT = pathlib.Path(__file__).resolve().parent / "results" / "fundedhive_results.json"
RESET = 0                     # FundedHive daily reset 00:00 UTC (bots: DailyResetHourUtc = 0)
SLIP = 0.0005                 # slippage when the bot's daily stop closes everything
RULES = {"low": dict(daily=0.02, floor=0.95, target=0.10, fee=0.01, guard=0.015),
         "moderate": dict(daily=0.03, floor=0.94, target=0.10, fee=0.02, guard=0.02)}
WINDOWS = {"2y": ("2024-09-21", "2026-09-19"), "3y": ("2023-09-23", "2026-09-19"), "10y": ("2016-01-09", "2026-09-19")}
REAL = ("2016-01-09", "2024-09-21")          # weekly fresh starts on the real sequence (each has 2 years of data after it)


@nb.njit(cache=True)
def evaluate(ent, ext, sym, Rr, off, fc, fw, rg, rv, e0, guard, slip, horizon, daily, target, floor, reset, minm=1.0, dz=0.0):
    """One evaluation account starting at equity e0 (1.0 = start). Returns (status, minutes): 1 pass, -1 fail, 0 open.
    minm < 1: risk scaling below the START balance 1.0 (bots v1.3 / v5.4): risk x max(minm, (bal - floor) / (1 - floor)) while bal < 1."""
    n = len(ent)
    if n == 0: return 0, 0
    t0 = ent[0]; bal = e0; base = e0; halted = False
    op = np.empty(64, np.int64); sz = np.empty(64); no = 0; j = 0
    m = t0 - (t0 - reset) % 1440
    while True:
        if m - t0 > horizon: return 0, m - t0
        if no == 0:
            if j >= n: return 0, m - t0
            nr = m + 1440 - ((m - reset) % 1440) if (m - reset) % 1440 != 0 else m
            m = min(ent[j], nr)
        eq = bal
        for q in range(no):
            i = op[q]; eq += sz[q] * fc[off[i] + min(m - 1 - ent[i], ext[i] - ent[i])] if m > ent[i] else 0.0
        if (m - reset) % 1440 == 0:
            base = max(bal, eq); halted = False
        while j < n and ent[j] == m:
            if not halted:
                op[no] = j; sz[no] = (rg if sym[j] == 0 else rv) * bal
                if minm < 1.0 and bal < 1.0 - dz: sz[no] *= max(minm, (bal - floor) / ((1.0 - dz) - floor))
                no += 1
            j += 1
        ew = bal
        for q in range(no):
            i = op[q]; ew += sz[q] * fw[off[i] + m - ent[i]]
        if no > 0 and ew <= base * (1 - guard):                     # bot daily stop: close all, stand down
            lvl = base * (1 - guard) - slip * base
            if lvl <= base * (1 - daily) or lvl <= floor: return -1, m - t0
            bal = lvl; no = 0; halted = True
        elif ew <= base * (1 - daily) or ew <= floor:
            return -1, m - t0
        q = 0
        while q < no:
            i = op[q]
            if ext[i] == m:
                bal += sz[q] * Rr[i]; op[q] = op[no - 1]; sz[q] = sz[no - 1]; no -= 1
            else: q += 1
        if bal >= 1 + target: return 1, m - t0
        m += 1


@nb.njit(cache=True)
def funded(ent, ext, sym, Rr, off, fc, fw, thr, RG, RV, bb_hi, bb_lo, calm_days, fee, guard, slip, horizon, daily, floor, reset,
           minm=1.0, bbo=1):
    """Funded account with a buffer ladder. Risk tier chosen at each daily reset from buffer = equity - 1 - debt.
    B book: equity < 0.99 at a reset -> B book, debt += 1%; back at >= 1.00 -> A book, first tier for calm_days resets.
    Debt (fee, B-book debt) is repaid at once from any balance above the start, so the balance stays at the start until it is 0.
    minm < 1: the bots' risk scaling below the start (x max(minm, (bal - floor) / (1 - floor))). bbo = 0: no manual B-book risk
    cuts (the ladder's first row applies in B book; the bots' scaling does the cutting).
    Returns (lost, withdrawable at the end = max(balance - 1 - debt, 0), ever in B book)."""
    n = len(ent); t0 = ent[0]; bal = 1.0; base = 1.0; halted = False
    debt = fee; inb = False; calm = 0; ever = 0
    rg = RG[0]; rv = RV[0]
    op = np.empty(64, np.int64); sz = np.empty(64); no = 0; j = 0
    m = t0 - (t0 - reset) % 1440
    while True:
        if m - t0 > horizon or (j >= n and no == 0):
            return 0, max(bal - 1.0 - debt, 0.0), ever
        if no == 0:
            nr = m + 1440 - ((m - reset) % 1440) if (m - reset) % 1440 != 0 else m
            m = min(ent[j], nr) if j < n else nr
        eq = bal
        for q in range(no):
            i = op[q]; eq += sz[q] * fc[off[i] + min(m - 1 - ent[i], ext[i] - ent[i])] if m > ent[i] else 0.0
        if (m - reset) % 1440 == 0:
            base = max(bal, eq); halted = False
            if (not inb) and eq < 0.99:
                inb = True; debt += 0.01; ever = 1
            elif inb and eq >= 1.0:
                inb = False; calm = calm_days
            if inb and bbo == 1:
                if eq >= 0.995:
                    rg = bb_hi[0]; rv = bb_hi[1]
                else:
                    rg = bb_lo[0]; rv = bb_lo[1]
            elif calm > 0 and bbo == 1:
                rg = RG[0]; rv = RV[0]; calm -= 1
            else:
                buf = (eq - 1.0 - debt) * 100.0; k = 0
                for t in range(len(thr)):
                    if buf >= thr[t]: k = t
                rg = RG[k]; rv = RV[k]
        while j < n and ent[j] == m:
            if not halted:
                w = (rg if sym[j] == 0 else rv) * bal
                if minm < 1.0 and bal < 1.0: w *= max(minm, (bal - floor) / (1.0 - floor))
                op[no] = j; sz[no] = w; no += 1
            j += 1
        ew = bal
        for q in range(no):
            i = op[q]; ew += sz[q] * fw[off[i] + m - ent[i]]
        if no > 0 and ew <= base * (1 - guard):
            lvl = base * (1 - guard) - slip * base
            if lvl <= floor or lvl <= base * (1 - daily): return 1, 0.0, ever
            bal = lvl; no = 0; halted = True
        elif ew <= floor or ew <= base * (1 - daily):
            return 1, 0.0, ever
        q = 0
        while q < no:
            i = op[q]
            if ext[i] == m:
                bal += sz[q] * Rr[i]; op[q] = op[no - 1]; sz[q] = sz[no - 1]; no -= 1
            else: q += 1
        if debt > 0.0 and bal > 1.0:                                # FundedHive: profit above the start repays the debt at once
            r = min(bal - 1.0, debt); bal -= r; debt -= r
        m += 1


def paths(D, a, b, N, blocks, seed):
    """Index and time shift of N paths built from `blocks` random Saturday-aligned 4-week windows of [a, b)."""
    ent = D[0]; rng = np.random.default_rng(seed); W = F.WEEK
    starts = np.arange(F.sat(a), F.sat(b) - 4 * W, W); lo = np.searchsorted(ent, starts); hi = np.searchsorted(ent, starts + 4 * W)
    for p in range(N):
        pick = rng.integers(0, len(starts), blocks); idx = np.concatenate([np.arange(lo[q], hi[q]) for q in pick])
        sh = np.repeat(np.arange(blocks) * 4 * W - starts[pick] + starts[0], hi[pick] - lo[pick])
        yield idx, sh


def summ(o):
    ok = o[:, 0] == 1; mo = o[ok, 1] / 1440 / 30.4
    return dict(passp=round(100 * ok.mean(), 1), fail=round(100 * (o[:, 0] == -1).mean(), 1),
                med=round(float(np.median(mo)), 1) if ok.any() else None)


def eval_cell(D, rule, rg, rv, e0=1.0, N=3000, minm=1.0):
    ent, ext, sym, Rr, off, fc, fw = D; R_ = RULES[rule]; out = {}
    args = lambda: (rg / 100, rv / 100, e0, R_["guard"], SLIP)
    tail = (R_["daily"], R_["target"], R_["floor"], RESET, minm)
    for w, (a, b) in WINDOWS.items():
        o = np.array([evaluate(ent[i] + s, ext[i] + s, sym[i], Rr[i], off[i], fc, fw, *args(), 26 * 28 * 1440, *tail)
                      for i, s in paths(D, a, b, N, 26, 7)], float)
        out[w] = summ(o)
    o = []
    for s in range(F.sat(REAL[0]), F.sat(REAL[1]), F.WEEK):
        k = np.searchsorted(ent, s)
        o.append(evaluate(ent[k:], ext[k:], sym[k:], Rr[k:], off[k:], fc, fw, *args(), 24 * 30 * 1440, *tail))
    out["real"] = summ(np.array(o, float))
    return out


def funded_cell(D, rule, thr, RG, RV, N=2500, minm=1.0, bbo=1):
    ent, ext, sym, Rr, off, fc, fw = D; R_ = RULES[rule]; out = {}
    for w, (a, b) in WINDOWS.items():
        o = np.array([funded(ent[i] + s, ext[i] + s, sym[i], Rr[i], off[i], fc, fw, np.array(thr, float), np.array(RG) / 100,
                             np.array(RV) / 100, np.array([0.0025, 0.0035]), np.array([0.0015, 0.0020]), 10, R_["fee"],
                             R_["guard"], SLIP, 365 * 1440, R_["daily"], R_["floor"], RESET, minm, bbo)
                      for i, s in paths(D, a, b, N, 14, 5)], float)
        out[w] = dict(lost=round(100 * o[:, 0].mean(), 1), p25=round(100 * np.percentile(o[:, 1], 25), 1),
                      med=round(100 * np.median(o[:, 1]), 1), p75=round(100 * np.percentile(o[:, 1], 75), 1),
                      bbook=int(round(100 * o[:, 2].mean())))
    return out


# (gold, USDJPY, shrink minimum); 1.0 = fixed risk. Oct 2026 recommendation: Low 0.4/0.5, min 0.3x. (Moderate dropped 5 Oct 2026.)
EVAL_RISKS = {"low": [(0.3, 0.4, 1.0), (0.4, 0.5, 1.0), (0.5, 0.6, 1.0), (0.6, 0.7, 1.0), (0.6, 0.8, 1.0), (0.7, 0.9, 1.0),
                      (0.3, 0.4, 0.3), (0.4, 0.5, 0.6), (0.4, 0.5, 0.5), (0.4, 0.5, 0.3), (0.5, 0.6, 0.5), (0.5, 0.6, 0.3)]}
# evaluation already in profit (Low): (start equity, gold, USDJPY, shrink minimum below the ORIGINAL start)
AHEAD = [(1.02, 0.4, 0.5, 0.3), (1.02, 0.5, 0.6, 0.3), (1.04, 0.4, 0.5, 0.3), (1.04, 0.5, 0.6, 0.3), (1.06, 0.4, 0.5, 0.3), (1.06, 0.5, 0.6, 0.3)]
def ekey(prefix, rg, rv, mm): return f"{prefix}/{rg}/{rv}" + ("" if mm >= 1 else f"/m{mm}")
LADDERS = {
    "low": {
        "old": ([-99, 1, 2, 4, 7], [0.15, 0.25, 0.40, 0.55, 0.65], [0.20, 0.35, 0.50, 0.70, 0.85]),
        "old_capped": ([-99, 1, 2, 4, 7], [0.15, 0.25, 0.35, 0.45, 0.50], [0.20, 0.30, 0.40, 0.50, 0.60]),
        "rec": ([-99, 1, 2, 4], [0.25, 0.30, 0.40, 0.50], [0.35, 0.40, 0.50, 0.60]),
        "rec_cap_0.6": ([-99, 1, 3, 5], [0.25, 0.35, 0.45, 0.60], [0.35, 0.45, 0.55, 0.70]),
        "flat_0.4": ([-99], [0.40], [0.50]),
    },
}
# Oct 2026 (5 Oct): funded Low = the "rec" ladder + the bots' risk scaling below the start (min 0.3x), no manual B-book cuts.
# (ladder name, shrink minimum, manual B-book cuts 1/0)
FUNDED_EXTRA = {"low": {"rec_shrink": ("rec", 0.3, 0), "rec_shrink_bb": ("rec", 0.3, 1), "flat_0.4_shrink": ("flat_0.4", 0.3, 0)}}

if __name__ == "__main__":
    D = F.load(); print("trades", len(D[0]), flush=True)
    res = json.load(open(OUT)) if OUT.exists() else {}
    for rule, risks in EVAL_RISKS.items():
        for rg, rv, mm in risks:
            key = ekey(f"eval/{rule}", rg, rv, mm)
            if key not in res: res[key] = eval_cell(D, rule, rg, rv, minm=mm); print(key, res[key], flush=True)
            json.dump(res, open(OUT, "w"), indent=1)
    for e0, rg, rv, mm in AHEAD:
        key = ekey(f"ahead/low/{e0}", rg, rv, mm)
        if key not in res: res[key] = eval_cell(D, "low", rg, rv, e0=e0, minm=mm); print(key, res[key], flush=True)
        json.dump(res, open(OUT, "w"), indent=1)
    for rule, lads in LADDERS.items():
        for name, (thr, RG, RV) in lads.items():
            key = f"funded/{rule}/{name}"
            if key not in res: res[key] = funded_cell(D, rule, thr, RG, RV); print(key, res[key], flush=True)
            json.dump(res, open(OUT, "w"), indent=1)
    for rule, ex in FUNDED_EXTRA.items():
        for name, (lad, mm, bbo) in ex.items():
            key = f"funded/{rule}/{name}"; thr, RG, RV = LADDERS[rule][lad]
            if key not in res: res[key] = funded_cell(D, rule, thr, RG, RV, minm=mm, bbo=bbo); print(key, res[key], flush=True)
            json.dump(res, open(OUT, "w"), indent=1)
    res = {k: v for k, v in res.items() if "/moderate" not in k}                # Moderate dropped
    json.dump(res, open(OUT, "w"), indent=1)
    print("written", OUT)
