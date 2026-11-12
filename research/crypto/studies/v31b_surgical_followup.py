"""v3.1b surgical follow-up (Nov 2026; read-only on cryptobot/). Same engine, gates and data as v31_drawdown_and_sleeves.py.

PKG = the v3.1 candidate: TBO v3.0 + failed-breakout stop tighten (T 8 h, hourly, MFE >= 0.9R, close < -0.2R -> stop -0.5R,
cooldown after a rule exit) + BTC stop-out cascade (ETH / alts' stop -> -0.25R), with Panic v3.0.
Rules marked 'on PKG' are scored against PKG (its own 41 phase copies and money base), the others against v3.0.

  pkgbase   PKG trades at 41 phases + PKG money base
  h3t2      (1) the T8_H3 partial-scratch passer and the best T2a re-anchors, alone and on PKG
  cluster   (2) non-cycling portfolio cluster size-down / cap-tighten (trade list unchanged: exact in one pass), on v3.0 and PKG
  fast      (3) fast-fakeout defence (T 1-4 h, never reached +0.2-0.4R, close deep below entry -> stop -0.65..-0.8R or
            take-profit at entry), on v3.0 and PKG
  volc      (4) 4h VOLC + OI sleeve: core 5 vs DEV12, size 0.10-0.25 x BTC risk, uncapped / inside the open-risk cap /
            only while open TBO risk < 0.5 x cap
  risk      (5) iso-return table: risk x k (0.75 .. 1.00) and a smoother ladder on v3.0, PKG and v3.1b (PKG + VOLC)

    python v31b_surgical_followup.py <stage>          -> research/results/v31b_*.csv"""
import itertools, os, sys
from multiprocessing import Pool
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v30")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import common as C, v29lib as L, v31lib as W, sleeve31 as SL
import v31_drawdown_and_sleeves as M
import v31_sleeves as S8

RES, log = M.RES, M.log
V30DIR, PKGDIR = W.CACHE, W.CACHE / "pkg"
FB = dict(T_h=8, G=60, cont=1, mlo=0.9, mhi=99.0, thr=-0.2, act=3, lvl=-0.5)
CASC = -0.25
MINS = W.MIN


def use_base(which):
    """Switch the scoring baseline of M.evaluate / money_for between v3.0 and PKG."""
    M.CACHE = PKGDIR if which == "pkg" else V30DIR
    M._BASE.clear(); M._BS.clear(); M._MB.clear()


# ── BTC cascade driven by BTC's own trades under any exit spec (BX registry, filled before the pools fork) ──────────────
BX = {"fb": dict(exL=dict(A=FB, rcool=1), exS=dict(A=FB, rcool=1))}
_BT = {}


def btc_x(shift, bx):
    key = (shift, bx)
    if key not in _BT:
        _BT.clear()
        kw = BX[bx]
        _BT[key] = W.trades31("BTCUSDT", shift=shift, exL=kw.get("exL"), exS=kw.get("exS"), fa_tf=kw.get("fa_tf", 0))
    return _BT[key]


@S8._ctrl
def cascade_bx(sym, shift, t, act=CASC, bx="fb"):
    b = btc_x(shift, bx); b = b[b.R < -0.5]
    out = {}
    for d, nm in ((1, "l"), (-1, "s")):
        j = np.searchsorted(t, M._mins(b[b.dir == d].exit_time)) + 1
        m = np.zeros(len(t), np.bool_); m[j[j < len(t)]] = True
        out["tight_" + nm] = m
    out["tight_to"] = float(act)
    return out


def pkg_spec(sid, p, exL=None, exS=None, fa_tf=0, bx=None):
    """PKG + extra exit options: exL / exS are merged over the FB rule (slot A)."""
    eL = dict(dict(A=FB, rcool=1), **(exL or {})); eS = dict(dict(A=FB, rcool=1), **(exS or {}))
    if bx is None:
        bx = sid
        BX[bx] = dict(exL=eL, exS=eS, fa_tf=fa_tf)
    sp = dict(id=sid, p=p, exL=eL, exS=eS, ctrlfn=("cascade_bx", (("act", CASC), ("bx", bx))))
    if fa_tf:
        sp["fa_tf"] = fa_tf
    return sp


def pkgbase():
    PKGDIR.mkdir(parents=True, exist_ok=True)
    sp = pkg_spec("pkg", {}, bx="fb")
    r = M.run_jobs([sp], shifts=[0] + M.SH)["pkg"]
    for sh, X in r.items():
        X.to_pickle(PKGDIR / f"base_s{sh}.pkl")
    use_base("pkg")
    f = PKGDIR / "money_base.pkl"
    if f.exists():
        f.unlink()
    b = M.money_base()
    log(f"PKG: {len(r[0])} trades, sum R {r[0].R.sum():.1f}; money {b}")


# ══ (1) H3 partial scratch + T2a re-anchors ══════════════════════════════════════════════════════════════════════
def h3t2():
    cols = ["id", "x_dev", "x_oos", "netr_dev", "netr_oos", "plateau", "phase_dev", "phase_oos", "null_pct", "E1", "E2", "E3", "M_k1_m2022",
            "M_k1_m2024", "M_k1_dd2024", "M_k1_dd_fall26", "M_k1_boot_med", "M_k1_boot_p10", "M_k1_boot_dd90", "E4", "M_k", "G6", "PASS"]
    for f in ("v31_T8_H3_partial_scratch", "v31_T2a_reanchor"):
        R = pd.read_csv(RES / f"{f}.csv").sort_values("minx", ascending=False).head(12)
        R[[c for c in cols if c in R]].to_csv(RES / f"v31b_1_top_{f[4:]}.csv", index=False)
        print(f); print(R[[c for c in cols if c in R]].round(3).to_string(index=False))
    use_base("pkg")
    # (a) partial scratch on top of PKG (trade list = PKG; exact)
    specs = [dict(id=f"pkg+partial_f{f}_T{T}_M{Mf}_c{thr}", p=dict(f=f, T=T, M=Mf, thr=thr), engine=False)
             for f, T, Mf, thr in itertools.product((0.33, 0.5), (6, 8), (0.6, 0.75, 0.9), (0.0, -0.2))]
    _PR = {}

    def pr(sp, X):
        key = (sp["id"], id(X))
        if key not in _PR:
            if len(_PR) > 4:
                _PR.clear()
            _PR[key] = S8.partial_R(X, sp["p"]["T"], sp["p"]["M"], sp["p"]["thr"], sp["p"]["f"])
        return _PR[key]
    mf = lambda sp, X: np.where(X.R.to_numpy() != 0, pr(sp, X)[0] / np.where(X.R.to_numpy() == 0, 1, X.R.to_numpy()), 1.0)
    R, _, X0 = M.evaluate("v31b_1a_pkg_partial", specs, ["f", "T", "M", "thr"], [], M.P20, mult_fn=mf)

    def rows_fn(sp, X, m):
        Rn, trig = pr(sp, X)
        return W.rows(X.assign(R=Rn, half_time=pd.to_datetime(np.where(trig >= 0, trig, M._mins(X.be_time)) * MINS)), half=True)
    Mo = M.money_for("v31b_1a_pkg_partial", R, X0, rows_fn=rows_fn, specs=specs, mk_fn=lambda sp: dict(hfrac=1 - sp["p"]["f"]))
    M.finish("v31b_1a_pkg_partial", R, Mo, ["id"])
    # (b) the best T2a re-anchors on top of PKG (engine; the cascade follows BTC's re-anchored trades)
    top = pd.read_csv(RES / "v31_T2a_reanchor.csv")
    top = top[top.E1 & top.E2].sort_values("minx", ascending=False).head(8)
    specs = []
    for _, r in top.iterrows():
        kk = M.RA_KIND[r.kind]
        mode = {"tight": 1, "widen": 2, "both": 3}[r["mode"]]
        ra = dict(mode=mode, lo=r.lo if r.lo > 0 else 0.0, hi=r.hi if r.hi > 0 else 99.0, alpha=r.alpha, anchor=int(r.anchor), den=kk["den"],
                  k=kk.get("k", 2.0), rmax=2.0, rmin=0.3)
        specs.append(pkg_spec(f"pkg+{r['id']}", dict(mode=r["mode"], kind=r.kind, lo=r.lo, hi=r.hi, alpha=r.alpha, anchor=r.anchor),
                              exL=dict(ra=ra), exS=dict(ra=ra), fa_tf=kk["fa"]))
    R, _, X0 = M.evaluate("v31b_1b_pkg_reanchor", specs, ["lo", "hi", "alpha"], ["mode", "kind", "anchor"], M.P20, top=8)
    M.finish("v31b_1b_pkg_reanchor", R, M.money_for("v31b_1b_pkg_reanchor", R, X0, specs=specs, ids=list(R.id)), ["id"])


# ══ (2) non-cycling cluster size-down / cap-tighten ════════════════════════════════════════════════════════════════
def cluster_windows(X, K, Wh, H):
    """[start, end) windows: from each stop-out (R <= -0.5) that completes >= K distinct coins' stop-outs within Wh hours,
    for H hours. Only closed trades are read, so the rule is causal; it changes sizes, never the trade list."""
    s = X[X.R <= -0.5].sort_values("exit_time")
    et = M._mins(s.exit_time); sy = s.sym.to_numpy()
    out = []
    for i in range(len(s)):
        w = (et >= et[i] - Wh * 60) & (et <= et[i])
        if len(set(sy[w])) >= K:
            out.append((et[i], et[i] + H * 60))
    return np.array(out, np.int64).reshape(-1, 2)


def in_windows(t, iv):
    if not len(iv):
        return np.zeros(len(t), bool)
    k = np.searchsorted(iv[:, 0], t, side="right") - 1
    ok = k >= 0
    # windows can overlap: take the max end among windows started at or before t
    ends = np.maximum.accumulate(iv[:, 1])
    return ok & (t < ends[np.clip(k, 0, None)]) & (t > iv[np.clip(k, 0, None), 0] - 1)


def csize_mult(p, X):
    iv = cluster_windows(X, p["K"], p["W"], p["H"])
    return np.where(in_windows(M._mins(X.entry_time), iv), p["m"], 1.0)


def fixed_ratio(A, pol, mk):
    out = {}
    for per, (a, b) in W.PERIODS.items():
        r = W.money31(W.window(A, a, b), pol, eq0=1e6, fixed=True, **mk)
        out[per] = (r["final"] - 1e6) / r["dd_abs"]
    return out


def cluster_one(which):
    use_base(which)
    tag = "v30" if which == "v30" else "pkg"
    # size-down: multiplier on the fixed-unit account (exact), nulls, phase copies, money
    specs = [dict(id=f"{tag}_csize_K{K}_W{Wh}_H{H}_m{m}", p=dict(K=K, W=Wh, H=H, m=m), engine=False)
             for K, Wh, H, m in itertools.product((2, 3), (4, 6, 8, 12, 16, 24), (8, 12, 16, 24, 36), (0.35, 0.5, 0.65))]
    mf = lambda sp, X: csize_mult(sp["p"], X)
    R, _, X0 = M.evaluate(f"v31b_2a_{tag}_cluster_size", specs, ["K", "W", "H", "m"], [], M.P20, mult_fn=mf,
                          null_fn=lambda sp, X, rng: (X, M.permute_by_coin_side(X, mf(sp, X), rng)))
    M.finish(f"v31b_2a_{tag}_cluster_size", R, M.money_for(f"v31b_2a_{tag}_cluster_size", R, X0, mult_fn=mf, specs=specs), ["id"])
    # cap-tighten: open-risk cap x c for new entries inside the windows (capped non-compounding account for E1)
    B0 = M.base_at(0); pol = W.base_policy()
    base_fx = fixed_ratio(W.rows(B0, half=True), pol, {})
    rows = []
    cfg = list(itertools.product((2, 3), (4, 6, 8, 12, 16, 24), (8, 12, 16, 24, 36), (0.65, 0.75)))

    def capA(X, K, Wh, H, c):
        A = W.rows(X, half=True)
        iv = cluster_windows(X, K, Wh, H)
        cm = np.where(in_windows(A[:, 0].astype(np.int64), iv), c, 1.0)
        return np.c_[A, cm]
    for K, Wh, H, c in cfg:
        fx = fixed_ratio(capA(B0, K, Wh, H, c), pol, {})
        rows.append(dict(id=f"{tag}_ccap_K{K}_W{Wh}_H{H}_c{c}", K=K, W=Wh, H=H, c=c, x_dev=fx[M.P20] / base_fx[M.P20], x_oos=fx[M.P24] / base_fx[M.P24]))
    Rc = pd.DataFrame(rows); Rc["E1"] = (Rc.x_dev > 1) & (Rc.x_oos > 1); Rc["minx"] = Rc[["x_dev", "x_oos"]].min(axis=1)
    Rc["plateau"] = M.plateau(Rc, ["K", "W", "H", "c"], [], "E1"); Rc["E2"] = Rc.plateau >= 0.6
    show = list(dict.fromkeys(list(Rc[Rc.E1 & Rc.E2].sort_values("minx", ascending=False).id.head(10)) + list(Rc.sort_values("minx", ascending=False).id.head(3))))
    Rc["phase_dev"] = np.nan; Rc["phase_oos"] = np.nan
    for i in show:
        r = Rc[Rc.id == i].iloc[0]; w = []
        for sh in M.SH:
            Xs = M.base_at(sh); b = fixed_ratio(W.rows(Xs, half=True), pol, {}); v = fixed_ratio(capA(Xs, r.K, r.W, r.H, r.c), pol, {})
            w.append((v[M.P20] / b[M.P20] > 1, v[M.P24] / b[M.P24] > 1))
        w = np.array(w, float); Rc.loc[Rc.id == i, ["phase_dev", "phase_oos"]] = [w[:, 0].mean(), w[:, 1].mean()]
    Rc["E3"] = (Rc.phase_dev >= M.PH_MIN) & (Rc.phase_oos >= M.PH_MIN)
    items = [(i, W.with_sleeve(capA(B0, *Rc[Rc.id == i][["K", "W", "H", "c"]].iloc[0].tolist()), W.sleeve30()), pol, {}) for i in show]
    Mo = M.g6_many(items) if items else pd.DataFrame()
    M.finish(f"v31b_2b_{tag}_cluster_cap", Rc, Mo, ["id"])


def cluster():
    cluster_one("v30"); cluster_one("pkg")


# ══ (3) fast-fakeout defence ══════════════════════════════════════════════════════════════════════════════════════
FAST_ACT = {"t-0.65": dict(act=3, lvl=-0.65), "t-0.75": dict(act=3, lvl=-0.75), "t-0.8": dict(act=3, lvl=-0.8), "tp0": dict(act=1, lvl=0.0)}


def fast():
    import collections
    base = pd.read_pickle(V30DIR / "base_s0.pkl")
    late = base[(base.entry_time >= "2026-10-01") & (base.R < -0.5)]
    cnt = collections.OrderedDict(n=len(late), lt8=int((late.hours < 8).sum()), lt4=int((late.hours < 4).sum()),
                                  oct_n=int((late.entry_time < "2026-11-01").sum()), oct_lt8=int(((late.entry_time < "2026-11-01") & (late.hours < 8)).sum()))
    log(f"Oct 1 - Nov 6 2026 full stop-outs (v3.0): {dict(cnt)}")
    A = pd.read_pickle(V30DIR / "anatomy.pkl")
    st = A[A.R < -0.5]; win = A[A.R >= 2]
    rows = []
    for T in (1, 2, 3, 4):
        for mk in (0.25, 0.4):                      # anatomy marks nearest to the brief's 0.2-0.3 / 0.4R
            never = lambda Z: (Z[f"t_{mk}"].isna() | (Z[f"t_{mk}"] > T))
            deep = lambda Z: Z[f"maeafter_0.25"].notna()
            rows.append(dict(T_h=T, mfe_mark=mk, stopouts_not_reached_by_T=float(never(st).mean()),
                             winners2R_not_reached_by_T=float(never(win).mean()), n_stop=len(st), n_win=len(win)))
    pd.DataFrame(rows).to_csv(RES / "v31b_3_fast_anatomy.csv", index=False)
    grid = list(itertools.product((1, 2, 3, 4), (15, 60), (0.2, 0.3, 0.4), (-0.45, -0.55, -0.65, -0.75), tuple(FAST_ACT)))
    for which in ("v30", "pkg"):
        use_base(which)
        specs = []
        for T, G, mh, thr, act in grid:
            rk = dict(T_h=T, G=G, cont=1, mlo=-99.0, mhi=mh, thr=thr, **FAST_ACT[act])
            sid = f"{which}_fast_T{T}_G{G}_mfe{mh}_c{thr}_{act}"
            p = dict(T=T, G=G, mh=mh, thr=thr, act=act)
            if which == "v30":
                specs.append(dict(id=sid, p=p, exL=dict(B=rk, rcool=1), exS=dict(B=rk, rcool=1)))
            else:
                specs.append(pkg_spec(sid, p, exL=dict(B=rk), exS=dict(B=rk)))
        R, _, X0 = M.evaluate(f"v31b_3_{which}_fast_fakeout", specs, ["T", "G", "mh", "thr"], ["act"], M.P20, top=25)
        M.finish(f"v31b_3_{which}_fast_fakeout", R, M.money_for(f"v31b_3_{which}_fast_fakeout", R, X0, specs=specs), ["id"])


# ══ (4) 4h VOLC + OI sleeve ═════════════════════════════════════════════════════════════════════════════════════
VOLC = {"N8_H36": dict(tf=240, sq="atr0.6", N=8, dm="hybrid", TP=1.5, H=36, oi=0.0, sc=0),
        "N10_H36": dict(tf=240, sq="atr0.6", N=10, dm="hybrid", TP=1.5, H=36, oi=0.0, sc=0),
        "N10_H48": dict(tf=240, sq="atr0.6", N=10, dm="hybrid", TP=1.5, H=48, oi=0.0, sc=0),
        "N8_H24": dict(tf=240, sq="atr0.6", N=8, dm="hybrid", TP=1.5, H=24, oi=0.0, sc=0)}
_VT = {}


def volc_trades():
    if not _VT:
        f = W.CACHE / "v31b_volc.pkl"
        if f.exists():
            _VT.update(pd.read_pickle(f))
        else:
            _VT.update(S8.run_fam("volc", list(VOLC.items()), S8.DEV12))
            pd.to_pickle(dict(_VT), f)
    return _VT


def volc_rows(T, univ, capped):
    T = T[T.sym.isin(W.COINS if univ == "core5" else S8.DEV12)]
    m = lambda s: pd.to_datetime(T[s]).values.astype("datetime64[m]").astype(np.int64)
    be = m("t_exit") if capped else m("t")                       # counted under the cap until the exit
    return np.c_[m("t"), m("t_exit"), be, T.dir.to_numpy(float), T.R.to_numpy(float), np.full(len(T), 6.0), np.ones(len(T))]


def volc():
    VT = volc_trades()
    st = []
    for nm, T in VT.items():
        for univ in ("core5", "DEV12"):
            g = T[T.sym.isin(W.COINS if univ == "core5" else S8.DEV12)]
            s = SL.stats(g)
            st.append(dict(id=nm, univ=univ, **{f"{p}_{k}": v for p, d in s.items() for k, v in d.items() if k in ("n", "avg", "pf", "net", "dd")}))
    ST = pd.DataFrame(st); ST.to_csv(RES / "v31b_4_volc_stats.csv", index=False); print(ST.round(3).to_string(index=False))
    items = []
    for which in ("v30", "pkg"):
        X = pd.read_pickle((V30DIR if which == "v30" else PKGDIR) / "base_s0.pkl")
        for nm, univ, w, mode in itertools.product(VT, ("core5", "DEV12"), (0.10, 0.15, 0.20, 0.25), ("uncapped", "capped", "gate0.5")):
            Sv = volc_rows(VT[nm], univ, mode != "uncapped")
            A = W.with_sleeve(W.rows(X), W.sleeve30()); A = np.r_[A, Sv]; A = A[np.lexsort((A[:, 5], A[:, 0]))]
            mk = {} if mode == "uncapped" else dict(cap_sleeves=(6,), sl_gate=0.5 if mode == "gate0.5" else 0.0)
            items.append((f"{which}+volc_{nm}_{univ}_w{w}_{mode}", A, W.base_policy(extra_risk=[(5, 0.5), (6, w)]), mk))
    use_base("v30")
    Mo = M.g6_many(items)
    b30 = M.money_base(); use_base("pkg"); bpk = M.money_base()
    Mo["E4_vs_v30"] = [M.e4_literal(r, b30) for _, r in Mo.iterrows()]
    Mo["E4_vs_pkg"] = [M.e4_literal(r, bpk) for _, r in Mo.iterrows()]
    Mo.to_csv(RES / "v31b_4_volc_money.csv")
    cols = ["k1_m2022", "k1_m2024", "k1_dd2024", "k1_dd_fall26", "k1_boot_med", "k1_boot_p10", "k1_boot_dd90", "E4_vs_v30", "E4_vs_pkg"]
    print(Mo[Mo.index.str.startswith("pkg")].sort_values("k1_boot_dd90")[cols].head(30).round(2).to_string())
    print("E4 vs v3.0 pass share by mode:", Mo.groupby(Mo.index.str.split("_").str[-1]).E4_vs_v30.mean().round(2).to_dict())


# ══ (5) iso-return / risk-scaled table ═══════════════════════════════════════════════════════════════════════════
LADDERS = {
    "live 6/5/2.5": None,
    "smooth 5/4.2/2.2 cap1.0": dict(open_risk_cap_pct=5.0, cap_exempt=["BTCUSDT"], cap_min_fraction=0.25, risk_ladder=[
        {"from_usdt": 0, "BTCUSDT": 5.0, "ETHUSDT": 3.33, "BNBUSDT": 0.83, "SOLUSDT": 0.83, "ADAUSDT": 0.83, "cap_pct": 5.0},
        {"from_usdt": 1000, "BTCUSDT": 4.2, "ETHUSDT": 2.8, "BNBUSDT": 0.83, "SOLUSDT": 0.83, "ADAUSDT": 0.83, "cap_pct": 4.2},
        {"from_usdt": 10000, "BTCUSDT": 2.2, "ETHUSDT": 1.47, "BNBUSDT": 0.42, "SOLUSDT": 0.42, "ADAUSDT": 0.42, "cap_pct": 2.2}]),
}


def monthly_stats(A, pol, a="2024-01-01", **mk):
    r = W.money31(W.window(A, a), pol, path=True, **mk)
    pt, pe, pw = r["path"]
    t0 = pd.Timestamp(a).value // MINS
    s = pd.Series(pe, index=pd.to_datetime((pt + t0) * MINS)).sort_index()
    me = s.resample("ME").last().ffill()
    ret = me.pct_change(); ret.iloc[0] = me.iloc[0] / 300.0 - 1
    lose = ret[ret < 0]
    return len(lose), float(lose.mean() * 100) if len(lose) else 0.0, len(ret)


def risk():
    VT = volc_trades()
    pick = os.environ.get("V31B_VOLC", "N10_H36|DEV12|0.2|uncapped").split("|")
    X30 = pd.read_pickle(V30DIR / "base_s0.pkl"); XPK = pd.read_pickle(PKGDIR / "base_s0.pkl")
    Sv = volc_rows(VT[pick[0]], pick[1], pick[3] != "uncapped")
    mkv = {} if pick[3] == "uncapped" else dict(cap_sleeves=(6,), sl_gate=0.5 if pick[3] == "gate0.5" else 0.0)
    pkgs = {"v3.0": (W.with_sleeve(W.rows(X30), W.sleeve30()), [(5, 0.5)], {}),
            "v3.1 (PKG)": (W.with_sleeve(W.rows(XPK), W.sleeve30()), [(5, 0.5)], {})}
    A = W.with_sleeve(W.rows(XPK), W.sleeve30()); A = np.r_[A, Sv]; A = A[np.lexsort((A[:, 5], A[:, 0]))]
    pkgs[f"v3.1b (PKG + VOLC {pick[0]} {pick[1]} {pick[2]} {pick[3]})"] = (A, [(5, 0.5), (6, float(pick[2]))], mkv)
    rows = []
    for (nm, (A_, ex, mk)), (ln, pf), k in itertools.product(pkgs.items(), LADDERS.items(), (1.00, 0.95, 0.90, 0.85, 0.80, 0.75)):
        pol = W.base_policy(pf=pf, extra_risk=ex) if pf else W.base_policy(extra_risk=ex)
        pol = dict(pol, mult=k)
        r = W.money_all(A_, pol, **mk)
        r26 = W.money31(W.window(A_, "2026-10-01"), pol, **mk)
        nl, al, nm_ = monthly_stats(A_, pol, **mk)
        rows.append(dict(package=nm, ladder=ln, k=k, m2022=r["m2022"], dd2022=r["dd2022"], m2024=r["m2024"], dd2024=r["dd2024"],
                         oct_nov26_ret_pct=(r26["final"] / 300 - 1) * 100, oct_nov26_dd=r26["dd"], losing_months_2024run=nl, months_2024run=nm_,
                         avg_losing_month_pct=al, boot_med=r["boot_med"], boot_p10=r["boot_p10"], boot_dd90=r["boot_dd90"], boot_dd_med=r["boot_dd_med"]))
        log(f"{nm} | {ln} | k {k}: 2024 ${r['m2024']:,.0f} dd {r['dd2024']:.1f} | boot med ${r['boot_med']:,.0f} dd90 {r['boot_dd90']:.1f}")
    T = pd.DataFrame(rows); T.to_csv(RES / f"v31b_5_risk_table{os.environ.get('V31B_TAG', '')}.csv", index=False)
    print(T.round(1).to_string(index=False))


if __name__ == "__main__":
    {"pkgbase": pkgbase, "h3t2": h3t2, "cluster": cluster, "fast": fast, "volc": volc, "risk": risk}[sys.argv[1]]()
