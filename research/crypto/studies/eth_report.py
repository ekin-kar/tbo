"""ETH with TBO v2.1 (BTC settings, untuned on ETH) + BTC+ETH together on one account."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import numpy as np, pandas as pd
import common as C, families as F
from wf2 import V21

res = {}
for sym in ["BTCUSDT", "ETHUSDT"]:
    x = C.between(F.channel_breakout(C.load(sym), **V21), "2020-03-01", "2026-10-01").sort_values("exit_time")
    res[sym] = x
    r = x.R.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    s = C.stats(x)
    print(f"{sym}: {len(r)} trades ({len(r)/79:.1f}/month), win {s['win_rate']}%, PF {s['PF']}, +{r.sum():.0f}R, max DD {dd:.1f}R, "
          f"longs {x[x.dir>0].R.sum():+.0f}R shorts {x[x.dir<0].R.sum():+.0f}R, worst losing streak {s['worst_streak']}")
    print("   by year R:", C.yearly(x).to_dict())
    mo = x.groupby(x.exit_time.dt.to_period("M")).R.sum()
    print(f"   months positive {(mo>0).mean()*100:.0f}%, best month {mo.max():+.1f}R, worst month {mo.min():+.1f}R")
    for risk in (0.01, 0.015, 0.02, 0.03):
        e = 1000 * np.cumprod(1 + risk * r); pk = np.maximum.accumulate(e)
        print(f"   {risk*100:.1f}% risk: $1000 -> ${e[-1]:,.0f}, {((e[-1]/1000)**(1/79)-1)*100:.1f}%/month, max DD {((pk-e)/pk).max()*100:.0f}%")
b, e_ = res["BTCUSDT"], res["ETHUSDT"]
mb = b.groupby(b.exit_time.dt.to_period("M")).R.sum(); me = e_.groupby(e_.exit_time.dt.to_period("M")).R.sum()
mm = pd.concat([mb, me], axis=1).fillna(0)
print(f"monthly R correlation BTC vs ETH: {mm.corr().iloc[0,1]:.2f}")
both = pd.concat([b, e_]).sort_values("exit_time")
ov = 0
for _, t in b.iterrows():
    ov += ((e_.entry_time < t.exit_time) & (e_.exit_time > t.entry_time) & (e_.dir == t.dir)).any()
print(f"BTC trades overlapping an ETH trade in the same direction: {ov/len(b)*100:.0f}%")
print("BTC + ETH on one account (closed-trade compounding, both bots at the same risk):")
for risk in (0.01, 0.015, 0.02):
    r = both.R.to_numpy(); e = 1000 * np.cumprod(1 + risk * r); pk = np.maximum.accumulate(e)
    print(f"   {risk*100:.1f}% each: $1000 -> ${e[-1]:,.0f}, {((e[-1]/1000)**(1/79)-1)*100:.1f}%/month, max DD {((pk-e)/pk).max()*100:.0f}%")
