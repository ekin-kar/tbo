"""FundedHive Low funded account (12 months, fee 1% as debt repaid at once from any balance above the start, B book below 99% at
a reset): which funded setting is best? The plan's buffer ladder, with or without its manual B-book risk cuts, against the bots'
risk scaling below the start (min 0.3x, floor 95%) and flat risk. Uses fundedhive_sim.funded (minm = scaling, bbo = manual cuts)."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd
import fundedhive_sim as H, fundingpips_sim as F
D = F.load(); ent, ext, sym, Rr, off, fc, fw = D; R_ = H.RULES["low"]
LAD = H.LADDERS["low"]["rec"]; FLAT = lambda g, j: ([-99], [g], [j])
CASES = [("ladder + manual B-book cuts (plan until 5 Oct)", LAD, 1.0, 1), ("ladder + shrink + manual cuts", LAD, 0.3, 1),
         ("ladder + shrink, no manual cuts (plan now)", LAD, 0.3, 0), ("flat 0.3/0.4 + shrink", FLAT(0.30, 0.40), 0.3, 0),
         ("flat 0.4/0.5 + shrink (= evaluation)", FLAT(0.40, 0.50), 0.3, 0), ("flat 0.4/0.5 + shrink + manual cuts", FLAT(0.40, 0.50), 0.3, 1),
         ("flat 0.4/0.5, manual cuts, no shrink", FLAT(0.40, 0.50), 1.0, 1), ("flat 0.5/0.6 + shrink", FLAT(0.50, 0.60), 0.3, 0)]
rows = []
for lab, (thr, RG, RV), minm, bbo in CASES:
    r = dict(setting=lab)
    for w, (a, b) in H.WINDOWS.items():
        o = np.array([H.funded(ent[i] + s, ext[i] + s, sym[i], Rr[i], off[i], fc, fw, np.array(thr, float), np.array(RG) / 100,
                               np.array(RV) / 100, np.array([0.0025, 0.0035]), np.array([0.0015, 0.0020]), 10, R_["fee"],
                               R_["guard"], H.SLIP, 365 * 1440, R_["daily"], R_["floor"], H.RESET, minm, bbo)
                      for i, s in H.paths(D, a, b, 2500, 14, 5)], float)
        r[f"{w} lost%"] = round(100 * o[:, 0].mean(), 1)
        r[f"{w} withdrawable med%"] = round(100 * np.median(o[:, 1]), 1)
        r[f"{w} p25%"] = round(100 * np.percentile(o[:, 1], 25), 1)
        if w == "10y": r["10y ever B book%"] = int(round(100 * o[:, 2].mean()))
    rows.append(r); print(r, flush=True)
pd.DataFrame(rows).to_csv(pathlib.Path(__file__).resolve().parent.parent / "results" / "fh_funded_shrink.csv", index=False)
