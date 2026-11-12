"""Builds the bot's backtest trade list for the five coins with the research engine (live settings: 4h, channel 20,
1.0 ATR stop, breakeven 1.5R, 120 h, OI filter 72 h <= -3%; slippage BTC/ETH 0.01%, alts 0.03%), optionally with the
v2.6 profit lock (+5R -> stop +1.5R) and the v2.8 OI-low filter (OI in the lowest 20% of 90 days -> no order). Writes cache/portfolio_trades_<tag>.pkl (same format as v24: sym, entry_time,
exit_time, be_time, dir, R, hours) and cache/trade_prices_<tag>.pkl (entry, exit, sl_dist, reason).
    python build_trades.py check     # rebuild without the lock and compare with v24 (must be identical)
    python build_trades.py v26       # with the profit lock
    python build_trades.py v28       # + the OI-low filter (the live rules v2.8)
    python build_trades.py v31       # TBO v3.1 (live from 13 Nov 2026; botsim's default): v3.0 + failed-breakout stop tighten,
                                     # BTC stop-out cascade and the VOLC sleeve on the same coins (core/v31deploy.py, the
                                     # research twin of cryptobot/); also writes cache/volc_trades_v31.pkl
    python build_trades.py v30       # TBO v3.0 (live 6-12 Nov 2026): v2.8 + 16 h cooldown after a loss
                                     # (< -0.5R) + exits lock +5R -> +2R, 2nd lock +8R -> +3.5R, stale stop to entry at 60 h
                                     # (engine core/xengine30.py via v30lib.trades_v30, exact parity with v2.8 when off)"""
import os, pickle, sys
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C, families as F
import grid_v25 as G
from wf2 import V21

COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
END = os.environ.get("TBO_END", "2026-11-07")          # data end (extended by fetch_extend.py); v28 used 2026-10-01


def build(args):
    sym, tag = args
    if tag.startswith("v30"):
        import v30lib as V
        x = V.trades_v30(sym, start="2020-01-01", end=END).reset_index(drop=True)
        return sym, x
    lock, low = tag != "check", tag.startswith("v28")
    m = C.load(sym)
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    kw = dict(V21, tf=240, n=20, be_R=1.5, hold_h=120, **G.STOPS[1][1])
    kw["skip_fn"] = G.oi_skip(sym, 240)
    if low:
        f72, flow = kw["skip_fn"], G.oi_low_skip(sym, 240)
        kw["skip_fn"] = lambda c, a, hi, lo, s: f72(c, a, hi, lo, s) | flow(c, a, hi, lo, s)
    if lock:
        kw.update(lock_R=5.0, lock_to=1.5)
    x = C.between(F.channel_breakout(m, **kw), "2020-01-01", END).reset_index(drop=True)
    t = m["t"]; e = x.entry_time.values.astype("datetime64[m]").astype(np.int64); xm = x.exit_time.values.astype("datetime64[m]").astype(np.int64)
    be = []
    for k in range(len(x)):                                   # first full minute after the fill at +1.5R (before the exit)
        j0 = int(np.searchsorted(t, e[k])); j1 = int(np.searchsorted(t, xm[k]))
        d, lvl = x.dir[k], x.entry[k] + x.dir[k] * 1.5 * x.sl_dist[k]
        seg = m["h"][j0 + 1:j1 + 1] >= lvl if d > 0 else m["l"][j0 + 1:j1 + 1] <= lvl
        hit = np.nonzero(seg)[0]
        be.append(t[j0 + 1 + hit[0]] if len(hit) else xm[k])
    x["be_time"] = C.D.to_datetime(np.array(be))
    x["sym"] = sym
    return sym, x


def build_v31():
    os.environ["BOT_TRADES"] = "v30"                 # (botsim is imported on the way, by the panic sleeve: not the list being built)
    import v31deploy as D
    T, V, it = D.build()
    if it < 0:
        raise SystemExit("v31deploy did not settle")
    cols = ["sym", "entry_time", "exit_time", "be_time", "dir", "R", "hours"]
    pickle.dump({(s, 0.0003): T[T.sym == s][cols].reset_index(drop=True) for s in COINS}, open(C.D.CACHE / "portfolio_trades_v31.pkl", "wb"))
    T[["sym", "entry_time", "entry", "exit", "sl_dist", "reason"]].to_pickle(C.D.CACHE / "trade_prices_v31.pkl")
    V.to_pickle(C.D.CACHE / "volc_trades_v31.pkl")
    print("v31", len(T), "TBO trades;", {s: round(float(T[T.sym == s].R.sum()), 1) for s in COINS}, "| VOLC", len(V), "trades",
          round(float(V.R.sum()), 1), "R")


if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "check"
    if tag == "v31":
        build_v31(); raise SystemExit
    with Pool(3) as p:
        res = dict(p.map(build, [(s, tag) for s in COINS]))
    cols = ["sym", "entry_time", "exit_time", "be_time", "dir", "R", "hours"]
    if tag == "check":
        V = pickle.load(open(C.D.CACHE / "portfolio_trades_v24.pkl", "rb"))
        for s in COINS:
            a, b = res[s][cols].reset_index(drop=True), V[(s, 0.0003)][cols].reset_index(drop=True)
            same = len(a) == len(b) and (a.entry_time == b.entry_time).all() and (a.exit_time == b.exit_time).all() and \
                (np.abs(a.R - b.R) < 1e-9).all() and (a.be_time == b.be_time).all()
            print(s, len(a), len(b), "identical" if same else "DIFFERENT",
                  "" if same else f"be_time equal {(a.be_time == b.be_time).mean() if len(a) == len(b) else '-'}")
    else:
        pickle.dump({(s, 0.0003): res[s][cols] for s in COINS}, open(C.D.CACHE / f"portfolio_trades_{tag}.pkl", "wb"))
        pd.concat([res[s][["sym", "entry_time", "entry", "exit", "sl_dist", "reason"]] for s in COINS], ignore_index=True) \
            .to_pickle(C.D.CACHE / f"trade_prices_{tag}.pkl")
        n = sum(len(res[s]) for s in COINS)
        print(tag, n, "trades;", {s: round(float(res[s].R.sum()), 1) for s in COINS})
