"""Is it bad that ETH gets (almost) nothing while a fresh BTC trade is open? (Oct 2026, follow-up to sizing_v4)
1. ETH trades that START while BTC is in a fresh trade (not yet at breakeven) vs the other ETH trades: average R, win rate
   (same for the alts), split by same / opposite direction.
2. Variants of the cap: minimum fraction (0 = ETH takes the 0.5% crumb, 0.25 now, 0.5, 1 = never shrink, only skip),
   ETH exempt too, ETH a separate cap, cap 7.5% (ETH fits fully next to a BTC long). Fill-time rule, $200."""
import numpy as np, pandas as pd
from multiprocessing import Pool
import sizing_v4 as V

T = V.T


def btc_state():
    b = T[T.sym == "BTCUSDT"]
    rows = []
    for _, r in T[T.sym != "BTCUSDT"].iterrows():
        m = (b.entry_time < r.entry_time) & (b.exit_time > r.entry_time) & (b.be_time > r.entry_time)
        rows.append("none" if not m.any() else ("same" if (b.dir[m] == r.dir).any() else "opposite"))
    x = T[T.sym != "BTCUSDT"].assign(btc=rows)
    x["coin"] = np.where(x.sym == "ETHUSDT", "ETH", "alts")
    x["period"] = np.where(x.entry_time < "2024-01-01", "2020-23", "2024-26")
    g = x.groupby(["coin", "btc"]).R.agg(n="size", avgR="mean", win=lambda r: (r > 0).mean() * 100, totalR="sum")
    print(g.round(2).to_string())
    print(x.groupby(["coin", "period", "btc"]).R.agg(n="size", avgR="mean").round(2).unstack("btc").to_string())


def job(a):
    n, kw = a
    return n, V.hist_kw(kw)


R = V.R(5, 2.5, 0.83)
VARS = [("no cap", dict(cap=0)), ("now: cap 5.5%, skip if < 25% fits", dict(cap=0.055)),
        ("cap 5.5%, ETH takes whatever fits (0.5%)", dict(cap=0.055, minf=0.0)),
        ("cap 5.5%, skip if < 50% fits", dict(cap=0.055, minf=0.5)),
        ("cap 5.5%, never shrink (fit fully or skip)", dict(cap=0.055, minf=0.999)),
        ("cap 5.5%, BTC and ETH exempt", dict(cap=0.055, exempt=(0, 1))),
        ("cap 7.5% (ETH fits next to a BTC long)", dict(cap=0.075)),
        ("cap 6.5%", dict(cap=0.065)), ("cap 4.5%", dict(cap=0.045))]

if __name__ == "__main__":
    print("=== trades starting while BTC is in a fresh trade (risk not yet at breakeven) ===")
    btc_state()
    with Pool(4) as p:
        res = p.map(job, VARS)
    print(f"\n{'':44s} | 2020-23 %/mo drop | 2024-26 $200->  %/mo  drop | 2022-26 %/mo drop")
    for n, (a, h, w) in res:
        print(f"{n:44s} | {a[1]:6.2f} {a[2]:5.1f}% | ${h[0]:>8,.0f} {h[1]:6.2f} {h[2]:5.1f}% | {w[1]:6.2f} {w[2]:5.1f}%")
