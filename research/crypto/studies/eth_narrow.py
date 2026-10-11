"""ETH: narrow walk-forward (only channel n, stop, breakeven vary; everything else = BTC v2.1)."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import pickle, sys
sys.argv = ["x", "eval", "eth", "ETHUSDT"]
import numpy as np, pandas as pd
import common as C
from wf2 import V21, TESTS, stream, mar, summary

z = pickle.load(open(C.D.CACHE / "wf2_eth_ETHUSDT.pkl", "rb")); cfgs, T = z["cfgs"], z["trades"]
fixed = {k: V21[k] for k in ["tf", "hold_h", "ema_n", "slope_d", "sides", "max_ext"]}
sub = [i for i, c in enumerate(cfgs) if all(c[k] == v for k, v in fixed.items())]
print(len(sub), "configs:", sorted({(cfgs[i]["n"], cfgs[i]["sl_atr"], cfgs[i]["be_R"]) for i in sub})[:5], "...")
base = next(i for i, c in enumerate(cfgs) if c == V21)
summary(pd.concat([stream(T[base], f"{y}-01-01", f"{y+1}-01-01") for y in TESTS]), "BTC v2.1 settings (2022-26)")
picks = []
for y in TESTS:
    yrs = (pd.Timestamp(f"{y}-01-01") - pd.Timestamp("2020-03-01")).days / 365.25
    sc = [mar(stream(T[i], "2020-03-01", f"{y}-01-01"), yrs) for i in sub]
    picks.append(sub[int(np.argmax(sc))])
summary(pd.concat([stream(T[i], f"{y}-01-01", f"{y+1}-01-01") for y, i in zip(TESTS, picks)]), "narrow walk-forward (out of sample)")
for y, i in zip(TESTS, picks):
    print("  ", y, {k: cfgs[i][k] for k in ["n", "sl_atr", "be_R"]})
print("all data 2020-26, each (n, sl) with be 1.5:")
for i in sub:
    c = cfgs[i]
    if c["be_R"] == 1.5:
        summary(stream(T[i], "2020-03-01", "2026-10-01"), f"  n {c['n']} sl {c['sl_atr']}", yrs=6.58)
