"""Shared tools of the v3.0 round (Nov 2026).
  trades30   exact TBO v2.8 engine run (xengine30) with separate long / short entry settings (channel n, daily EMA, max
             extension), separate long / short exits, cross-coin masks, post-loss cooldown and extra skip filters;
             phase-shifted 4h candles as in v29lib.trades
  be_nb      numba breakeven times (botsim's 'at +1.5R' moment)
  money_nb   numba botsim (= v29lib.run_money, plus a per-trade risk multiplier column), checked equal in parity()
  boot30     paired block-bootstrap 2-year journeys on numba money
  g6         the drawdown-matched money gate of the v3.0 protocol
Rows for money: (entry, exit, be, dir, R, coin, mult) in minutes; coins 0-4 = BTC ETH BNB SOL ADA, >= 5 sleeves."""
import os
import numpy as np, pandas as pd
from numba import njit
import common as C, families as F
import grid_v25 as G
import xengine30 as X30
import v29lib as L

COINS = L.COINS
END = L.END
LIVE_KW = dict(L.LIVE_KW)
SHIFTS = [int(round(240 * k / 41)) for k in range(1, 41)]
P20, P22, P24 = "2020-23", "2022-23", "2024-26"
PERIODS = L.PERIODS
MIN = L.MIN
SLIPS = {"BTCUSDT": 0.0001, "ETHUSDT": 0.0001}


def exit_vec(be_R=1.5, lock_R=5.0, lock_to=1.5, lock2_R=0.0, lock2_to=0.0, stale_h=0, stale_thr=-0.3, stale_to=0.0):
    return np.array([be_R, lock_R, lock_to, lock2_R, lock2_to, stale_h * 60, stale_thr if stale_h else -99.0, stale_to], float)


def _orders(mm, kw, side, skip):
    cap = {}
    def fake(m1, o, **k):
        cap["o"] = o; cap["k"] = k
    old = F.run
    F.run = fake
    try:
        F.channel_breakout(mm, **dict(kw, sides=side, skip_fn=skip))
    finally:
        F.run = old
    return cap["o"], cap["k"]


def _skip(sym, shift, low, extra):
    f72 = G.oi_skip(sym, 240); flow = G.oi_low_skip(sym, 240) if low else None
    def skip(c, a, hi, lo, s):
        cr = dict(c, t=c["t"] - shift) if shift else c
        out = f72(cr, a, hi, lo, s)
        if flow:
            out = out | flow(cr, a, hi, lo, s)
        if extra is not None:
            out = out | extra(cr, s)
        return out
    return skip


def trades30(sym, kwL=None, kwS=None, exL=None, exS=None, shift=0, low=True, ctrl=None, skipx=None, start="2020-01-01", end=END):
    """kwL / kwS: channel_breakout settings for longs / shorts (n, ema_n, max_ext, slope_d, hold_h ...) over LIVE_KW.
    exL / exS: exit_vec() kwargs. ctrl(m1_real_t) -> dict of per-minute masks fill_l fill_s tight_l tight_s exit_long
    exit_short (+ tight_to) and cool=(minutes, R, mode, clear). skipx(c_realtime, side) -> bool per 4h candle (True = skip)."""
    m = L.m1(sym)
    C.SLIP = SLIPS.get(sym, 0.0003)
    kL = dict(LIVE_KW, **(kwL or {})); kS = dict(LIVE_KW, **(kwS or {}))
    skip = _skip(sym, shift, low, skipx)
    mm = dict(m, t=m["t"] + shift) if shift else m
    try:
        if kL == kS:
            o, _ = _orders(mm, kL, "both", skip)
        else:
            o, _ = _orders(mm, kL, "long", skip)
            o2, _ = _orders(mm, kS, "short", skip)
            for a in ("kind", "direction", "price", "sl", "tp", "expiry"):
                getattr(o, a)[:, 1] = getattr(o2, a)[:, 1]
    finally:
        if shift:
            F._rs.cache_clear(); F._M1.clear()
    n = len(m["t"])
    bad = (o.kind != 0) & ~(o.sl > 0); o.kind[bad] = 0
    pl = exit_vec(**dict(dict(be_R=kL["be_R"], lock_R=kL["lock_R"], lock_to=kL["lock_to"]), **(exL or {})))
    ps = exit_vec(**dict(dict(be_R=kS["be_R"], lock_R=kS["lock_R"], lock_to=kS["lock_to"]), **(exS or {})))
    cc = ctrl(m["t"]) if ctrl else {}
    ones, zeros = np.ones(n, np.bool_), np.zeros(n, np.bool_)
    cool = cc.get("cool", (0, -0.5, 0, 0.0))
    res = X30.sim30(mm["t"], m["o"], m["h"], m["l"], m["c"], o.kind, o.direction, o.price, o.sl, np.nan_to_num(o.tp), o.expiry,
                    o.allow_entry, o.allow_fill, o.force_exit, cc.get("exit_long", o.exit_long), cc.get("exit_short", o.exit_short),
                    np.zeros(n), int(kL["hold_h"] * 60), int(kS["hold_h"] * 60), pl, ps,
                    cc.get("fill_l", ones), cc.get("fill_s", ones), cc.get("tight_l", zeros), cc.get("tight_s", zeros),
                    float(cc.get("tight_to", 0.0)), int(cool[0]), float(cool[1]), int(cool[2]), float(cool[3]))
    e_idx, x_idx, dirs, e_px, x_px, dist, reason = res
    tr = pd.DataFrame({"entry_time": C.D.to_datetime(m["t"][e_idx]), "exit_time": C.D.to_datetime(m["t"][x_idx]),
                       "dir": dirs, "entry": e_px, "exit": x_px, "sl_dist": dist, "reason": [C.E.REASONS[r] for r in reason]})
    fee = C.TAKER + C.SLIP
    gross = (tr["exit"] - tr["entry"]) * tr["dir"]
    hours = (tr["exit_time"] - tr["entry_time"]).dt.total_seconds() / 3600
    cost = fee * tr["entry"] + fee * tr["exit"] + C.FUNDING_8H * hours / 8 * tr["entry"]
    tr["R"] = (gross - cost) / tr["sl_dist"]; tr["hours"] = hours
    tr["e_i"] = e_idx; tr["x_i"] = x_idx
    tr = C.between(tr, start, end).reset_index(drop=True)
    tr["sym"] = sym
    beR = np.where(tr.dir.to_numpy() > 0, pl[0], ps[0])
    tr["be_time"] = C.D.to_datetime(be_nb(m["t"], m["h"], m["l"], tr.e_i.to_numpy(np.int64), tr.x_i.to_numpy(np.int64),
                                          tr.dir.to_numpy(np.int64), tr.entry.to_numpy(float), tr.sl_dist.to_numpy(float), beR))
    return tr


@njit(cache=True)
def be_nb(t, h, l, ei, xi, d, e, dist, R):
    out = np.empty(len(ei), np.int64)
    for k in range(len(ei)):
        lvl = e[k] + d[k] * R[k] * dist[k]; out[k] = t[xi[k]]
        for j in range(ei[k] + 1, xi[k] + 1):
            if (d[k] > 0 and h[j] >= lvl) or (d[k] < 0 and l[j] <= lvl):
                out[k] = t[j]; break
    return out


# ── money ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def pol_arrays(pol):
    rows = pol["rows"]
    thr = np.array([r[0] for r in rows], float); risk = np.array([r[1] for r in rows], float); capv = np.array([r[2] for r in rows], float)
    exl = np.array([i in pol["exempt"] for i in range(5)], np.bool_); exs = np.array([i in pol["exempt_s"] for i in range(5)], np.bool_)
    extra = np.zeros(16)
    for c_, f in pol.get("extra", []):
        extra[int(c_)] = f
    return (thr, risk, capv, exl, exs, np.array(pol["smult_c"], float), pol.get("cap_short") == "short", float(pol["minf"]),
            float(pol["mult"]), extra)


@njit(cache=True)
def _money(ev_t, ev_k, ev_i, d, R, coin, mult, eq0, thr, risk, capv, exl, exs, smult, cap_short, minf, gm, extra):
    n = len(d)
    amt = np.zeros(n); isopen = np.zeros(n, np.bool_); counted = np.zeros(n, np.bool_)
    eq = eq0; pk = eq0; dd = 0.0; csum = 0.0; skipped = 0
    for q in range(len(ev_t)):
        kd = ev_k[q]; i = ev_i[q]; c = coin[i]
        if kd == 1:
            r = 0
            for rr in range(len(thr)):
                if eq >= thr[rr]:
                    r = rr
            if c >= 5:
                a = eq * risk[r, 0] * extra[c] / 100 * gm * mult[i]
                if a > 0:
                    amt[i] = a; isopen[i] = True; counted[i] = False
                continue
            sm = smult[c] if d[i] < 0 else 1.0
            a = eq * risk[r, c] / 100 * gm * sm * mult[i]
            capx = capv[r]
            if d[i] < 0 and cap_short:
                capx = capv[r] * smult[0]
            ex = exs[c] if d[i] < 0 else exl[c]
            if capx > 0 and (not ex) and a > 0:
                room = capx / 100 * gm * eq - csum
                if a > room:
                    a = room if room > minf * a else 0.0
            if a > 0:
                amt[i] = a; isopen[i] = True; counted[i] = True; csum += a
            else:
                skipped += 1
        elif kd == 0:
            if isopen[i] and counted[i]:
                counted[i] = False; csum -= amt[i]
        else:
            if isopen[i]:
                eq += amt[i] * R[i]; isopen[i] = False
                if counted[i]:
                    counted[i] = False; csum -= amt[i]
        w = eq - csum
        if w > pk:
            pk = w
        if pk > 0 and (pk - w) / pk > dd:
            dd = (pk - w) / pk
    return eq, dd * 100, skipped


def money_nb(x, pol, eq0=300.0):
    """x rows (entry, exit, be, dir, R, coin[, mult]); same result as v29lib.run_money."""
    x = np.asarray(x, float)
    mult = x[:, 6] if x.shape[1] > 6 else np.ones(len(x))
    e = x[:, 0]; be = np.maximum(x[:, 2], e + 1e-3); xx = np.maximum(x[:, 1], e + 2e-3)
    n = len(x); idx = np.arange(n)
    t = np.r_[e, be, xx]; kind = np.r_[np.ones(n, np.int64), np.zeros(n, np.int64), np.full(n, 2, np.int64)]
    ii = np.r_[idx, idx, idx]; rank = np.r_[np.full(n, 2), np.ones(n), np.zeros(n)]
    order = np.lexsort((np.r_[3 * idx, 3 * idx + 1, 3 * idx + 2], rank, t))
    a = pol_arrays(pol)
    f, dd, sk = _money(t[order], kind[order], ii[order], x[:, 3], x[:, 4], x[:, 5].astype(np.int64), mult, eq0, *a)
    return dict(final=f, dd=dd, skipped=sk)


def window(A, a, b=END):
    t0, t1 = pd.Timestamp(a).value // MIN, pd.Timestamp(b).value // MIN
    x = A[(A[:, 0] >= t0) & (A[:, 0] < t1)].copy(); x[:, :3] -= t0
    return x


BOOT_N = int(os.environ.get("V30_BOOT", 1000))


def boot_paths(n=BOOT_N, a="2022-01-01", b=END, months=24, seed=0):
    t0, t1 = pd.Timestamp(a).value // MIN, pd.Timestamp(b).value // MIN
    r = np.random.default_rng(seed); nb = int(np.ceil(months * L.MON / L.BLK))
    return [t0 + r.integers(0, (t1 - L.BLK - t0) // 240, nb) * 240 for _ in range(n)]


def path_rows(A, us):
    rows = []
    for k, u in enumerate(us):
        s = A[(A[:, 0] >= u) & (A[:, 0] < u + L.BLK)].copy(); s[:, :3] += k * L.BLK - u
        rows.append(s)
    return np.concatenate(rows)


_PATHS = {}


def boot30(A, pol, n=BOOT_N, eq0=300.0, seed=0):
    key = (n, seed)
    if key not in _PATHS:
        _PATHS[key] = boot_paths(n, seed=seed)
    v = np.array([[*money_nb(path_rows(A, us), pol, eq0).values()][:2] for us in _PATHS[key]])
    return dict(med=float(np.median(v[:, 0])), p10=float(np.percentile(v[:, 0], 10)), dd_med=float(np.median(v[:, 1])),
                dd90=float(np.percentile(v[:, 1], 90)), p_loss=float((v[:, 0] < eq0).mean()))


def money_all(A, pol):
    out = {}
    for a in ("2020-01-01", "2022-01-01", "2024-01-01"):
        r = money_nb(window(A, a), pol); out[f"m{a[:4]}"] = r["final"]; out[f"dd{a[:4]}"] = r["dd"]
    out.update({f"boot_{k}": v for k, v in boot30(A, pol).items()})
    return out


KS = (1.00, 0.96, 0.93, 0.90)


def g6(A, pol, base, ks=KS):
    """Drawdown-matched money gate. base = money_all() of the baseline. For k = 1.00, 0.96, 0.93, 0.90 (all risks x k) the
    first k with boot_dd90 <= base boot_dd90 is used; PASS if there boot_med > base, boot_p10 >= base, money from $300 in 2022
    and 2024 > base, and the 2022 / 2024 window drops <= base + 1 point. Returns the row at the chosen k (or at k=1)."""
    first = None
    for k in ks:
        r = money_all(A, dict(pol, mult=pol.get("mult", 1.0) * k)); r["k"] = k
        first = first or r
        if r["boot_dd90"] <= base["boot_dd90"]:
            r["G6"] = bool(r["boot_med"] > base["boot_med"] and r["boot_p10"] >= base["boot_p10"] and r["m2022"] > base["m2022"]
                           and r["m2024"] > base["m2024"] and r["dd2022"] <= base["dd2022"] + 1 and r["dd2024"] <= base["dd2024"] + 1)
            r["matched"] = True
            return r
    first["G6"] = False; first["matched"] = False
    return first


# ── baseline portfolio: bot v2.8 + panic v2.7 ─────────────────────────────────────────────────────────────────────
def rows(X, coins=COINS, mult=None):
    m = lambda c: X[c].values.astype("datetime64[m]").astype(np.int64)
    ci = X.sym.map({s: i for i, s in enumerate(coins)}).to_numpy()
    mu = np.ones(len(X)) if mult is None else np.asarray(mult, float)
    A = np.c_[m("entry_time"), m("exit_time"), m("be_time"), X.dir.to_numpy(float), X["R"].to_numpy(float), ci, mu]
    return A[np.lexsort((A[:, 5], A[:, 0]))]


_SLV = {}


def sleeve():
    if "s" not in _SLV:
        import panic_sleeve as PSL
        ev = PSL.events(start="2022-01-01", end=END, extra_coins=())          # the v2.7 baseline (core coins only)
        S = PSL.sleeve_rows(ev)
        _SLV["s"] = np.c_[S, np.ones(len(S))]
    return _SLV["s"]


def with_sleeve(A, S=None):
    S = sleeve() if S is None else S
    B = np.r_[A, S]
    return B[np.lexsort((B[:, 5], B[:, 0]))]


def base_policy(**kw):
    kw.setdefault("extra_risk", [(5, 0.5)])
    return L.policy(**kw)


# ── fixed-unit account ────────────────────────────────────────────────────────────────────────────────────────────
def units(X, smult=0.5, mult=None):
    u = L.units(X, smult=smult)
    return u * (1.0 if mult is None else np.asarray(mult, float))


def score(X, mult=None, smult=0.5):
    return L.score(X, units(X, smult, mult))


def xr(sv, sb):
    return {k: (sv[k]["ratio"] / sb[k]["ratio"] if sb[k]["ratio"] and np.isfinite(sv[k]["ratio"]) else np.nan) for k in sb}


def parity():
    """xengine30 / money_nb vs the v2.8 list (botsim) and v29lib.run_money."""
    import botsim as B
    out = []
    for s in COINS:
        x = trades30(s)
        ref = B.ALL[(s, 0.0003)]
        same = len(x) == len(ref) and (x.entry_time.values == ref.entry_time.values).all() and np.allclose(x.R.values, ref.R.values, atol=1e-9)
        be_ok = (x.be_time.values == ref.be_time.values).mean() if len(x) == len(ref) else np.nan
        out.append((s, len(x), len(ref), same, be_ok))
    pol = base_policy()
    A = with_sleeve(np.c_[B.TR[:, :6], np.ones(len(B.TR))])
    for a in ("2022-01-01", "2024-01-01"):
        r1 = money_nb(window(A, a), pol); r2 = L.money_window(A[:, :6], a, END, pol)
        out.append((a, r1["final"], r2["final"], abs(r1["final"] - r2["final"]) < 1e-6 * r2["final"], r1["dd"] - r2["dd"]))
    return out


# ── TBO v3.0 live rules (C1 + C2, Nov 2026) ───────────────────────────────────────────────────────────────────────
V30_EXIT = dict(be_R=1.5, lock_R=5.0, lock_to=2.0, lock2_R=8.0, lock2_to=3.5, stale_h=60, stale_thr=-0.3, stale_to=0.0)
V30_COOL = (16 * 60, -0.5, 1, 0.25)            # 16 h after a trade closed below -0.5R (price R): no fill on that coin


def trades_v30(sym, shift=0, start="2020-01-01", end=END):
    """The v3.0 trades of one coin. be_time = when the trade stops counting under the open-risk cap: the first full minute
    at +1.5R, or the stale move (stop to entry at 60 h) if that comes first and the trade stays open."""
    x = trades30(sym, exL=V30_EXIT, exS=V30_EXIT, ctrl=lambda t: {"cool": V30_COOL}, shift=shift, start=start, end=end)
    m = L.m1(sym)
    sb = x.e_i.to_numpy() + V30_EXIT["stale_h"] * 60
    ok = sb < x.x_i.to_numpy()                                         # still open at the stale moment
    sbc = np.clip(sb, 0, len(m["t"]) - 1)
    cur = (m["o"][sbc] - x.entry.to_numpy()) * x.dir.to_numpy()
    st_t = C.D.to_datetime(m["t"][sbc])
    moved = ok & (cur > V30_EXIT["stale_thr"] * x.sl_dist.to_numpy()) & (x.be_time.values > st_t.values)
    x.loc[moved, "be_time"] = st_t[moved]
    return x
