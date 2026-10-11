"""Without the 2020-21 bull run: each coin 2022-01 .. 2026-09 at 1% risk, and every 4- and 5-coin set containing BTC
(risk BTC 5%, ETH 2.5%, every other coin 1.25%, shorts x0.5), ranked on 2022-26; plus pick-on-2022-23 / check-on-2024-26."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import itertools
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
from portfolio import simulate

RES = pd.read_pickle(C.D.CACHE / "all12_v24.pkl")
OTHERS = [s for s in RES if s != "BTCUSDT"]


def acct(coins, a, b, risk=0.05, single=False):
    T = pd.concat([RES[s] for s in coins])
    w = None if single else {s: (1.0 if s == "BTCUSDT" else 0.5 if s == "ETHUSDT" else 0.25) for s in coins}
    cv, tk = simulate(T, risk=risk, cap=99, short_mult=0.5, start=a, end=b, eq0=200.0, weights=w)
    mo = (pd.Timestamp(b) - pd.Timestamp(a)).days / 30.44; pk = cv.worst.cummax()
    pm = ((cv.equity.iloc[-1] / 200) ** (1 / mo) - 1) * 100; dd = ((pk - cv.worst) / pk).max() * 100
    return cv.equity.iloc[-1], pm, dd


def combo(c):
    coins = ("BTCUSDT",) + c
    full = acct(coins, "2022-01-01", "2026-10-01"); d = acct(coins, "2022-01-01", "2024-01-01"); h = acct(coins, "2024-01-01", "2026-10-01")
    return coins, full, d, h


if __name__ == "__main__":
    print("=== each coin alone, 1% risk, $200, 2022-01 .. 2026-09 (no 2020-21) ===")
    rows = []
    for s, x in RES.items():
        f = acct([s], "2022-01-01", "2026-10-01", risk=0.01, single=True)
        yr = {y: x[(x.entry_time.dt.year == y)].R.sum() for y in (2022, 2023, 2024, 2025, 2026)}
        rows.append((s[:-4], f[0], f[1], f[2], (x[x.entry_time >= "2022"].R > .2).mean() * 100, yr))
    for r in sorted(rows, key=lambda r: -r[2]):
        print(f"  {r[0]:5s} $200 -> ${r[1]:6.0f}  {r[2]:5.2f}%/mo  worst drop {r[3]:4.1f}%  winners {r[4]:4.1f}%   net R by year: " +
              "  ".join(f"{y}:{v:+6.1f}" for y, v in r[5].items()))
    jobs = [c for k in (3, 4) for c in itertools.combinations(OTHERS, k)]
    with Pool(4) as p:
        out = p.map(combo, jobs)
    df = pd.DataFrame([dict(set="+".join(s[:-4] for s in co), n=len(co), usd=f[0], pm=f[1], dd=f[2], ratio=f[1] / f[2],
                            pm_22_23=d[1], dd_22_23=d[2], r_22_23=d[1] / d[2], pm_24_26=h[1], dd_24_26=h[2], r_24_26=h[1] / h[2])
                       for co, f, d, h in out])
    df["rank_full"] = df.ratio.rank(ascending=False).astype(int)
    cur = df[df.set == "BTC+ETH+DOGE+ADA"].iloc[0]
    print(f"\n=== {len(df)} sets with BTC (4 or 5 coins), 2022-26, ranked by %/month divided by worst drop ===")
    pd.set_option("display.width", 250)
    cols = ["set", "usd", "pm", "dd", "ratio", "pm_22_23", "dd_22_23", "pm_24_26", "dd_24_26"]
    print(df.sort_values("ratio", ascending=False)[cols].head(12).round(2).to_string(index=False))
    print(f"\ncurrent set BTC+ETH+DOGE+ADA: rank {cur.rank_full} of {len(df)}: ${cur.usd:,.0f}, {cur.pm:.2f}%/mo, drop {cur.dd:.1f}%, ratio {cur.ratio:.3f}")
    # honest check: pick the best 10 on 2022-23 only, see how they did 2024-26
    top = df.sort_values("r_22_23", ascending=False).head(10)
    print(f"\nbest 10 sets picked on 2022-23 -> their 2024-26 ratio: median {top.r_24_26.median():.3f} "
          f"(all sets median {df.r_24_26.median():.3f}, current set {cur.r_24_26:.3f}, rank of current in 2024-26: "
          f"{int(df.r_24_26.rank(ascending=False)[df.set == 'BTC+ETH+DOGE+ADA'].iloc[0])})")
    print(top[["set", "r_22_23", "r_24_26", "pm_24_26", "dd_24_26"]].round(3).to_string(index=False))
    print("\ncorrelation of a set's 2022-23 ratio with its 2024-26 ratio:", round(np.corrcoef(df.r_22_23, df.r_24_26)[0, 1], 2))
    df.to_pickle(C.D.CACHE / "combos22.pkl")
