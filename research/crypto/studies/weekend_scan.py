"""Weekend-continuation grid on BTC and ETH: dev (2020-03..2023) and 2024-26 shown separately, plus monthly
correlation with TBO v2.1."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F, families3 as G3
from wf2 import V21

GRID = dict(th=[0.25, 0.5, 1.0], hold_h=[12, 24, 48, 96], sl_k=[0.75, 1.0, 1.5, 3.0], tp_k=[0.0, 1.5, 3.0], entry=["cme", "mon"])
DATA = {}


def one(args):
    sym, kw = args
    if sym not in DATA:
        DATA[sym] = C.load(sym)
    tr = G3.weekend_momo(DATA[sym], **kw)
    out = dict(sym=sym, **kw)
    for per, (a, b) in {"dev": C.DEV, "new": C.HOLDOUT}.items():
        x = C.between(tr, a, b); r = x.R.to_numpy()
        eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max() if len(r) else 0
        yrs = 3.83 if per == "dev" else 2.75
        out[f"{per}_n"] = len(r); out[f"{per}_R"] = round(r.sum(), 1); out[f"{per}_PF"] = round(r[r > 0].sum() / -r[r <= 0].sum(), 2) if (r <= 0).any() else 9
        out[f"{per}_MAR"] = round(r.sum() / yrs / max(dd, 3), 2)
    return out


if __name__ == "__main__":
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    jobs = [(s, c) for s in ("BTCUSDT", "ETHUSDT") for c in combos]
    with Pool(4) as p:
        df = pd.DataFrame(p.map(one, jobs, chunksize=8))
    df.to_csv(C.ROOT / "research" / "results" / "crypto_weekend_scan.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30)
    w = df.pivot_table(index=list(GRID), columns="sym", values=["dev_MAR", "new_MAR", "dev_R", "new_R", "dev_n"]).reset_index()
    w.columns = ["_".join(c).strip("_") for c in w.columns]
    w["dev_both"] = w[["dev_MAR_BTCUSDT", "dev_MAR_ETHUSDT"]].min(axis=1)
    print("share of settings with dev MAR > 0 on BOTH coins:", round((w.dev_both > 0).mean(), 2),
          "| of those, 2024-26 positive on both:", round(((w.dev_both > 0) & (w.new_R_BTCUSDT > 0) & (w.new_R_ETHUSDT > 0)).sum() / max((w.dev_both > 0).sum(), 1), 2))
    print(w.sort_values("dev_both", ascending=False).head(15).to_string(index=False))
    for k in GRID:
        print(f"  {k:7s} dev MAR (median, both coins):", w.groupby(k).dev_both.median().round(2).to_dict())
