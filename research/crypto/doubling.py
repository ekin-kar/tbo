"""Fresh account started on the 1st of every month: months until it doubles (v2.2, 4 coins, 0.75%/0.375%)."""
import pickle
import numpy as np, pandas as pd
import common as C
from portfolio import simulate

ALL = pickle.load(open(C.D.CACHE / "portfolio_trades.pkl", "rb"))
T4 = pd.concat([ALL[(s, 0.0003)] for s in ("BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT")])
rows = []
for st in pd.date_range("2020-03-01", "2026-03-01", freq="MS"):
    cv, _ = simulate(T4, risk=0.0075, cap=0.03, short_mult=0.5, start=str(st.date()), eq0=500.0)
    eq = cv.equity
    hit = eq[eq >= 1000]
    low = eq.min()
    rows.append(dict(start=st, months=(hit.index[0] - st).days / 30.44 if len(hit) else np.nan, lowest=low,
                     censored=not len(hit), avail=(pd.Timestamp("2026-10-01") - st).days / 30.44))
d = pd.DataFrame(rows)
done = d[~d.censored]
print(f"starts: {len(d)}; doubled before Sep 2026: {len(done)}; not yet: {d.censored.sum()} (started {', '.join(str(x.date())[:7] for x in d[d.censored].start)})")
for lab, x in (("all starts 2020-26", done), ("starts from 2023 on", done[done.start >= "2023-01-01"])):
    print(f"{lab}: median {x.months.median():.1f} months | fastest {x.months.min():.1f} | 75% within {x.months.quantile(.75):.1f} | slowest {x.months.max():.1f}")
print("lowest balance on the way (from $500): median ${:.0f}, worst ${:.0f}".format(d.lowest.median(), d.lowest.min()))
print(d.assign(start=d.start.dt.strftime("%Y-%m"), months=d.months.round(1), lowest=d.lowest.round(0))[["start", "months", "lowest"]].to_string(index=False))
