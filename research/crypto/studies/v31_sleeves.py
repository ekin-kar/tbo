"""v3.1 Part 2 (Tracks 5-8), called from v31_drawdown_and_sleeves.py (t5 / t6 / t7 / t8). Sleeve gates S1-S6 as in its
docstring. Decision bars hourly / 4h; execution by the exact 1m engine on DEV12 (and HOLD_BIG when its 1m data exists),
hourly-bar approximation elsewhere (sleeve31.run1h)."""
import itertools, os, sys, time
from multiprocessing import Pool
from pathlib import Path
import numpy as np, pandas as pd
import common as C, v29lib as L, v31lib as W, sleeve31 as SL, hourly51 as H
import v31_drawdown_and_sleeves as M

RES, PROCS, log = M.RES, M.PROCS, M.log
DEV12, HOLD_BIG, HOLD_SMALL, HOLD39 = SL.DEV12, SL.HOLD_BIG, SL.HOLD_SMALL, SL.HOLD39
OUR5 = W.COINS
P20, P22, P24 = "2020-23", "2022-23", "2024-26"
MINS = W.MIN


def tmin(idx):
    return np.asarray(idx, "datetime64[ns]").astype("datetime64[m]").astype(np.int64)


def roll_max(x, n):
    return pd.Series(x).rolling(n, min_periods=n).max().to_numpy()


def roll_min(x, n):
    return pd.Series(x).rolling(n, min_periods=n).min().to_numpy()


def odf(t_place, d, kind, price, dist, tp_R, valid_min):
    n = len(t_place)
    f = lambda v: np.broadcast_to(np.asarray(v), (n,)).copy() if np.ndim(v) == 0 else np.asarray(v)
    return pd.DataFrame(dict(t_place=f(t_place).astype(np.int64), dir=f(d).astype(np.int64), kind=f(kind), price=f(price).astype(float),
                             dist=f(dist).astype(float), tp_R=f(tp_R).astype(float), valid_min=f(valid_min).astype(np.int64)))


# ══ families ═════════════════════════════════════════════════════════════════════════════════════════════════════
def fam_volc(sym, p):
    """Track 5: volatility compression -> stop orders at the N-bar high / low, fixed TP, short hold."""
    B = SL.resample_bars(SL.bars(sym), p["tf"])
    h, l, c = B.h.to_numpy(), B.l.to_numpy(), B.c.to_numpy()
    a14 = SL.atr(B, 14); a100 = SL.atr(B, 100)
    with np.errstate(invalid="ignore", divide="ignore"):
        if p["sq"].startswith("atr"):
            sq = a14 / a100 < float(p["sq"][3:])
        else:
            cs = pd.Series(c); bw = 4 * cs.rolling(20).std() / cs.rolling(20).mean()
            sq = (bw.rolling(250, min_periods=125).rank(pct=True) < float(p["sq"][3:]) / 100).to_numpy()
        tcl = B.index + pd.Timedelta(minutes=p["tf"])
        D = SL.daily_at(sym, tcl.values)
        side, er = D["side"], D["er"]
        rng = er < 0.25
        if p["dm"] == "trend":
            okL, okS = side > 0, side < 0
        elif p["dm"] == "range2":
            okL = okS = rng
        else:
            okL, okS = (side > 0) | rng, (side < 0) | rng
        oi_ok = np.ones(len(B), bool)
        if p.get("oi") is not None:
            k = int(round(1440 / p["tf"]))
            oi = B.oi.to_numpy(float); prev = np.r_[np.full(k, np.nan), oi[:-k]]
            oi_ok = oi / prev - 1 > p["oi"]
        hi, lo = roll_max(h, p["N"]), roll_min(l, p["N"])
        base = sq & np.isfinite(a14) & np.isfinite(a100) & (np.arange(len(B)) > 120)
        base &= oi_ok & ~SL.near_panic(tmin(tcl.values))
    tp_ = tmin(tcl.values)
    mL, mS = base & okL, base & okS
    od = pd.concat([odf(tp_[mL], 1, "stop", hi[mL], a14[mL], p["TP"], p["tf"]), odf(tp_[mS], -1, "stop", lo[mS], a14[mS], p["TP"], p["tf"])])
    rule = dict(T_h=p["sc"], G=60, cont=0, mlo=0.4, mhi=99.0, thr=-0.1, act=2) if p.get("sc") else None
    return od, dict(hold_h=p["H"], be_R=0.0, rule=rule, tbo_flat=True)


def fam_trap(sym, p):
    """Track 6: bull / bear trap of the n-candle 4h channel -> fade back toward the range."""
    df = SL.bars(sym); B4 = SL.resample_bars(df, 240)
    a4 = SL.atr(B4, 14); hi4 = roll_max(B4.h.to_numpy(), p["n"]); lo4 = roll_min(B4.l.to_numpy(), p["n"])
    t4c = tmin((B4.index + pd.Timedelta(hours=4)).values)
    th = tmin(df.index.values)
    k4 = np.searchsorted(t4c, th, side="right") - 1                      # last 4h candle closed at the hour's open
    ok4 = k4 >= 0; kk = np.clip(k4, 0, None)
    LH, LL, A = np.where(ok4, hi4[kk], np.nan), np.where(ok4, lo4[kk], np.nan), np.where(ok4, a4[kk], np.nan)
    h, l, c, o = df.h.to_numpy(), df.l.to_numpy(), df.c.to_numpy(), df.o.to_numpy()
    oi = df.oi.to_numpy(float)
    tcl = df.index + pd.Timedelta(hours=1)
    D = SL.daily_at(sym, tcl.values); er = D["er"]
    npan = SL.near_panic(tmin(tcl.values))
    sig = []
    n = len(df)
    for side in (1, -1):
        lvl = LH if side > 0 else LL
        i = 1
        while i < n - 1:
            if not np.isfinite(lvl[i]) or not np.isfinite(A[i]):
                i += 1; continue
            brk = (h[i] > lvl[i]) if side > 0 else (l[i] < lvl[i])
            if not brk:
                i += 1; continue
            b = i; L0, A0 = lvl[b], A[b]; ext = 0.0; fired = False
            for q in range(b, min(b + p["k"], n - 1)):
                ext = max(ext, (h[q] - L0) if side > 0 else (L0 - l[q]))
                if ext >= 1.0 * A0:
                    break
                back = (c[q] < L0 - p["back"] * A0) if side > 0 else (c[q] > L0 + p["back"] * A0)
                if back:
                    ok = not npan[q]
                    if p["conf"] == "er":
                        ok &= er[q] < p["er"]
                    elif p["conf"] == "oi":
                        ok &= (oi[b] > oi[b - 1]) and (oi[q] < oi[b])
                    if ok:
                        wick = (h[b:q + 1].max() + p["sl"] * A0) if side > 0 else (l[b:q + 1].min() - p["sl"] * A0)
                        dist = abs(wick - c[q])
                        if p["TP"] == "mid":
                            mid = (LH[b] + LL[b]) / 2
                            tpR = ((c[q] - mid) if side > 0 else (mid - c[q])) / dist
                        else:
                            tpR = float(p["TP"])
                        if tpR > 0.3:
                            sig.append((th[q] + 60, -side, dist, tpR))
                    fired = True
                    break
            i = max(q, b) + 1 if not fired else q + 1
            while i < n and ((h[i] > lvl[i]) if side > 0 else (l[i] < lvl[i])):   # skip the rest of this break episode
                i += 1
    if not sig:
        return odf([], 1, "market", 0, 0, 0, 60), dict(hold_h=p["H"], be_R=1.0, rule=None)
    s = np.array(sig, dtype=object)
    od = odf(s[:, 0].astype(np.int64), s[:, 1].astype(np.int64), "market", 0.0, s[:, 2].astype(float), s[:, 3].astype(float), 60)
    return od, dict(hold_h=p["H"], be_R=1.0, rule=None)


def _days(df):
    return pd.date_range(df.index[0].normalize() + pd.Timedelta(days=1), df.index[-1].normalize(), freq="D")


def fam_asiab(sym, p):
    """Track 7 C1a: Asia box (00:00 - box_end UTC) breakout in London / NY, tight box, fixed TP, flat by 20:00 UTC."""
    df = SL.bars(sym)
    be_h = p["box"]
    g = df.groupby(df.index.normalize())
    box = pd.DataFrame({"hi": df.h[df.index.hour < be_h].groupby(df.index[df.index.hour < be_h].normalize()).max(),
                        "lo": df.l[df.index.hour < be_h].groupby(df.index[df.index.hour < be_h].normalize()).min()})
    box["w"] = box.hi - box.lo
    box["med"] = box.w.shift(1).rolling(20, min_periods=15).median()
    a1 = pd.Series(SL.atr(df, 14), index=df.index)
    tbox = box.index + pd.Timedelta(hours=be_h)
    box["atr"] = a1.reindex(tbox - pd.Timedelta(hours=1)).to_numpy()
    oi = df.oi
    box["doi"] = (oi.reindex(tbox - pd.Timedelta(hours=1)).to_numpy() / oi.reindex(tbox - pd.Timedelta(hours=25)).to_numpy()) - 1
    D = SL.daily_at(sym, tbox.values)
    with np.errstate(invalid="ignore"):
        ok = (box.w < p["tight"] * box.med).to_numpy() & np.isfinite(box.atr.to_numpy())
        if p["oi"]:
            ok &= box.doi.to_numpy() > 0
        ok &= ~SL.near_panic(tmin(tbox.values))
    dist = {"mid": box.w.to_numpy() / 2, "atr1": box.atr.to_numpy(), "atr1.5": 1.5 * box.atr.to_numpy()}[p["sl"]]
    okL = ok & ((D["side"] > 0) if p["dir"] == "trend" else True)
    okS = ok & ((D["side"] < 0) if p["dir"] == "trend" else True)
    tp_ = tmin(tbox.values); vm = (16 - be_h) * 60
    od = pd.concat([odf(tp_[okL], 1, "stop", box.hi.to_numpy()[okL], dist[okL], p["TP"], vm),
                    odf(tp_[okS], -1, "stop", box.lo.to_numpy()[okS], dist[okS], p["TP"], vm)])
    exit_at = tmin((box.index + pd.Timedelta(hours=20)).values)
    return od, dict(hold_h=12, be_R=0.0, rule=None, exit_at=exit_at)


def fam_judas(sym, p):
    """Track 7 C1b: London / NY sweep of the Asia box (0.2-0.8 ATR beyond), back inside at the check hour -> fade."""
    df = SL.bars(sym)
    hr = df.index.hour; day = df.index.normalize()
    asia = df[hr < 8]; bx = pd.DataFrame({"hi": asia.h.groupby(asia.index.normalize()).max(), "lo": asia.l.groupby(asia.index.normalize()).min()})
    lon = df[(hr >= 8) & (hr < p["chk"])]
    sw = pd.DataFrame({"mx": lon.h.groupby(lon.index.normalize()).max(), "mn": lon.l.groupby(lon.index.normalize()).min()})
    a1 = pd.Series(SL.atr(df, 14), index=df.index)
    tchk = bx.index + pd.Timedelta(hours=p["chk"])
    cl = df.c.reindex(tchk - pd.Timedelta(hours=1)).to_numpy()
    A = a1.reindex(tchk - pd.Timedelta(hours=1)).to_numpy()
    sw = sw.reindex(bx.index)
    pr = df.prem; pz = ((pr - pr.rolling(168, min_periods=84).mean()) / pr.rolling(168, min_periods=84).std()).reindex(tchk - pd.Timedelta(hours=1)).to_numpy()
    D = SL.daily_at(sym, tchk.values)
    with np.errstate(invalid="ignore"):
        up = (sw.mx.to_numpy() - bx.hi.to_numpy()) / A; dn = (bx.lo.to_numpy() - sw.mn.to_numpy()) / A
        sU = (up >= 0.2) & (up <= 0.8) & ~(dn > 0) & (cl < bx.hi.to_numpy())          # swept the high only, back inside -> short
        sD = (dn >= 0.2) & (dn <= 0.8) & ~(up > 0) & (cl > bx.lo.to_numpy())
        if p["prem"]:
            sU &= pz > 0.5; sD &= pz < -0.5
        if p["dir"] == "trend":
            sU &= D["side"] < 0; sD &= D["side"] > 0
        npn = SL.near_panic(tmin(tchk.values))
        sU &= ~npn & np.isfinite(A); sD &= ~npn & np.isfinite(A)
    distS = sw.mx.to_numpy() + p["buf"] * A - cl; distL = cl - (sw.mn.to_numpy() - p["buf"] * A)
    mid = (bx.hi.to_numpy() + bx.lo.to_numpy()) / 2
    def tpr(dist, side):
        if p["TP"] == "mid":
            return ((cl - mid) if side < 0 else (mid - cl)) / dist
        if p["TP"] == "edge":
            return ((cl - bx.lo.to_numpy()) if side < 0 else (bx.hi.to_numpy() - cl)) / dist
        return np.full(len(cl), float(p["TP"]))
    tS, tL = tpr(distS, -1), tpr(distL, 1)
    sU &= tS > 0.3; sD &= tL > 0.3
    tp_ = tmin(tchk.values)
    od = pd.concat([odf(tp_[sU], -1, "market", 0.0, distS[sU], tS[sU], 60), odf(tp_[sD], 1, "market", 0.0, distL[sD], tL[sD], 60)])
    return od, dict(hold_h=p["H"], be_R=0.0, rule=None)


def fam_fund(sym, p):
    """Track 7 C2: extreme 8h funding + price stretched into the settlement + OI up -> fade after the settlement."""
    df = SL.bars(sym)
    fu = df.fund.to_numpy(float); c = df.c.to_numpy(); o = df.o.to_numpy(); oi = df.oi.to_numpy(float)
    a1 = SL.atr(df, 14)
    idx = np.flatnonzero(df.index.hour % 8 == 0)
    rks = pd.Series(fu[idx]).rolling(270, min_periods=135).rank(pct=True).to_numpy()   # vs the last 90 days of settlements
    rk = np.full(len(df), np.nan); rk[idx] = rks
    lb = p["lb"]
    sig = []
    npn = SL.near_panic(tmin(df.index.values))
    for i in idx:
        if i - lb - 1 < 0 or i + 4 >= len(df) or npn[i] or not np.isfinite(a1[i - 1]) or not np.isfinite(rk[i]):
            continue
        mv = (c[i - 1] - c[i - 1 - lb]) / a1[i - 1]
        doi = oi[i - 1] / oi[i - 1 - lb] - 1 if np.isfinite(oi[i - 1]) and np.isfinite(oi[i - 1 - lb]) else np.nan
        if p["oi"] is not None and not (doi > p["oi"]):
            continue
        side = 0
        if mv >= p["ext"] and rk[i] >= 1 - p["pct"]:
            side = -1
        elif mv <= -p["ext"] and rk[i] <= p["pct"]:
            side = 1
        if not side:
            continue
        if p["ent"] == "5m":
            sig.append((tmin(df.index.values[i:i + 1])[0] + 5, side, p["sl"] * a1[i - 1]))
        else:                                                         # first hourly close against the stretch within 3 h
            for q in range(i, i + 3):
                if (c[q] - o[q]) * side > 0:
                    sig.append((tmin(df.index.values[q:q + 1])[0] + 60, side, p["sl"] * a1[q])); break
    if not sig:
        return odf([], 1, "market", 0, 0, 0, 60), dict(hold_h=p["H"], be_R=0.0, rule=None)
    s = np.array(sig)
    od = odf(s[:, 0].astype(np.int64), s[:, 1].astype(np.int64), "market", 0.0, s[:, 2], p["TP"], 60)
    return od, dict(hold_h=p["H"], be_R=0.0, rule=None)


FAMS = {"volc": fam_volc, "trap": fam_trap, "asiab": fam_asiab, "judas": fam_judas, "fund": fam_fund}


# ══ jobs ═════════════════════════════════════════════════════════════════════════════════════════════════════════
_CUR = {"sym": None}
_TBOF = {}


def tbo_flat(sym):
    if sym not in _TBOF:
        B = M.base_at(0); x = B[B.sym == sym]
        t = L.m1(sym)["t"]
        _TBOF[sym] = ~M._mask(t, np.c_[M._mins(x.entry_time), M._mins(x.exit_time)])
    return _TBOF[sym]


def _switch(sym):
    if _CUR["sym"] != sym:
        L._M.clear(); SL._HB.clear(); SL._DD.clear(); _TBOF.clear(); _OD.clear()
        import gc; gc.collect()
        _CUR["sym"] = sym


_OD = {}


def fam_job(args):
    fam, pid, p, sym, prefer, rnd = args
    _switch(sym)
    key = (fam, pid.split("#")[0], sym)
    if key not in _OD:
        if len(_OD) > 64:
            _OD.clear()
        _OD[key] = FAMS[fam](sym, p)
    od, ex = _OD[key]
    if rnd is not None:
        od = random_orders(sym, od, rnd)
    kw = dict(be_R=ex["be_R"], rule=ex.get("rule"), exit_at=ex.get("exit_at"))
    if prefer == "1m" and SL.has_m1(sym):
        if ex.get("tbo_flat") and sym in OUR5:
            kw["fill_ok"] = tbo_flat(sym)
        T = SL.run1m(sym, od, ex["hold_h"], **kw)
    else:
        T = SL.run1h(sym, od, ex["hold_h"], **kw)
    return fam, pid, sym, T


def random_orders(sym, od, seed):
    """Null: the same number of orders per side and year, placed as MARKET orders at random hours (not near a panic
    trigger), with the same stop distance in ATR(1h) units and the same TP."""
    rng = np.random.default_rng(seed)
    df = SL.bars(sym); a1 = SL.atr(df, 14)
    th = tmin(df.index.values) + 60
    ok = np.isfinite(a1) & ~SL.near_panic(th)
    pool = np.flatnonzero(ok)
    j0 = np.clip(np.searchsorted(th, od.t_place.to_numpy()) - 1, 0, len(th) - 1)
    k = a1[j0]
    with np.errstate(invalid="ignore", divide="ignore"):
        mult = od.dist.to_numpy() / k
    yrs = pd.to_datetime(od.t_place.to_numpy() * MINS).year
    pyr = pd.to_datetime(th[pool] * MINS).year
    out = []
    for y in np.unique(yrs):
        sel = np.flatnonzero(yrs == y); cand = pool[pyr == y]
        if not len(cand):
            continue
        pick = rng.choice(cand, len(sel), replace=len(cand) < len(sel))
        out.append(odf(th[pick], od.dir.to_numpy()[sel], "market", 0.0, np.nan_to_num(mult[sel]) * a1[pick], od.tp_R.to_numpy()[sel], 60))
    return pd.concat(out) if out else od.iloc[0:0]


def run_fam(fam, plist, coins, prefer="1m", rnd=None):
    """plist: [(pid, p)] -> {pid: trades of all coins}."""
    tasks = [(fam, pid, p, s, prefer, rnd) for pid, p in plist for s in coins]
    tasks.sort(key=lambda z: z[3])
    out = {}
    with Pool(PROCS) as pool:
        for f, pid, s, T in pool.imap_unordered(fam_job, tasks, chunksize=4):
            out.setdefault(pid, []).append(T)
    return {pid: (pd.concat(v, ignore_index=True) if v else SL._empty("x")) for pid, v in out.items()}


# ══ sleeve gates ═════════════════════════════════════════════════════════════════════════════════════════════════
_TBOM = {}


def tbo_monthly():
    if "m" not in _TBOM:
        B = M.base_at(0)
        u = W.L.units(B)
        _TBOM["m"] = pd.Series(u).groupby(pd.to_datetime(B.exit_time).dt.to_period("M").to_numpy()).sum()
    return _TBOM["m"]


def s5(T, dev):
    tm = tbo_monthly()
    sm = SL.monthly(T)
    idx = pd.period_range("2022-01" if dev == P22 else "2020-01", "2026-10", freq="M")
    a = tm.reindex(idx).fillna(0.0); b = sm.reindex(idx).fillna(0.0)
    corr = float(np.corrcoef(a, b)[0, 1]) if b.std() > 0 else np.nan
    out = dict(corr=corr)
    for nm, (x0, x1) in (("22", ("2022-01", "2023-12")), ("24", ("2024-01", "2026-10"))):
        ii = pd.period_range(x0, x1, freq="M")
        lm = [m for m in ii if tm.get(m, 0.0) < 0]
        out[f"lose_months_{nm}"] = len(lm); out[f"R_in_tbo_losing_{nm}"] = float(sm.reindex(lm).fillna(0.0).sum())
    out["S5"] = bool(np.isfinite(corr) and corr <= 0.15 and out["R_in_tbo_losing_22"] > 0 and out["R_in_tbo_losing_24"] > 0)
    return out


def s1_row(T, dev):
    s = SL.stats(T)
    r = {}
    for per in (dev, P24):
        for k, v in s[per].items():
            r[f"{per}_{k}"] = v
    r["S1"] = bool(all(s[q]["n"] >= 30 and s[q]["avg"] > 0 and s[q]["pf"] >= 1.25 for q in (dev, P24)))
    r["mina"] = min(s[dev]["avg"] if s[dev]["n"] else -9, s[P24]["avg"] if s[P24]["n"] else -9)
    return r


def sleeve_money(name_T, share_list=(0.1, 0.2, 0.33)):
    """S6: the sleeve (coin index 6, per-trade risk = share x BTC risk, outside the cap) next to bot + panic."""
    items = []
    for nm, T in name_T:
        if len(T) == 0:
            continue
        m = lambda s: pd.to_datetime(T[s]).values.astype("datetime64[m]").astype(np.int64)
        S = np.c_[m("t"), m("t_exit"), m("t"), T.dir.to_numpy(float), T.R.to_numpy(float), np.full(len(T), 6.0), np.ones(len(T))]
        S = S[(S[:, 0] >= pd.Timestamp("2020-01-01").value // MINS)]
        for sh in share_list:
            A = W.with_sleeve(W.rows(M.base_at(0)), W.sleeve30())
            A = np.r_[A, S]; A = A[np.lexsort((A[:, 5], A[:, 0]))]
            pol = W.base_policy(extra_risk=[(5, 0.5), (6, sh)])
            items.append((f"{nm}|share{sh}", A, pol))
    if not items:
        return pd.DataFrame()
    R = M.g6_many(items)
    b = M.money_base(); R["E4"] = [M.e4_literal(r, b) for _, r in R.iterrows()]
    return R


def sleeve_track(name, fam, grid, ords, cats, dev, top=10, hold_prefer="1m"):
    """Grid on DEV12 -> S1 -> S2 -> (top) S3 nulls, S4 HOLD39, S5 -> S6 money."""
    SL.panic_times(); tbo_monthly()
    plist = [(f"{fam}_" + "_".join(f"{k}{v}" for k, v in p.items()), p) for p in grid]
    log(f"[{name}] {len(plist)} configs x {len(DEV12)} DEV12 coins")
    TT = run_fam(fam, plist, DEV12)
    rows = []
    for pid, p in plist:
        T = TT.get(pid, SL._empty("x"))
        rows.append(dict(id=pid, **{k: ("none" if v is None else v) for k, v in p.items()}, **s1_row(T, dev)))
    R = pd.DataFrame(rows)
    R["plateau"] = M.plateau(R, ords, cats, "S1"); R["S2"] = R.plateau >= 0.6
    cand = list(dict.fromkeys(list(R[R.S1 & R.S2].sort_values("mina", ascending=False).id.head(top)) + list(R.sort_values("mina", ascending=False).id.head(3))))
    byid = dict(plist)
    for c_ in ("null_dev", "null_oos", "S3", "hold_avg_dev", "hold_avg_oos", "hold_n_dev", "hold_n_oos", "hb_avg_dev", "hb_avg_oos", "S4", "corr",
               "R_in_tbo_losing_22", "R_in_tbo_losing_24", "S5"):
        R[c_] = np.nan
    if cand:
        log(f"[{name}] S3-S5 for {len(cand)} configs")
        HT = run_fam(fam, [(i, byid[i]) for i in cand], HOLD39, prefer="1m")
        for i in cand:
            T = TT[i]; s = SL.stats(T)
            nl = run_null(fam, i, byid[i], dev)
            R.loc[R.id == i, "null_dev"] = float(np.mean(nl[:, 0] < s[dev]["avg"])); R.loc[R.id == i, "null_oos"] = float(np.mean(nl[:, 1] < s[P24]["avg"]))
            hs = SL.stats(HT[i]); hb = SL.stats(HT[i][HT[i].sym.isin(HOLD_BIG)])
            R.loc[R.id == i, ["hold_avg_dev", "hold_avg_oos", "hold_n_dev", "hold_n_oos", "hb_avg_dev", "hb_avg_oos"]] = [
                hs[dev]["avg"], hs[P24]["avg"], hs[dev]["n"], hs[P24]["n"], hb[dev]["avg"], hb[P24]["avg"]]
            for k, v in s5(T, dev).items():
                if k in R:
                    R.loc[R.id == i, k] = v
    R["S3"] = (R.null_dev >= 0.95) & (R.null_oos >= 0.95)
    R["S4"] = (R.hold_avg_dev > 0) & (R.hold_avg_oos > 0)
    R["S5"] = R.S5.fillna(False).astype(bool)
    passers = R[R.S1 & R.S2 & R.S3 & R.S4 & R.S5].id.tolist()
    mids = list(dict.fromkeys(passers + list(R.sort_values("mina", ascending=False).id.head(2))))
    Mo = sleeve_money([(i, TT[i]) for i in mids])
    R["S6"] = False
    if len(Mo):
        Mo.to_csv(RES / f"v31_{name}_money.csv")
        for i in mids:
            ok = [bool(Mo.loc[f"{i}|share{sh}", "E4"]) for sh in (0.1, 0.2, 0.33) if f"{i}|share{sh}" in Mo.index]
            R.loc[R.id == i, "S6"] = any(ok)
    R["PASS"] = R.S1 & R.S2 & R.S3 & R.S4 & R.S5 & R.S6
    R.to_csv(RES / f"v31_{name}.csv", index=False)
    log(f"[{name}] funnel: {len(R)} -> S1 {int(R.S1.sum())} -> +S2 {int((R.S1 & R.S2).sum())} -> +S3 {int((R.S1 & R.S2 & R.S3).sum())} -> "
        f"+S4 {int((R.S1 & R.S2 & R.S3 & R.S4).sum())} -> +S5 {int((R.S1 & R.S2 & R.S3 & R.S4 & R.S5).sum())} -> +S6 PASS {int(R.PASS.sum())}")
    cols = [c_ for c_ in ["id", f"{dev}_n", f"{dev}_avg", f"{dev}_pf", f"{P24}_n", f"{P24}_avg", f"{P24}_pf", "plateau", "null_dev", "null_oos",
                          "hold_avg_dev", "hold_avg_oos", "corr", "R_in_tbo_losing_22", "R_in_tbo_losing_24", "S1", "S2", "S3", "S4", "S5", "S6", "PASS"] if c_ in R]
    print(R.sort_values(["PASS", "S1", "mina"], ascending=False).head(12)[cols].round(3).to_string(index=False), flush=True)
    if len(Mo):
        print(Mo[["k1_m2022", "k1_m2024", "k1_dd2024", "k1_dd_fall26", "k1_boot_med", "k1_boot_p10", "k1_boot_dd90", "E4", "G6"]].round(2).to_string(), flush=True)
    return R, TT


def run_null(fam, pid, p, dev, n=200):
    """S3: average R of n random-entry copies (DEV12), per period."""
    res = np.zeros((n, 2))
    out = {}
    tasks = [(fam, f"{pid}#n{q}", p, s, "1m", 1000 + q) for q in range(n) for s in DEV12]
    tasks.sort(key=lambda z: z[3])
    with Pool(PROCS) as pool:
        for f, i, s, T in pool.imap_unordered(fam_job, tasks, chunksize=8):
            out.setdefault(i, []).append(T[["t", "t_exit", "R", "sym", "dir"]])
    for q in range(n):
        T = pd.concat(out.get(f"{pid}#n{q}", [SL._empty("x")]), ignore_index=True)
        s = SL.stats(T)
        res[q] = [s[dev]["avg"] if s[dev]["n"] else -9, s[P24]["avg"] if s[P24]["n"] else -9]
    return res


def grid(**axes):
    return [dict(zip(axes, v)) for v in itertools.product(*axes.values())]


# ══ tracks ═══════════════════════════════════════════════════════════════════════════════════════════════════════
def t5():
    g = grid(tf=(60, 240), sq=("atr0.65", "atr0.75", "atr0.85", "bbw15", "bbw25"), N=(8, 12, 16), dm=("trend", "range2", "hybrid"),
             TP=(1.5, 2.0, 2.5, 3.0), H=(12, 24, 36))
    g = [dict(p, oi=None, sc=0) for p in g if not (p["tf"] == 240 and p["H"] == 12)]
    R, TT = sleeve_track("T5_volc", "volc", g, ["N", "TP", "H"], ["tf", "sq", "dm"], P20)
    # OI build-up condition and early scratch on the 10 best
    top = R.sort_values("mina", ascending=False).head(10)
    g2 = []
    for _, r in top.iterrows():
        for oi_, sc in itertools.product((None, -0.01, 0.0, 0.02), (0, 3, 4, 6)):
            if oi_ is None and sc == 0:
                continue
            g2.append(dict(tf=r.tf, sq=r.sq, N=r.N, dm=r.dm, TP=r.TP, H=r.H, oi=oi_, sc=sc))
    sleeve_track("T5b_volc_oi_scratch", "volc", g2, ["N", "TP", "H", "sc"], ["tf", "sq", "dm", "oi"], P22)


def t6():
    g = grid(n=(15, 20, 30), k=(1, 2, 4), back=(0.3, 0.5, 0.75), conf=("none", "er", "oi"), sl=(0.75, 1.0), TP=(1.5, 2.0, "mid"), H=(12, 24))
    for p in g:
        p["er"] = 0.3
    gn = [p for p in g if p["conf"] != "oi"]; go = [p for p in g if p["conf"] == "oi"]
    sleeve_track("T6_trap", "trap", gn, ["n", "k", "back", "sl", "H"], ["conf", "TP"], P20)
    sleeve_track("T6b_trap_oi", "trap", go, ["n", "k", "back", "sl", "H"], ["TP"], P22)


def t7():
    g = grid(box=(7, 8), tight=(0.6, 0.8, 1.0), oi=(0, 1), dir=("both", "trend"), sl=("mid", "atr1", "atr1.5"), TP=(1.5, 2.0, 2.5))
    gp = [p for p in g if not p["oi"]]; go = [p for p in g if p["oi"]]
    sleeve_track("T7a_asia_box", "asiab", gp, ["tight", "TP"], ["box", "dir", "sl"], P20)
    sleeve_track("T7a2_asia_box_oi", "asiab", go, ["tight", "TP"], ["box", "dir", "sl"], P22)
    g = grid(chk=(13, 14), buf=(0.25, 0.5), TP=("mid", "edge", 1.5, 2.0), H=(6, 8), dir=("both", "trend"), prem=(0, 1))
    sleeve_track("T7b_judas", "judas", [p for p in g if not p["prem"]], ["buf", "H"], ["chk", "TP", "dir"], P20)
    sleeve_track("T7b2_judas_prem", "judas", [p for p in g if p["prem"]], ["buf", "H"], ["chk", "TP", "dir"], P22)
    g = grid(pct=(0.02, 0.05, 0.10), ext=(1.5, 2.0), lb=(4, 8), oi=(None, 0.02), ent=("5m", "rev"), TP=(1.5, 2.0), H=(4, 8, 12), sl=(1.0,))
    sleeve_track("T7c_funding", "fund", g, ["pct", "ext", "lb", "TP", "H"], ["oi", "ent"], P22)


# ══ TRACK 8 — own hypotheses ═════════════════════════════════════════════════════════════════════════════════════
CTRLS = {}


def _ctrl(f):
    CTRLS[f.__name__] = f
    return f


_PBC = {}


def panic_by_coin():
    """Panic v3.0 trigger moments (the entry hour = signal hour close) per DEV12 coin, minutes."""
    if "d" not in _PBC:
        import panic_sleeve as PSL
        ev = PSL.events(start="2021-11-01", extra_coins=PSL.EXTRA_COINS, max_extra_open=None)
        _PBC["d"] = {s: np.sort(g.t.values.astype("datetime64[m]").astype(np.int64)) for s, g in ev.groupby("sym")}
        _PBC["all"] = np.sort(ev.t.values.astype("datetime64[m]").astype(np.int64))
    return _PBC


@_ctrl
def panic_block(sym, shift, t, X=24, scope="same", side="short"):
    """H2: no TBO fills (shorts, or both sides) for X hours after a panic trigger (same coin / any DEV12 coin)."""
    P = panic_by_coin()
    ev = P["d"].get(sym, np.array([], np.int64)) if scope == "same" else P["all"]
    iv = np.c_[ev, ev + X * 60]
    mk = ~M._mask(t, iv)
    out = {"fill_s": mk}
    if side == "both":
        out["fill_l"] = mk
    return out


@_ctrl
def weekend(sym, shift, t, when="fri20", lvl=-0.5):
    """H7: at Friday 20:00 / Saturday 00:00 UTC every open trade's stop moves to entry + lvl x risk if lower (lvl = 'close'
    closes it at that open)."""
    wd = ((t // 1440) + 3) % 7; mn = t % 1440
    at = (wd == 4) & (mn == 1200) if when == "fri20" else (wd == 5) & (mn == 0)
    if lvl == "close":
        return {"exit_long": at, "exit_short": at}
    return {"tight_l": at, "tight_s": at, "tight_to": float(lvl)}


_BTCX = {}


def btc_trades(shift, rule):
    """BTC's own trades (BTC is never touched by the cascade): the base, or with the Track 1 failed-breakout rule."""
    if rule is None:
        return M.base_at(shift)
    key = (shift, rule)
    if key not in _BTCX:
        _BTCX.clear()
        fb = dict(T_h=8, G=60, cont=1, mlo=0.9, mhi=99.0, thr=float(rule), act=3, lvl=-0.5)
        _BTCX[key] = W.trades31("BTCUSDT", shift=shift, exL=dict(A=fb, rcool=1), exS=dict(A=fb, rcool=1))
    return _BTCX[key]


@_ctrl
def btc_cascade(sym, shift, t, act=-0.5, rule=None):
    """H8: when a BTC trade closes below -0.5R, ETH / alt trades open in the same direction get their stop raised to
    entry + act x risk (or closed: act = 'close') at the next minute. BTC's own trades are unaffected (exact, one pass).
    rule = the failed-breakout threshold if BTC also runs the Track 1 rule (combination)."""
    B = btc_trades(shift, rule); b = B[(B.sym == "BTCUSDT") & (B.R < -0.5)]
    out = {}
    for d, nm in ((1, "l"), (-1, "s")):
        j = np.searchsorted(t, M._mins(b[b.dir == d].exit_time)) + 1
        m = np.zeros(len(t), np.bool_); m[j[j < len(t)]] = True
        out[("exit_long" if d > 0 else "exit_short") if act == "close" else "tight_" + nm] = m
    if act != "close":
        out["tight_to"] = float(act)
    return out


_ER = {}


def er_at(sym, t):
    if sym not in _ER:
        _ER.clear()
        _ER[sym] = M._daily(sym)
    D = M._daily(sym)
    k = np.searchsorted(D["tc"], t, side="right") - 1
    return np.where(k >= 0, D["er"][np.clip(k, 0, None)], np.nan)


@_ctrl
def regime_rule(sym, shift, t, src="BTC", e=0.25):
    """H4: the checkpoint rule applies only to trades filled while the last closed day's ER10 (BTC's or the coin's own)
    is below e (a choppy macro regime)."""
    s = "BTCUSDT" if src == "BTC" else sym
    D = M._daily(s)
    k = np.searchsorted(D["tc"], t, side="right") - 1
    er = np.where(k >= 0, D["er"][np.clip(k, 0, None)], np.nan)
    return {"rmask": np.nan_to_num(er, nan=1.0) < e}


from numba import njit  # noqa: E402


@njit(cache=True)
def partial_trigger(t, o, h, l, c, ei, xi, d, e, dist, T, G, Mfe, thr, be):
    """H3: per trade, the minute the failed-breakout rule (as xengine31: checked at the open of a minute j >= fill + T on
    the G-minute grid, MFE so far >= Mfe, last close < thr R, never at +be) fires, or -1."""
    out = np.full(len(ei), -1, np.int64)
    for k in range(len(ei)):
        best = 0.0; behit = False
        for j in range(ei[k] + 1, xi[k] + 1):
            if not behit and j - ei[k] >= T and (G <= 1 or t[j] % G == 0):
                cur = (c[j - 1] - e[k]) * d[k] / dist[k]
                if best / dist[k] >= Mfe and cur < thr:
                    out[k] = j
                    break
            fv = (h[j] - e[k]) if d[k] > 0 else (e[k] - l[j])
            if fv > best:
                best = fv
            if best >= be * dist[k]:
                behit = True
    return out


def partial_R(X, T, Mfe, thr, f):
    """R of each trade if a fraction f is closed at the rule's trigger (at that minute's open) and the rest runs as before;
    also the trigger time (for the open-risk cap: remaining risk = 1 - f from then)."""
    R = X.R.to_numpy(float).copy(); trig = np.full(len(X), -1, np.int64)
    for s in W.COINS:
        idx = np.flatnonzero((X.sym == s).to_numpy())
        if not len(idx):
            continue
        m = L.m1(s); t = m["t"]
        x = X.iloc[idx]
        ei = np.searchsorted(t, M._mins(x.entry_time)); xi = np.searchsorted(t, M._mins(x.exit_time))
        j = partial_trigger(t, m["o"], m["h"], m["l"], m["c"], ei, xi, x.dir.to_numpy(np.int64), x.entry.to_numpy(float),
                            x.sl_dist.to_numpy(float), int(T * 60), 60, float(Mfe), float(thr), 1.5)
        hit = j >= 0
        sl = 0.0001 if s in ("BTCUSDT", "ETHUSDT") else 0.0003
        fee = C.TAKER + sl
        px = m["o"][np.where(hit, j, 0)]
        e = x.entry.to_numpy(float); d = x.dir.to_numpy(float); D = x.sl_dist.to_numpy(float)
        hrs = (j - ei) / 60.0
        rt = ((px - e) * d - fee * e - fee * px - C.FUNDING_8H * hrs / 8 * e) / D
        R[idx[hit]] = f * rt[hit] + (1 - f) * R[idx[hit]]
        trig[idx[hit]] = t[j[hit]]
    return R, trig


def chop_mult(p, X):
    """H5: ETH / alt (or alt) entries while BTC's last closed day has ER10 < e -> size x m."""
    er = er_at("BTCUSDT", M._mins(X.arm_time))
    tg = X.sym.isin(M.ALT if p["tgt"] == "alts" else M.MAJ[1:] + M.ALT).to_numpy()
    return np.where(tg & (np.nan_to_num(er, nan=1.0) < p["e"]), p["m"], 1.0)


def crowd_mult(p, X):
    """H6: an entry while >= k other coins hold same-direction trades entered within the last W hours that are not yet at
    their risk-free stop -> size x m."""
    et = M._mins(X.entry_time); bt = M._mins(X.be_time); xt = M._mins(X.exit_time); d = X.dir.to_numpy(); sy = X.sym.to_numpy()
    m = np.ones(len(X))
    o = np.argsort(et)
    for i in o:
        w = (et < et[i]) & (et >= et[i] - p["W"] * 60) & (bt > et[i]) & (xt > et[i]) & (d == d[i]) & (sy != sy[i])
        if len(set(sy[w])) >= p["k"]:
            m[i] = p["m"]
    return m


def mini_panic_cands(sym, p):
    """H1: the panic signal with a smaller OI drop (moderate flush), outside +-12 h of a real panic trigger; exits = the
    live panic exits; hourly bars (the panic research engine), one trade per coin at a time."""
    import panic_signal as PS
    df = SL.bars(sym)
    df = df[df.index >= "2021-11-01"]
    o, h, l, c = (df[k].to_numpy(float) for k in "ohlc")
    f = PS.features(h, l, c, df.oi.to_numpy(float), df.prem.to_numpy(float), p["w"])
    sig = PS.signal(f, move_k=p["k"], oi_drop=p["oi"], premium_z=p["pz"])
    with np.errstate(invalid="ignore"):
        sig &= f["doi"] > -0.12                                        # not the panic tier itself
    th = tmin(df.index.values) + 60
    sig &= ~SL.near_panic(th)
    if p["reg"] == "chop":
        er = er_at("BTCUSDT", th); sig &= np.nan_to_num(er, nan=1.0) < 0.25
    P0 = dict(tp_atr=3.0, stop_atr=4.0, stop_max=0.2, be_atr=2.0, hold_h=p["H"])
    cost = 2 * (0.0005 + SL.SLIP.get(sym, 0.0003)); a_ = f["atr"]; Hh = int(P0["hold_h"]); rows = []; busy = -1
    for i in np.flatnonzero(sig):
        if i <= busy or i + Hh + 2 >= len(o):
            continue
        e = o[i + 1]; a = a_[i]; st = max(e - P0["stop_atr"] * a, e * (1 - P0["stop_max"])); tg = e + P0["tp_atr"] * a; best = e
        px, j = o[i + 1 + Hh], i + 1 + Hh
        for jj in range(i + 1, i + 1 + Hh):
            if l[jj] <= st:
                px, j = st, jj; break
            if h[jj] >= tg:
                px, j = tg, jj; break
            best = max(best, h[jj])
            if best >= e + P0["be_atr"] * a:
                st = max(st, e)
        busy = j
        rows.append((df.index[i + 1], df.index[j], sym, px / e - 1 - cost))
    T = pd.DataFrame(rows, columns=["t", "t_exit", "sym", "ret"])
    T["R"] = T.ret / 0.05; T["dir"] = 1
    return T


def mp_job(args):
    pid, p, sym = args
    _switch(sym)
    return pid, sym, mini_panic_cands(sym, p)


def t8():
    import json
    # ── H1 mini-panic tier (sleeve) ──
    SL.panic_times(); tbo_monthly(); panic_by_coin()
    g = grid(w=(3, 4, 6), oi=(0.06, 0.07, 0.08, 0.09, 0.10), pz=(-0.5, -1.0), k=(1.0, 1.5), reg=("none", "chop"), H=(6, 12))
    plist = [("mp_" + "_".join(f"{k}{v}" for k, v in p.items()), p) for p in g]
    log(f"[T8 H1 mini-panic] {len(plist)} configs x DEV12 (+ HOLD39 for the best)")
    def run_mp(pl, coins):
        tasks = sorted([(pid, p, s) for pid, p in pl for s in coins], key=lambda z: z[2]); out = {}
        with Pool(PROCS) as pool:
            for pid, s, T in pool.imap_unordered(mp_job, tasks, chunksize=8):
                out.setdefault(pid, []).append(T)
        return {k: pd.concat(v, ignore_index=True) for k, v in out.items()}
    TT = run_mp(plist, DEV12)
    rows = [dict(id=pid, **p, **s1_row(TT[pid], P22)) for pid, p in plist]
    R = pd.DataFrame(rows); R["plateau"] = M.plateau(R, ["w", "oi", "pz", "k", "H"], ["reg"], "S1"); R["S2"] = R.plateau >= 0.6
    cand = list(dict.fromkeys(list(R[R.S1 & R.S2].sort_values("mina", ascending=False).id.head(8)) + list(R.sort_values("mina", ascending=False).id.head(3))))
    byid = dict(plist)
    HT = run_mp([(i, byid[i]) for i in cand], HOLD39) if cand else {}
    for i in cand:
        hs = SL.stats(HT.get(i, SL._empty("x")))
        R.loc[R.id == i, ["hold_avg_dev", "hold_avg_oos", "hold_n_dev", "hold_n_oos"]] = [hs[P22]["avg"], hs[P24]["avg"], hs[P22]["n"], hs[P24]["n"]]
        for k, v in s5(TT[i], P22).items():
            R.loc[R.id == i, k] = v
        # S3 null: random hours (same coin, year, count), same exits, 200 draws
        R.loc[R.id == i, ["null_dev", "null_oos"]] = mp_null(TT[i], byid[i])
    for c_ in ("hold_avg_dev", "hold_avg_oos", "null_dev", "null_oos", "S5"):
        if c_ not in R:
            R[c_] = np.nan
    R["S3"] = (R.null_dev >= 0.95) & (R.null_oos >= 0.95); R["S4"] = (R.hold_avg_dev > 0) & (R.hold_avg_oos > 0)
    R["S5"] = R.S5.fillna(False).astype(bool)
    ids = list(dict.fromkeys(R[R.S1 & R.S2 & R.S3 & R.S4].id.tolist() + R.sort_values("mina", ascending=False).id.head(2).tolist()))
    items = []
    for i in ids:
        T = TT[i]
        m_ = lambda s: pd.to_datetime(T[s]).values.astype("datetime64[m]").astype(np.int64)
        n_ev = T.groupby("t").sym.transform("count").to_numpy(float)
        for share in (0.5, 0.75):
            S = np.c_[m_("t"), m_("t_exit"), m_("t"), np.ones(len(T)), T.R.to_numpy() * share / n_ev, np.full(len(T), 7.0), np.ones(len(T))]
            A = W.with_sleeve(W.rows(M.base_at(0)), W.sleeve30()); A = np.r_[A, S]; A = A[np.lexsort((A[:, 5], A[:, 0]))]
            items.append((f"{i}|share{share}", A, W.base_policy(extra_risk=[(5, 0.5), (7, 0.5)])))
    Mo = M.g6_many(items) if items else pd.DataFrame()
    R["S6"] = False
    if len(Mo):
        b = M.money_base(); Mo["E4"] = [M.e4_literal(r, b) for _, r in Mo.iterrows()]
        Mo.to_csv(RES / "v31_T8_H1_mini_panic_money.csv")
        for i in ids:
            R.loc[R.id == i, "S6"] = any(bool(Mo.loc[f"{i}|share{sh}", "E4"]) for sh in (0.5, 0.75))
        print(Mo[["k1_m2022", "k1_m2024", "k1_dd2024", "k1_dd_fall26", "k1_boot_med", "k1_boot_p10", "k1_boot_dd90", "E4", "G6"]].round(2).to_string())
    R["PASS"] = R.S1 & R.S2 & R.S3 & R.S4 & R.S5 & R.S6
    R.to_csv(RES / "v31_T8_H1_mini_panic.csv", index=False)
    log(f"[T8 H1] funnel: {len(R)} -> S1 {int(R.S1.sum())} -> +S2 {int((R.S1 & R.S2).sum())} -> +S3 {int((R.S1 & R.S2 & R.S3).sum())} -> "
        f"+S4 {int((R.S1 & R.S2 & R.S3 & R.S4).sum())} -> +S5 {int((R.S1 & R.S2 & R.S3 & R.S4 & R.S5).sum())} -> PASS {int(R.PASS.sum())}")
    print(R.sort_values(["PASS", "mina"], ascending=False).head(10)[["id", f"{P22}_n", f"{P22}_avg", f"{P22}_pf", f"{P24}_n", f"{P24}_avg", f"{P24}_pf",
          "plateau", "null_dev", "null_oos", "hold_avg_dev", "hold_avg_oos", "S5", "PASS"]].round(3).to_string(index=False))

    # ── H2 post-flush TBO short block (engine, exact: panic triggers do not depend on TBO) ──
    specs = []
    for X, sc, sd in itertools.product((6, 12, 24, 48, 72), ("same", "any"), ("short", "both")):
        specs.append(dict(id=f"pblock_X{X}_{sc}_{sd}", p=dict(X=X, scope=sc, side=sd), ctrlfn=("panic_block", (("X", X), ("scope", sc), ("side", sd)))))
    R, _, X0 = M.evaluate("T8_H2_postflush_block", specs, ["X"], ["scope", "side"], P22, null_fn=M.null_remove)
    M.finish("T8_H2_postflush_block", R, M.money_for("T8_H2_postflush_block", R, X0, specs=specs), ["id"])

    # ── H3 partial failed-breakout scratch (f closed at the trigger, the rest unchanged; trade list = base) ──
    specs = []
    for f, T, Mf, thr in itertools.product((0.33, 0.5, 0.67), (4, 6, 8, 12), (0.6, 0.75, 0.9, 1.1), (0.0, -0.2)):
        specs.append(dict(id=f"partial_f{f}_T{T}_M{Mf}_c{thr}", p=dict(f=f, T=T, M=Mf, thr=thr), engine=False))
    _PR = {}

    def pr(sp, X):
        key = (sp["id"], id(X))
        if key not in _PR:
            if len(_PR) > 4:
                _PR.clear()
            _PR[key] = partial_R(X, sp["p"]["T"], sp["p"]["M"], sp["p"]["thr"], sp["p"]["f"])
        return _PR[key]
    mf = lambda sp, X: np.where(X.R.to_numpy() != 0, pr(sp, X)[0] / np.where(X.R.to_numpy() == 0, 1, X.R.to_numpy()), 1.0)
    R, _, X0 = M.evaluate("T8_H3_partial_scratch", specs, ["f", "T", "M", "thr"], [], P20, mult_fn=mf)

    def rows_fn(sp, X, m):
        Rn, trig = pr(sp, X)
        A = W.rows(X.assign(R=Rn, half_time=pd.to_datetime(np.where(trig >= 0, trig, M._mins(X.be_time)) * MINS)), half=True)
        return A
    byid = {s["id"]: s for s in specs}
    Mo = M.money_for("T8_H3_partial_scratch", R, X0, rows_fn=rows_fn, specs=specs, mk_fn=lambda sp: dict(hfrac=1 - sp["p"]["f"]))
    M.finish("T8_H3_partial_scratch", R, Mo, ["id"])

    # ── H4 regime-conditional failed-breakout rule (top-5 rules of T1b, applied only in a choppy regime) ──
    T1 = pd.read_csv(RES / "v31_T1b_failed_breakout.csv").sort_values("minx", ascending=False).head(5)
    specs = []
    for _, r in T1.iterrows():
        rk = dict(T_h=r["T"], G=60, cont=1, mlo=r.M, mhi=99.0, thr=r.thr, **M.RULE_ACT[r.act])
        for src, e in itertools.product(("BTC", "own"), (0.2, 0.25, 0.3, 0.35, 0.4)):
            specs.append(dict(id=f"regime_{src}_e{e}_{r['id']}", p=dict(rule=r["id"], src=src, e=e), exL=dict(A=rk, rcool=1), exS=dict(A=rk, rcool=1),
                              ctrlfn=("regime_rule", (("src", src), ("e", e)))))
    R, _, X0 = M.evaluate("T8_H4_regime_rule", specs, ["e"], ["rule", "src"], P20)
    M.finish("T8_H4_regime_rule", R, M.money_for("T8_H4_regime_rule", R, X0, specs=specs), ["id"])

    # ── H5 chop-regime ETH / alt sizing ──
    specs = [dict(id=f"chopsize_e{e}_m{m}_{tg}", p=dict(e=e, m=m, tgt=tg), engine=False)
             for e, m, tg in itertools.product((0.15, 0.2, 0.25, 0.3), (0.0, 0.5, 0.75), ("alts", "eth+alts"))]
    mf5 = lambda sp, X: chop_mult(sp["p"], X)
    R, _, X0 = M.evaluate("T8_H5_chop_sizing", specs, ["e", "m"], ["tgt"], P20, mult_fn=mf5,
                          null_fn=lambda sp, X, rng: (X, M.permute_by_coin_side(X, mf5(sp, X), rng)))
    M.finish("T8_H5_chop_sizing", R, M.money_for("T8_H5_chop_sizing", R, X0, mult_fn=mf5, specs=specs), ["id"])

    # ── H6 unconfirmed-crowd sizing ──
    specs = [dict(id=f"crowd_k{k}_W{Wh}_m{m}", p=dict(k=k, W=Wh, m=m), engine=False) for k, Wh, m in itertools.product((2, 3), (4, 8, 12), (0.5, 0.75))]
    mf6 = lambda sp, X: crowd_mult(sp["p"], X)
    R, _, X0 = M.evaluate("T8_H6_crowd_sizing", specs, ["k", "W", "m"], [], P20, mult_fn=mf6,
                          null_fn=lambda sp, X, rng: (X, M.permute_by_coin_side(X, mf6(sp, X), rng)))
    M.finish("T8_H6_crowd_sizing", R, M.money_for("T8_H6_crowd_sizing", R, X0, mult_fn=mf6, specs=specs), ["id"])

    # ── H7 weekend stop tightening / H8 BTC stop-out cascade ──
    specs = [dict(id=f"weekend_{w}_{lv}", p=dict(when=w, lvl=str(lv)), ctrlfn=("weekend", (("when", w), ("lvl", lv))))
             for w, lv in itertools.product(("fri20", "sat0"), (-0.75, -0.5, -0.25, 0.0, "close"))]
    R, _, X0 = M.evaluate("T8_H7_weekend", specs, [], ["when", "lvl"], P20)
    M.finish("T8_H7_weekend", R, M.money_for("T8_H7_weekend", R, X0, specs=specs), ["id"])
    specs = [dict(id=f"cascade_{a}", p=dict(act=str(a)), coins=W.COINS[1:], ctrlfn=("btc_cascade", (("act", a),))) for a in (-0.75, -0.5, -0.25, 0.0, "close")]
    R, _, X0 = M.evaluate("T8_H8_btc_cascade", specs, [], ["act"], P20)
    M.finish("T8_H8_btc_cascade", R, M.money_for("T8_H8_btc_cascade", R, X0, specs=specs), ["id"])


def mp_null(T, p, n=200):
    """Random-hour copies of a mini-panic trade list (same coin, same year, same count), same exits; avg R per period."""
    rng = np.random.default_rng(0)
    res = np.zeros((n, 2))
    per_coin = {}
    for s, g in T.groupby("sym"):
        df = SL.bars(s); df = df[df.index >= "2021-11-01"]
        o, h, l, c = (df[k].to_numpy(float) for k in "ohlc"); a_ = SL.atr(df, 14)
        per_coin[s] = (df, o, h, l, c, a_, g)
    for q in range(n):
        Rs = []
        for s, (df, o, h, l, c, a_, g) in per_coin.items():
            yrs = g.t.dt.year.to_numpy()
            for y in np.unique(yrs):
                cand = np.flatnonzero((df.index.year == y) & np.isfinite(a_))
                cand = cand[cand + p["H"] + 2 < len(o)]
                for i in rng.choice(cand, int((yrs == y).sum())):
                    e = o[i + 1]; a = a_[i]; st = max(e - 4 * a, e * 0.8); tg = e + 3 * a; best = e; px = o[i + 1 + p["H"]]
                    for jj in range(i + 1, i + 1 + p["H"]):
                        if l[jj] <= st:
                            px = st; break
                        if h[jj] >= tg:
                            px = tg; break
                        best = max(best, h[jj])
                        if best >= e + 2 * a:
                            st = max(st, e)
                    Rs.append((df.index[i + 1], (px / e - 1 - 2 * (0.0005 + SL.SLIP.get(s, 0.0003))) / 0.05))
        Z = pd.DataFrame(Rs, columns=["t", "R"])
        a1 = Z[(Z.t >= "2022-01-01") & (Z.t < "2024-01-01")].R.mean(); a2 = Z[Z.t >= "2024-01-01"].R.mean()
        res[q] = [a1, a2]
    s = SL.stats(T.assign(t_exit=T.t_exit))
    return [float(np.mean(res[:, 0] < s[P22]["avg"])), float(np.mean(res[:, 1] < s[P24]["avg"]))]
