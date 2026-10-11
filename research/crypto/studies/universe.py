"""Universe expansion (Oct 2026): the bot's sizing (risk ladder + open-risk cap, BTC exempt; botsim.run) on more coins.
Trades: v2.4 rules on all 12 coins with data (all12.py cache; the 5 live coins are the same trades as v24). Extra coins
start when their data starts. Scored on 2020-23 and 2024-26 separately, ladder from $200 and a fixed-size R account."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import numpy as np, pandas as pd
import common as C
import botsim as BS

R12 = pd.read_pickle(C.D.CACHE / "all12_v24.pkl")
LIVE = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
EXTRA = ["DOGEUSDT", "XRPUSDT", "LINKUSDT", "AVAXUSDT", "LTCUSDT", "TRXUSDT", "DOTUSDT"]


def arr(coins):
    T = pd.concat([R12[s] for s in coins]).copy()
    T["_c"] = T.sym.map({s: i for i, s in enumerate(coins)})
    T = T.sort_values(["entry_time", "_c"], kind="stable").reset_index(drop=True)
    m = lambda c: T[c].values.astype("datetime64[m]").astype(np.int64)
    return np.c_[m("entry_time"), m("exit_time"), m("be_time"), T.dir.values, T.R.values, T._c.values]


def policy(coins, alt):
    rows = []
    for f, rk, cap in BS.bot_policy()["rows"]:
        r = rk[:2] + [rk[2] * alt / 0.83] * (len(coins) - 2)    # BTC, ETH as the ladder; every other coin `alt` % at the 5% step
        rows.append((f, r, cap))
    p = BS.bot_policy(); p["rows"] = rows
    return p


def fixedR(x, coins, alt):
    w = np.array([2, 1] + [alt / 2.5] * (len(coins) - 2))[x[:, 5].astype(int)] * np.where(x[:, 3] < 0, 0.5, 1)
    o = np.argsort(x[:, 1]); e = np.cumsum((x[:, 4] * w)[o]); return e[-1], (np.maximum.accumulate(np.r_[0, e])[1:] - e).max()


SETS = [("now: 5 coins (alts 0.83%)", LIVE, 0.83),
        ("12 coins, extra alts 0.83% each", LIVE + EXTRA, 0.83),
        ("12 coins, alts 0.42% each", LIVE + EXTRA, 0.42),
        ("12 coins, same alt budget (10 alts x 0.25%)", LIVE + EXTRA, 0.25),
        ("5 + DOGE (best extra in 2020-23)", LIVE + ["DOGEUSDT"], 0.83),
        ("5 + DOGE, XRP, LINK, AVAX (alts 0.5%)", LIVE + ["DOGEUSDT", "XRPUSDT", "LINKUSDT", "AVAXUSDT"], 0.5)]

if __name__ == "__main__":
    base = None
    print(f"{'':46s} | 2020-23 ladder $200: final, drop, %/mo/drop | 2024-26: final, drop, %/mo/drop | fixed R acct net/DD 20-23 / 24-26 | trades 24-26")
    for name, coins, alt in SETS:
        x = arr(coins); pol = policy(coins, alt); out = []
        for a, b in (("2020-03-01", "2024-01-01"), ("2024-01-01", "2026-10-01")):
            t0, t1 = pd.Timestamp(a).value // BS.MIN, pd.Timestamp(b).value // BS.MIN
            xs = x[(x[:, 0] >= t0) & (x[:, 0] < t1)]
            r = BS.run(xs, pol, 200.0); mo = (t1 - t0) / 1440 / 30.44
            pm = ((r["final"] / 200) ** (1 / mo) - 1) * 100
            n, dd = fixedR(xs, coins, alt)
            out.append((r["final"], r["dd"], pm / r["dd"], n / dd, len(xs)))
        base = base or out
        print(f"{name:46s} | ${out[0][0]:>10,.0f} {out[0][1]:5.1f}% {out[0][2]:.3f} (x{out[0][2]/base[0][2]:.2f}) | ${out[1][0]:>8,.0f} {out[1][1]:5.1f}% {out[1][2]:.3f} (x{out[1][2]/base[1][2]:.2f}) | "
              f"x{out[0][3]/base[0][3]:.2f} / x{out[1][3]/base[1][3]:.2f} | {out[1][4]}")
