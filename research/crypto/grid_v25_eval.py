"""Evaluate grid_v25: score = min(dev net/DD, holdout net/DD) relative to the live settings, then smoothed over each
config's neighbours (one step in channel, stop size, breakeven or hold, same timeframe and stop type) so a lone
lucky peak does not win."""
import numpy as np, pandas as pd
import common as C

G = pd.read_csv(C.D.CACHE / "grid_v25.csv")
base = G[(G.tf == 240) & (G.n == 20) & (G.stop_name == "atr") & (G.stop_val == 1.0) & (G.be_R == 1.5) & (G.hold_h == 120)].iloc[0]
G["rel_dev"] = G.dev_ratio / base.dev_ratio; G["rel_ho"] = G.ho_ratio / base.ho_ratio
G["score"] = np.minimum(G.rel_dev, G.rel_ho)
G["lose_years"] = (G[[f"y{y}" for y in range(2020, 2027)]] < 0).sum(axis=1)
G["trades_yr"] = (G.dev_n + G.ho_n) / 6.6
axes = {"n": sorted(G.n.unique()), "be_R": sorted(G.be_R.unique()), "hold_h": sorted(G.hold_h.unique())}
key = lambda r: (r.tf, r.stop_name, r.n, r.stop_val, r.be_R, r.hold_h)
idx = {key(r): i for i, r in G.iterrows()}
vals = {s: sorted(g.stop_val.unique()) for s, g in G.groupby("stop_name")}
sm = []
for i, r in G.iterrows():
    nb = [r.score]
    for ax, lst in (("n", axes["n"]), ("be_R", axes["be_R"]), ("hold_h", axes["hold_h"]), ("stop_val", vals[r.stop_name])):
        j = lst.index(r[ax])
        for d in (-1, 1):
            if 0 <= j + d < len(lst):
                k = list(key(r)); pos = {"n": 2, "stop_val": 3, "be_R": 4, "hold_h": 5}[ax]; k[pos] = lst[j + d]
                if tuple(k) in idx:
                    nb.append(G.score[idx[tuple(k)]])
    sm.append(np.median(nb))
G["plateau"] = sm
G.to_pickle(C.D.CACHE / "grid_v25_scored.pkl")
pd.set_option("display.width", 250)
cols = ["tf", "n", "stop_name", "stop_val", "be_R", "hold_h", "trades_yr", "dev_ratio", "ho_ratio", "rel_dev", "rel_ho", "plateau", "lose_years", "ho_win"]
print(f"{len(G)} configs. Live settings: dev net/DD {base.dev_ratio:.2f}, holdout {base.ho_ratio:.2f}, "
      f"trades/yr {(base.dev_n + base.ho_n)/6.6:.0f}")
cur = G[(G.tf == 240) & (G.n == 20) & (G.stop_name == "atr") & (G.stop_val == 1.0) & (G.be_R == 1.5) & (G.hold_h == 120)].iloc[0]
print(f"live settings rank by plateau score: {int((G.plateau > cur.plateau).sum()) + 1} of {len(G)} (plateau {cur.plateau:.2f})")
print(f"configs better than live in BOTH periods: {((G.rel_dev > 1) & (G.rel_ho > 1)).sum()}; by >10% in both: {((G.rel_dev > 1.1) & (G.rel_ho > 1.1)).sum()}")
print("\n=== top 25 by plateau score (neighbourhood median of min(dev, holdout) vs live) ===")
print(G.sort_values("plateau", ascending=False)[cols].head(25).round(2).to_string(index=False))
print("\n=== best plateau per timeframe ===")
print(G.loc[G.groupby("tf").plateau.idxmax()][cols].round(2).to_string(index=False))
print("\n=== best plateau per stop type ===")
print(G.loc[G.groupby("stop_name").plateau.idxmax()][cols].round(2).to_string(index=False))
print("\n=== median score by dimension (all other settings mixed) ===")
for ax in ("tf", "n", "stop_name", "be_R", "hold_h"):
    print(ax, G.groupby(ax)[["rel_dev", "rel_ho"]].median().round(2).to_dict("index"))
print("\ncorrelation of dev and holdout scores across configs:", round(np.corrcoef(G.rel_dev.fillna(0), G.rel_ho.fillna(0))[0, 1], 2))
