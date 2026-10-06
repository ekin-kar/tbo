"""
ETH/BTC spread mean reversion (market neutral): long ETH + short BTC (equal dollars) when ETH is cheap vs
its recent ratio to BTC, the reverse when rich. Decisions on closed tf candles, fills at the next open.
Costs: 4 taker fills (2 legs x in/out) at 0.06% each = 0.24% of one leg's notional per round trip;
funding roughly cancels (one leg long, one short) and is ignored.
Returns are in % of ONE leg's notional (leg notional = account equity -> 2x gross exposure).
"""
import itertools, sys
from multiprocessing import Pool
import numpy as np, pandas as pd
from numba import njit
import common as C, families as F

COST = 4 * (C.TAKER + C.SLIP)


def bars(tf):
    b = F.resample(C.load("BTCUSDT"), tf); e = F.resample(C.load("ETHUSDT"), tf)
    t = np.intersect1d(b["t"], e["t"])
    ib = np.searchsorted(b["t"], t); ie = np.searchsorted(e["t"], t)
    return dict(t=t, bo=b["o"][ib], bc=b["c"][ib], eo=e["o"][ie], ec=e["c"][ie])


@njit(cache=True)
def _sim(s_close, z, so, k, xz, kstop, hold):
    """Position in the spread s = log(ETH/BTC). Signal at close i, fill at open i+1."""
    n = len(z)
    ent = np.empty(n, np.int64); ext = np.empty(n, np.int64); dirs = np.empty(n, np.int64); ret = np.empty(n)
    m = 0; pos = 0; ei = 0; ep = 0.0
    for i in range(n - 1):
        if np.isnan(z[i]):
            continue
        if pos != 0:
            done = (pos == 1 and z[i] >= -xz) or (pos == -1 and z[i] <= xz) or (i + 1 - ei >= hold) \
                   or (kstop > 0 and abs(z[i]) >= kstop)
            if done:
                xp = so[i + 1]
                ent[m] = ei; ext[m] = i + 1; dirs[m] = pos; ret[m] = pos * (xp - ep); m += 1
                pos = 0
                continue
        if pos == 0:
            if z[i] <= -k:
                pos = 1; ei = i + 1; ep = so[i + 1]
            elif z[i] >= k:
                pos = -1; ei = i + 1; ep = so[i + 1]
    return ent[:m], ext[:m], dirs[:m], ret[:m]


def run(B, n=72, k=2.0, xz=0.0, kstop=0.0, hold=72):
    s_c = np.log(B["ec"] / B["bc"]); s_o = np.log(B["eo"] / B["bo"])
    sc = pd.Series(s_c)
    z = ((sc - sc.rolling(n).mean()) / sc.rolling(n).std()).to_numpy()
    ent, ext, d, r = _sim(s_c, z, s_o, k, xz, kstop, hold)
    # leg returns: exp(log spread change) - 1 is close enough; use simple: r (log) minus costs
    tr = pd.DataFrame(dict(entry_time=pd.to_datetime(B["t"][ent] * 60, unit="s"),
                           exit_time=pd.to_datetime(B["t"][ext] * 60, unit="s"), dir=d, ret=r - COST))
    return tr


GRID = dict(tf=[60, 240], n=[24, 72, 168, 500], k=[1.5, 2.0, 2.5, 3.0], xz=[0.0, 0.5], kstop=[0.0, 4.0],
            hold=[24, 72, 168])   # hold in BARS
BARS = {}


def one(kw):
    kw = dict(kw); tf = kw.pop("tf")
    if tf not in BARS:
        BARS[tf] = bars(tf)
    tr = run(BARS[tf], **kw)
    tr = tr[(tr.entry_time >= C.DEV[0]) & (tr.entry_time < C.DEV[1])]
    if len(tr) < 30:
        return None
    r = tr.ret.to_numpy()
    eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    y = tr.groupby(tr.entry_time.dt.year).ret.sum()
    mo = tr.groupby(tr.exit_time.dt.to_period("M")).ret.sum()
    return dict(tf=tf, **kw, trades=len(r), win=round((r > 0).mean() * 100, 1), avg_bp=round(r.mean() * 1e4, 1),
                total_pct=round(r.sum() * 100, 1), DD_pct=round(dd * 100, 1), MAR=round(r.sum() / 3.83 / max(dd, 0.01), 2),
                mpos=round((mo > 0).mean(), 2), yrs_pos=int((y > 0).sum()), **{f"y{k_}": round(v * 100, 1) for k_, v in y.items()})


if __name__ == "__main__":
    combos = [dict(zip(GRID, v)) for v in itertools.product(*GRID.values())]
    with Pool(4) as p:
        rows = [r for r in p.map(one, combos, chunksize=8) if r]
    df = pd.DataFrame(rows); df.to_csv(C.ROOT / "research" / "results" / "crypto_pairs_dev.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)
    print(len(combos), "combos; share MAR>0.5 & 4/4 yrs:", round(((df.MAR > 0.5) & (df.yrs_pos == 4)).mean(), 3))
    print(df.sort_values("MAR", ascending=False).head(15).to_string(index=False))
    for k_ in GRID:
        print(f"  {k_:6s}", df.groupby(k_).MAR.median().round(2).to_dict())
