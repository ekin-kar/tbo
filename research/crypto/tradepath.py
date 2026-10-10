"""1-minute trade path for one position managed like the bot (stop 1 ATR from the fill, breakeven at +1.5R, time exit
after 120 h), costs as the research engine (taker + slippage in and out, funding 0.01%/8h on the entry notional).
Used to re-enter blocked trades later (gate_test.py). Validated against the engine's own trades (__main__)."""
import numpy as np, pandas as pd
import common as C
import botsim as BS

COINS = BS.COINS
SLIP = {"BTCUSDT": 0.0001, "ETHUSDT": 0.0001, "BNBUSDT": 0.0003, "SOLUSDT": 0.0003, "ADAUSDT": 0.0003}
M = {}


def m1(ci):
    if ci not in M:
        M[ci] = C.load(COINS[ci])
    return M[ci]


def idx(ci, t):
    m = m1(ci)
    return int(np.searchsorted(m["t"], t))


def price(ci, t):
    """Close of the last finished 1m bar before minute t."""
    m = m1(ci); j = max(0, int(np.searchsorted(m["t"], t)) - 1)
    return float(m["c"][j])


def run(ci, d, t_e, p_e, dist, hold_min=7200, be_R=1.5, entry_fee=None, marks=(0.5, 1.0), end_min=None):
    """Position opened during minute t_e at p_e (stop p_e - d*dist). Returns dict(exit_t, exit_px, R, be_t, mark_t{k: t},
    reason). end_min: forced close at this minute (e.g. the coin's next own trade)."""
    m = m1(ci); j0 = int(np.searchsorted(m["t"], t_e)); j1 = min(len(m["t"]), j0 + hold_min + 1)
    if end_min is not None:
        j1 = min(j1, int(np.searchsorted(m["t"], end_min)) + 1)
    o, h, l, c, t = m["o"][j0:j1], m["h"][j0:j1], m["l"][j0:j1], m["c"][j0:j1], m["t"][j0:j1]
    fav = h if d > 0 else -l                                        # favourable extreme, sign-adjusted
    adv = l if d > 0 else -h
    sp, ep = d * (p_e - d * dist), d * p_e                           # stop / entry in sign-adjusted units
    hit = np.nonzero(adv <= sp)[0]                                   # initial stop (fill minute included: pessimistic)
    k_stop = hit[0] if len(hit) else 10**9
    beh = np.nonzero(fav[1:] >= ep + be_R * dist)[0]                 # breakeven from the first full minute after the fill
    k_be = beh[0] + 1 if len(beh) else 10**9
    marks_t = {}
    for q in marks:
        mh = np.nonzero(fav[1:] >= ep + q * dist)[0]
        marks_t[q] = int(t[mh[0] + 1]) if len(mh) and mh[0] + 1 < min(k_stop, len(t)) else None
    if k_stop <= k_be:
        k = k_stop
        if k < len(t):
            xp = d * min(sp, d * o[k] if k > 0 else sp); reason = "SL"
        else:
            k = len(t) - 1; xp = c[k]; reason = "TIME"
    else:
        hit2 = np.nonzero(adv[k_be + 1:] <= ep)[0]
        if len(hit2):
            k = k_be + 1 + hit2[0]; xp = d * min(ep, d * o[k]); reason = "BE"
        else:
            k = len(t) - 1; xp = c[k]; reason = "TIME"
    if k >= len(t):
        k = len(t) - 1; xp = c[k]; reason = "TIME"
    if reason == "TIME":
        xp = float(o[k]) if k > 0 else float(c[k])
    sl = SLIP[COINS[ci]]
    f_in = C.TAKER + sl if entry_fee is None else entry_fee
    hours = (int(t[k]) - t_e) / 60
    cost = f_in * p_e + (C.TAKER + sl) * xp + C.FUNDING_8H * hours / 8 * p_e
    R = ((xp - p_e) * d - cost) / dist
    return dict(exit_t=int(t[k]), exit_px=float(xp), R=float(R), be_t=int(t[k_be]) if k_be < len(t) and k_be < k + 1 else None,
                marks=marks_t, reason=reason)


if __name__ == "__main__":
    P = pd.read_pickle(C.D.CACHE / "trade_prices_v24.pkl")
    T = BS.T.merge(P, on=["sym", "entry_time"], how="left")
    e = T.entry_time.values.astype("datetime64[m]").astype(np.int64); x = T.exit_time.values.astype("datetime64[m]").astype(np.int64)
    ci = T.sym.map({s: i for i, s in enumerate(COINS)}).to_numpy()
    rng = np.random.default_rng(1); pick = rng.choice(len(T), 300, replace=False)
    dR, dx = [], []
    for k in pick:
        r = run(int(ci[k]), int(T.dir[k]), int(e[k]), float(T.entry[k]), float(T.sl_dist[k]))
        dR.append(r["R"] - T.R[k]); dx.append(r["exit_t"] - x[k])
    dR, dx = np.abs(dR), np.abs(dx)
    print(f"300 trades: |R diff| median {np.median(dR):.4f}, 95% {np.percentile(dR, 95):.3f}, max {dR.max():.3f}; "
          f"exit minute equal {np.mean(dx == 0)*100:.0f}%, within 1 min {np.mean(dx <= 1)*100:.0f}%")
