"""v3.3 campaign (Nov 2026): structural follow-ups on top of TBO v3.2 as deployed (946b026). Read-only on cryptobot/.

BASE = v3.2: the v3.1 trade list (1,355 trades; 41 phase copies in cache/v31/pkg) x the wild-pullback size (x0.25 when the
coin's VolReg >= 0.98 and dir x Chg5 <= -0.25 at entry), the v3.2 ladder (portfolio.json: v3.0 at k 1.00, first row flat),
live cap counting, panic v3.0 + VOLC 0.25 (the v3.1 lists).

  t1a  late-life lock (engine, xengine33 rule C): from T_lock h, once MFE >= m (and < +5R): stop to +L, unconditionally at
       T_lock (one check) or at the first hourly close below +X R from T_lock on
  t1b  zone-2 failed extension (rule C): from T h, at each 1h / 4h close, MFE >= mlo (< +5R) and the close below +thr R or
       giving back >= gb of the peak: stop to +L or a limit take-profit at +L
  t2   cut-only regime sizing (never > 1, combined with v3.2's size as the smaller multiplier): FlatWild megaphone (coin or
       BTC VolReg high and |Dir20| small), Q5 climax (VolReg >= v, unconditional or after a 5-day run >= b ATR in the
       trade's direction), counter-macro shorts (short while Dir20 >= d)
  t3v  VOLC intra-trade protection (its own engine vector): failed-breakout tighten (rule A) and a lock (+X -> Y R)
  t3p  panic intra-trade protection: failed-bounce tighten at hour T; same-coin repeat-flush block / half size
  final  the passing rules together, k and ladder as deployed

GATES (v3.2c's): E1 = uncapped fixed-unit ratio x > 1 in 2020-23 and 2024-26 with net >= 92% AND the capped non-compounding
account (live cap counting) x > 1 in both; E2 plateau 60%; E3 engine rules: >= 75% of the 40 phase copies (uncapped and
capped), sizing rules: also >= 95% of 200 coin/side-shuffled nulls (uncapped and capped); HOLD_BIG (14 untouched coins) shown;
E4 money from $300 and 1,000 two-year journeys vs v3.2 deployed (G6 drawdown-matched read shown).
Sleeve rules (t3v / t3p) on the sleeve's own R stream (dev 2022-23, oos 2024-26): E1 ratio x > 1 in both, net >= 92%; E2
plateau; E3 >= 75% of 200 paired month-block bootstraps x > 1 in both periods (+ VOLC: x > 1 on the 7 coins outside its
universe in both periods); E4 the whole system's money vs v3.2.

    python v33_structural_frontiers.py base | t1a | t1b | t2 | t3v | t3p | final"""
import itertools, json, os, sys, time
from multiprocessing import Pool, get_context
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v32")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import common as C, v29lib as L, v30lib as V0, v31lib as W, xengine31 as X31
import crypto_regimes as R
import v31_drawdown_and_sleeves as M
import v32_market_regimes_and_alpha as S
import v32b_cap_fix_and_wild_regime as B
import v31deploy as D
import v33lib as V33
import panic_sleeve as PSL

RES = M.RES
P20, P22, P24 = M.P20, M.P22, M.P24
PROCS = int(os.environ.get("V31_PROCS", 5))
CDIR = C.D.CACHE / "v33"
log = M.log
COINS = W.COINS
V32P = dict(kind="pull", vr=0.98, c=-0.25, m=0.25)
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 70); pd.set_option("display.max_rows", 400)
SPAWN = get_context("spawn")       # post-processing pools: a fork after the engine pools deadlocked (futex) once


def _g6(a):
    i, A, p, base, mk = a
    return i, W.g6(A, p, base, **mk)


def g6_pool(items):
    if not items:
        return pd.DataFrame()
    with SPAWN.Pool(PROCS) as pool:
        res = pool.map(_g6, items, chunksize=1)
    return pd.DataFrame([dict(id=i, **r) for i, r in res]).set_index("id")


# ══ setup ══════════════════════════════════════════════════════════════════════════════════════════════════════════
_SL = {}


def setup():
    base = CDIR / "base"; base.mkdir(parents=True, exist_ok=True)
    for f in (W.CACHE / "pkg").glob("base_s*.pkl"):
        if not (base / f.name).exists():
            (base / f.name).symlink_to(f)
    V = pd.read_pickle(C.D.CACHE / "volc_trades_v32.pkl")
    panic = W.sleeve30()
    _SL["panic"] = panic; _SL["volc"] = V
    W.sleeve30 = lambda: np.r_[panic, volc_rows(V)]
    _bp = W.base_policy
    W.base_policy = lambda **kw: _bp(**dict(dict(extra_risk=[(5, 0.5), (6, 0.25)]), **kw))
    M.CACHE = base; M._BASE.clear(); M._BS.clear(); M._MB.clear()
    M.job = V33.job33
    _tg = {}

    def tagged(X):
        k = id(X)
        if k not in _tg:
            _tg[k] = S.tag(X)
        return _tg[k]
    S.tagged = tagged


def volc_rows(V):
    m = lambda c: V[c].values.astype("datetime64[m]").astype(np.int64)
    return np.c_[m("entry_time"), m("exit_time"), m("entry_time"), V.dir.to_numpy(float), V.R.to_numpy(float), np.full(len(V), 6.0), np.ones(len(V))]


def sleeve(panic=None, V=None):
    p = _SL["panic"] if panic is None else panic
    v = _SL["volc"] if V is None else V
    return np.r_[p, volc_rows(v)]


def pol():
    return B.pol("live")


def m32(X):
    return B.pullback(V32P, X)


def mrows(X, m, Sl=None):
    return W.with_sleeve(W.rows(X, half=True, mult=m), sleeve() if Sl is None else Sl)


_REF = {}


def ref():
    if "r" not in _REF:
        f = CDIR / "ref_money_v32.pkl"
        if f.exists():
            _REF["r"] = pd.read_pickle(f)
        else:
            X = M.base_at(0)
            _REF["r"] = W.money_all(mrows(X, m32(X)), pol()); pd.to_pickle(_REF["r"], f)
    return _REF["r"]


def base():
    setup()
    r = ref()
    log("v3.2 reference (money31, live cap, v3.2 ladder): " + ", ".join(f"{k} {v:,.2f}" for k, v in r.items()))
    X = M.base_at(0)
    log(f"trades {len(X)}, at x0.25 {int((m32(X) < 1).sum())}")


# ══ shared scoring ══════════════════════════════════════════════════════════════════════════════════════════════════
def finish(name, Rr, ords, cats, money_ids, mk_items, refm=None):
    refm = refm or ref()
    Mo = g6_pool(mk_items(money_ids)) if money_ids else pd.DataFrame()
    Rr = B.attach_money(Rr, Mo, refm)
    Rr.to_csv(RES / f"v33_{name}.csv", index=False)
    log(f"[{name}] {len(Rr)} -> E1 {int(Rr.E1.sum())} -> +E2 {int((Rr.E1 & Rr.E2).sum())} -> +E3 {int((Rr.E1 & Rr.E2 & Rr.E3).sum())} -> "
        f"PASS {int(Rr.PASS.sum())} (G6 {int(Rr.PASS_dd_matched.sum())})")
    B.show_table(Rr, ords + cats, n=12)
    return Rr


def gates_e1(Rr, ords, cats):
    Rr["E1u"] = (Rr.x_dev > 1) & (Rr.x_oos > 1) & (Rr.netr_dev >= M.NET_MIN) & (Rr.netr_oos >= M.NET_MIN)
    Rr["E1c"] = (Rr.cx_dev > 1) & (Rr.cx_oos > 1)
    Rr["E1"] = Rr.E1u & Rr.E1c
    Rr["plateau"] = M.plateau(Rr, ords, cats, "E1"); Rr["E2"] = Rr.plateau >= 0.6
    Rr["minx"] = Rr[["x_dev", "x_oos", "cx_dev", "cx_oos"]].min(axis=1)
    return Rr


def xrow(X, m, sb, fb):
    s = W.score(X, mult=m); x = W.xr(s, sb)
    f = B.fixed_ratio(W.rows(X, half=True, mult=m), pol())
    return dict(x_dev=x[P20], x_oos=x[P24], netr_dev=s[P20]["net"] / sb[P20]["net"], netr_oos=s[P24]["net"] / sb[P24]["net"],
                cx_dev=f[P20] / fb[P20], cx_oos=f[P24] / fb[P24], n=len(X))


_BSH = {}


def base_sh(sh):
    if sh not in _BSH:
        Xs = M.base_at(sh); ms = m32(Xs)
        _BSH[sh] = (W.score(Xs, mult=ms), B.fixed_ratio(W.rows(Xs, half=True, mult=ms), pol()))
    return _BSH[sh]


# ══ engine rules (Track 1) ═════════════════════════════════════════════════════════════════════════════════════════
def volc_task(args):
    cid, T = args
    f = CDIR / f"volc_{cid}.pkl"
    if f.exists():
        return cid, pd.read_pickle(f)
    for s in COINS:
        volc_orders_cached(s)
    tb = D.blocks_from(T)
    kicks = {s: g.entry_time.values.astype("datetime64[m]").astype(np.int64) + 1 for s, g in T.groupby("sym")}
    V = pd.concat([D.volc_coin(s, tb.get(s), kick=kicks.get(s)) for s in COINS], ignore_index=True)
    V.to_pickle(f)
    return cid, V


def hb_coin_task(args):
    """One HOLD_BIG coin, every shown setting (the coin's data loaded once)."""
    s, items = args
    out = []
    for sid, kw in items:
        try:
            out.append((sid, V33.trades33(s, 0, **kw)[W.KEEP]))
        except Exception:                                  # noqa: BLE001
            pass
    return out


def hb_cols(Rr, ids, byid):
    """HOLD_BIG (14 untouched coins, v3.1 rules without the cascade) x for the shown engine rules (shown, not gated)."""
    hb0 = S.holdbig_trades().reset_index(drop=True); s0 = W.score(hb0)
    items = [(i, byid[i].get("kw", {})) for i in ids]
    with SPAWN.Pool(PROCS) as pool:
        parts = pool.map(hb_coin_task, [(s, items) for s in R.HOLD_BIG], chunksize=1)
    res = {}
    for part in parts:
        for sid, x in part:
            res.setdefault(sid, []).append(x)
    res = {k: pd.concat(v, ignore_index=True) for k, v in res.items()}
    for i, X in res.items():
        s = W.score(X); x = W.xr(s, s0)
        Rr.loc[Rr.id == i, ["hb_x_dev", "hb_x_oos", "hb_net_oos", "hb_net_oos_base"]] = [x[P20], x[P24], s[P24]["net"], s0[P24]["net"]]
    return Rr


def eng_eval(name, specs, ords, cats, top=30, money_top=12):
    t0 = time.time()
    log(f"[{name}] {len(specs)} engine settings")
    runs = M.run_jobs(specs)
    X0 = M.base_at(0); sb, fb = base_sh(0)
    rows = []
    for sp in specs:
        X = runs[sp["id"]][0]
        rows.append(dict(id=sp["id"], **sp["p"], **xrow(X, m32(X), sb, fb)))
    Rr = gates_e1(pd.DataFrame(rows), ords, cats)
    show = list(dict.fromkeys(list(Rr[Rr.E1 & Rr.E2].sort_values("minx", ascending=False).id.head(top)) +
                              list(Rr.sort_values("minx", ascending=False).id.head(3))))
    byid = {s["id"]: s for s in specs}
    for c in ("ph_dev", "ph_oos", "phc_dev", "phc_oos", "hb_x_dev", "hb_x_oos", "hb_net_oos", "hb_net_oos_base"):
        Rr[c] = np.nan
    if show:
        log(f"[{name}] phase copies for {len(show)}")
        ph = M.run_jobs([byid[i] for i in show], shifts=M.SH)
        for i in show:
            w = []
            for sh in M.SH:
                Xs = ph[i][sh]; ms = m32(Xs); sbs, fbs = base_sh(sh)
                x = W.xr(W.score(Xs, mult=ms), sbs); f = B.fixed_ratio(W.rows(Xs, half=True, mult=ms), pol())
                w.append((x[P20] > 1, x[P24] > 1, f[P20] / fbs[P20] > 1, f[P24] / fbs[P24] > 1))
            Rr.loc[Rr.id == i, ["ph_dev", "ph_oos", "phc_dev", "phc_oos"]] = np.array(w, float).mean(axis=0)
        Rr = hb_cols(Rr, show, byid)
    Rr["E3"] = (Rr[["ph_dev", "ph_oos", "phc_dev", "phc_oos"]] >= M.PH_MIN).all(axis=1)
    ids = list(dict.fromkeys(list(Rr[Rr.E1 & Rr.E2 & Rr.E3].sort_values("minx", ascending=False).id.head(money_top)) +
                             list(Rr.sort_values("minx", ascending=False).id.head(3))))

    def items(ids_):
        for s_ in COINS:
            volc_orders_cached(s_)
        with SPAWN.Pool(PROCS) as pool:
            VV = dict(pool.map(volc_task, [(f"{name}_{i}", runs[i][0]) for i in ids_], chunksize=1))
        out = []
        for i in ids_:
            X = runs[i][0]
            out.append((i, mrows(X, m32(X), sleeve(V=VV[f"{name}_{i}"])), pol(), ref(), {}))
        return out
    Rr = finish(name, Rr, ords, cats, ids, items)
    pd.to_pickle({i: runs[i][0] for i in ids}, CDIR / f"lists_{name}.pkl")
    log(f"[{name}] done [{time.time() - t0:.0f}s]")
    return Rr


def t1a():
    setup()
    specs = []
    for T, mf, lk, X in itertools.product((48, 60, 72, 84, 96), (2.0, 2.5, 3.0, 3.5), (0.5, 0.75, 1.0, 1.25, 1.5), (99.0, 1.5, 2.0, 2.5)):
        if lk >= mf or (X < 99 and lk >= X):
            continue
        Cr = dict(T_h=T, G=60, cont=0 if X >= 99 else 1, mlo=mf, mhi=5.0, thr=X, act=3, lvl=lk)
        specs.append(dict(id=f"t1a_T{T}_m{mf}_L{lk}_X{'any' if X >= 99 else X}", p=dict(T=T, mfe=mf, lock=lk, X=X), kw=dict(ex=dict(Cr=Cr))))
    eng_eval("T1A_late_lock", specs, ["T", "mfe", "lock", "X"], [])


def t1b():
    setup()
    specs = []
    for mlo, T, (tk, tv), (ak, av), G in itertools.product((2.0, 2.5, 3.0, 3.5), (16, 24, 36, 48),
                                                            [("thr", v) for v in (0.3, 0.5, 0.75, 1.0)] + [("gb", v) for v in (0.6, 0.7, 0.8)],
                                                            [("stop", v) for v in (0.25, 0.5, 0.75)] + [("tp", v) for v in (1.0, 1.25, 1.5)], (60, 240)):
        Cr = dict(T_h=T, G=G, cont=1, mlo=mlo, mhi=5.0, thr=tv if tk == "thr" else 99.0, gb=tv if tk == "gb" else 0.0,
                  act=3 if ak == "stop" else 1, lvl=av)
        p = dict(mlo=mlo, T=T, trig=tk, thr=tv if tk == "thr" else np.nan, gb=tv if tk == "gb" else np.nan, act=ak,
                 stop_lvl=av if ak == "stop" else np.nan, tp_lvl=av if ak == "tp" else np.nan, G=G)
        specs.append(dict(id=f"t1b_m{mlo}_T{T}_{tk}{tv}_{ak}{av}_G{G}", p=p, kw=dict(ex=dict(Cr=Cr))))
    eng_eval("T1B_zone2_failed_extension", specs, ["mlo", "T", "thr", "gb", "stop_lvl", "tp_lvl"], ["trig", "act", "G"])


# ══ cut-only sizing (Track 2) ══════════════════════════════════════════════════════════════════════════════════════
_F = {}


def feats(X):
    k = id(X)
    if k not in _F:
        out = np.full((len(X), 5), np.nan)
        for s, idx in X.groupby("sym").groups.items():
            pos = X.index.get_indexer(idx); t = X.entry_time.iloc[pos]
            out[pos, :3] = R.at(s, t, ["VolReg", "Chg5", "Dir20"]).to_numpy(float)
            out[pos, 3:] = R.at("BTCUSDT", t, ["VolReg", "Dir20"]).to_numpy(float)
        _F[k] = pd.DataFrame(out, columns=["VolReg", "Chg5", "Dir20", "bVolReg", "bDir20"])
    return _F[k]


def cut_mult(p, X):
    F = feats(X); d = X.dir.to_numpy()
    with np.errstate(invalid="ignore"):
        if p["kind"] == "flatwild":
            v = F.VolReg.to_numpy() if p["src"] == "own" else F.bVolReg.to_numpy()
            dr = F.Dir20.to_numpy() if p["src"] == "own" else F.bDir20.to_numpy()
            hit = (v >= p["v"]) & (np.abs(dr) <= p["d"])
        elif p["kind"] == "q5":
            hit = (F.VolReg.to_numpy() >= p["v"]) & ((d * F.Chg5.to_numpy() >= p["b"]) if p["b"] > -50 else True)
        elif p["kind"] == "ctrshort":
            hit = (d < 0) & (F.Dir20.to_numpy() >= p["d"])
        else:
            raise ValueError(p["kind"])
    return np.where(hit, p["m"], 1.0)


def sz_eval(name, specs, ords, cats, top=30, money_top=12, null_n=200):
    """Rule multiplier r = cut_mult; the trade's size = min(v3.2's, r). Reference = v3.2 (the same list, v3.2 sizes)."""
    t0 = time.time()
    X = M.base_at(0); m0 = m32(X); sb, fb = base_sh(0)
    rows = []
    for sp in specs:
        r = cut_mult(sp["p"], X)
        rows.append(dict(id=sp["id"], **sp["p"], share=float((r < 1).mean()), **xrow(X, np.minimum(m0, r), sb, fb)))
    Rr = gates_e1(pd.DataFrame(rows), ords, cats)
    show = list(dict.fromkeys(list(Rr[Rr.E1 & Rr.E2].sort_values("minx", ascending=False).id.head(top)) +
                              list(Rr.sort_values("minx", ascending=False).id.head(3))))
    byid = {s["id"]: s for s in specs}
    for c in ("null_u", "null_c", "ph_dev", "ph_oos", "phc_dev", "phc_oos", "hb_x_dev", "hb_x_oos", "hb_net_oos", "hb_net_oos_base"):
        Rr[c] = np.nan
    hb = S.holdbig_trades().reset_index(drop=True); mh0 = m32(hb); sh0 = W.score(hb, mult=mh0)
    for i in show:
        p = byid[i]["p"]; r = cut_mult(p, X); rr = Rr[Rr.id == i].iloc[0]
        rng = np.random.default_rng(abs(hash(i)) % 2 ** 32); du, dc = [], []
        for _ in range(null_n):
            mn = np.minimum(m0, M.permute_by_coin_side(X, r, rng))
            x = W.xr(W.score(X, mult=mn), sb); du.append(min(x[P20], x[P24]))
            f = B.fixed_ratio(W.rows(X, half=True, mult=mn), pol()); dc.append(min(f[P20] / fb[P20], f[P24] / fb[P24]))
        Rr.loc[Rr.id == i, ["null_u", "null_c"]] = [float(np.mean(np.array(du) < min(rr.x_dev, rr.x_oos))),
                                                     float(np.mean(np.array(dc) < min(rr.cx_dev, rr.cx_oos)))]
        w = []
        for sh in M.SH:
            Xs = M.base_at(sh); sbs, fbs = base_sh(sh); ms = np.minimum(m32(Xs), cut_mult(p, Xs))
            x = W.xr(W.score(Xs, mult=ms), sbs); f = B.fixed_ratio(W.rows(Xs, half=True, mult=ms), pol())
            w.append((x[P20] > 1, x[P24] > 1, f[P20] / fbs[P20] > 1, f[P24] / fbs[P24] > 1))
        Rr.loc[Rr.id == i, ["ph_dev", "ph_oos", "phc_dev", "phc_oos"]] = np.array(w, float).mean(axis=0)
        sh_ = W.score(hb, mult=np.minimum(mh0, cut_mult(p, hb))); xh = W.xr(sh_, sh0)
        Rr.loc[Rr.id == i, ["hb_x_dev", "hb_x_oos", "hb_net_oos", "hb_net_oos_base"]] = [xh[P20], xh[P24], sh_[P24]["net"], sh0[P24]["net"]]
    Rr["E3"] = ((Rr.null_u >= 0.95) & (Rr.null_c >= 0.95) & (Rr[["ph_dev", "ph_oos", "phc_dev", "phc_oos"]] >= M.PH_MIN).all(axis=1))
    ids = list(dict.fromkeys(list(Rr[Rr.E1 & Rr.E2 & Rr.E3].sort_values("minx", ascending=False).id.head(money_top)) +
                             list(Rr.sort_values("minx", ascending=False).id.head(3))))
    items = lambda ids_: [(i, mrows(X, np.minimum(m0, cut_mult(byid[i]["p"], X))), pol(), ref(), {}) for i in ids_]
    Rr = finish(name, Rr, ords, cats, ids, items)
    log(f"[{name}] done [{time.time() - t0:.0f}s]")
    return Rr


def t2():
    setup()
    fw = [dict(id=f"fw_{src}_v{v}_d{d}_m{m}", p=dict(kind="flatwild", src=src, v=v, d=d, m=m))
          for src, v, d, m in itertools.product(("own", "btc"), (0.92, 0.98, 1.05), (0.75, 1.0, 1.25, 1.5), (0.25, 0.35, 0.5))]
    q5 = [dict(id=f"q5_v{v}_b{'any' if b < -50 else b}_m{m}", p=dict(kind="q5", v=v, b=b, m=m))
          for v, b, m in itertools.product((1.12, 1.18, 1.25), (-99.0, 1.25, 1.75, 2.25), (0.25, 0.35, 0.5))]
    cs = [dict(id=f"cs_d{d}_m{m}", p=dict(kind="ctrshort", d=d, m=m)) for d, m in itertools.product((0.5, 0.75, 1.0, 1.25), (0.25, 0.35, 0.5))]
    setup_base_lists()
    sz_eval("T2A_flatwild_cut", fw, ["v", "d", "m"], ["src"])
    sz_eval("T2B_q5_climax_cut", q5, ["v", "b", "m"], [])
    sz_eval("T2C_counter_macro_short_cut", cs, ["d", "m"], [])


def setup_base_lists():
    for sh in [0] + list(M.SH):                            # warm the base lists (and their features) once
        M.base_at(sh)


# ══ VOLC (Track 3a) ════════════════════════════════════════════════════════════════════════════════════════════════
EXTRA7 = list(PSL.EXTRA_COINS)


def volc_orders_cached(sym):
    key = (sym, tuple(sorted(D.VOLC_P.items())))
    if key not in D._VO:
        f = CDIR / f"volc_orders_{sym}.pkl"
        if f.exists():
            D._VO[key] = pd.read_pickle(f)
        else:
            D._VO[key] = D.volc_orders(sym); D._VO[key].to_pickle(f)
    return D._VO[key]


def volc_coin33(sym, block=None, kick=None, pa_kw=None):
    """v31deploy.volc_coin with its exit vector from W.exit31(**pa_kw) on top of the deployed one (no breakeven / locks)."""
    p = dict(D.VOLC_P)
    od = volc_orders_cached(sym)
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
    sl[inv, slot] = od.dist.to_numpy(float); exp[inv, slot] = D.TF
    tp[inv, slot] = od.tp_R.to_numpy(float) * od.dist.to_numpy(float)
    ones, zeros = np.ones(n, np.bool_), np.zeros(n, np.bool_)
    free = ~D._mask(t, block) if block is not None and len(block) else ones
    xk = zeros.copy()
    if kick is not None and len(kick):
        q = np.searchsorted(t, np.asarray(kick, np.int64)); xk[q[q < n]] = True
    pa = W.exit31(**dict(dict(be_R=0.0, lock_R=0.0, lock_to=0.0, lock2_R=0.0, lock2_to=0.0, stale_h=0), **(pa_kw or {})))
    hold = int(p["hold_h"] * 60)
    res = X31.sim31(t, m["o"], m["h"], m["l"], m["c"], optr, kind, dirn, price, sl, tp, exp, ones, ones, zeros, xk, xk,
                    np.zeros(n), hold, hold, pa, pa, free, free, zeros, zeros, 0.0, 0, -0.5, 0, 0.0, np.zeros(n), ones)
    e_idx, x_idx, dirs, e_px, x_px, dist, reason, *_ = res
    tr = pd.DataFrame({"entry_time": C.D.to_datetime(t[e_idx]), "exit_time": C.D.to_datetime(t[x_idx]), "dir": dirs, "entry": e_px,
                       "exit": x_px, "sl_dist": dist, "reason": [C.E.REASONS[r] for r in reason]})
    tpm = tr.reason.to_numpy() == "TP"
    tr.loc[tpm, "exit"] = tr.entry[tpm] + tr.dir[tpm] * (float(p["tp_R"]) * tr.sl_dist[tpm] - D.TP_PAD * tr.entry[tpm])
    fee = C.TAKER + D.SLIP.get(sym, 0.0003)
    f_out = np.where(tpm, C.MAKER, fee)
    hours = (tr.exit_time - tr.entry_time).dt.total_seconds() / 3600
    tr["R"] = ((tr.exit - tr.entry) * tr.dir - fee * tr.entry - f_out * tr.exit - C.FUNDING_8H * hours / 8 * tr.entry) / tr.sl_dist
    tr["hours"] = hours; tr["sym"] = sym
    return tr[(tr.reason != "END")].reset_index(drop=True)


_TB = {}


def tbo_blocks():
    if "b" not in _TB:
        T = M.base_at(0)
        _TB["b"] = (D.blocks_from(T), {s: g.entry_time.values.astype("datetime64[m]").astype(np.int64) + 1 for s, g in T.groupby("sym")})
    return _TB["b"]


def volc_cfg_task(args):
    """One VOLC exit setting: core-5 trades (around v3.2's TBO list) and the 7 extra coins (no trend bot there)."""
    cid, pa_kw = args
    tb, kk = tbo_blocks()
    core = pd.concat([volc_coin33(s, tb.get(s), kk.get(s), pa_kw) for s in COINS], ignore_index=True)
    ext = pd.concat([volc_coin33(s, None, None, pa_kw) for s in EXTRA7], ignore_index=True)
    return cid, core, ext


def stream_score(df, tcol="exit_time", rcol="R"):
    """Per period: n, net R, max drawdown of cumulative R (ordered by exit), ratio."""
    out = {}
    for per, (a, b) in ((P22, ("2022-01-01", "2024-01-01")), (P24, ("2024-01-01", W.END))):
        x = df[(df[tcol] >= a) & (df[tcol] < b)].sort_values(tcol)
        r = x[rcol].to_numpy(float); cum = np.r_[0.0, np.cumsum(r)]; dd = float(np.max(np.maximum.accumulate(cum) - cum))
        out[per] = dict(n=len(x), net=float(r.sum()), dd=dd, ratio=float(r.sum()) / dd if dd > 0 else np.nan)
    return out


def month_boot(base_df, rule_df, n=200, rcol="R", tcol="exit_time", seed=0):
    """Share of paired month-block bootstraps (months drawn with replacement within each period) with x > 1 in both periods."""
    rng = np.random.default_rng(seed); wins = 0
    mb = base_df.assign(_m=base_df[tcol].dt.to_period("M")); mr = rule_df.assign(_m=rule_df[tcol].dt.to_period("M"))
    per = {P22: ("2022-01-01", "2024-01-01"), P24: ("2024-01-01", W.END)}
    gb = {k: v[rcol].to_numpy(float) for k, v in mb.groupby("_m")}; gr = {k: v[rcol].to_numpy(float) for k, v in mr.groupby("_m")}
    months = {p: pd.period_range(a, pd.Timestamp(b) - pd.Timedelta(days=1), freq="M") for p, (a, b) in per.items()}

    def ratio(seq):
        cum = np.r_[0.0, np.cumsum(seq)]; dd = np.max(np.maximum.accumulate(cum) - cum)
        return cum[-1] / dd if dd > 0 else (np.inf if cum[-1] > 0 else 0.0)
    for _ in range(n):
        ok = True
        for p, ms in months.items():
            pick = ms[rng.integers(0, len(ms), len(ms))]
            rb = ratio(np.concatenate([gb.get(m, np.zeros(0)) for m in pick] + [np.zeros(0)]))
            rr = ratio(np.concatenate([gr.get(m, np.zeros(0)) for m in pick] + [np.zeros(0)]))
            ok &= (rr > rb) if np.isfinite(rb) else (rr >= rb)
        wins += ok
    return wins / n


def sleeve_eval(name, specs, ords, cats, build, base_key, money_rows_fn, extra=None, money_top=12):
    """build(specs) -> {id: stream df}; base stream = build of the deployed setting (base_key). extra: {id: (x_dev, x_oos)}
    out-of-universe check (VOLC)."""
    t0 = time.time()
    streams = build(specs)
    b = streams[base_key]; sb = stream_score(b)
    rows = []
    for sp in specs:
        if sp["id"] == base_key:
            continue
        s = stream_score(streams[sp["id"]])
        rows.append(dict(id=sp["id"], **sp["p"], x_dev=s[P22]["ratio"] / sb[P22]["ratio"], x_oos=s[P24]["ratio"] / sb[P24]["ratio"],
                         netr_dev=s[P22]["net"] / sb[P22]["net"], netr_oos=s[P24]["net"] / sb[P24]["net"],
                         n_dev=s[P22]["n"], n_oos=s[P24]["n"], net_dev=s[P22]["net"], net_oos=s[P24]["net"], dd_dev=s[P22]["dd"], dd_oos=s[P24]["dd"]))
    Rr = pd.DataFrame(rows)
    Rr["E1"] = (Rr.x_dev > 1) & (Rr.x_oos > 1) & (Rr.netr_dev >= M.NET_MIN) & (Rr.netr_oos >= M.NET_MIN)
    Rr["plateau"] = M.plateau(Rr, ords, cats, "E1"); Rr["E2"] = Rr.plateau >= 0.6
    Rr["minx"] = Rr[["x_dev", "x_oos"]].min(axis=1)
    show = list(dict.fromkeys(list(Rr[Rr.E1 & Rr.E2].sort_values("minx", ascending=False).id.head(30)) +
                              list(Rr.sort_values("minx", ascending=False).id.head(3))))
    Rr["boot"] = np.nan
    for i in show:
        Rr.loc[Rr.id == i, "boot"] = month_boot(b, streams[i], seed=abs(hash(i)) % 2 ** 31)
    Rr["E3"] = Rr.boot >= 0.75
    if extra is not None:
        Rr["out_x_dev"] = Rr.id.map(lambda i: extra.get(i, (np.nan, np.nan))[0]); Rr["out_x_oos"] = Rr.id.map(lambda i: extra.get(i, (np.nan, np.nan))[1])
        Rr["E3"] &= (Rr.out_x_dev > 1) & (Rr.out_x_oos > 1)
    ids = list(dict.fromkeys(list(Rr[Rr.E1 & Rr.E2 & Rr.E3].sort_values("minx", ascending=False).id.head(money_top)) +
                             list(Rr.sort_values("minx", ascending=False).id.head(3))))
    X = M.base_at(0); m0 = m32(X)
    items = lambda ids_: [(i, W.with_sleeve(W.rows(X, half=True, mult=m0), money_rows_fn(streams[i])), pol(), ref(), {}) for i in ids_]
    Rr = finish(name, Rr, ords, cats, ids, items)
    pd.to_pickle({i: streams[i] for i in ids}, CDIR / f"streams_{name}.pkl")
    log(f"[{name}] base stream: " + ", ".join(f"{p} n {v['n']} net {v['net']:.1f}R dd {v['dd']:.1f}R" for p, v in sb.items()) + f" [{time.time() - t0:.0f}s]")
    return Rr


def t3v():
    setup()
    for s in COINS + EXTRA7:                                 # VOLC orders once (the slow part), then every exit setting
        volc_orders_cached(s)
    specs = [dict(id="volc_base", p={}, pa={})]
    for T, mf, thr, act in itertools.product((4, 6, 8, 12), (0.4, 0.6, 0.8), (0.0, -0.15, -0.25), ("stop-0.35", "stop-0.5", "close")):
        A = dict(T_h=T, G=60, cont=1, mlo=mf, mhi=1.5, thr=thr, **({"act": 2} if act == "close" else {"act": 3, "lvl": float(act[4:])}))
        specs.append(dict(id=f"vfb_T{T}_m{mf}_thr{thr}_{act}", p=dict(rule="fb", T=T, mfe=mf, thr=thr, act=act, X=np.nan, Y=np.nan), pa=dict(A=A)))
    for X_, Y_ in itertools.product((0.85, 1.0, 1.15), (-0.2, 0.0, 0.25)):
        specs.append(dict(id=f"vlock_X{X_}_Y{Y_}", p=dict(rule="lock", T=np.nan, mfe=np.nan, thr=np.nan, act="lock", X=X_, Y=Y_),
                          pa=dict(lock_R=X_, lock_to=Y_)))
    with Pool(PROCS) as pool:
        res = pool.map(volc_cfg_task, [(s["id"], s["pa"]) for s in specs], chunksize=1)
    core = {i: c for i, c, e in res}; ext = {i: e for i, c, e in res}
    V32 = pd.read_pickle(C.D.CACHE / "volc_trades_v32.pkl")
    k = lambda Z: sorted(zip(Z.sym, Z.entry_time, Z.exit_time, Z.R.round(9)))
    log(f"[T3v] VOLC base rebuilt here = volc_trades_v32: {k(core['volc_base']) == k(V32)} ({len(core['volc_base'])} trades)")
    se = stream_score(ext["volc_base"])
    extra = {}
    for i, e in ext.items():
        s = stream_score(e)
        extra[i] = (s[P22]["ratio"] / se[P22]["ratio"], s[P24]["ratio"] / se[P24]["ratio"])
    log("[T3v] VOLC on the 7 extra coins (base): " + ", ".join(f"{p} n {v['n']} net {v['net']:.1f}R dd {v['dd']:.1f}R" for p, v in se.items()))
    for nm, sub, ords in (("T3VA_volc_failed_breakout", [s for s in specs if s["id"].startswith(("volc_base", "vfb"))], ["T", "mfe", "thr"]),
                          ("T3VB_volc_lock", [s for s in specs if s["id"].startswith(("volc_base", "vlock"))], ["X", "Y"])):
        sleeve_eval(nm, sub, ords, ["act"] if nm.startswith("T3VA") else [], lambda sp, core=core: {s["id"]: core[s["id"]] for s in sp}, "volc_base",
                    lambda V: np.r_[_SL["panic"], volc_rows(V)], extra=extra)


# ══ panic (Track 3b) ═══════════════════════════════════════════════════════════════════════════════════════════════
def candidates33(sym, fb=None, **kw):
    """panic_sleeve.candidates + fb = dict(T, X, y, z): at the open of hour T after the entry (the T-th hourly close known),
    if the trade has been +X ATR (never the breakeven +be_atr) and that close is below -y ATR: stop to -z ATR (a stop
    already past: closed at that open)."""
    p = dict(PSL.P0, **kw); rows = []
    df = PSL.hourly(sym); o, h, l, c = (df[k].values for k in "ohlc")
    f = PSL.PS.features(h, l, c, df.oi.values, df.prem.values, p["window_h"])
    sig = PSL.PS.signal(f, **p); a_ = f["atr"]; H = int(p["hold_h"])
    cost = 2 * (PSL.TAKER + PSL.SLIP.get(sym, 0.0003)); Lw = int(p["window_h"])
    for i in np.flatnonzero(sig):
        if i + H + 2 >= len(o):
            continue
        e = o[i + 1]; a = a_[i]; st = max(e - p["stop_atr"] * a, e * (1 - p["stop_max"])); tg = e + p["tp_atr"] * a if p["tp_atr"] > 0 else np.inf; best = e
        px, j, why = o[i + 1 + H], i + 1 + H, "time"
        for jj in range(i + 1, i + 1 + H):
            if fb is not None and jj == i + 1 + fb["T"] and best < e + p["be_atr"] * a and best >= e + fb["X"] * a and c[jj - 1] < e - fb["y"] * a:
                st = max(st, e - fb["z"] * a)
                if o[jj] <= st:
                    px, j, why = o[jj], jj, "fb"; break
            if l[jj] <= st:
                px, j, why = st, jj, ("stop" if st < e else "breakeven"); break
            if h[jj] >= tg:
                px, j, why = tg, jj, "take profit"; break
            best = max(best, h[jj])
            if p["be_atr"] > 0 and best >= e + p["be_atr"] * a:
                st = max(st, e)
        rows.append((i, j, df.index[i + 1], df.index[j], sym, e, px, a, px / e - 1 - cost, why, c[i] / c[i - Lw] - 1, f["rz"][i], f["doi"][i], f["pz"][i]))
    return pd.DataFrame(rows, columns=["i", "j", "t", "t_exit", "sym", "entry", "exit", "atr", "ret", "why", "move", "rz", "doi", "pz"])


def events33(fb=None, rep=None, start="2022-01-01", end="2026-11-07"):
    """panic_sleeve.events (core + extra pools, max 2 extra open) with candidates33; rep = dict(H, act): after a trade on a coin
    stopped out ('stop' / 'fb' below the entry), that coin's entries within H hours of the exit are blocked ('block') or at
    half size ('half')."""
    coins, extra_coins = PSL.COINS, PSL.EXTRA_COINS
    cd = pd.concat([candidates33(s, fb) for s in list(coins) + list(extra_coins)], ignore_index=True)
    xs = set(extra_coins); busy = {}; open_x = []; out = []; last_loss = {}
    for t, g in cd.sort_values(["t", "sym"]).groupby("t", sort=True):
        open_x = [x for x in open_x if x >= t]
        g = g[[r.i > busy.get(r.sym, -1) for r in g.itertuples()]]
        half = set()
        if rep is not None:
            hot = [r.sym for r in g.itertuples() if r.sym in last_loss and t <= last_loss[r.sym] + pd.Timedelta(hours=rep["H"])]
            if rep["act"] == "block":
                g = g[~g.sym.isin(hot)]
            else:
                half = set(hot)
        if g.empty:
            continue
        core, ext = g[~g.sym.isin(xs)], g[g.sym.isin(xs)]
        if len(ext) and PSL.MAX_EXTRA_OPEN is not None:
            free = PSL.MAX_EXTRA_OPEN - len(open_x)
            ext = ext.iloc[0:0] if free <= 0 else ext.assign(_s=-(ext.doi.abs() * ext.pz.abs())).sort_values("_s", kind="stable").head(free).drop(columns="_s")
        for part, share, pool in ((core, 1.0, "core"), (ext, PSL.EXTRA_SHARE, "extra")):
            if part.empty:
                continue
            for r in part.itertuples():
                busy[r.sym] = r.j
                if pool == "extra":
                    open_x.append(r.t_exit)
                if r.why in ("stop", "fb") and r.exit < r.entry:
                    last_loss[r.sym] = r.t_exit
            w = (share / len(part)) * np.where(part.sym.isin(half), 0.5, 1.0)
            out.append(part.assign(n=len(part), w=w, pool=pool))
    ev = pd.concat(out, ignore_index=True).drop(columns=["i", "j"])
    return ev[(ev.t >= start) & (ev.t < end)].sort_values(["t", "sym"]).reset_index(drop=True)


def panic_stream(ev):
    return pd.DataFrame({"exit_time": ev.t_exit.values, "R": ev.ret.values / 0.05 * ev.w.values, "sym": ev.sym.values})


def panic_task(args):
    cid, fb, rep = args
    return cid, events33(fb, rep)


def t3p():
    setup()
    specs = [dict(id="panic_base", p={}, fb=None, rep=None)]
    for T, X_, y, z in itertools.product((3, 4, 6), (0.75, 1.0, 1.25), (0.5, 1.0), (1.5, 2.0)):
        specs.append(dict(id=f"pfb_T{T}_X{X_}_y{y}_z{z}", p=dict(rule="fb", T=T, X=X_, y=y, z=z, H=np.nan, act="fb"), fb=dict(T=T, X=X_, y=y, z=z), rep=None))
    for H, act in itertools.product((6, 12, 24, 48), ("block", "half")):
        specs.append(dict(id=f"prep_H{H}_{act}", p=dict(rule="rep", T=np.nan, X=np.nan, y=np.nan, z=np.nan, H=H, act=act), fb=None, rep=dict(H=H, act=act)))
    with Pool(PROCS) as pool:
        evs = dict(pool.map(panic_task, [(s["id"], s["fb"], s["rep"]) for s in specs], chunksize=1))
    base_rows = PSL.sleeve_rows(evs["panic_base"])
    pr = _SL["panic"]
    log(f"[T3p] panic base rebuilt here = the money rows' panic sleeve: {len(base_rows)} vs {len(pr)} trades, "
        f"same entries {np.array_equal(np.sort(base_rows[:, 0]), np.sort(pr[:, 0]))}, max |R diff| "
        f"{np.max(np.abs(np.sort(base_rows[:, 4]) - np.sort(pr[:, 4]))) if len(base_rows) == len(pr) else np.nan:.2e}")
    streams = {i: panic_stream(e) for i, e in evs.items()}
    rowfn = {i: PSL.sleeve_rows(e) for i, e in evs.items()}
    inv = {id(v): k for k, v in streams.items()}
    for nm, sub, ords, cats in (("T3PA_panic_failed_bounce", [s for s in specs if s["id"].startswith(("panic_base", "pfb"))], ["T", "X", "y", "z"], []),
                                ("T3PB_panic_repeat_flush", [s for s in specs if s["id"].startswith(("panic_base", "prep"))], ["H"], ["act"])):
        sleeve_eval(nm, sub, ords, cats, lambda sp: {s["id"]: streams[s["id"]] for s in sp}, "panic_base",
                    lambda st: np.r_[W.pad_sleeve(rowfn[inv[id(st)]], 7), volc_rows(_SL["volc"])])


# ══ FINAL ══════════════════════════════════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    {"base": base, "t1a": t1a, "t1b": t1b, "t2": t2, "t3v": t3v, "t3p": t3p}.get(sys.argv[1], lambda: None)()


def final():
    """v3.2 vs the Track 1B passers: full table (v32c money_full: 2022 / 2024, Sep-Nov 2026 from $300 and inside the 2024
    run, Oct-Nov 2026, P(>= $10k in 2 y), bootstrap)."""
    setup()
    import v32c_exact_engine_and_ladder as V32C
    X0 = M.base_at(0)
    lists = pd.read_pickle(CDIR / "lists_T1B_zone2_failed_extension.pkl")
    Rr = pd.read_csv(RES / "v33_T1B_zone2_failed_extension.csv")
    P = Rr[Rr.PASS].sort_values("minx", ascending=False).head(3)
    items = [("v3.2 deployed", mrows(X0, m32(X0)), pol())]
    for i in P.id:
        X = lists[i]; V = pd.read_pickle(CDIR / f"volc_T1B_zone2_failed_extension_{i}.pkl")
        items.append((f"v3.2 + {i}", mrows(X, m32(X), sleeve(V=V)), pol()))
    with SPAWN.Pool(PROCS) as pool:
        res = pool.map(_final_job, items, chunksize=1)
    T = pd.DataFrame(res)
    T.to_csv(RES / "v33_final_comparison.csv", index=False)
    fm = {c: "{:.0f}".format for c in T if c.startswith(("m_", "boot_med", "boot_p10", "bal_"))}
    fm.update({c: "{:.3f}".format for c in T if c.startswith("dd") or c == "boot_dd90"})
    print(T.to_string(index=False, formatters=fm), flush=True)


def _final_job(a):
    import v32c_exact_engine_and_ladder as V32C
    nm, A, p = a
    return dict(name=nm, **V32C.money_full(A, p))


if __name__ == "__main__" and sys.argv[1] == "final":
    final()
