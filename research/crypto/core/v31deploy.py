"""TBO v3.1 as deployed (Nov 2026): the research twin of cryptobot/ (bot.py, volc.py, panic.py) for build_trades.py v31.

  TBO    v3.0 + failed-breakout stop tighten (from 8 h, hourly closes, been +0.9R but never +1.5R, close < -0.2R -> stop
         -0.5R, the cooldown after the trade whatever its result) + BTC stop-out cascade (BTC's trade closed below -0.5R
         net -> ETH / alts' open same-direction trades: stop -0.25R at the next minute). Engine core/xengine31.py.
  VOLC   cryptobot/volc_signal.py (the live code) on 4h candles from the 1m data; stop orders valid one 4h candle, stop
         1 ATR14, take-profit 1.5R (TAKE_PROFIT_MARKET: taker fee), 36 h; no order in the 12 h after a panic trigger (past
         only, as live); core 5 coins.
  Same coin, one position (Binance one-way mode), as live: a VOLC trade blocks the coin's TBO fills from its fill minute
  to the first 4h close after its exit, and a TBO trade blocks VOLC fills the same way. The two lists depend on each other
  (and the cascade on BTC's list): iterated until neither changes.
Money: TBO rows + Panic v3.0 rows + VOLC rows (coin 6, share 0.25 x the ladder's BTC risk), botsim sizing with the
portfolio.json in force (v3.1: the v3.0 ladder x 0.90)."""
import os, sys
from pathlib import Path
import numpy as np, pandas as pd
import common as C, v29lib as L, v31lib as W, xengine31 as X31

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "cryptobot"), str(ROOT / "cryptobot" / "dev")]
import volc_signal as VS                                            # noqa: E402

COINS = W.COINS
END = W.END
FB = dict(T_h=8, G=60, cont=1, mlo=0.9, mhi=99.0, thr=-0.2, act=3, lvl=-0.5)
CASC_R, CASC_TO = -0.5, -0.25
VOLC_SHARE = 0.25
VOLC_P = dict(VS.DEFAULTS)
TF = 240
MIN = W.MIN
SLIP = {"BTCUSDT": 0.0001, "ETHUSDT": 0.0001}


def next_close(t):
    """The first 4h close strictly after minute t."""
    return (np.asarray(t, np.int64) // TF + 1) * TF


def blocks_from(X):
    """{sym: [start, end) minute intervals} where X's trades hold the coin (to the first 4h close after the exit)."""
    out = {}
    for s, g in X.groupby("sym"):
        e = g.entry_time.values.astype("datetime64[m]").astype(np.int64)
        x = g.exit_time.values.astype("datetime64[m]").astype(np.int64) if "exit_time" in g else g.t_exit.values.astype("datetime64[m]").astype(np.int64)
        out[s] = np.c_[e, next_close(x)]
    return out


def _mask(t, iv):
    m = np.zeros(len(t), np.bool_)
    if iv is not None and len(iv):
        a = np.searchsorted(t, iv[:, 0]); b = np.searchsorted(t, iv[:, 1])
        d = np.zeros(len(t) + 1, np.int64); np.add.at(d, a, 1); np.add.at(d, b, -1)
        m = np.cumsum(d)[:-1] > 0
    return m


# ── TBO ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def tbo_coin(sym, block=None, btc=None, start="2020-01-01", end=END):
    """One coin's v3.1 TBO trades. block: intervals with no fills (VOLC holds the coin); btc: BTC's v3.1 trades (cascade)."""
    def ctrl(t):
        out = {}
        if block is not None and len(block):
            free = ~_mask(t, block)
            out["fill_l"] = free; out["fill_s"] = free
        if btc is not None and sym != "BTCUSDT":
            b = btc[btc.R < CASC_R]
            for d, nm in ((1, "l"), (-1, "s")):
                j = np.searchsorted(t, b[b.dir == d].exit_time.values.astype("datetime64[m]").astype(np.int64)) + 1
                m = np.zeros(len(t), np.bool_); m[j[j < len(t)]] = True
                out["tight_" + nm] = m
            out["tight_to"] = CASC_TO
        return out
    ex = dict(A=FB, rcool=1)
    return W.trades31(sym, exL=ex, exS=ex, ctrl=ctrl, start=start, end=end)


# ── VOLC ─────────────────────────────────────────────────────────────────────────────────────────────────────────
_PT = {}


def panic_triggers():
    """Panic v3.0 trigger moments (the signal hour's close, minutes) on DEV12, every signal (as panic.py's 'triggers')."""
    if "t" not in _PT:
        import panic_sleeve as PSL
        ev = PSL.events(start="2021-11-01", extra_coins=PSL.EXTRA_COINS, max_extra_open=None)
        _PT["t"] = np.unique(ev.t.values.astype("datetime64[m]").astype(np.int64))
    return _PT["t"]


def oi_series(sym):
    """(minute times, OI USD) of the archive rows (the last 5-minute sample of each hour), zeros carried forward."""
    import replay as RP                                           # cryptobot/dev/replay.load_oi (the parity tests' loader)
    t, v = RP.load_oi(sym)
    return t // 60_000, v


def volc_orders(sym, p=None):
    """VOLC orders of one coin at every 4h close, decided by cryptobot/volc_signal.decide on the same windows as live
    (1000 4h candles, 500 daily candles). Returns a DataFrame (t_place minute, dir, price, dist, tp_R)."""
    p = dict(VOLC_P, **(p or {}))
    m = L.m1(sym)
    c4 = C.D.resample(m, TF); d1 = C.D.resample(m, 1440)
    ot, ov = oi_series(sym)
    pt = panic_triggers()
    rows = []
    for k in range(len(c4["t"])):
        close = int(c4["t"][k]) + TF
        if close <= m["t"][0] + TF or c4["act"][k] >= len(m["t"]):
            continue
        k0 = max(0, k - 999)
        kd = int(np.searchsorted(d1["t"] + 1440, close, side="right"))     # daily candles closed by then
        dc = d1["c"][max(0, kd - 500):kd]

        def oi_at(end):
            j = int(np.searchsorted(ot, end, side="left")) - 1
            return float(ov[j]) if j >= 0 and ot[j] >= end - 30 else float("nan")
        dec = VS.decide(c4["h"][k0:k + 1], c4["l"][k0:k + 1], c4["c"][k0:k + 1], dc, oi_at(close), oi_at(close - 24 * 60), p)
        if dec["long"] is None and dec["short"] is None:
            continue
        j = np.searchsorted(pt, close, side="left")
        if j > 0 and pt[j - 1] >= close - int(p["excl_h"]) * 60:
            continue
        for d, lv in ((1, dec["long"]), (-1, dec["short"])):
            if lv is not None:
                rows.append((close, d, lv, dec["dist"], dec["tp_R"]))
    return pd.DataFrame(rows, columns=["t_place", "dir", "price", "dist", "tp_R"])


_VO = {}


def volc_coin(sym, block=None, start="2020-01-01", end=END, p=None):
    """One coin's VOLC trades on the 1m engine. block: intervals with no fills (TBO holds the coin)."""
    p = dict(VOLC_P, **(p or {}))
    key = (sym, tuple(sorted(p.items())))
    if key not in _VO:
        _VO[key] = volc_orders(sym, p)
    od = _VO[key]
    m = L.m1(sym); t = m["t"]; n = len(t)
    j = np.searchsorted(t, od.t_place.to_numpy(np.int64))
    ok = (j < n) & (od.dist.to_numpy() > 0)
    od = od[ok]; j = j[ok]
    uj, inv = np.unique(j, return_inverse=True)
    optr = np.full(n, -1, np.int64); optr[uj] = np.arange(len(uj))
    shp = (len(uj), 2)
    kind = np.zeros(shp, np.int64); dirn = np.zeros(shp, np.int64); price = np.zeros(shp); sl = np.zeros(shp); tp = np.zeros(shp)
    exp = np.zeros(shp, np.int64)
    slot = np.where(od.dir.to_numpy() > 0, 0, 1)
    kind[inv, slot] = C.E.STOP; dirn[inv, slot] = od.dir.to_numpy(np.int64); price[inv, slot] = od.price.to_numpy(float)
    sl[inv, slot] = od.dist.to_numpy(float); tp[inv, slot] = od.tp_R.to_numpy(float) * od.dist.to_numpy(float); exp[inv, slot] = TF
    ones, zeros = np.ones(n, np.bool_), np.zeros(n, np.bool_)
    free = ~_mask(t, block) if block is not None and len(block) else ones
    pa = W.exit31(be_R=0.0, lock_R=0.0, lock_to=0.0, lock2_R=0.0, lock2_to=0.0, stale_h=0)
    hold = int(p["hold_h"] * 60)
    res = X31.sim31(t, m["o"], m["h"], m["l"], m["c"], optr, kind, dirn, price, sl, tp, exp, ones, ones, zeros, zeros, zeros,
                    np.zeros(n), hold, hold, pa, pa, free, free, zeros, zeros, 0.0, 0, -0.5, 0, 0.0, np.zeros(n), ones)
    e_idx, x_idx, dirs, e_px, x_px, dist, reason, *_ = res
    tr = pd.DataFrame({"entry_time": C.D.to_datetime(t[e_idx]), "exit_time": C.D.to_datetime(t[x_idx]), "dir": dirs, "entry": e_px,
                       "exit": x_px, "sl_dist": dist, "reason": [C.E.REASONS[r] for r in reason]})
    fee = C.TAKER + SLIP.get(sym, 0.0003)                          # every fill taker (stop entry, stop / TP market exits)
    hours = (tr.exit_time - tr.entry_time).dt.total_seconds() / 3600
    tr["R"] = ((tr.exit - tr.entry) * tr.dir - fee * (tr.entry + tr.exit) - C.FUNDING_8H * hours / 8 * tr.entry) / tr.sl_dist
    tr["hours"] = hours; tr["sym"] = sym
    return tr[(tr.entry_time >= start) & (tr.entry_time < end) & (tr.reason != "END")].reset_index(drop=True)


# ── the joint simulation ─────────────────────────────────────────────────────────────────────────────────────────
def _keys(X):
    return set(zip(X.sym, X.entry_time.values.astype("datetime64[m]").astype(np.int64), X.dir))


def build(max_it=10, log=print, volc_p=None):
    """(TBO trades, VOLC trades, iterations). Starts from TBO without VOLC, then alternates until both lists are stable."""
    V = pd.DataFrame(columns=["sym", "entry_time", "exit_time", "dir", "R"])
    T = None
    for it in range(1, max_it + 1):
        vb = blocks_from(V) if len(V) else {}
        btc = tbo_coin("BTCUSDT", vb.get("BTCUSDT"))
        T_new = pd.concat([btc] + [tbo_coin(s, vb.get(s), btc) for s in COINS[1:]], ignore_index=True)
        tb = blocks_from(T_new)
        V_new = pd.concat([volc_coin(s, tb.get(s), p=volc_p) for s in COINS], ignore_index=True)
        stable = T is not None and _keys(T_new) == _keys(T) and _keys(V_new) == _keys(V)
        log(f"v31deploy iteration {it}: TBO {len(T_new)} trades ({T_new.R.sum():.1f}R), VOLC {len(V_new)} trades ({V_new.R.sum():.1f}R)"
            + (" -> stable" if stable else ""))
        T, V = T_new, V_new
        if stable:
            return T, V, it
    return T, V, -1


def volc_rows(V, share=VOLC_SHARE):
    m = lambda c: V[c].values.astype("datetime64[m]").astype(np.int64)
    return np.c_[m("entry_time"), m("exit_time"), m("entry_time"), V.dir.to_numpy(float), V.R.to_numpy(float), np.full(len(V), 6.0),
                 np.ones(len(V))]


def money_rows(T, V, with_volc=True):
    A = W.with_sleeve(W.rows(T), W.sleeve30())
    if with_volc and len(V):
        A = np.r_[A, volc_rows(V)]; A = A[np.lexsort((A[:, 5], A[:, 0]))]
    return A


def policy(pf=None, with_volc=True):
    ex = [(5, 0.5)] + ([(6, VOLC_SHARE)] if with_volc else [])
    return W.base_policy(pf=pf, extra_risk=ex) if pf else W.base_policy(extra_risk=ex)
