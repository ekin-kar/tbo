"""Shared tools of the v2.9 research round (Nov 2026): engine runs with the extra U2 / U3 options, phase-shifted 4h
candles, the fixed-unit account, a generalized botsim (per-tier short sizes, directional open-risk cap, extra sleeves),
and paired block-bootstrap journeys.

Periods (data to 2026-11-06): P2020 = 2020-23 (dev), P2223 = 2022-23 (OI dev), P2426 = 2024-26 (holdout incl. Oct-Nov 2026)."""
import os
import numpy as np, pandas as pd
import common as C, families as F
import grid_v25 as G
import xengine29 as X29
from wf2 import V21

COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
END = "2026-11-07"
PERIODS = {"2020-23": ("2020-01-01", "2024-01-01"), "2022-23": ("2022-01-01", "2024-01-01"), "2024-26": ("2024-01-01", END)}
BOT_W = {"BTCUSDT": 6.0, "ETHUSDT": 4.0}                     # fixed-unit weights (= the $0-1k ladder row); others 0.83
LIVE_KW = dict(V21, tf=240, n=20, be_R=1.5, hold_h=120, sl_mode="atr", sl_atr=1.0, lock_R=5.0, lock_to=1.5)
MIN = 60_000_000_000
_EXTRA = {}


def _run29(m1, orders, fee=None, funding=None, entry="taker", tp="taker", pad=0.0001, **kw):
    """common.run with xengine29 and the module-level _EXTRA options (sl floor applied to the orders here)."""
    funding = C.FUNDING_8H if funding is None else funding
    n = len(m1["t"])
    bad = (orders.kind != 0) & ~(orders.sl > 0)
    orders.kind[bad] = 0
    ex = dict(_EXTRA)
    flo = ex.pop("sl_min_pct", 0.0)
    if flo > 0:                                                        # U3: stop distance >= flo x the order price
        has = orders.kind != 0
        ref = np.where(orders.price > 0, orders.price, m1["o"][:, None])
        orders.sl[has] = np.maximum(orders.sl[has], flo * ref[has])
    late = ex.pop("late", None)
    lx = late[0] if late is not None else np.zeros(n, np.bool_)
    sx = late[1] if late is not None else np.zeros(n, np.bool_)
    res = X29._simulate(m1["t"], m1["o"], m1["h"], m1["l"], m1["c"],
                        orders.kind, orders.direction, orders.price, orders.sl, np.nan_to_num(orders.tp),
                        orders.expiry, orders.allow_entry, orders.allow_fill, orders.force_exit, orders.exit_long,
                        orders.exit_short, C.D.day_index(m1["t"]), kw.get("max_trades_day", 0), kw.get("max_bars", 0),
                        np.zeros(n), m1["o"] * pad, kw.get("group_size", 0), kw.get("miss_if_crossed", False),
                        kw.get("be_R", 0.0), kw.get("be_off", 0.0), kw.get("trail_k", 0.0), kw.get("trail_start", 0.0),
                        kw.get("early_bars", 0), kw.get("early_R", 0.0), kw.get("ext_bars", 0), kw.get("ext_R", 0.0),
                        kw.get("trail_after", 0), kw.get("lock_R", 0.0), kw.get("lock_to", 0.0),
                        int(ex.get("hold_s_h", 0) * 60), ex.get("lock2_R", 0.0), ex.get("lock2_to", 0.0), ex.get("lock3_R", 0.0),
                        ex.get("lock3_to", 0.0), int(ex.get("stale_h", 0) * 60), ex.get("stale_thr", -99.0), ex.get("stale_to", 0.0),
                        int(ex.get("run_mode", 0)), ex.get("run_R", 0.0), ex.get("run_k", 0.0), int(ex.get("run_max_h", 0) * 60), lx, sx)
    e_idx, x_idx, dirs, e_px, x_px, dist, reason = res
    tr = pd.DataFrame({"entry_time": C.D.to_datetime(m1["t"][e_idx]), "exit_time": C.D.to_datetime(m1["t"][x_idx]),
                       "dir": dirs, "entry": e_px, "exit": x_px, "sl_dist": dist,
                       "reason": [C.E.REASONS[r] for r in reason]})
    f_in = np.full(len(tr), C.TAKER + C.SLIP)
    f_out = np.where(tr["reason"].to_numpy() == "TP", C.MAKER if tp == "maker" else C.TAKER + C.SLIP, C.TAKER + C.SLIP)
    gross = (tr["exit"] - tr["entry"]) * tr["dir"]
    hours = (tr["exit_time"] - tr["entry_time"]).dt.total_seconds() / 3600
    cost = f_in * tr["entry"] + f_out * tr["exit"] + funding * hours / 8 * tr["entry"]
    tr["R_gross"] = gross / tr["sl_dist"]; tr["R"] = (gross - cost) / tr["sl_dist"]; tr["hours"] = hours
    tr["cost_R"] = cost / tr["sl_dist"]
    return tr


def ema_late_masks(m1, tf=240, n=10):
    """Per 1m bar: the last closed tf candle closed below (long exit) / above (short exit) its EMA(n)."""
    c = F.resample(m1, tf); e = C.I.ema(c["c"], n)
    k = np.searchsorted(c["act"], np.arange(len(m1["t"])), side="right") - 1
    kk = np.clip(k, 0, None)
    return ((k >= n) & (c["c"][kk] < e[kk])), ((k >= n) & (c["c"][kk] > e[kk]))


_M = {}


def m1(sym):
    if sym not in _M:
        _M[sym] = C.load(sym)
    return _M[sym]


def trades(sym, extra=None, shift=0, low=True, start="2020-01-01", end=END, kw=None):
    """v2.8 trades of one coin with the U2/U3 options in `extra`; shift (minutes) moves the 4h / daily candle boundaries
    (phase-shifted copy; the OI filters still read real time). Times returned in real time."""
    global _EXTRA
    m = m1(sym)
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    k = dict(LIVE_KW, **(kw or {}))
    f72 = G.oi_skip(sym, 240); flow = G.oi_low_skip(sym, 240) if low else None
    def skip(c, a, hi, lo, s):
        cr = dict(c, t=c["t"] - shift) if shift else c
        out = f72(cr, a, hi, lo, s)
        return out | flow(cr, a, hi, lo, s) if flow else out
    k["skip_fn"] = skip
    mm = dict(m, t=m["t"] + shift) if shift else m
    ex = dict(extra or {})
    if ex.get("run_mode") == 2:
        ex["late"] = ema_late_masks(mm, 240, int(ex.get("run_ema", 10)))
    _EXTRA = ex
    old = F.run
    F.run = _run29
    try:
        x = F.channel_breakout(mm, **k)
    finally:
        F.run = old; _EXTRA = {}
        if shift:
            F._rs.cache_clear(); F._M1.clear()
    if shift:
        x["entry_time"] -= pd.Timedelta(minutes=shift); x["exit_time"] -= pd.Timedelta(minutes=shift)
    x = C.between(x, start, end).reset_index(drop=True)
    x["sym"] = sym
    return x


def be_times(x, sym, R=1.5):
    """First full minute after the fill at +R (else the exit) = build_trades' be_time (botsim's 'at breakeven' moment)."""
    m = m1(sym); t = m["t"]
    e = x.entry_time.values.astype("datetime64[m]").astype(np.int64); xm = x.exit_time.values.astype("datetime64[m]").astype(np.int64)
    out = np.empty(len(x), np.int64)
    for k in range(len(x)):
        j0 = int(np.searchsorted(t, e[k])); j1 = int(np.searchsorted(t, xm[k]))
        d, lvl = x.dir.iat[k], x.entry.iat[k] + x.dir.iat[k] * R * x.sl_dist.iat[k]
        seg = m["h"][j0 + 1:j1 + 1] >= lvl if d > 0 else m["l"][j0 + 1:j1 + 1] <= lvl
        hit = np.nonzero(seg)[0]
        out[k] = t[j0 + 1 + hit[0]] if len(hit) else xm[k]
    return C.D.to_datetime(out)


# ── fixed-unit account ─────────────────────────────────────────────────────────────────────────────────────────
def units(X, w=None, smult=0.5, col="R"):
    """Per-trade P&L in units: coin weight x (shorts: smult, a number or {sym: mult}) x R."""
    w = w or {}
    cw = X.sym.map(lambda s: w.get(s, BOT_W.get(s, 0.83))).to_numpy(float)
    if isinstance(smult, dict):
        sm = X.sym.map(lambda s: smult.get(s, smult.get("alt", 0.5))).to_numpy(float)
    else:
        sm = np.full(len(X), float(smult))
    return X[col].to_numpy(float) * cw * np.where(X.dir.to_numpy() < 0, sm, 1.0)


def score(X, pnl=None, periods=PERIODS):
    """net, max drawdown (closed, in units) and net / drawdown per period; trades ordered by exit."""
    pnl = units(X) if pnl is None else pnl
    o = np.argsort(X.exit_time.values, kind="stable"); et = X.entry_time.values[o]; p = pnl[o]
    out = {}
    for nm, (a, b) in periods.items():
        m = (et >= np.datetime64(a)) & (et < np.datetime64(b))
        e = np.cumsum(p[m]); dd = float(np.max(np.maximum.accumulate(np.r_[0, e])[1:] - e)) if m.any() else np.nan
        net = float(e[-1]) if m.any() else 0.0
        out[nm] = dict(net=net, dd=dd, ratio=net / dd if dd else np.nan, n=int(m.sum()))
    return out


def ratio_x(sv, sb):
    return {k: sv[k]["ratio"] / sb[k]["ratio"] for k in sv}


# ── money: botsim generalized ──────────────────────────────────────────────────────────────────────────────────
def to_rows(X, coins=COINS):
    m = lambda c: X[c].values.astype("datetime64[m]").astype(np.int64)
    ci = X.sym.map({s: i for i, s in enumerate(coins)}).to_numpy()
    R = X["R"].to_numpy(float)
    A = np.c_[m("entry_time"), m("exit_time"), m("be_time"), X.dir.to_numpy(float), R, ci]
    return A[np.lexsort((A[:, 5], A[:, 0]))]


def policy(pf=None, smult=None, cap_short=None, exempt_short=None, extra_risk=()):
    """Bot policy (botsim.bot_policy) + options: smult = list of short multipliers per coin (default 0.5 all);
    cap_short = 'short' -> cap on short entries = cap_x x the BTC SHORT risk (cap_x = cap / BTC long risk);
    exempt_short = coin indices exempt on shorts (default = the long exemptions); extra_risk = [(coin index, risk as a
    fraction of the row's BTC risk)] for sleeves (always exempt, never counted)."""
    import botsim as B
    p = B.bot_policy(pf)
    p = dict(p, smult_c=list(smult) if smult is not None else [p["smult"]] * 5, cap_short=cap_short,
             exempt_s=set(exempt_short) if exempt_short is not None else set(p["exempt"]), extra=list(extra_risk))
    return p


def run_money(x, pol, eq0=300.0, keep=False):
    """botsim.run (same event order and rule) with the policy() options. x rows (entry, exit, be, dir, R, coin)."""
    ev = []
    for i, (e, xx, be, d, R, c) in enumerate(x):
        ev += [(e, 1, i), (max(be, e + 1e-3), 0, i), (max(xx, e + 2e-3), 2, i)]
    rank = {2: 0, 0: 1, 1: 2}
    ev.sort(key=lambda z: (z[0], rank[z[1]]))
    eq = eq0; opn = {}; pk = eq0; dd = 0.0; skipped = 0
    ex = dict(pol.get("extra", []))
    import botsim as B
    for t, kind, i in ev:
        e, xx, be, d, R, c = x[i]; c = int(c)
        if kind == 1:
            fr, rk, cap = B.row_at(pol, eq)
            if c >= 5:
                amt = eq * rk[0] * ex.get(c, 0.0) / 100 * pol["mult"]
                if amt > 0:
                    opn[i] = [amt, True]
                continue
            sm = pol["smult_c"][c] if d < 0 else 1.0
            amt = eq * rk[c] / 100 * pol["mult"] * sm
            capx = cap
            if d < 0 and pol.get("cap_short") == "short":
                capx = cap * pol["smult_c"][0]
            exempt = pol["exempt_s"] if d < 0 else pol["exempt"]
            if capx > 0 and c not in exempt and amt > 0:
                room = capx / 100 * pol["mult"] * eq - sum(v[0] for v in opn.values() if not v[1])
                if amt > room:
                    amt = room if room > pol["minf"] * amt else 0.0
            if amt > 0:
                opn[i] = [amt, False]
            else:
                skipped += 1
        elif kind == 0 and i in opn:
            opn[i][1] = True
        elif kind == 2 and i in opn:
            a = opn.pop(i)[0]; eq += a * R
        w = eq - sum(v[0] for v in opn.values() if not v[1])
        pk = max(pk, w); dd = max(dd, (pk - w) / pk)
    return dict(final=eq, dd=dd * 100, skipped=skipped)


def money_window(A, a, b, pol, eq0=300.0):
    t0, t1 = pd.Timestamp(a).value // MIN, pd.Timestamp(b).value // MIN
    x = A[(A[:, 0] >= t0) & (A[:, 0] < t1)].copy(); x[:, :3] -= t0
    return run_money(x, pol, eq0)


MON, BLK = 30.44 * 1440, 28 * 1440


def journeys(arrays, n=1000, a="2022-01-01", b=END, months=24, seed=0):
    """Paired block bootstrap: the same random 4-week time blocks cut from every array in `arrays` (variants of the same
    trade history), glued into 2-year paths starting at t=0. Yields lists of paths (one per array)."""
    t0, t1 = pd.Timestamp(a).value // MIN, pd.Timestamp(b).value // MIN
    r = np.random.default_rng(seed); nb = int(np.ceil(months * MON / BLK))
    for _ in range(n):
        us = t0 + r.integers(0, (t1 - BLK - t0) // 240, nb) * 240
        outs = []
        for A in arrays:
            rows = []
            for k, u in enumerate(us):
                s = A[(A[:, 0] >= u) & (A[:, 0] < u + BLK)].copy(); s[:, :3] += k * BLK - u
                rows.append(s)
            outs.append(np.concatenate(rows))
        yield outs


def boot_money(arrays, pols, n=1000, eq0=300.0, seed=0):
    """Median end balance and 1-in-10 worst drop over n paired journeys, per (array, policy) pair."""
    res = [[] for _ in arrays]
    for paths in journeys(arrays, n, seed=seed):
        for k, (x, p) in enumerate(zip(paths, pols)):
            r = run_money(x, p, eq0); res[k].append((r["final"], r["dd"]))
    out = []
    for v in res:
        v = np.array(v)
        out.append(dict(med=float(np.median(v[:, 0])), p10=float(np.percentile(v[:, 0], 10)), dd_med=float(np.median(v[:, 1])),
                        dd90=float(np.percentile(v[:, 1], 90)), p_loss=float((v[:, 0] < eq0).mean())))
    return out
