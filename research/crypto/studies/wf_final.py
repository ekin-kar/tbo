"""Pick the live config the walk-forward procedure would use now (trained on 2020-03 .. 2026-09) and check
the chosen changes on ETH (never used for tuning)."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import numpy as np, pandas as pd
import common as C, families as F
from wf_eval import combos, trades, stream, mar

yrs = (pd.Timestamp("2026-10-01") - pd.Timestamp("2020-03-01")).days / 365.25
sc = np.array([mar(stream(trades[i], "2020-03-01", "2026-10-01"), yrs)[0] for i in range(len(combos))])
order = np.argsort(-sc)
print("top 10 on all data (MAR):")
for i in order[:10]:
    x = stream(trades[i], "2020-03-01", "2026-10-01")
    print(round(sc[i], 2), len(x), round(x.R.sum(), 1), combos[i])
top = [combos[i] for i in order[:25]]
for key in ["n", "sl_atr", "hold_h", "ema_n", "sides", "trail", "slope_d", "no_weekend", "be_R", "tf"]:
    vals = pd.Series([str(c[key]) for c in top]).value_counts().to_dict()
    print(key, vals)
