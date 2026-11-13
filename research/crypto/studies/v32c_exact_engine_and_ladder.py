"""v3.2c (Nov 2026): the v3.2b candidates re-tested exactly, and the ladder's first tier. Read-only on cryptobot/.

STAGE 1  the wild x 5-day-pullback skip INSIDE the 1-minute engine. v32lib.trades32(ofilt=...) drops the entry orders the
         live bot would not arm: at each order's own 4h arming close (by side), coin VolReg (ATR14 / ATR100 of the last
         daily close) >= vr AND dir x Chg5 (5-day close change / ATR14) <= c. Everything downstream is re-run: the coin's
         later orders (re-entries), cooldowns, BTC first -> the cascade on ETH / alts, then VOLC around the new TBO list
         (v31deploy.volc_coin: blocks and hand-overs). All 41 phase copies. Grid vr {0.98, 1.05, 1.12} x c {0, -0.25, -0.5}.
         Side by side: the v32b frozen-list skip (m = 0 on the v3.1 list) and non-skip size-downs (m 0.25 / 0.35 / 0.5:
         the trade is taken, so the engine path is v3.1's exactly), both cap counts. HOLD_BIG (14 untouched coins).
STAGE 2  smooth piecewise-linear VolReg sizing (w_calm at <= v_lo -> 1 at v_mid -> w_wild at >= v_hi), live and base cap,
         on v3.1 and on the stage-1 engine list; the T1 q_lo = 0.75 sub-grid; the 0.79 cliff traced to its trades.
STAGE 3  the ladder: tier 0 (< $1,000) at the tier-1 risk, k 0.90 / 0.95 / 1.00, for the candidates.

Gates as v3.2b (E1 uncapped AND capped account; E2 plateau 60%; E3 phase copies 75% uncapped and capped, + 200 nulls 95%
for sizing rules; E4 money from $300 vs the reference). Engine rules: E3 = phase copies (as the v3.1 protocol).

    python v32c_exact_engine_and_ladder.py s1 | s2 | s3          (results/v32c_*.csv)"""
import itertools, json, os, sys, time
from multiprocessing import Pool
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v31")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import common as C, v29lib as L, v30lib as V0, v31lib as W, v32lib as V32
import crypto_regimes as R
import v31_drawdown_and_sleeves as M
import v32_market_regimes_and_alpha as S
import v32b_cap_fix_and_wild_regime as B
import v31deploy as D

RES = M.RES
P20, P24 = M.P20, M.P24
PROCS = int(os.environ.get("V31_PROCS", 5))
CDIR = Path(os.path.expanduser(os.environ.get("TRADING_CACHE", "~/.cache/tbo"))) / "v32c"
log = M.log
COINS = W.COINS
GRID1 = [(vr, c) for vr in (0.98, 1.05, 1.12) for c in (0.0, -0.25, -0.5)]
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 400)


def cfg_id(cfg):
    return "v31" if cfg is None else f"eng_vr{cfg[0]}_c{cfg[1]}"


# ══ the engine skip ════════════════════════════════════════════════════════════════════════════════════════════════
def ofilt_for(sym, vr, c):
    def f(o, t, shift):
        rows = np.flatnonzero(o["optr"] >= 0)
        tm = t[rows]
        arm = tm - ((tm + shift) % 240)                              # the order's own 4h arming close (real minutes)
        F = R.at(sym, C.D.to_datetime(arm), ["VolReg", "Chg5"]).to_numpy(float)
        k = o["kind"].copy(); oi = o["optr"][rows]
        for col in range(k.shape[1]):
            d = o["direction"][oi, col].astype(float)
            hit = (F[:, 0] >= vr) & (d * F[:, 1] <= c) & (k[oi, col] != 0)
            k[oi[hit], col] = 0
        o["kind"] = k
        return o
    return f


def _clear():
    L._M.clear(); W._ORD.clear(); W._FA.clear()


def eng_task(sh):
    """All configs at one phase shift (coin-major: BTC first for the cascade)."""
    f = CDIR / f"eng_s{sh}.pkl"
    if f.exists():
        return sh
    out = {cfg_id(c): [] for c in [None] + GRID1}; btc = {}
    for s in COINS:
        _clear()
        for cfg in [None] + GRID1:
            of = ofilt_for(s, *cfg) if cfg else None
            x = V32.trades32(s, sh, btc=btc.get(cfg_id(cfg)), ofilt=of)
            if s == "BTCUSDT":
                btc[cfg_id(cfg)] = x
            out[cfg_id(cfg)].append(x[[c for c in W.KEEP if c in x]])
    _clear()
    pd.to_pickle({k: pd.concat(v, ignore_index=True) for k, v in out.items()}, f)
    return sh


def holdbig_task(s):
    out = {}
    try:
        for cfg in [None] + GRID1:
            x = V32.trades32(s, 0, ofilt=ofilt_for(s, *cfg) if cfg else None)
            out[cfg_id(cfg)] = x[[c for c in W.KEEP if c in x]]
    except Exception as e:                                         # noqa: BLE001
        return s, None, str(e)
    finally:
        _clear()
    return s, out, ""


def volc_task(args):
    cid, T = args
    f = CDIR / f"volc_{cid}.pkl"
    if f.exists():
        return cid, pd.read_pickle(f)
    tb = D.blocks_from(T)
    kicks = {s: g.entry_time.values.astype("datetime64[m]").astype(np.int64) + 1 for s, g in T.groupby("sym")}
    V = pd.concat([D.volc_coin(s, tb.get(s), kick=kicks.get(s)) for s in COINS], ignore_index=True)
    V.to_pickle(f)
    return cid, V


_E = {}


def eng(sh, cid):
    if sh not in _E:
        _E.clear(); _E[sh] = pd.read_pickle(CDIR / f"eng_s{sh}.pkl")
    return _E[sh][cid]


_ENGX = {}


def eng_list(cid, sh):
    """Engine trades of a config at a shift (cached per (cid, sh): stage 2 phase loops reuse them)."""
    k = (cid, sh)
    if k not in _ENGX:
        _ENGX[k] = eng(sh, cid)
    return _ENGX[k]


# ══ money helpers ══════════════════════════════════════════════════════════════════════════════════════════════════
_PANIC = {}


def panic_rows():
    if "p" not in _PANIC:
        full = W.sleeve30(); n = len(pd.read_pickle(C.D.CACHE / "volc_trades_v31.pkl"))
        p = full[:-n]; assert (p[:, 5] == 5).all()
        _PANIC["p"] = p
    return _PANIC["p"]


def sleeve(V):
    m = lambda c: V[c].values.astype("datetime64[m]").astype(np.int64)
    VR = np.c_[m("entry_time"), m("exit_time"), m("entry_time"), V.dir.to_numpy(float), V.R.to_numpy(float), np.full(len(V), 6.0), np.ones(len(V))]
    return np.r_[panic_rows(), VR]


def mrows(X, Sl, mult=None):
    return W.with_sleeve(W.rows(X, half=True, mult=mult), Sl)


def ladder(p, flat=False, k=0.95):
    """Policy at v3.0 ladder x k (portfolio.json = x 0.95); flat: tier 0 (< $1,000) at tier 1's risk and cap."""
    p = dict(p, mult=p.get("mult", 1.0) * k / 0.95)
    if flat:
        rows = list(p["rows"]); rows[0] = (rows[0][0], list(rows[1][1]), rows[1][2]); p["rows"] = rows
    return p


# ══ generic sizing / list evaluator ════════════════════════════════════════════════════════════════════════════════
def evalz(name, specs, ords, cats, mfn, getX, Sl, cap, ref, top=30, money_top=15, null_n=200):
    """Sizing rules mfn(p, X) on the trade lists getX(shift) (reference = the same lists unscaled; money with sleeve Sl)."""
    t0 = time.time()
    p_ = B.pol(cap); X = getX(0)
    sb = W.score(X); fb = B.fixed_ratio(W.rows(X, half=True), p_)
    rows = []
    for sp in specs:
        m = mfn(sp["p"], X)
        s = W.score(X, mult=m); x = W.xr(s, sb)
        f = B.fixed_ratio(W.rows(X, half=True, mult=m), p_)
        rows.append(dict(id=sp["id"], **sp["p"], x_dev=x[P20], x_oos=x[P24], netr_dev=s[P20]["net"] / sb[P20]["net"],
                         netr_oos=s[P24]["net"] / sb[P24]["net"], cx_dev=f[P20] / fb[P20], cx_oos=f[P24] / fb[P24],
                         share_scaled=float((m != 1.0).mean())))
    Rr = pd.DataFrame(rows)
    Rr["E1u"] = (Rr.x_dev > 1) & (Rr.x_oos > 1) & (Rr.netr_dev >= M.NET_MIN) & (Rr.netr_oos >= M.NET_MIN)
    Rr["E1c"] = (Rr.cx_dev > 1) & (Rr.cx_oos > 1); Rr["E1"] = Rr.E1u & Rr.E1c
    Rr["plateau"] = M.plateau(Rr, ords, cats, "E1"); Rr["E2"] = Rr.plateau >= 0.6
    Rr["minx"] = Rr[["x_dev", "x_oos", "cx_dev", "cx_oos"]].min(axis=1)
    show = list(dict.fromkeys(list(Rr[Rr.E1 & Rr.E2].sort_values("minx", ascending=False).id.head(top)) +
                              list(Rr.sort_values("minx", ascending=False).id.head(3))))
    byid = {s["id"]: s for s in specs}
    for c in ("null_u", "null_c", "ph_dev", "ph_oos", "phc_dev", "phc_oos"):
        Rr[c] = np.nan
    bsh = {}
    for i in show:
        p = byid[i]["p"]; m = mfn(p, X); r = Rr[Rr.id == i].iloc[0]
        rng = np.random.default_rng(abs(hash(i)) % 2 ** 32); du, dc = [], []
        for _ in range(null_n):
            mn = M.permute_by_coin_side(X, m, rng)
            x = W.xr(W.score(X, mult=mn), sb); du.append(min(x[P20], x[P24]))
            f = B.fixed_ratio(W.rows(X, half=True, mult=mn), p_); dc.append(min(f[P20] / fb[P20], f[P24] / fb[P24]))
        Rr.loc[Rr.id == i, ["null_u", "null_c"]] = [float(np.mean(np.array(du) < min(r.x_dev, r.x_oos))),
                                                     float(np.mean(np.array(dc) < min(r.cx_dev, r.cx_oos)))]
        w = []
        for sh in M.SH:
            Xs = getX(sh)
            if sh not in bsh:
                bsh[sh] = (W.score(Xs), B.fixed_ratio(W.rows(Xs, half=True), p_))
            sbs, fbs = bsh[sh]; ms = mfn(p, Xs)
            x = W.xr(W.score(Xs, mult=ms), sbs); f = B.fixed_ratio(W.rows(Xs, half=True, mult=ms), p_)
            w.append((x[P20] > 1, x[P24] > 1, f[P20] / fbs[P20] > 1, f[P24] / fbs[P24] > 1))
        Rr.loc[Rr.id == i, ["ph_dev", "ph_oos", "phc_dev", "phc_oos"]] = np.array(w, float).mean(axis=0)
    Rr["E3"] = ((Rr.null_u >= 0.95) & (Rr.null_c >= 0.95) & (Rr.ph_dev >= M.PH_MIN) & (Rr.ph_oos >= M.PH_MIN) &
                (Rr.phc_dev >= M.PH_MIN) & (Rr.phc_oos >= M.PH_MIN))
    ids = list(dict.fromkeys(list(Rr[Rr.E1 & Rr.E2 & Rr.E3].sort_values("minx", ascending=False).id.head(money_top)) +
                             list(Rr.sort_values("minx", ascending=False).id.head(3))))
    Mo = B.g6_pool([(i, mrows(X, Sl, mfn(byid[i]["p"], X)), p_, ref, {}) for i in ids])
    Rr = B.attach_money(Rr, Mo, ref)
    Rr.to_csv(RES / f"v32c_{name}.csv", index=False)
    log(f"[{name}] {len(Rr)} -> E1u {int(Rr.E1u.sum())}, E1c {int(Rr.E1c.sum())}, E1 {int(Rr.E1.sum())} -> +E2 {int((Rr.E1 & Rr.E2).sum())} -> "
        f"+E3 {int((Rr.E1 & Rr.E2 & Rr.E3).sum())} -> PASS {int(Rr.PASS.sum())} (G6 {int(Rr.PASS_dd_matched.sum())})  [{time.time() - t0:.0f}s]")
    B.show_table(Rr, ords + cats, n=12)
    return Rr


# ══ STAGE 1 ════════════════════════════════════════════════════════════════════════════════════════════════════════
def s1():
    B.setup(); CDIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with Pool(PROCS) as pool:
        pool.map(eng_task, [0] + list(M.SH), chunksize=1)
    log(f"[S1] engine: {len(GRID1)} configs + base x {len(M.SH)} shifts  [{time.time() - t0:.0f}s]")
    # parity: the engine base = the v3.1 package at every shift
    k = lambda Z: sorted(zip(Z.sym, Z.entry_time, Z.exit_time, Z.R.round(9)))
    bad = [sh for sh in [0] + list(M.SH) if k(eng(sh, "v31")) != k(M.base_at(sh))]
    log(f"[S1] parity of the engine base with the v3.1 package: {len(M.SH) + 1 - len(bad)}/{len(M.SH) + 1} shifts identical {bad[:5]}")
    # VOLC around each config's TBO list
    T0 = {cfg_id(c): eng(0, cfg_id(c)) for c in [None] + GRID1}
    with Pool(PROCS) as pool:
        VV = dict(pool.map(volc_task, list(T0.items()), chunksize=1))
    k0 = lambda Z: sorted(zip(Z.sym, Z.entry_time, Z.exit_time, Z.R.round(9)))
    log(f"[S1] VOLC rebuilt around the base = volc_trades_v31: {k0(VV['v31']) == k0(pd.read_pickle(C.D.CACHE / 'volc_trades_v31.pkl'))}")
    # gates
    p_ = B.pol("live"); X0 = T0["v31"]; sb = W.score(X0); fb = B.fixed_ratio(W.rows(X0, half=True), p_)
    kk = lambda Z: set(zip(Z.sym, Z.entry_time, Z.dir))
    rows = []
    for cfg in GRID1:
        cid = cfg_id(cfg); X = T0[cid]
        s = W.score(X); x = W.xr(s, sb); f = B.fixed_ratio(W.rows(X, half=True), p_)
        kx, k0_ = kk(X), kk(X0)
        gone = X0[[z not in kx for z in zip(X0.sym, X0.entry_time, X0.dir)]]
        new = X[[z not in k0_ for z in zip(X.sym, X.entry_time, X.dir)]]
        w = []
        for sh in M.SH:
            Xs, Bs = eng(sh, cid), eng(sh, "v31")
            xs = W.xr(W.score(Xs), W.score(Bs)); fs, fbs = B.fixed_ratio(W.rows(Xs, half=True), p_), B.fixed_ratio(W.rows(Bs, half=True), p_)
            w.append((xs[P20] > 1, xs[P24] > 1, fs[P20] / fbs[P20] > 1, fs[P24] / fbs[P24] > 1))
        w = np.array(w, float).mean(axis=0)
        V = VV[cid]
        rows.append(dict(id=cid, vr=cfg[0], c=cfg[1], n=len(X), n_removed=len(gone), R_removed=gone.R.sum(), n_new=len(new), R_new=new.R.sum(),
                         netR=X.R.sum(), netR_v31=X0.R.sum(), volc_n=len(V), volc_R=V.R.sum(),
                         x_dev=x[P20], x_oos=x[P24], netr_dev=s[P20]["net"] / sb[P20]["net"], netr_oos=s[P24]["net"] / sb[P24]["net"],
                         cx_dev=f[P20] / fb[P20], cx_oos=f[P24] / fb[P24], ph_dev=w[0], ph_oos=w[1], phc_dev=w[2], phc_oos=w[3]))
    Rr = pd.DataFrame(rows)
    Rr["E1u"] = (Rr.x_dev > 1) & (Rr.x_oos > 1) & (Rr.netr_dev >= M.NET_MIN) & (Rr.netr_oos >= M.NET_MIN)
    Rr["E1c"] = (Rr.cx_dev > 1) & (Rr.cx_oos > 1); Rr["E1"] = Rr.E1u & Rr.E1c
    Rr["plateau"] = M.plateau(Rr, ["vr", "c"], [], "E1"); Rr["E2"] = Rr.plateau >= 0.6
    Rr["E3"] = (Rr[["ph_dev", "ph_oos", "phc_dev", "phc_oos"]] >= M.PH_MIN).all(axis=1)
    Rr["minx"] = Rr[["x_dev", "x_oos", "cx_dev", "cx_oos"]].min(axis=1)
    Sl0 = sleeve(VV["v31"])
    Mo = B.g6_pool([(cfg_id(c), mrows(T0[cfg_id(c)], sleeve(VV[cfg_id(c)])), p_, M.money_base(), {}) for c in GRID1])
    Rr = B.attach_money(Rr, Mo, M.money_base())
    # the v32b frozen-list skip, money on the same sleeve (VOLC unchanged), for the side-by-side
    Mf = B.g6_pool([(f"frozen_{cfg_id(c)}", mrows(X0, Sl0, B.pullback(dict(kind="pull", vr=c[0], c=c[1], m=0.0), X0)), p_, M.money_base(), {})
                    for c in GRID1])
    Mf.index = Mf.index.str.replace("frozen_", "")
    Rr = Rr.merge(Mf[["k1_m2022", "k1_m2024", "k1_dd2024", "k1_dd_fall26", "k1_boot_med", "k1_boot_p10", "k1_boot_dd90"]].add_prefix("FZ_"),
                  left_on="id", right_index=True, how="left")
    Rr.to_csv(RES / "v32c_S1_engine_skip.csv", index=False)
    log(f"[S1] engine skip: {len(Rr)} -> E1 {int(Rr.E1.sum())} -> +E2 {int((Rr.E1 & Rr.E2).sum())} -> +E3 {int((Rr.E1 & Rr.E2 & Rr.E3).sum())} -> PASS {int(Rr.PASS.sum())}")
    print(Rr[["id", "n_removed", "R_removed", "n_new", "R_new", "netR", "volc_n", "volc_R", "x_dev", "x_oos", "cx_dev", "cx_oos", "plateau",
              "ph_dev", "ph_oos", "phc_dev", "phc_oos", "E1", "E2", "E3", "E4", "PASS"]].round(3).to_string(index=False))
    print(Rr[["id", "M_k1_m2022", "FZ_k1_m2022", "M_k1_m2024", "FZ_k1_m2024", "M_k1_dd2024", "FZ_k1_dd2024", "M_k1_dd_fall26", "FZ_k1_dd_fall26",
              "M_k1_boot_med", "FZ_k1_boot_med", "M_k1_boot_p10", "FZ_k1_boot_p10", "M_k1_boot_dd90", "FZ_k1_boot_dd90"]].round(1).to_string(index=False))
    P = Rr[Rr.PASS]
    if len(P):
        b = P.sort_values("minx", ascending=False).iloc[0]
        (RES / "v32c_engine_winner.json").write_text(json.dumps(dict(id=b.id, vr=float(b.vr), c=float(b.c)), indent=1))
        log(f"[S1] engine winner: {b.id}")
    # non-skip size-downs on the v3.1 list (the trade is taken: engine path = v3.1), both cap counts
    getX = M.base_at
    specs = [dict(id=f"size_vr{vr}_c{c}_m{m}", p=dict(kind="pull", vr=vr, c=c, m=m)) for (vr, c), m in itertools.product(GRID1, (0.25, 0.35, 0.5))]
    for cap in ("live", "base"):
        evalz(f"S1_sizedown_{cap}", specs, ["vr", "c", "m"], ["kind"], B.pullback, getX, Sl0, cap, M.money_base())
    # HOLD_BIG
    with Pool(PROCS) as pool:
        res = pool.map(holdbig_task, R.HOLD_BIG, chunksize=1)
    HB = {cfg_id(c): [] for c in [None] + GRID1}
    for s, out, err in res:
        if out is None:
            log(f"[S1] HOLD_BIG {s}: {err}"); continue
        for k_, v in out.items():
            HB[k_].append(v)
    HB = {k_: pd.concat(v, ignore_index=True) for k_, v in HB.items()}
    old = S.holdbig_trades()
    log(f"[S1] HOLD_BIG engine base = v3.2 holdbig_v31 list: {k(HB['v31']) == k(old[old.sym.isin(HB['v31'].sym.unique())])}")
    hb = []
    for cid, X in HB.items():
        sc = W.score(X)
        for per in (P20, P24):
            hb.append(dict(id=cid, period=per, n=sc[per]["n"], net=sc[per]["net"], dd=sc[per]["dd"], ratio=sc[per]["ratio"]))
    HBr = pd.DataFrame(hb).pivot(index="id", columns="period")
    HBr.columns = [f"{a}_{b}" for a, b in HBr.columns]
    HBr.to_csv(RES / "v32c_S1_holdbig.csv")
    print(HBr.round(2).to_string(), flush=True)


# ══ STAGE 2 ════════════════════════════════════════════════════════════════════════════════════════════════════════
def ramp(p, X):
    v = B.feats(X).VolReg.to_numpy()
    w = np.interp(v, [p["v_lo"], p["v_mid"], p["v_hi"]], [p["w_calm"], 1.0, p["w_wild"]])
    return np.where(np.isnan(v), 1.0, w)


def cliff():
    """T1's 0.79 knife edge: the capped account's worst 2024-26 episode for q_lo 0.75 / 0.79 / 0.83 (other axes = S5a-like)."""
    X = M.base_at(0).reset_index(drop=True); out = []
    a, b = W.PERIODS[P24]; t0 = pd.Timestamp(a).value // 60_000_000_000
    vr = B.feats(X).VolReg.to_numpy()
    for ql in (None, 0.75, 0.79, 0.83):
        m = None if ql is None else B.tier3(dict(q_lo=ql, w_calm=1.15, q_med=0.93, w_med=0.75, q_hi=1.25, w_wild=0.45), X)
        r = W.money31(W.window(W.rows(X, half=True, mult=m), a, b), B.pol("base"), eq0=1e6, fixed=True, path=True)
        pt, pe, pw = r["path"]; pk = np.maximum.accumulate(pw); j = int(np.argmax(pk - pw)); i = int(np.argmax(pw[:j + 1]))
        ts, te = C.D.to_datetime(np.array([pt[i] + t0, pt[j] + t0], np.int64))
        inn = X[(X.entry_time >= ts) & (X.entry_time <= te)]
        band = inn[(vr[inn.index] > 0.75) & (vr[inn.index] <= 0.83)]
        out.append(dict(q_lo=ql, net=r["final"] - 1e6, dd_abs=r["dd_abs"], ratio=(r["final"] - 1e6) / r["dd_abs"], peak=str(ts), trough=str(te),
                        trades_in_episode=len(inn), band_trades=";".join(f"{s[:3]} {d:+d} {e:%Y-%m-%d} VR{v:.3f} R{x:+.2f}" for s, d, e, v, x in
                                                                          zip(band.sym, band.dir, band.entry_time, vr[band.index], band.R))))
    T = pd.DataFrame(out); T.to_csv(RES / "v32c_S2_cliff_079.csv", index=False)
    print(T.to_string(index=False), flush=True)


def t1_subgrid():
    T = pd.read_csv(RES / "v32b_T1_volreg_3tier.csv")
    s = T[T.q_lo == 0.75].copy()
    s["plateau_sub"] = M.plateau(s, ["w_calm", "q_med", "w_med", "q_hi", "w_wild"], [], "E1")
    log(f"[S2] T1 q_lo = 0.75 sub-grid: {len(s)} settings, E1 {int(s.E1.sum())} ({s.E1.mean():.0%}), plateau >= 60% (within the sub-grid) "
        f"{int((s.E1 & (s.plateau_sub >= 0.6)).sum())}, median sub-plateau of E1 rows {s[s.E1].plateau_sub.median():.2f}")
    cols = ["id", "x_dev", "x_oos", "cx_dev", "cx_oos", "plateau", "plateau_sub", "null_u", "null_c", "ph_dev", "ph_oos", "phc_dev", "phc_oos",
            "M_k1_m2024", "M_k1_dd2024", "M_k1_boot_med", "M_k1_boot_dd90", "E3", "E4"]
    s.to_csv(RES / "v32c_S2_T1_qlo075_subgrid.csv", index=False)
    print(s.sort_values("minx", ascending=False)[cols].head(12).round(3).to_string(index=False), flush=True)


def s2():
    B.setup()
    cliff(); t1_subgrid()
    specs = [dict(id=f"ramp_lo{lo}x{wc}_mid{md}_hi{hi}x{ww}", p=dict(v_lo=lo, w_calm=wc, v_mid=md, v_hi=hi, w_wild=ww))
             for wc, lo, md, ww, hi in itertools.product((1.05, 1.10, 1.15), (0.72, 0.75, 0.78), (0.88, 0.92), (0.50, 0.60, 0.70, 0.75), (1.05, 1.12, 1.20))]
    ords = ["v_lo", "w_calm", "v_mid", "v_hi", "w_wild"]
    Sl0 = sleeve(pd.read_pickle(C.D.CACHE / "volc_trades_v31.pkl"))
    for cap in ("live", "base"):
        evalz(f"S2_ramp_on_v31_{cap}", specs, ords, [], ramp, M.base_at, Sl0, cap, M.money_base())
    wf = RES / "v32c_engine_winner.json"
    if wf.exists():
        w = json.loads(wf.read_text()); cid = w["id"]
        X = eng_list(cid, 0); Sl = sleeve(pd.read_pickle(CDIR / f"volc_{cid}.pkl"))
        for cap in ("live", "base"):
            ref = W.money_all(mrows(X, Sl), B.pol(cap))
            evalz(f"S2_ramp_on_{cid}_{cap}", specs, ords, [], ramp, lambda sh, cid=cid: eng_list(cid, sh), Sl, cap, ref)


# ══ STAGE 3 ════════════════════════════════════════════════════════════════════════════════════════════════════════
_BP = {}


def money_full(A, p, n=1000, seed=0):
    out = {}
    for nm, a in (("2022", "2022-01-01"), ("2024", "2024-01-01"), ("sep26", "2026-09-15"), ("oct26", "2026-10-01")):
        r = W.money31(W.window(A, a), p, path=(nm == "2024")); out[f"m_{nm}"] = r["final"]; out[f"dd_{nm}"] = r["dd"]
        if nm == "2024":                                            # the Sep 15 - Nov 6 2026 drop inside the 2024 run
            pt, pe, pw = r["path"]
            t0 = pd.Timestamp(a).value // 60_000_000_000; ws = pd.Timestamp("2026-09-15").value // 60_000_000_000 - t0
            k0 = np.searchsorted(pt, ws)
            w0 = pw[k0 - 1] if k0 > 0 else pw[0]
            seg = np.r_[w0, pw[k0:]]; pk = np.maximum.accumulate(seg)
            out["dd_sep26_inrun"] = float(((pk - seg) / pk).max() * 100); out["bal_sep26_inrun"] = float(w0)
            pk_all = np.maximum.accumulate(pw)
            out["dd_sep26_inrun_from_ath"] = float(((pk_all[k0:] - pw[k0:]) / pk_all[k0:]).max() * 100)
    if seed not in _BP:
        _BP[seed] = V0.boot_paths(n, seed=seed)
    v = np.array([[(r := W.money31(W.path_rows(A, us), p))["final"], r["dd"]] for us in _BP[seed]])
    out.update(boot_med=float(np.median(v[:, 0])), boot_p10=float(np.percentile(v[:, 0], 10)), boot_dd90=float(np.percentile(v[:, 1], 90)),
               p_10k=float((v[:, 0] >= 10_000).mean()), p_loss=float((v[:, 0] < 300).mean()))
    return out


def _s3_job(a):
    nm, A, p, meta = a
    return dict(name=nm, **meta, **money_full(A, p))


def s3():
    B.setup()
    X31 = M.base_at(0); Sl0 = sleeve(pd.read_pickle(C.D.CACHE / "volc_trades_v31.pkl"))
    cands = [("v3.1", X31, Sl0, None, "live")]
    wf = RES / "v32c_engine_winner.json"

    def best(f):
        if not (RES / f).exists():
            return None
        d = pd.read_csv(RES / f); d = d[d.PASS]
        return d.sort_values("minx", ascending=False).iloc[0] if len(d) else None
    for cap in ("live", "base"):
        r = best(f"v32c_S2_ramp_on_v31_{cap}.csv")
        if r is not None:
            p = {k: float(r[k]) for k in ("v_lo", "w_calm", "v_mid", "v_hi", "w_wild")}
            cands.append((f"v3.1 + ramp {r.id} ({cap} cap)", X31, Sl0, ramp(p, X31), cap))
    for cap in ("live", "base"):                                    # stage 1's non-skip size-downs (v3.1 engine path)
        r = best(f"v32c_S1_sizedown_{cap}.csv")
        if r is not None:
            p = dict(kind="pull", vr=float(r.vr), c=float(r.c), m=float(r.m))
            cands.append((f"v3.1 + size-down {r.id} ({cap} cap)", X31, Sl0, B.pullback(p, X31), cap))
    cid = "eng_vr1.05_c-0.25"                                        # v32b's skip, exact engine (fails E4; for reference)
    cands.append((f"v3.1 + engine skip {cid} (no PASS)", eng_list(cid, 0), sleeve(pd.read_pickle(CDIR / f"volc_{cid}.pkl")), None, "live"))
    if wf.exists():
        w = json.loads(wf.read_text()); cid = w["id"]
        X = eng_list(cid, 0); Sl = sleeve(pd.read_pickle(CDIR / f"volc_{cid}.pkl"))
        cands.append((f"v3.2c skip {cid}", X, Sl, None, "live"))
        for cap in ("live", "base"):
            r = best(f"v32c_S2_ramp_on_{cid}_{cap}.csv")
            if r is not None:
                p = {k: float(r[k]) for k in ("v_lo", "w_calm", "v_mid", "v_hi", "w_wild")}
                cands.append((f"v3.2c skip {cid} + ramp {r.id} ({cap} cap)", X, Sl, ramp(p, X), cap))
    items = []
    for nm, X, Sl, m, cap in cands:
        A = mrows(X, Sl, m)
        for flat, k in itertools.product((False, True), (0.90, 0.95, 1.00)):
            items.append((nm, A, ladder(B.pol(cap), flat, k), dict(cap=cap, ladder="tier0=tier1" if flat else "portfolio", k=k)))
    log(f"[S3] {len(items)} rows: {[c[0] for c in cands]}")
    with Pool(PROCS) as pool:
        res = pool.map(_s3_job, items, chunksize=1)
    T = pd.DataFrame(res)
    T.to_csv(RES / "v32c_S3_ladder_comparison.csv", index=False)
    fm = {c: "{:.0f}".format for c in T if c.startswith(("m_", "boot_med", "boot_p10", "bal_"))}
    fm.update({c: "{:.1f}".format for c in T if c.startswith("dd") or c == "boot_dd90"})
    fm.update({"k": "{:.2f}".format, "p_10k": "{:.3f}".format, "p_loss": "{:.3f}".format})
    print(T.to_string(index=False, formatters=fm), flush=True)


if __name__ == "__main__":
    {"s1": s1, "s2": s2, "s3": s3}[sys.argv[1]]()
