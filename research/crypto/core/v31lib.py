"""Shared tools of the v3.1 round (Nov 2026; data to 2026-11-06). Baseline = the deployed TBO v3.0 (v2.8 entries + 16 h
cooldown after a stop + exits lock +5R -> +2R / +8R -> +3.5R / stale stop to entry at 60 h) + Panic v3.0 (5 core coins +
7 DEV12 extra coins at 0.75 share, max 2 extra open).

  trades31   exact engine run (xengine31.sim31) with the v3.0 rules as defaults; options: checkpoint rules A / B, soft
             ratchet, fill-time re-anchor (fast ATR 15m / 1h), cross-coin masks, cooldown variants, order validity window,
             extra skip filters with access to the 4h candle / ATR / channel (c, a, hi, lo, side)
  exit31     exit vector for sim31 (v3.0 exits + the v3.1 controls)
  money31    numba botsim (= v30lib.money_nb when the new options are off) with: a half-risk moment per trade (column 7,
             counted open risk -> hfrac x amount), BTC open risk counted x k while underwater (per-entry flag column 8),
             and a rolling closed-loss brake (risk x m for new TBO entries after the closed P&L over the last D days fell
             below -X BTC-risk units; reset the moment any open TBO trade reaches its risk-free stop or a sleeve trade wins)
  base31     the v3.0 trades (shift 0 or a phase shift), cached on disk
Rows for money: (entry, exit, be, dir, R, coin, mult[, half, btc_uw]) in minutes; coins 0-4 = BTC ETH BNB SOL ADA, >= 5 sleeves."""
import os
import numpy as np, pandas as pd
from numba import njit
import common as C, families as F
import grid_v25 as G
import xengine31 as X31
import v29lib as L
import v30lib as V

COINS = V.COINS
END = V.END
LIVE_KW = dict(V.LIVE_KW)
SHIFTS = V.SHIFTS
P20, P22, P24 = V.P20, V.P22, V.P24
PERIODS = L.PERIODS
MIN = L.MIN
SLIPS = V.SLIPS
CACHE = C.D.CACHE / "v31"

V30_EXIT = dict(V.V30_EXIT)
V30_COOL = V.V30_COOL                               # (16 h, -0.5R, mode 1, clear 0.25)


def exit31(be_R=1.5, lock_R=5.0, lock_to=2.0, lock2_R=8.0, lock2_to=3.5, stale_h=60, stale_thr=-0.3, stale_to=0.0,
           sr_at=0.0, sr_to=-0.5, A=None, B=None, ra=None, rcool=0):
    """v3.0 exits by default. A / B: dict(T_h, G=1|15|60, cont=0|1, mlo, mhi, thr, act=1|2|3, lvl). ra: dict(mode, lo, hi,
    alpha, anchor=0|1, den=0|1, k=2, rmax=2, rmin=0.3)."""
    v = np.zeros(X31.NP)
    v[:8] = [be_R, lock_R, lock_to, lock2_R, lock2_to, stale_h * 60, stale_thr if stale_h else -99.0, stale_to]
    v[X31.SR_AT] = sr_at; v[X31.SR_TO] = sr_to
    for base, r in ((X31.RA_, A), (X31.RB_, B)):
        if r:
            v[base:base + 8] = [r["T_h"] * 60, r.get("G", 1), r.get("cont", 0), r.get("mlo", -99.0), r.get("mhi", 99.0),
                                r.get("thr", 0.0), r.get("act", 2), r.get("lvl", 0.0)]
    if ra:
        v[X31.RA_MODE:X31.RA_MIN + 1] = [ra["mode"], ra.get("lo", 0.0), ra.get("hi", 99.0), ra.get("alpha", 0.5),
                                         ra.get("anchor", 1), ra.get("den", 0), ra.get("k", 2.0), ra.get("rmax", 2.0),
                                         ra.get("rmin", 0.3)]
    v[X31.RCOOL] = rcool
    return v


# ── entry orders (cached per worker: exit-only variants reuse them) ──────────────────────────────────────────────────
_ORD = {}
ORD_CACHE = 4


def _skipfn(sym, shift, low, extra):
    f72 = G.oi_skip(sym, 240); flow = G.oi_low_skip(sym, 240) if low else None
    def skip(c, a, hi, lo, s):
        cr = dict(c, t=c["t"] - shift) if shift else c
        out = f72(cr, a, hi, lo, s)
        if flow:
            out = out | flow(cr, a, hi, lo, s)
        if extra is not None:
            out = out | extra(sym, cr, a, hi, lo, s)
        return out
    return skip


def orders(sym, shift=0, kwL=None, kwS=None, skipx=None, skey=None, low=True):
    """Entry orders of one coin (copy-safe: callers must not modify the cached arrays)."""
    key = (sym, shift, tuple(sorted((kwL or {}).items())), tuple(sorted((kwS or {}).items())), skey, low)
    if key in _ORD:
        return _ORD[key]
    if len(_ORD) >= ORD_CACHE:                       # tasks arrive sorted by (coin, shift): a small cache is enough
        _ORD.pop(next(iter(_ORD)))
    m = L.m1(sym)
    C.SLIP = SLIPS.get(sym, 0.0003)
    kL = dict(LIVE_KW, **(kwL or {})); kS = dict(LIVE_KW, **(kwS or {}))
    skip = _skipfn(sym, shift, low, skipx)
    mm = dict(m, t=m["t"] + shift) if shift else m
    try:
        if kL == kS:
            o, _ = V._orders(mm, kL, "both", skip)
        else:
            o, _ = V._orders(mm, kL, "long", skip)
            o2, _ = V._orders(mm, kS, "short", skip)
            for a in ("kind", "direction", "price", "sl", "tp", "expiry"):
                getattr(o, a)[:, 1] = getattr(o2, a)[:, 1]
    finally:
        if shift:
            F._rs.cache_clear(); F._M1.clear()
    bad = (o.kind != 0) & ~(o.sl > 0); o.kind[bad] = 0
    rows_ = np.flatnonzero((o.kind != 0).any(axis=1))
    optr = np.full(len(m["t"]), -1, np.int32); optr[rows_] = np.arange(len(rows_))
    co = dict(optr=optr, kind=o.kind[rows_].copy(), direction=o.direction[rows_].copy(), price=o.price[rows_].copy(),
              sl=o.sl[rows_].copy(), tp=np.nan_to_num(o.tp[rows_]), expiry=o.expiry[rows_].copy())
    for nm, dflt in (("allow_entry", True), ("allow_fill", True), ("force_exit", False), ("exit_long", False), ("exit_short", False)):
        a = getattr(o, nm)                                # TBO: all default -> not stored (memory)
        co[nm] = None if bool((a == dflt).all()) else a.copy()
    del o
    import gc; gc.collect()
    _ORD[key] = (co, kL, kS)
    return _ORD[key]


_FA = {}


def fast_atr(sym, tf, shift=0, n=14):
    """Per minute: ATR(n) of the last CLOSED tf-minute candle (cTrader style, as the bot's indicators)."""
    key = (sym, tf, shift, n)
    if key not in _FA:
        m = L.m1(sym)
        mm = dict(m, t=m["t"] + shift) if shift else m
        c = C.D.resample(mm, tf)
        a = C.I.atr(c["h"], c["l"], c["c"], n)
        k = np.searchsorted(c["act"], np.arange(len(m["t"])), side="right") - 1
        _FA[key] = np.where(k >= 0, np.nan_to_num(a[np.clip(k, 0, None)]), 0.0)
        if len(_FA) > 3:
            _FA.pop(next(iter(_FA)))
    return _FA[key]


def trades31(sym, kwL=None, kwS=None, exL=None, exS=None, shift=0, low=True, ctrl=None, skipx=None, skey=None,
             fa_tf=0, valid_min=0, start="2020-01-01", end=END, cool=V30_COOL, rmask=None):
    """exL / exS: exit31() kwargs (defaults = v3.0). ctrl(m1_real_t) -> dict of per-minute masks (fill_l fill_s tight_l
    tight_s exit_long exit_short tight_to). cool = (minutes, R, mode, clear) (default the v3.0 16 h cooldown; None = off).
    skipx(sym, c_realtime, a, hi, lo, side) -> bool per 4h candle (True = no order); skey = its cache key.
    fa_tf: fast ATR timeframe for the re-anchor (15 / 60). valid_min > 0: an order is cancelled valid_min minutes after the
    4h close that placed it."""
    m = L.m1(sym)
    C.SLIP = SLIPS.get(sym, 0.0003)
    o, kL, kS = orders(sym, shift, kwL, kwS, skipx, skey, low)
    n = len(m["t"])
    mm_t = m["t"] + shift if shift else m["t"]
    expiry = o["expiry"]
    if valid_min:
        expiry = np.where(o["kind"] != 0, np.minimum(expiry, valid_min), expiry)
    pl = exit31(**dict(V30_EXIT, **(exL or {})))
    ps = exit31(**dict(V30_EXIT, **(exS or {})))
    cc = ctrl(m["t"]) if ctrl else {}
    ones, zeros = np.ones(n, np.bool_), np.zeros(n, np.bool_)
    dflt = lambda nm, d: o[nm] if o[nm] is not None else d
    cl = cc.get("cool", cool) or (0, -0.5, 0, 0.0)
    fa = fast_atr(sym, fa_tf, shift) if fa_tf else np.zeros(n)
    res = X31.sim31(mm_t, m["o"], m["h"], m["l"], m["c"], o["optr"], o["kind"], o["direction"], o["price"], o["sl"], o["tp"], expiry,
                    dflt("allow_entry", ones), dflt("allow_fill", ones), dflt("force_exit", zeros), cc.get("exit_long", dflt("exit_long", zeros)),
                    cc.get("exit_short", dflt("exit_short", zeros)),
                    np.zeros(n), int(kL["hold_h"] * 60), int(kS["hold_h"] * 60), pl, ps,
                    cc.get("fill_l", ones), cc.get("fill_s", ones), cc.get("tight_l", zeros), cc.get("tight_s", zeros),
                    float(cc.get("tight_to", 0.0)), int(cl[0]), float(cl[1]), int(cl[2]), float(cl[3]), fa,
                    ones if rmask is None else np.asarray(rmask, np.bool_))
    e_idx, x_idx, dirs, e_px, x_px, dist, reason, rf, hf, mfe, ld, rule, arm = res
    t = m["t"]
    tr = pd.DataFrame({"entry_time": C.D.to_datetime(t[e_idx]), "exit_time": C.D.to_datetime(t[x_idx]), "dir": dirs, "entry": e_px,
                       "exit": x_px, "sl_dist": dist, "reason": [C.E.REASONS[r] for r in reason]})
    fee = C.TAKER + C.SLIP
    f_out = np.where(tr.reason.to_numpy() == "TP", C.MAKER, fee)
    gross = (tr["exit"] - tr["entry"]) * tr["dir"]
    hours = (tr["exit_time"] - tr["entry_time"]).dt.total_seconds() / 3600
    cost = fee * tr["entry"] + f_out * tr["exit"] + C.FUNDING_8H * hours / 8 * tr["entry"]
    tr["R"] = (gross - cost) / tr["sl_dist"]; tr["hours"] = hours
    tr["e_i"] = e_idx; tr["x_i"] = x_idx
    tr["be_time"] = C.D.to_datetime(t[rf]); tr["half_time"] = C.D.to_datetime(t[hf])
    tr["mfe"] = mfe; tr["ldist"] = ld; tr["rule"] = rule; tr["arm_time"] = C.D.to_datetime(t[np.clip(arm, 0, n - 1)])
    tr = C.between(tr, start, end).reset_index(drop=True)
    tr["sym"] = sym
    return tr


KEEP = ["entry_time", "exit_time", "be_time", "half_time", "dir", "R", "sym", "entry", "exit", "sl_dist", "reason", "mfe", "ldist",
        "rule", "arm_time", "hours"]


def parity():
    """sim31 with every v3.1 control off vs the deployed v3.0 list (v30lib.trades_v30 / build_trades v30): trades, R and
    the open-risk release time (be_time) must be identical."""
    out = []
    for s in COINS:
        a = trades31(s)
        b = V.trades_v30(s)
        same = len(a) == len(b) and (a.entry_time.values == b.entry_time.values).all() and \
            (a.exit_time.values == b.exit_time.values).all() and np.allclose(a.R.values, b.R.values, atol=1e-12)
        be = (a.be_time.values == b.be_time.values).mean() if len(a) == len(b) else np.nan
        out.append(dict(sym=s, n31=len(a), n30=len(b), identical=bool(same), be_time_equal=float(be)))
    return pd.DataFrame(out)


# ── money ─────────────────────────────────────────────────────────────────────────────────────────────────────────
@njit(cache=True)
def _money31(ev_t, ev_k, ev_i, d, R, coin, mult, eq0, thr, risk, capv, exl, exs, smult, cap_short, minf, gm, extra,
             hfrac, btc_uw, btc_k, br_days, br_x, br_m, r_btc, br_reset, fixed, capm, cap_sl, sl_gate, cap_base, lcap):
    """cap_base (v3.2b): the open-risk cap counts each TBO trade at its un-scaled base risk (row risk x short mult), the
    size multipliers (mult, loss brake) act after the cap -> a size-down never frees cap room for other coins and a boost
    never eats the alts' room. False = the live / v3.1 rule (the cap counts the actual, scaled risk).
    lcap: per-row max risk as a fraction of the sizing balance (sleeve leverage cap = lev x stop distance / entry; 0 = none)."""
    n = len(d)
    amt = np.zeros(n); camt = np.zeros(n); isopen = np.zeros(n, np.bool_); counted = np.zeros(n, np.bool_)
    oamt = np.zeros(n); osum = 0.0                                   # actual open risk of the counted trades (drawdown)
    eq = eq0; pk = eq0; dd = 0.0; csum = 0.0; skipped = 0; bsum = 0.0; dda = 0.0
    # closed-loss brake: ring of (time, units)
    cl_t = np.zeros(n); cl_u = np.zeros(n); ncl = 0; head = 0; wsum = 0.0; armed = False
    p_t = np.zeros(len(ev_t)); p_eq = np.zeros(len(ev_t)); p_w = np.zeros(len(ev_t))
    for q in range(len(ev_t)):
        kd = ev_k[q]; i = ev_i[q]; c = coin[i]; tq = ev_t[q]
        if br_days > 0:
            while head < ncl and cl_t[head] < tq - br_days * 1440.0:
                wsum -= cl_u[head]; head += 1
        if kd == 1:
            r = 0
            es = eq0 if fixed else eq                                   # fixed: sizing on the start balance (no compounding)
            for rr in range(len(thr)):
                if es >= thr[rr]:
                    r = rr
            if c >= 5:
                a = es * risk[r, 0] * extra[c] / 100 * gm * mult[i]
                if lcap[i] > 0 and a > es * lcap[i]:
                    a = es * lcap[i]
                if cap_sl[c] and a > 0:                                 # sleeve inside the open-risk cap (v3.1b)
                    capd = capv[r] / 100 * gm * es * capm[i]
                    if sl_gate > 0 and csum >= sl_gate * capd:
                        a = 0.0
                    elif capv[r] > 0:
                        room = capd - csum
                        if a > room:
                            a = room if room > minf * a else 0.0
                    if a > 0:
                        amt[i] = a; camt[i] = a; isopen[i] = True; counted[i] = True; csum += a; oamt[i] = a; osum += a
                    else:
                        skipped += 1
                elif a > 0:
                    amt[i] = a; isopen[i] = True; counted[i] = False
                p_t[q] = tq; p_eq[q] = eq; p_w[q] = eq - osum
                continue
            sm = smult[c] if d[i] < 0 else 1.0
            bm = br_m if armed else 1.0
            a = es * risk[r, c] / 100 * gm * sm * mult[i] * bm
            scl = 1.0
            if cap_base:
                scl = mult[i] * bm
                a = es * risk[r, c] / 100 * gm * sm if scl > 0 else 0.0
            capx = capv[r]
            if d[i] < 0 and cap_short:
                capx = capv[r] * smult[0]
            ex = exs[c] if d[i] < 0 else exl[c]
            if capx > 0 and (not ex) and a > 0:
                extra_btc = (btc_k - 1.0) * bsum if (btc_k != 1.0 and btc_uw[i] > 0) else 0.0
                room = capx / 100 * gm * es * capm[i] - csum - extra_btc
                if a > room:
                    a = room if room > minf * a else 0.0
            if a > 0:
                amt[i] = a * scl; camt[i] = a; isopen[i] = True; counted[i] = True; csum += a; oamt[i] = a * scl; osum += a * scl
                if c == 0:
                    bsum += a
            else:
                skipped += 1
        elif kd == 0:
            if isopen[i] and counted[i]:
                counted[i] = False; csum -= camt[i]; osum -= oamt[i]
                if c == 0:
                    bsum -= camt[i]
                camt[i] = 0.0; oamt[i] = 0.0
            if c < 5 and isopen[i] and br_reset == 0:
                armed = False
        elif kd == 3:
            if isopen[i] and counted[i] and hfrac < 1.0:
                nw = camt[i] * hfrac
                csum -= camt[i] - nw; osum -= oamt[i] * (1.0 - hfrac); oamt[i] *= hfrac
                if c == 0:
                    bsum -= camt[i] - nw
                camt[i] = nw
        else:
            if isopen[i]:
                pnl = amt[i] * R[i]
                eq += pnl; isopen[i] = False
                if counted[i]:
                    counted[i] = False; csum -= camt[i]; osum -= oamt[i]
                    if c == 0:
                        bsum -= camt[i]
                    camt[i] = 0.0; oamt[i] = 0.0
                if br_days > 0:
                    if (c >= 5 and R[i] > 0 and br_reset == 0) or (c < 5 and R[i] > 0 and br_reset == 1):
                        armed = False
                    rr0 = 0
                    for rr in range(len(thr)):
                        if (eq0 if fixed else eq) >= thr[rr]:
                            rr0 = rr
                    u = pnl / ((eq0 if fixed else eq) * r_btc[rr0] / 100 * gm) if eq > 0 else 0.0
                    if c < 5:
                        cl_t[ncl] = tq; cl_u[ncl] = u; ncl += 1; wsum += u
                        if u < 0 and wsum <= -br_x:
                            armed = True
        w = eq - osum
        if w > pk:
            pk = w
        if pk > 0 and (pk - w) / pk > dd:
            dd = (pk - w) / pk
        if pk - w > dda:
            dda = pk - w
        p_t[q] = tq; p_eq[q] = eq; p_w[q] = w
    return eq, dd * 100, skipped, dda, p_t, p_eq, p_w


def money31(x, pol, eq0=300.0, hfrac=1.0, btc_k=1.0, brake=None, fixed=False, cap_sleeves=(), sl_gate=0.0, path=False):
    """x rows (entry, exit, be, dir, R, coin[, mult[, half[, btc_uw]]]). brake = (days, X units, size mult) or None.
    With hfrac=1, btc_k=1, brake=None: identical to v30lib.money_nb."""
    x = np.asarray(x, float)
    n = len(x)
    mult = x[:, 6] if x.shape[1] > 6 else np.ones(n)
    half = x[:, 7] if x.shape[1] > 7 else x[:, 2]
    buw = x[:, 8] if x.shape[1] > 8 else np.zeros(n)
    capm = x[:, 9] if x.shape[1] > 9 else np.ones(n)
    lcap = x[:, 10] if x.shape[1] > 10 else np.zeros(n)
    csl = np.zeros(16, np.bool_)
    for c_ in cap_sleeves:
        csl[int(c_)] = True
    e = x[:, 0]; be = np.maximum(x[:, 2], e + 1e-3); xx = np.maximum(x[:, 1], e + 2e-3)
    hh = np.minimum(np.maximum(half, e + 1e-3), be)
    idx = np.arange(n)
    if hfrac < 1.0:
        t = np.r_[e, be, xx, hh]; kind = np.r_[np.ones(n, np.int64), np.zeros(n, np.int64), np.full(n, 2, np.int64), np.full(n, 3, np.int64)]
        ii = np.r_[idx, idx, idx, idx]; rank = np.r_[np.full(n, 3), np.ones(n), np.zeros(n), np.full(n, 2)]
        tie = np.r_[4 * idx, 4 * idx + 1, 4 * idx + 2, 4 * idx + 3]
    else:
        t = np.r_[e, be, xx]; kind = np.r_[np.ones(n, np.int64), np.zeros(n, np.int64), np.full(n, 2, np.int64)]
        ii = np.r_[idx, idx, idx]; rank = np.r_[np.full(n, 2), np.ones(n), np.zeros(n)]
        tie = np.r_[3 * idx, 3 * idx + 1, 3 * idx + 2]
    order = np.lexsort((tie, rank, t))
    a = V.pol_arrays(pol)
    bd, bx, bm, brs = (tuple(brake) + (0,))[:4] if brake else (0.0, 0.0, 1.0, 0)
    rb = a[1][:, 0].copy()
    f, dd, sk, dda, pt, pe, pw = _money31(t[order], kind[order], ii[order], x[:, 3], x[:, 4], x[:, 5].astype(np.int64), mult, eq0, *a,
                                          float(hfrac), buw, float(btc_k), float(bd), float(bx), float(bm), rb, int(brs), bool(fixed),
                                          capm, csl, float(sl_gate), pol.get("cap_basis") == "base", lcap)
    out = dict(final=f, dd=dd, skipped=sk, dd_abs=dda)
    if path:
        out["path"] = (pt, pe, pw)
    return out


def window(A, a, b=END):
    t0, t1 = pd.Timestamp(a).value // MIN, pd.Timestamp(b).value // MIN
    x = A[(A[:, 0] >= t0) & (A[:, 0] < t1)].copy(); x[:, :3] -= t0
    if x.shape[1] > 7:
        x[:, 7] -= t0
    return x


def pad(A, ncol):
    """Rows padded to ncol columns (mult 1, half = be, btc_uw 0, capm 1, lcap 0)."""
    A = np.asarray(A, float)
    d = {6: lambda B: np.ones(len(B)), 7: lambda B: B[:, 2], 8: lambda B: np.zeros(len(B)), 9: lambda B: np.ones(len(B)),
         10: lambda B: np.zeros(len(B))}
    while A.shape[1] < ncol:
        A = np.c_[A, d[A.shape[1]](A)]
    return A


def path_rows(A, us):
    rows = []
    for k, u in enumerate(us):
        s = A[(A[:, 0] >= u) & (A[:, 0] < u + L.BLK)].copy(); s[:, :3] += k * L.BLK - u
        if s.shape[1] > 7:
            s[:, 7] += k * L.BLK - u
        rows.append(s)
    return np.concatenate(rows)


_PATHS = {}
BOOT_N = int(os.environ.get("V31_BOOT", 1000))


def boot31(A, pol, n=BOOT_N, eq0=300.0, seed=0, **mk):
    key = (n, seed)
    if key not in _PATHS:
        _PATHS[key] = V.boot_paths(n, seed=seed)
    v = np.array([[(r := money31(path_rows(A, us), pol, eq0, **mk))["final"], r["dd"]] for us in _PATHS[key]])
    return dict(med=float(np.median(v[:, 0])), p10=float(np.percentile(v[:, 0], 10)), dd_med=float(np.median(v[:, 1])),
                dd90=float(np.percentile(v[:, 1], 90)), p_loss=float((v[:, 0] < eq0).mean()))


def money_all(A, pol, oct26=True, **mk):
    out = {}
    for a in ("2020-01-01", "2022-01-01", "2024-01-01"):
        r = money31(window(A, a), pol, **mk); out[f"m{a[:4]}"] = r["final"]; out[f"dd{a[:4]}"] = r["dd"]
    if oct26:                                                     # the live-period chop: Sep 15 - Nov 06 2026 from $300
        r = money31(window(A, "2026-09-15"), pol, **mk); out["m_fall26"] = r["final"]; out["dd_fall26"] = r["dd"]
    out.update({f"boot_{k}": v for k, v in boot31(A, pol, **mk).items()})
    return out


KS = (1.00, 0.96, 0.93, 0.90, 0.85)


def g6(A, pol, base, ks=KS, **mk):
    """E4 (the v3.0 drawdown-matched gate, plus a stricter v3.1 read): for k = 1.00 .. 0.85 (all risks x k) the first k with
    boot_dd90 <= base boot_dd90 is used; G6 PASS there if boot_med > base, boot_p10 >= base, 2022 / 2024 money > base and
    window drops <= base + 1 pt. Also returned: G6s (strict, at k = 1: dd90 < base, med > base, p10 > base, 2022 / 2024 money
    >= base, 2024 drop < base) = the v3.1 brief's literal E4."""
    first = None
    for k in ks:
        r = money_all(A, dict(pol, mult=pol.get("mult", 1.0) * k), **mk); r["k"] = k
        if first is None:
            first = r
            first["G6s"] = bool(r["boot_dd90"] < base["boot_dd90"] and r["boot_med"] > base["boot_med"] and r["boot_p10"] > base["boot_p10"]
                                and r["m2022"] >= base["m2022"] and r["m2024"] >= base["m2024"] and r["dd2024"] < base["dd2024"])
        if r["boot_dd90"] <= base["boot_dd90"]:
            r["G6"] = bool(r["boot_med"] > base["boot_med"] and r["boot_p10"] >= base["boot_p10"] and r["m2022"] > base["m2022"]
                           and r["m2024"] > base["m2024"] and r["dd2022"] <= base["dd2022"] + 1 and r["dd2024"] <= base["dd2024"] + 1)
            r["matched"] = True; r["G6s"] = first["G6s"]
            for kk in ("m2022", "m2024", "dd2024", "boot_med", "boot_p10", "boot_dd90", "dd_fall26"):
                r[f"k1_{kk}"] = first[kk]
            return r
    first["G6"] = False; first["matched"] = False
    for kk in ("m2022", "m2024", "dd2024", "boot_med", "boot_p10", "boot_dd90", "dd_fall26"):
        first[f"k1_{kk}"] = first[kk]
    return first


def rows(X, mult=None, half=False, btc_uw=None):
    """Money rows from a trade frame; half=True adds column 7 (half_time) and 8 (btc_uw flag)."""
    A = V.rows(X, mult=mult)
    if half or btc_uw is not None:
        m = lambda c: X[c].values.astype("datetime64[m]").astype(np.int64)
        ci = X.sym.map({s: i for i, s in enumerate(COINS)}).to_numpy()
        mu = np.ones(len(X)) if mult is None else np.asarray(mult, float)
        h_ = m("half_time") if "half_time" in X else m("be_time")
        bu = np.zeros(len(X)) if btc_uw is None else np.asarray(btc_uw, float)
        A = np.c_[m("entry_time"), m("exit_time"), m("be_time"), X.dir.to_numpy(float), X["R"].to_numpy(float), ci, mu, h_, bu]
        A = A[np.lexsort((A[:, 5], A[:, 0]))]
    return A


def pad_sleeve(S, ncol):
    """Sleeve rows (6 or 7 columns) padded to ncol (half = be, btc_uw = 0)."""
    S = np.asarray(S, float)
    if S.shape[1] == 6:
        S = np.c_[S, np.ones(len(S))]
    if ncol > 7:
        S = np.c_[S, S[:, 2], np.zeros(len(S))]
    return S


def with_sleeve(A, S):
    B = np.r_[A, pad(pad_sleeve(S, min(A.shape[1], 9)), A.shape[1])]
    return B[np.lexsort((B[:, 5], B[:, 0]))]


_SLV = {}


def sleeve30():
    """Panic v3.0 (deployed): 5 core coins + 7 extra at 0.75 share, max 2 extra open."""
    if "s" not in _SLV:
        import panic_sleeve as PSL
        ev = PSL.events(extra_coins=PSL.EXTRA_COINS, max_extra_open=2)
        _SLV["ev"] = ev
        _SLV["s"] = np.c_[PSL.sleeve_rows(ev), np.ones(len(ev))]
    return _SLV["s"]


def base_policy(**kw):
    return V.base_policy(**kw)


# ── fixed-unit account ────────────────────────────────────────────────────────────────────────────────────────────
def score(X, mult=None, smult=0.5):
    return V.score(X, mult=mult, smult=smult)


def xr(sv, sb):
    return V.xr(sv, sb)
