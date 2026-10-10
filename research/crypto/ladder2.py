"""Smoother risk ladders (Oct 2026): the live 3-step ladder vs more steps / a gradual glide by balance. BTC risk is a
function of the balance; ETH = min(2.5, BTC/2), each alt = ETH/3 (as the live rows); open-risk cap 1.1 x BTC risk, BTC
exempt; v2.6 trades (botsim, profit lock). Glides are done in small steps (every +5% of balance).
Scored: real history from $200 (2020, 2022, 2024 runs), every real 2-year window 2022-26, and 3,000 reshuffled 2-year
journeys (4-week blocks of 2022-26 trades), with the drop once the account is above $1k (money you care about)."""
from multiprocessing import Pool
import numpy as np, pandas as pd
import botsim as BS
from three_months import dd_after


def glide(points):
    """points: [(balance, BTC%)], log-linear between them, flat outside. -> policy rows every 5% of balance."""
    bal = np.array([p[0] for p in points], float); r = np.array([p[1] for p in points], float)
    rows, b = [], 0.0
    lv = [0.0] + list(np.geomspace(bal[0], 200_000, int(np.log(200_000 / bal[0]) / np.log(1.05)) + 1))
    for b in lv:
        btc = float(np.interp(np.log(max(b, bal[0])), np.log(bal), r))
        btc = round(btc, 3); eth = min(2.5, btc / 2); alt = round(eth / 3, 3)
        if not rows or rows[-1][1] != btc:
            rows.append((b, btc, eth, alt))
    return BS.ladder_policy(rows)


P = {"now: 7.5% -> 5% at $1k -> 2.5% at $10k": BS.bot_policy(),
     "7 steps: 7.5/6.5/5.5/5/4/3/2.5 at 0/500/1k/2.5k/5k/10k/20k":
         BS.ladder_policy([(0, 7.5, 2.5, .83), (500, 6.5, 2.5, .83), (1000, 5.5, 2.5, .83), (2500, 5, 2.5, .83),
                           (5000, 4, 2, .67), (10000, 3, 1.5, .5), (20000, 2.5, 1.25, .42)]),
     "glide 7.5% at $200 -> 2.5% at $20k": glide([(200, 7.5), (20000, 2.5)]),
     "glide 7.5% to $1k, -> 2.5% at $10k": glide([(1000, 7.5), (10000, 2.5)]),
     "glide 7.5% at $200 -> 5% at $2k -> 2.5% at $20k": glide([(200, 7.5), (2000, 5), (20000, 2.5)]),
     "glide 7.5% to $500 -> 5% at $2k -> 2.5% at $10k": glide([(500, 7.5), (2000, 5), (10000, 2.5)]),
     "glide 9% at $200 -> 5% at $2k -> 2.5% at $20k": glide([(200, 9), (2000, 5), (20000, 2.5)]),
     "flat 5% (reference)": BS.flat_policy(5, 2.5, 0.83)}
M24 = 24 * BS.MON


def one(x, pol):
    r = BS.run(x, pol, 200.0, end=M24, keep="events")
    return r["final"], r["dd"], dd_after(r["events"]), r["top"]


def boot(args):
    s, name = args
    return one(BS.journey_trades(s, months=24), P[name])


def window(args):
    t0, name = args
    x = BS.TR[(BS.TR[:, 0] >= t0) & (BS.TR[:, 0] < t0 + M24)].copy(); x[:, :3] -= t0
    return one(x, P[name])


if __name__ == "__main__":
    starts = np.arange(pd.Timestamp("2022-01-03").value // BS.MIN, (pd.Timestamp("2026-10-01") - pd.Timedelta(days=731)).value // BS.MIN, 7 * 1440)
    print(f"{'':54s} | history from $200 to Sep 2026: final, worst drop      | 2 yrs, reshuffled: typical, 1-in-4 bad, >=$10k, >=$20k, drop after $1k typ/1-in-10 | real 2-yr windows: typical, >=$10k, drop after $1k")
    with Pool(3) as p:
        for name, pol in P.items():
            h = []
            for a in ("2020-03-01", "2022-01-01", "2024-01-01"):
                x, _, _ = BS.window(a, "2026-10-01"); r = BS.run(x, pol, 200.0); h.append(f"${r['final']:>10,.0f} {r['dd']:4.1f}%")
            b = np.array(p.map(boot, [(s, name) for s in range(3000)], chunksize=50))
            w = np.array(p.map(window, [(t, name) for t in starts]))
            f, d1 = b[:, 0], b[:, 2]; q = np.percentile
            print(f"{name:54s} | {' | '.join(h)} | ${q(f,50):>7,.0f} ${q(f,25):>6,.0f} {(f>=1e4).mean()*100:3.0f}% {(f>=2e4).mean()*100:3.0f}% {q(d1,50):3.0f}%/{q(d1,90):3.0f}% | "
                  f"${q(w[:,0],50):>7,.0f} {(w[:,0]>=1e4).mean()*100:3.0f}% {q(w[:,2],50):3.0f}%", flush=True)
