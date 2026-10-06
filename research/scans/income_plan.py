"""Income estimate for the user's accounts started fresh on 5 Oct 2026, all on the SAME simulated market path (the bots trade the same
signals everywhere): FundedHive 200k and 10k Low (evaluation 0.4/0.5 with risk scaling from the start; funded: ladder + scaling, fee and
B-book debt repaid at once from profit above the start, payout on demand at +4%, keep 3%) and Funding Pips 10k and 50k (challenge
0.7/0.9, full to -4% then min 0.3x; funded 0.5/0.6 with the same scaling, payout every 14 days at +2%, keep 1%). 80% split.
FundedHive 200k / 10k and Funding Pips 10k / 50k follow the same rules in percent, so each pair shares one simulation (dollars scaled).
A failed account pays nothing (no re-buy). Writes research/results/income_plan.json (read by make_outlook_html.py)."""
import sys, pathlib, json; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, datetime as dt
import fundingpips_sim as F, fundingpips_report as FPR, fundedhive_report as FHR, fundedhive_sim as H
D = F.load(); ent, ext, sym, Rr, off, fc, fw = D; R_ = H.RULES["low"]; P = FHR.PLAN["low"]
thr, RG, RV = (np.array(x, float) for x in P["ladder"]); RG /= 100; RV /= 100
TODAY = dt.date(2026, 10, 5); NM = 18
MONTHS = [dt.date(2026 + (9 + k) // 12, (9 + k) % 12 + 1, 1) for k in range(1, NM + 1)]          # month ends: 1 Nov 2026 ...
MDAY = np.array([(m - TODAY).days for m in MONTHS]); MLAB = [(m - dt.timedelta(days=1)).strftime("%b %Y") for m in MONTHS]
SPLIT, DELAY, HEV, HFU = 0.8, 3, 730, 600
ACCS = [("FundedHive 200k", 0, 200000), ("FundedHive 10k", 0, 10000), ("Funding Pips 10k", 1, 10000), ("Funding Pips 50k", 1, 50000)]
WINDOWS = {"6m": ("2026-03-21", "2026-09-19"), "1y": ("2025-09-20", "2026-09-19"), "2y": ("2024-09-21", "2026-09-19"),
           "3y": ("2023-09-23", "2026-09-19"), "5y": ("2021-09-18", "2026-09-19"), "10y": ("2016-01-09", "2026-09-19")}

def run(a, b, N=3000, seed=31):
    """Per firm (0 FundedHive, 1 Funding Pips): status, pass day, first payout day, paid in the first 12 funded months (fraction of
    the account, gross), funded lost, cumulative paid (fraction, gross) at each month end."""
    blocks = (HEV + HFU + DELAY) // 28 + 2
    st = np.zeros((2, N)); pday = np.full((2, N), np.nan); fpay = np.full((2, N), np.nan); p12 = np.full((2, N), np.nan)
    flost = np.full((2, N), np.nan); cum = np.zeros((2, N, NM))
    rec_e = np.zeros((2, HEV)); rec_f = np.zeros((2, HFU))
    com = (thr, RG, RV, FHR.BB_HI, FHR.BB_LO, FHR.CALM, R_["fee"], R_["guard"], H.SLIP)
    for p, (idx, sh) in enumerate(H.paths(D, a, b, N, blocks, seed)):
        e0 = ent[idx] + sh; e1 = ext[idx] + sh; t0 = int(e0[0]) - int(e0[0]) % 1440
        args = (e0, e1, sym[idx], Rr[idx], off[idx], fc, fw)
        for f in (0, 1):
            if f == 0:
                s, mend, _, _, _ = FHR.phase(*args, t0, 0, P["ev"][0], P["ev"][1], *com, HEV, R_["daily"], R_["target"], R_["floor"],
                                             H.RESET, rec_e, 0.03, 0.01, 14, P["minm"], 1)
            else:
                s, mend, jn, _, _ = FPR.phase(*args, 0, t0, FPR.CH[0], FPR.CH[1], FPR.GUARD, FPR.SLIP, 0.12, 0.0, 1.0, FPR.PAY_EVERY,
                                              HEV, rec_e, 0.01, FPR.CH_MINM, FPR.CH_DZ)
            st[f, p] = s
            if s != 1: continue
            pday[f, p] = (mend - t0) / 1440
            tf = (int(mend) - int(mend) % 1440 if f == 0 else int(mend)) + DELAY * 1440
            if f == 0:
                sf = FHR.phase(*args, tf, 1, 0.0, 0.0, *com, HFU, R_["daily"], R_["target"], R_["floor"], H.RESET, rec_f, 0.03, 0.01, 1,
                               P["fminm"], P["bbo"])[0]
            else:
                sf = FPR.phase(*args, jn, tf, FPR.FU[0], FPR.FU[1], FPR.GUARD, FPR.SLIP, 0.0, 0.01, 1.0, FPR.PAY_EVERY, HFU, rec_f, 0.01,
                               FPR.FU_MINM, FPR.FU_DZ)[0]
            fs = (tf - t0) / 1440
            p12[f, p] = rec_f[1, 364]; flost[f, p] = sf == -1
            pays = np.flatnonzero(rec_f[1] > 0); fpay[f, p] = fs + pays[0] if len(pays) else np.nan
            for m, md in enumerate(MDAY):
                d = int(md - fs); cum[f, p, m] = rec_f[1, min(d, HFU - 1)] if d >= 0 else 0.0
    return st, pday, fpay, p12, flost, cum

pc = lambda x, q: float(np.nanpercentile(x, q)) if np.isfinite(x).any() else None
J = {"today": str(TODAY), "months": MLAB, "accounts": [a[0] for a in ACCS], "windows": {}}
for w, (a, b) in WINDOWS.items():
    st, pday, fpay, p12, flost, cum = run(a, b)
    accs = []; cum_d = []
    for name, f, size in ACCS:
        ok = st[f] == 1; k = SPLIT * size
        accs.append(dict(name=name, pass_pct=round(100 * ok.mean(), 1), fail_pct=round(100 * (st[f] == -1).mean(), 1),
                         pass_days={q: pc(pday[f], q) for q in (25, 50, 75)}, first_pay_days={q: pc(fpay[f], q) for q in (25, 50, 75)},
                         paid_within_12m=round(100 * np.mean(np.isfinite(fpay[f]) & (fpay[f] <= 365)), 1),
                         paid12={q: (pc(p12[f][ok], q) or 0) * k for q in (25, 50, 75)}, paid12_mean=float(np.nanmean(p12[f][ok])) * k,
                         funded_lost_pct=round(100 * np.nanmean(flost[f][ok]), 1)))
        cum_d.append(cum[f] * k)
    cum_d = np.array(cum_d); tot = cum_d.sum(0)
    monthly_mean = [np.diff(np.c_[np.zeros(len(c)), c], axis=1).mean(0).round(0).tolist() for c in cum_d]   # average paid in each month
    J["windows"][w] = dict(accounts=accs, total={q: np.percentile(tot, q, axis=0).round(0).tolist() for q in (25, 50, 75)},
                           total_mean=tot.mean(0).round(0).tolist(), by_acc_median=[np.median(c, axis=0).round(0).tolist() for c in cum_d],
                           monthly_mean=monthly_mean)
    print(w, " | ".join(f"{x['name']}: pass {x['pass_pct']}% fail {x['fail_pct']}% pass d{x['pass_days'][50]:.0f} first pay d"
                        f"{(x['first_pay_days'][50] or -1):.0f} yr1 ${x['paid12'][50]:,.0f}" for x in accs), flush=True)
json.dump(J, open(pathlib.Path(__file__).resolve().parent.parent / "results" / "income_plan.json", "w"), indent=1)
print("written")
