"""TBO v2.1 (BTC settings, untuned) on gold with Binance XAUUSDT costs; correlation and combination with BTC."""
from pathlib import Path
import numpy as np, pandas as pd
import common as C, families as F
from wf2 import V21

GOLD = Path("/home/user/trade2/data/XAUUSD_DUKA_BID.m1pack")


def load_gold():
    cache = C.D.CACHE / "XAU_m1.npz"
    if cache.exists():
        z = np.load(cache); return {k: z[k] for k in z.files}
    df = C.D._unpack(GOLD.read_bytes())
    d = {k: df[k].to_numpy(float if k != "t" else np.int64) for k in ["t", "o", "h", "l", "c", "v"]}
    np.savez(cache, **d); return d


def curve(x, risk):
    r = x.sort_values("exit_time").R.to_numpy(); e = 1000 * np.cumprod(1 + risk * r); pk = np.maximum.accumulate(e)
    return e, ((pk - e) / pk).max()


def flat_stats(x):
    x = x.sort_values("exit_time"); eq = np.cumsum(x.R.to_numpy()); hw = np.maximum.accumulate(eq)
    t = x.exit_time.to_numpy(); nh = t[np.r_[True, eq[1:] > hw[:-1]]]
    g = np.diff(nh).astype("timedelta64[D]").astype(int)
    return g.max(), (g > 90).sum()


if __name__ == "__main__":
    g = load_gold()
    print("gold data:", pd.Timestamp(int(g["t"][0]) * 60, unit="s"), "->", pd.Timestamp(int(g["t"][-1]) * 60, unit="s"), len(g["t"]), "bars")
    xg = F.channel_breakout(g, **V21)
    s = xg.sl_dist / xg.entry * 100
    print(f"gold stop size: median {s.median():.2f}% of price -> fees ~{(0.0012 / (s.median() / 100)):.2f}R per trade")
    for per, (a, b) in {"2016-2019": ("2016-03-01", "2020-01-01"), "2020-03..2026-09": ("2020-03-01", "2026-10-01")}.items():
        x = C.between(xg, a, b); st = C.stats(x)
        print(f"GOLD {per}: {st['trades']} trades, PF {st['PF']}, {st['total_R']}R, DD {st['maxDD_R']}R, long {st['long_R']} short {st['short_R']}, "
              f"months+ {st['pos_months']}", C.yearly(x).to_dict())
    xb = C.between(F.channel_breakout(C.load("BTCUSDT"), **V21), "2020-03-01", "2026-10-01")
    xe = C.between(F.channel_breakout(C.load("ETHUSDT"), **V21), "2020-03-01", "2026-10-01")
    xg = C.between(xg, "2020-03-01", "2026-10-01")
    mo = lambda x: x.groupby(x.exit_time.dt.to_period("M")).R.sum()
    mm = pd.concat([mo(xb), mo(xe), mo(xg)], axis=1, keys=["BTC", "ETH", "GOLD"]).fillna(0)
    print("monthly R correlation:\n", mm.corr().round(2))
    print("\n$1,000, 2020-03..2026-09 (closed-trade compounding):")
    for name, parts, risk in [("BTC alone 2%", [xb], 0.02), ("GOLD alone 2%", [xg], 0.02), ("BTC 1.5% + GOLD 1.5%", [xb, xg], 0.015),
                              ("BTC 1% + GOLD 1%", [xb, xg], 0.01), ("BTC+ETH+GOLD 1% each", [xb, xe, xg], 0.01)]:
        x = pd.concat(parts).sort_values("exit_time"); e, dd = curve(x, risk); fl, n90 = flat_stats(x)
        m = x.groupby(x.exit_time.dt.to_period("M")).R.sum()
        print(f"  {name:24s} -> ${e[-1]:>9,.0f}  {((e[-1]/1000)**(1/79)-1)*100:4.1f}%/mo  max DD {dd*100:3.0f}%  months+ {(m>0).mean()*100:3.0f}%  "
              f"longest flat {fl:3d} d  flats>90d {n90}")
