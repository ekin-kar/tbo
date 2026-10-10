"""Short size with the live v2.6 settings (ladder + cap + profit lock; botsim): shorts at 0 / 0.25 / 0.5 (now) / 0.75 / 1 x
the coin's risk. Ladder from $200 (2020, 2022, 2024 runs) and a fixed-size R account per period."""
import numpy as np, pandas as pd
import botsim as BS

WT = np.array([2, 1, 1 / 3, 1 / 3, 1 / 3])
if __name__ == "__main__":
    x = BS.TR
    sh = x[:, 3] < 0
    for pp, a, b in (("2020-23", "2020-03-01", "2024-01-01"), ("2024-26", "2024-01-01", "2026-10-01")):
        s = (x[:, 0] >= pd.Timestamp(a).value // BS.MIN) & (x[:, 0] < pd.Timestamp(b).value // BS.MIN)
        print(f"{pp}: longs {(s & ~sh).sum()} avg {x[s & ~sh, 4].mean():+.2f}R | shorts {(s & sh).sum()} avg {x[s & sh, 4].mean():+.2f}R, sum {x[s & sh, 4].sum():+.0f}R")
    base = None
    print(f"{'shorts x':9s} | fixed R account net/DD 2020-23 | 2024-26 | ladder $200: from 2020 | from 2022 | from 2024")
    for m in (0.0, 0.25, 0.5, 0.75, 1.0):
        out = []
        for a, b in (("2020-03-01", "2024-01-01"), ("2024-01-01", "2026-10-01")):
            s = (x[:, 0] >= pd.Timestamp(a).value // BS.MIN) & (x[:, 0] < pd.Timestamp(b).value // BS.MIN); xs = x[s]
            w = WT[xs[:, 5].astype(int)] * np.where(xs[:, 3] < 0, m, 1); o = np.argsort(xs[:, 1]); e = np.cumsum((xs[:, 4] * w)[o])
            out.append(e[-1] / (np.maximum.accumulate(np.r_[0, e])[1:] - e).max())
        lad = []
        for a in ("2020-03-01", "2022-01-01", "2024-01-01"):
            p = BS.bot_policy(); p["smult"] = m
            r = BS.run(x[x[:, 0] >= pd.Timestamp(a).value // BS.MIN], p, 200.0); lad.append((r["final"], r["dd"]))
        base = base or out
        print(f"{m:9.2f} | {out[0]:5.2f} (x{out[0]/base[0]:.2f})          | {out[1]:5.2f} (x{out[1]/base[1]:.2f}) | " +
              " | ".join(f"${f:>11,.0f} {d:4.1f}%" for f, d in lad))
