"""What the bot's first months can look like from $200 (v2.5 as configured: portfolio.json risk ladder + open-risk cap,
BTC exempt; botsim.py), plus 2 years for the ladder vs flat risks.
(1) every real window of 2022-26 (start each week); (2) 5,000 block-bootstrap journeys (4-week blocks of 2022-26).
Worst drop counts open risk not at breakeven as lost; 'after $1k' = drops once the balance has reached $1,000."""
import numpy as np, pandas as pd
from multiprocessing import Pool
import botsim as B

POL = B.bot_policy()
PROFILES = {"ladder (the bot)": POL, "flat 5% + cap": B.flat_policy(5, 2.5, 0.83), "flat 7.5% + cap": B.flat_policy(7.5, 2.5, 0.83)}


def dd_after(ev, level=1000.0):
    pk, dd = 0.0, 0.0
    for t, bal, w in ev:
        if pk or w >= level:
            pk = max(pk, w); dd = max(dd, (pk - w) / pk)
    return dd * 100


def one(x, pol, months):
    r = B.run(x, pol, 200.0, end=months * B.MON, keep="events")
    return r["final"], r["dd"], len(x[x[:, 0] < months * B.MON]), dd_after(r["events"]), r["top"]


def window(args):
    t0, name, months = args
    x = B.TR[(B.TR[:, 0] >= t0) & (B.TR[:, 0] < t0 + months * B.MON)].copy(); x[:, :3] -= t0
    return one(x, PROFILES[name], months)


def boot(args):
    seed, name, months = args
    return one(B.journey_trades(seed, months=months), PROFILES[name], months)


def show(title, z, months):
    f, dd, n, d1, top = z.T
    q = lambda a, p: np.percentile(a, p)
    print(f"{title}: end  1-in-10 bad ${q(f,10):,.0f} | 1-in-4 bad ${q(f,25):,.0f} | typical ${q(f,50):,.0f} | 1-in-4 good ${q(f,75):,.0f} | 1-in-10 good ${q(f,90):,.0f}")
    print(f"   below $200: {(f < 200).mean()*100:.0f}% | below $100: {(f < 100).mean()*100:.0f}% | doubled: {(f >= 400).mean()*100:.0f}% | >= $10k: {(f >= 1e4).mean()*100:.0f}% | >= $20k: {(f >= 2e4).mean()*100:.0f}%")
    print(f"   worst drop: typical {q(dd,50):.0f}%, 1 in 4 {q(dd,75):.0f}%, 1 in 10 {q(dd,90):.0f}% | after $1k: typical {q(d1,50):.0f}%, 1 in 10 {q(d1,90):.0f}%"
          f" | trades typical {q(n,50):.0f} ({q(n,10):.0f}-{q(n,90):.0f}) | gave back half of a $5k+ peak {((top >= 5e3) & (f < top / 2)).mean()*100:.0f}%")


if __name__ == "__main__":
    with Pool(4) as p:
        for months in (3, 24):
            last = pd.Timestamp("2026-10-01") - pd.Timedelta(days=int(months * 30.44))
            starts = np.arange(pd.Timestamp("2022-01-03").value // B.MIN, last.value // B.MIN, 7 * 1440)
            for name in (["ladder (the bot)"] if months == 3 else list(PROFILES)):
                w = np.array(p.map(window, [(t, name, months) for t in starts]))
                b = np.array(p.map(boot, [(s, name, months) for s in range(5000 if months == 3 else 3000)], chunksize=50))
                print(f"\n=== {months} months from $200, {name} ===")
                show(f"real windows 2022-26 (n={len(w)})", w, months)
                show("reshuffled journeys", b, months)
