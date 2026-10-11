"""
Daily 'condition score' strategy built from the feature study (robust on BTC+ETH in both dev halves):
  score = mean of causal percentiles of [ret_7d, dist_ema20, range_pos_20d, ret_3d] and (1 - pct of vol_ratio_7_90), minus 0.5
  Decision at each daily close (00:00 UTC): long if score > th, short if score < -th, else flat; position held
  until the next decision (re-evaluated daily; a trade only when the side changes).
  Size: vol-targeted, notional = target / sd20 (same risk every day). Costs: 0.06% per side per change,
  funding 0.01%/8h on any open position (pessimistic). Returns reported per unit of daily risk ('R-days').
Percentiles are EXPANDING (each day ranked against all earlier days only) -> no look-ahead.
"""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import sys
import numpy as np, pandas as pd
import common as C
from feature_study import daily, features
from wf2 import V21
import families as F

FEATS_POS = ["ret_7d", "dist_ema20", "range_pos_20d", "ret_3d"]
FEATS_NEG = ["vol_ratio_7_90"]


def score(f):
    parts = [f[c].expanding(min_periods=120).rank(pct=True) for c in FEATS_POS]
    parts += [1 - f[c].expanding(min_periods=120).rank(pct=True) for c in FEATS_NEG]
    return pd.concat(parts, axis=1).mean(axis=1) - 0.5


def backtest(sym, th=0.2, cost=0.0006, funding_day=0.0003, sides="both"):
    d = daily(sym); f, y, sd = features(d)
    s = score(f)
    pos = pd.Series(np.where(s > th, 1, np.where(s < -th, -1, 0)), index=d.index)
    if sides == "long":
        pos = pos.clip(lower=0)
    pos[s.isna()] = 0
    r_next = np.log(d.close.shift(-1) / d.close)                # next day's return, earned by today's decision
    lev = (1.0 / sd).clip(upper=100)                           # 1 unit = one daily st.dev of risk
    turn = pos.diff().abs().fillna(pos.abs())
    pnl = (pos * r_next - turn * cost - pos.abs() * funding_day) * lev   # in 'daily-sd' units
    out = pd.DataFrame(dict(pos=pos, pnl=pnl, sd=sd, score=s)).dropna()
    return out


def stats(p, a, b, label):
    x = p.loc[a:b]; r = x.pnl
    eq = r.cumsum(); dd = (eq.cummax() - eq).max()
    yrs = (pd.Timestamp(b) - pd.Timestamp(a)).days / 365.25
    mo = r.groupby(r.index.to_period("M")).sum()
    trades = (x.pos.diff().abs() > 0).sum()
    print(f"  {label:18s} {r.sum()/yrs:6.1f}/yr DD {dd:5.1f} MAR {r.sum()/yrs/dd:4.2f} | in market {(x.pos!=0).mean()*100:3.0f}% "
          f"(long {(x.pos>0).mean()*100:3.0f}% short {(x.pos<0).mean()*100:3.0f}%) | changes/yr {trades/yrs:4.0f} | months+ {(mo>0).mean()*100:3.0f}% | "
          f"long {r[x.pos>0].sum():6.1f} short {r[x.pos<0].sum():6.1f} | by year {r.groupby(r.index.year).sum().round(1).to_dict()}")


if __name__ == "__main__":
    look_holdout = len(sys.argv) > 1 and sys.argv[1] == "holdout"
    for sym in ("BTCUSDT", "ETHUSDT"):
        print(sym)
        for th in (0.1, 0.15, 0.2, 0.25):
            p = backtest(sym, th)
            stats(p, *C.DEV, f"th {th} dev")
            if look_holdout:
                stats(p, *C.HOLDOUT, f"th {th} 2024-26")
