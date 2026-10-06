"""Data for fundedhive_plan.html: full journeys evaluation -> funded for FundedHive 1-step Low accounts (Moderate dropped 5 Oct 2026).
Each path is built from random 4-week blocks of the bots' real trades (minute-level live equity, rules as in fundedhive_sim.py).
Evaluation at the recommended risk (with risk scaling below the start, min 0.3x) until +10% (pass) or a breach (fail). After a pass the SAME path continues, FUND_DELAY days
later, as the funded account with the recommended buffer ladder, fee debt and B-book rules, for 12 months, with on-demand payouts
(checked once a day, PAY_EVERY) for every combination of buffer (KEEPS) and trigger (TRIGS). Payouts are stored before the profit split.
Values are fractions of the starting balance, so they hold for any account size.
Writes research/results/fundedhive_plan_data.json (read by make_fundedhive_html.py).
Usage:  TRADING_DATA=<folder with data> python research/fundedhive_report.py
"""
import sys, pathlib, json; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent), str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, numba as nb
import fundingpips_sim as F
import fundedhive_sim as H

FUND_DELAY = 3                     # days from passing to the first funded trading day
HEV, HFU = 730, 365                # days simulated per phase
# Oct 2026: evaluation with risk scaling below the start balance (min 0.3x). 5 Oct 2026: funded = the ladder + the same risk
# scaling below the start (min 0.3x), no manual B-book risk cuts; Moderate dropped.
PLAN = {"low": dict(ev=(0.004, 0.005), minm=0.3, ladder=H.LADDERS["low"]["rec"], fminm=0.3, bbo=0)}
BB_HI, BB_LO, CALM = np.array([0.0025, 0.0035]), np.array([0.0015, 0.0020]), 10


@nb.njit(cache=True)
def phase(ent, ext, sym, Rr, off, fc, fw, t0, mode, rg0, rv0, thr, RG, RV, bb_hi, bb_lo, calm_days, fee,
          guard, slip, horizon_days, daily, target, floor, reset, rec, keep=0.03, trig=0.01, pay_every=14, minm=1.0, bbo=1):
    """mode 0: evaluation at rg0/rv0 until 1 + target. mode 1: funded with the buffer ladder, fee debt and B book.
    Funded payouts: every pay_every days, at the first moment with no open position, if balance - 1 - debt >= keep + trig, everything
    above 1 + keep is withdrawn; the debt (fee, B-book debt) is repaid from it first and the rest is paid out (before the split).
    rec[0, d] = balance at the end of day d (evaluation) or still withdrawable = max(balance - 1 - debt, 0) (funded);
    rec[1, d] = paid out so far (funded).
    Returns (status 1 pass / -1 fail / 0 running, end minute, ever in B book, paid, first payout minute or -1)."""
    n = len(ent); bal = 1.0; base = 1.0; halted = False; paid = 0.0; first = -1; nextpay = t0 + pay_every * 1440
    debt = fee if mode == 1 else 0.0; inb = False; calm = 0; ever = 0
    rg = rg0; rv = rv0
    if mode == 1:
        rg = RG[0]; rv = RV[0]
    op = np.empty(64, np.int64); sz = np.empty(64); no = 0; j = 0
    while j < n and ent[j] < t0: j += 1
    m = t0 - (t0 - reset) % 1440
    lastd = -1; Hm = horizon_days * 1440
    while True:
        d = (m - t0) // 1440
        if d > lastd:
            v = bal if mode == 0 else max(bal - 1.0 - debt, 0.0)
            for k in range(max(lastd, 0), min(d, horizon_days)):
                rec[0, k] = v; rec[1, k] = paid
            lastd = d
        if m - t0 >= Hm or (j >= n and no == 0):
            v = bal if mode == 0 else max(bal - 1.0 - debt, 0.0)
            for k in range(max(lastd, 0), horizon_days):
                rec[0, k] = v; rec[1, k] = paid
            return 0, m, ever, paid, first
        if no == 0:
            if mode == 1 and m >= nextpay:                            # payout window, flat account
                if bal - 1.0 - debt >= keep + trig:
                    paid += bal - 1.0 - keep - debt; bal = 1.0 + keep; debt = 0.0
                    if first < 0: first = m
                nextpay = m + pay_every * 1440
            nr = m + 1440 - ((m - reset) % 1440) if (m - reset) % 1440 != 0 else m
            nm = min(ent[j], nr) if j < n else nr
            if mode == 1: nm = min(nm, max(nextpay, m))
            nm = min(nm, t0 + Hm)
            if nm > m:
                m = nm
                continue
        eq = bal
        for q in range(no):
            i = op[q]; eq += sz[q] * fc[off[i] + min(m - 1 - ent[i], ext[i] - ent[i])] if m > ent[i] else 0.0
        if (m - reset) % 1440 == 0:
            base = max(bal, eq); halted = False
            if mode == 1:
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
                op[no] = j; sz[no] = (rg if sym[j] == 0 else rv) * bal
                if minm < 1.0 and bal < 1.0: sz[no] *= max(minm, (bal - floor) / (1.0 - floor))
                no += 1
            j += 1
        ew = bal
        for q in range(no):
            i = op[q]; ew += sz[q] * fw[off[i] + m - ent[i]]
        fail = False
        if no > 0 and ew <= base * (1 - guard):
            lvl = base * (1 - guard) - slip * base
            if lvl <= base * (1 - daily) or lvl <= floor: fail = True
            else:
                bal = lvl; no = 0; halted = True
        elif ew <= base * (1 - daily) or ew <= floor:
            fail = True
        if fail:
            v = min(bal, floor) if mode == 0 else 0.0
            for k in range(max(lastd, 0), horizon_days):
                rec[0, k] = v; rec[1, k] = paid
            return -1, m, ever, paid, first
        q = 0
        while q < no:
            i = op[q]
            if ext[i] == m:
                bal += sz[q] * Rr[i]; op[q] = op[no - 1]; sz[q] = sz[no - 1]; no -= 1
            else: q += 1
        if mode == 1 and debt > 0.0 and bal > 1.0:                  # FundedHive: profit above the start repays the debt at once
            r = min(bal - 1.0, debt); bal -= r; debt -= r
        if mode == 0 and bal >= 1.0 + target:
            for k in range(max(lastd, 0), horizon_days):
                rec[0, k] = bal; rec[1, k] = paid
            return 1, m, ever, paid, first
        m += 1


KEEPS = (0.0, 0.01, 0.02, 0.03, 0.04, 0.05)            # buffer left in the account after a payout
TRIGS = (0.005, 0.01, 0.015, 0.02, 0.03)               # payout only when equity - debt is this far above start + buffer
PAY_EVERY = 1                      # FundedHive pays on demand: checked once a day, at the first moment with no open position
WEEKS = np.arange(0, HFU, 7)

WINDOWS = {"6m": ("2026-03-21", "2026-09-19"), "1y": ("2025-09-20", "2026-09-19"), "2y": ("2024-09-21", "2026-09-19"),
           "3y": ("2023-09-23", "2026-09-19"), "5y": ("2021-09-18", "2026-09-19"), "10y": ("2016-01-09", "2026-09-19")}
POOL = 200                                              # example journeys stored per period (seed button)

def combo_key(k, t): return f"{k * 100:g}/{t * 100:g}"

def journeys(D, rule, a, b, N, seed):
    """Evaluation once per path, then the funded year for every (buffer, trigger) combination on the same path."""
    ent, ext, sym, Rr, off, fc, fw = D; R_ = H.RULES[rule]; P = PLAN[rule]
    thr, RG, RV = (np.array(x, float) for x in P["ladder"]); RG /= 100; RV /= 100
    blocks = (HEV + HFU + FUND_DELAY) // 28 + 2
    C = [(k, t) for k in KEEPS for t in TRIGS]
    ev_bal = np.zeros((N, HEV)); res = np.full((N, 3), np.nan)          # status, pass day, fail day
    fres = np.full((len(C), N, 4), np.nan)                               # lost, paid 12m, first payout day, ever B book
    fpaid = np.full((len(C), N, len(WEEKS)), np.nan)
    rec_e = np.zeros((2, HEV)); rec_f = np.zeros((2, HFU))
    common = (thr, RG, RV, BB_HI, BB_LO, CALM, R_["fee"], R_["guard"], H.SLIP)
    for p, (idx, sh) in enumerate(H.paths(D, a, b, N, blocks, seed)):
        e0 = ent[idx] + sh; e1 = ext[idx] + sh; t0 = int(e0[0]) - int(e0[0]) % 1440
        args = (e0, e1, sym[idx], Rr[idx], off[idx], fc, fw)
        st, mend, _, _, _ = phase(*args, t0, 0, P["ev"][0], P["ev"][1], *common, HEV, R_["daily"], R_["target"], R_["floor"], H.RESET, rec_e,
                                 0.03, 0.01, 14, P["minm"])
        ev_bal[p] = rec_e[0]; res[p, 0] = st
        if st == 1: res[p, 1] = (mend - t0) / 1440.0
        if st == -1: res[p, 2] = (mend - t0) / 1440.0
        if st != 1: continue
        tf = int(mend) - int(mend) % 1440 + FUND_DELAY * 1440
        for c, (k, t) in enumerate(C):
            sf, _, ever, paid, first = phase(*args, tf, 1, 0.0, 0.0, *common, HFU, R_["daily"], R_["target"], R_["floor"], H.RESET,
                                             rec_f, k, t, PAY_EVERY, P["fminm"], P["bbo"])
            fres[c, p] = (sf == -1, paid, (first - tf) / 1440.0 if first >= 0 else np.nan, ever)
            fpaid[c, p] = rec_f[1, WEEKS]
    return ev_bal, res, fres, fpaid


def summarise(ev_bal, res, fres, fpaid, seed=3):
    N = len(res); ok = res[:, 0] == 1; pd_ = res[ok, 1]; days = np.arange(HEV)
    pass_cum = [round(100 * np.mean(ok & (res[:, 1] <= d)), 2) for d in days]
    fail_cum = [round(100 * np.mean((res[:, 0] == -1) & (res[:, 2] <= d)), 2) for d in days]
    pct = lambda a, q: np.nanpercentile(a, q, axis=0)
    fan = {str(q): np.round(100 * (pct(ev_bal[:, :240], q) - 1), 2).tolist() for q in (10, 25, 50, 75, 90)}
    smp = np.random.default_rng(seed).choice(N, POOL, replace=False)
    end = lambda p: int(min(240, (res[p, 1] if res[p, 0] == 1 else res[p, 2] if res[p, 0] == -1 else 239) + 1))
    samples = [[int(res[p, 0])] + np.round(10000 * (ev_bal[p, :end(p)] - 1)).astype(int).tolist() for p in smp]   # status, then basis points
    funded = {}
    for c, (k, t) in enumerate((k, t) for k in KEEPS for t in TRIGS):
        fr = fres[c, ok]; fp = fpaid[c, ok] * 100; tot = pd_ + FUND_DELAY + fr[:, 2]
        funded[combo_key(k, t)] = {
            "paid": {str(q): np.round(pct(fp, q), 3).tolist() for q in (10, 25, 50, 75, 90)},
            "lost_pct": round(100 * np.mean(fr[:, 0] == 1), 1),
            "bbook_pct": round(100 * np.mean(fr[:, 3] == 1), 1),
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
    out = {"fund_delay": FUND_DELAY, "pay_every": PAY_EVERY, "keeps": [k * 100 for k in KEEPS], "trigs": [t * 100 for t in TRIGS],
           "weeks": WEEKS.tolist(), "plans": {}}
    for rule in PLAN:
        out["plans"][rule] = {}
        for w, (a, b) in WINDOWS.items():
            s = summarise(*journeys(D, rule, a, b, N=3000, seed=21))
            out["plans"][rule][w] = s; f = s["funded"]["3/1"]
            print(rule, w, "pass", s["pass_pct"], "median days", s["pass_days"]["50"], "| keep 3% / trigger 1%: lost", f["lost_pct"],
                  "paid12 median %", f["paid12"]["50"], "first payout days", f["first_payout_days"]["50"], "bbook", f["bbook_pct"], flush=True)
    json.dump(out, open(pathlib.Path(__file__).resolve().parent / "results" / "fundedhive_plan_data.json", "w"))
