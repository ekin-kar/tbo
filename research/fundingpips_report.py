"""Data for fundingpips_plan.html: full journeys challenge -> funded for the Funding Pips 1-Step Flex $10k account.
Each path is built from random 4-week blocks of the bots' real trades (minute-level floating P&L, firm rules as in
fundingpips_sim.py). Challenge: gold 0.7% / USDJPY 0.9% full risk until -4%, then risk scaling to min 0.3x, until +12% (pass) or a breach (fail). After a pass the SAME path
continues as the funded account: gold 0.5% / USDJPY 0.6%, for 12 months, with bi-weekly payouts for every combination of
buffer (KEEPS, left in the account) and trigger (TRIGS, pay out only when the balance is >= start + buffer + trigger): everything
above start + buffer is withdrawn. Payouts are stored before the profit split; the page applies it (default 80%). Both phases: bot daily stop 1.5%, firm daily limit 2%, static floor 88%, reset 21:00 UTC.
Writes research/results/fundingpips_plan_data.json.
Usage:  TRADING_DATA=<folder with data> python research/fundingpips_report.py
"""
import sys, pathlib, json; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent), str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, numba as nb
import fundingpips_sim as F

CH = (0.007, 0.009); CH_MINM, CH_DZ = 0.3, 0.04; FU = (0.005, 0.006); FU_MINM, FU_DZ = 0.3, 0.04; GUARD, SLIP = 0.015, 0.0005   # challenge 0.7/0.9, full risk until -4%, then risk scaling to min 0.3x
KEEP, SPLIT, PAY_EVERY, FUND_DELAY = 0.01, 0.8, 14, 3          # FUND_DELAY: days from passing to trading the funded account
HCH, HFU = 730, 365                                              # days simulated per phase

@nb.njit(cache=True)
def phase(ent, ext, sym, Rr, off, fc, fw, j0, t0, rg, rv, guard, slip, target, keep, split, pay_every, horizon_days, rec, trig=0.01, minm=1.0, dz=0.0):
    """One phase from minute t0, trades from index j0. target > 0: challenge (stop at +target); target <= 0: funded with payouts.
    rec[d] = balance at the end of day d (challenge) or cumulative payout (funded, rec has 2 rows: balance, paid).
    Returns (status 1 pass / -1 fail / 0 running, end minute, next trade index, paid, first payout minute or -1)."""
    n = len(ent); bal = 1.0; base = 1.0; halted = False; paid = 0.0; first = -1
    nextpay = t0 + pay_every * 1440
    op = np.empty(64, np.int64); sz = np.empty(64); no = 0; j = j0
    while j < n and ent[j] < t0: j += 1
    m = t0 - (t0 - F.RESET) % 1440
    lastd = -1; H = horizon_days * 1440
    while True:
        d = (m - t0) // 1440
        if d > lastd:
            for k in range(max(lastd, 0), min(d, horizon_days)):
                rec[0, k] = bal; rec[1, k] = paid
            lastd = d
        if m - t0 >= H or (j >= n and no == 0):
            for k in range(max(lastd, 0), horizon_days):
                rec[0, k] = bal; rec[1, k] = paid
            return 0, m, j, paid, first
        if no == 0:
            if target <= 0 and m >= nextpay:
                if bal >= 1.0 + keep + trig:
                    paid += split * (bal - 1.0 - keep); bal = 1.0 + keep
                    if first < 0: first = m
                nextpay = m + pay_every * 1440
            nr = m + 1440 - ((m - F.RESET) % 1440) if (m - F.RESET) % 1440 != 0 else m
            nm = min(ent[j], nr)
            if target <= 0: nm = min(nm, max(nextpay, m))
            nm = min(nm, t0 + H)
            if nm > m:
                m = nm
                continue
        eq = bal
        for q in range(no):
            i = op[q]; eq += sz[q] * fc[off[i] + min(m - 1 - ent[i], ext[i] - ent[i])] if m > ent[i] else 0.0
        if (m - F.RESET) % 1440 == 0:
            base = max(bal, eq); halted = False
        while j < n and ent[j] == m:
            if not halted:
                op[no] = j; sz[no] = (rg if sym[j] == 0 else rv) * bal
                if minm < 1.0 and bal < 1.0 - dz: sz[no] *= max(minm, (bal - F.FLOOR) / ((1.0 - dz) - F.FLOOR))
                no += 1
            j += 1
        ew = bal
        for q in range(no):
            i = op[q]; ew += sz[q] * fw[off[i] + m - ent[i]]
        fail = False
        if no > 0 and ew <= base * (1 - guard):
            lvl = base * (1 - guard) - slip * base
            if lvl <= base * (1 - F.DAILY) or lvl <= F.FLOOR: fail = True
            else:
                bal = lvl; no = 0; halted = True
        elif ew <= base * (1 - F.DAILY) or ew <= F.FLOOR:
            fail = True
        if fail:
            bal = min(bal, F.FLOOR)
            for k in range(max(lastd, 0), horizon_days):
                rec[0, k] = bal; rec[1, k] = paid
            return -1, m, j, paid, first
        q = 0
        while q < no:
            i = op[q]
            if ext[i] == m:
                bal += sz[q] * Rr[i]; op[q] = op[no - 1]; sz[q] = sz[no - 1]; no -= 1
            else: q += 1
        if target > 0 and bal >= 1.0 + target:
            for k in range(max(lastd, 0), horizon_days):
                rec[0, k] = bal; rec[1, k] = paid
            return 1, m, j, paid, first
        m += 1

KEEPS = (0.0, 0.01, 0.02, 0.03, 0.04, 0.05)            # buffer left in the account after a payout
TRIGS = (0.005, 0.01, 0.015, 0.02, 0.03)               # payout only when the balance is this far above start + buffer
WEEKS = np.arange(0, HFU, 7)

WINDOWS = {"6m": ("2026-03-21", "2026-09-19"), "1y": ("2025-09-20", "2026-09-19"), "2y": ("2024-09-21", "2026-09-19"),
           "3y": ("2023-09-23", "2026-09-19"), "5y": ("2021-09-18", "2026-09-19"), "10y": ("2016-01-09", "2026-09-19")}
POOL = 200                                              # example journeys stored per period (seed button)

def combo_key(k, t): return f"{k * 100:g}/{t * 100:g}"

def journeys(D, a, b, N, seed):
    """Challenge once per path, then the funded year for every (buffer, trigger) combination on the same path.
    Payouts are recorded gross (before the profit split); the page applies the split."""
    ent, ext, sym, Rr, off, fc, fw = D; rng = np.random.default_rng(seed); W = F.WEEK
    starts = np.arange(F.sat(a), F.sat(b) - 4 * W, W); lo = np.searchsorted(ent, starts); hi = np.searchsorted(ent, starts + 4 * W)
    blocks = (HCH + HFU + FUND_DELAY) // 28 + 2
    C = [(k, t) for k in KEEPS for t in TRIGS]
    ch_bal = np.zeros((N, HCH)); res = np.full((N, 3), np.nan)          # status, pass day, fail day
    fres = np.full((len(C), N, 3), np.nan)                               # lost, paid 12m, first payout day since funded start
    fpaid = np.full((len(C), N, len(WEEKS)), np.nan)
    rec_c = np.zeros((2, HCH)); rec_f = np.zeros((2, HFU))
    for p in range(N):
        pick = rng.integers(0, len(starts), blocks); idx = np.concatenate([np.arange(lo[q], hi[q]) for q in pick])
        shift = np.repeat(np.arange(blocks) * 4 * W - starts[pick] + starts[0], hi[pick] - lo[pick])
        e0 = ent[idx] + shift; e1 = ext[idx] + shift
        t0 = int(e0[0]) - int(e0[0]) % 1440
        args = (e0, e1, sym[idx], Rr[idx], off[idx], fc, fw)
        st, mend, jn, _, _ = phase(*args, 0, t0, CH[0], CH[1], GUARD, SLIP, 0.12, 0.0, 1.0, PAY_EVERY, HCH, rec_c, 0.01, CH_MINM, CH_DZ)
        ch_bal[p] = rec_c[0]; res[p, 0] = st
        if st == 1: res[p, 1] = (mend - t0) / 1440.0
        if st == -1: res[p, 2] = (mend - t0) / 1440.0
        if st != 1: continue
        tf = int(mend) + FUND_DELAY * 1440
        for c, (k, t) in enumerate(C):
            sf, _, _, paid, first = phase(*args, jn, tf, FU[0], FU[1], GUARD, SLIP, 0.0, k, 1.0, PAY_EVERY, HFU, rec_f, t, FU_MINM, FU_DZ)
            fres[c, p] = (sf == -1, paid, (first - tf) / 1440.0 if first >= 0 else np.nan)
            fpaid[c, p] = rec_f[1, WEEKS]
    return ch_bal, res, fres, fpaid

def summarise(ch_bal, res, fres, fpaid, seed=3):
    N = len(res); ok = res[:, 0] == 1; pd_ = res[ok, 1]; days = np.arange(HCH)
    pass_cum = [round(100 * np.mean(ok & (res[:, 1] <= d)), 2) for d in days]
    fail_cum = [round(100 * np.mean((res[:, 0] == -1) & (res[:, 2] <= d)), 2) for d in days]
    pct = lambda a, q: np.nanpercentile(a, q, axis=0)
    fan = {str(q): np.round(10000 * pct(ch_bal[:, :240], q), 0).tolist() for q in (10, 25, 50, 75, 90)}
    smp = np.random.default_rng(seed).choice(N, POOL, replace=False)
    end = lambda p: int(min(240, (res[p, 1] if res[p, 0] == 1 else res[p, 2] if res[p, 0] == -1 else 239) + 1))
    samples = [[int(res[p, 0])] + np.round(10000 * ch_bal[p, :end(p)]).astype(int).tolist() for p in smp]   # status, then daily balance
    funded = {}
    for c, (k, t) in enumerate((k, t) for k in KEEPS for t in TRIGS):
        fr = fres[c, ok]; fp = fpaid[c, ok] * 100; tot = pd_ + FUND_DELAY + fr[:, 2]
        funded[combo_key(k, t)] = {
            "paid": {str(q): np.round(pct(fp, q), 3).tolist() for q in (10, 25, 50, 75, 90)},
            "lost_pct": round(100 * np.mean(fr[:, 0] == 1), 1),
            "never_paid_pct": round(100 * np.mean(np.isnan(fr[:, 2])), 1),
            "first_payout_days": {str(q): round(float(np.nanpercentile(fr[:, 2], q)), 1) for q in (25, 50, 75)},
            "first_payout_within": {str(d): round(100 * np.mean(fr[:, 2] <= d), 1) for d in (14, 28, 42, 56, 90)},
            "first_payout_total_days": {str(q): round(float(np.nanpercentile(tot, q)), 1) for q in (25, 50, 75)},
            "paid12": {str(q): round(float(np.percentile(fr[:, 1] * 100, q)), 3) for q in (10, 25, 50, 75, 90)},
        }
    return {
        "n": int(N), "pass_pct": round(100 * ok.mean(), 1), "fail_pct": round(100 * (res[:, 0] == -1).mean(), 1),
        "pass_days": {str(q): round(float(np.percentile(pd_, q)), 1) for q in (10, 25, 50, 75, 90)},
        "pass_within": {str(m): round(100 * np.mean(ok & (res[:, 1] <= m * 30.4)), 1) for m in (1, 2, 3, 4, 6, 9, 12)},
        "pass_cum": pass_cum, "fail_cum": fail_cum, "fan": fan, "samples": samples, "funded": funded,
    }

if __name__ == "__main__":
    D = F.load()
    W = WINDOWS
    out = {"settings": {"challenge": CH, "challenge_minm": CH_MINM, "challenge_dz": CH_DZ, "funded": FU, "funded_minm": FU_MINM, "funded_dz": FU_DZ, "guard": GUARD, "keep": KEEP, "split": SPLIT, "pay_every": PAY_EVERY,
                        "fund_delay": FUND_DELAY, "keeps": [k * 100 for k in KEEPS], "trigs": [t * 100 for t in TRIGS],
                        "weeks": WEEKS.tolist()}, "windows": {}}
    for w, (a, b) in W.items():
        r = journeys(D, a, b, N=3000, seed=21)
        out["windows"][w] = summarise(*r)
        s = out["windows"][w]
        f = s["funded"]["1/1"]
        print(w, "pass", s["pass_pct"], "median days", s["pass_days"]["50"], "| keep 1% / trigger 1%: first payout total",
              f["first_payout_total_days"], "funded lost", f["lost_pct"], "paid12 gross median %", f["paid12"]["50"], flush=True)
    json.dump(out, open(pathlib.Path(__file__).resolve().parent / "results" / "fundingpips_plan_data.json", "w"))
