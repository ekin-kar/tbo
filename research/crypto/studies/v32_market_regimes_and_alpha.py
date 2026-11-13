"""v3.2 campaign (Nov 2026): crypto market regimes (core/crypto_regimes.py) and regime-conditional exits, vetoes, short-side
physics and risk on top of the deployed v3.1 (TBO v3.1 + Panic v3.0 + VOLC, ladder x 0.95). Read-only on cryptobot/.

BASE = v3.1 as deployed: TBO trades = research/crypto/core/v31deploy (= the v3.1b package, 1,355 trades; 41 phase copies in
cache/v31/pkg), panic sleeve v3.0, VOLC (cache/volc_trades_v31.pkl, 0.25 x BTC risk), ladder x 0.95 (portfolio.json).
Gates (same protocol as v3.1, fixed before the runs): E1 fixed-unit ratio > base in 2020-23 AND 2024-26 with net >= 92%; E2
plateau 60%; E3 40 phase copies 75% (engine rules) / 200 nulls 95% (sizing / removal rules) + HOLD_BIG shown; E4 money from
$300 (2022 / 2024 runs, Oct-Nov 2026, 1,000 two-year journeys) vs the base. Regime classifiers are fitted on 2020-23 only.

    python v32_market_regimes_and_alpha.py census | s2 | s3 | s4 | s5 | page"""
import itertools, os, pickle, sys, time
from multiprocessing import Pool
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v31")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import common as C, v29lib as L, v31lib as W, xengine31 as X31
import crypto_regimes as R
import v31_drawdown_and_sleeves as M

RES = M.RES
CACHE = R.CACHE
PKG = W.CACHE / "pkg"
log = M.log
GROUP = {"BTCUSDT": "BTC", "ETHUSDT": "ETH", "BNBUSDT": "Alts", "SOLUSDT": "Alts", "ADAUSDT": "Alts"}
PERIODS3 = {"2020-21": ("2020-01-01", "2022-01-01"), "2022-23": ("2022-01-01", "2024-01-01"), "2024-26": ("2024-01-01", W.END)}
FB = dict(T_h=8, G=60, cont=1, mlo=0.9, mhi=99.0, thr=-0.2, act=3, lvl=-0.5)


def use_pkg():
    M.CACHE = PKG; M._BASE.clear(); M._BS.clear(); M._MB.clear()


def with_path(X):
    """+ mfe (1m path, R of the stop distance) per trade."""
    out = []
    for s, x in X.groupby("sym"):
        x = x.reset_index(drop=True); m = L.m1(s); t = m["t"]
        ei = np.searchsorted(t, M._mins(x.entry_time)); xi = np.searchsorted(t, M._mins(x.exit_time))
        mfe, mae, *_ = X31.path_stats(t, m["h"], m["l"], m["c"], ei, xi, x.dir.to_numpy(np.int64), x.entry.to_numpy(float),
                                      x.sl_dist.to_numpy(float), np.array([1.5]))
        out.append(x.assign(mfe=mfe, mae=mae))
    return pd.concat(out, ignore_index=True)


def tag(X):
    """Regime labels at the entry (the coin's own and BTC's / the market's), known before the trade."""
    parts = []
    for s, x in X.groupby("sym"):
        x = x.reset_index(drop=True)
        own = R.at(s, x.entry_time, ["RB", "TS", "HM", "Bofu", "Bofd", "Ovl10", "Er20", "Dir20", "VolReg", "Bo4u", "Bo4d", "oi_rank90", "fund_rank90", "pz"])
        btc = R.at("BTCUSDT", x.entry_time, ["RB", "TS", "HM", "breadth50", "nethi", "disp", "corr7"]).add_prefix("btc_")
        parts.append(pd.concat([x, own, btc], axis=1))
    return pd.concat(parts, ignore_index=True)


def cell(g):
    if len(g) == 0:
        return dict(n=0)
    o = np.argsort(g.exit_time.values); e = np.cumsum(g.R.to_numpy()[o])
    w, lo = g.R[g.R > 0].sum(), -g.R[g.R <= 0].sum()
    return dict(n=len(g), win=float((g.R > 0).mean()), avgR=float(g.R.mean()), sumR=float(g.R.sum()), pf=float(w / lo) if lo > 0 else np.inf,
                maxdd=float(np.max(np.maximum.accumulate(np.r_[0, e])[1:] - e)), stop=float((g.R < -0.5).mean()),
                roundtrip=float(((g.mfe >= 1.5) & (g.mfe < 5) & (g.R < 0.1)).mean()))


_HB = {}


def holdbig_trades():
    """v3.1 TBO rules (failed-breakout stop; no cascade) on the 14 untouched HOLD_BIG coins."""
    f = CACHE / "holdbig_v31.pkl"
    if f.exists():
        return pd.read_pickle(f)
    out = []
    for s in R.HOLD_BIG:
        try:
            x = W.trades31(s, exL=dict(A=FB, rcool=1), exS=dict(A=FB, rcool=1))
            out.append(x[W.KEEP]); L._M.clear(); W._ORD.clear(); W._FA.clear()
        except Exception as e:
            log(f"{s}: {e}")
    X = pd.concat(out, ignore_index=True)
    X.to_pickle(f)
    return X


def census():
    R.fit()
    T = tag(with_path(pd.read_pickle(PKG / "base_s0.pkl")))
    T["group"] = T.sym.map(GROUP)
    HB = tag(with_path(holdbig_trades())); HB["group"] = "HOLD_BIG"
    A = pd.concat([T, HB], ignore_index=True)
    A.to_pickle(CACHE / "census_trades.pkl")
    rows = []
    for clf in ("RB", "TS", "HM", "btc_RB", "btc_HM"):
        for (state, d, grp), g in A.groupby([clf, "dir", "group"]):
            for per, (a, b) in PERIODS3.items():
                gg = g[(g.entry_time >= a) & (g.entry_time < b)]
                rows.append(dict(classifier=clf, state=state, dir="LONG" if d > 0 else "SHORT", group=grp, period=per, **cell(gg)))
    Cn = pd.DataFrame(rows)
    Cn.to_csv(RES / "v32_regime_census.csv", index=False)
    # the compact view: core 5 pooled, both sides, per RB state
    core = A[A.group != "HOLD_BIG"]
    view = []
    for clf in ("RB", "HM", "btc_RB"):
        for (state, d), g in core.groupby([clf, "dir"]):
            r = dict(classifier=clf, state=state, dir="LONG" if d > 0 else "SHORT")
            for per, (a, b) in PERIODS3.items():
                c = cell(g[(g.entry_time >= a) & (g.entry_time < b)])
                r[f"{per}_n"] = c["n"]; r[f"{per}_avgR"] = c.get("avgR", np.nan); r[f"{per}_rt"] = c.get("roundtrip", np.nan)
            hb = HB[(HB[clf] == state) & (HB.dir == d)] if clf in HB else HB.iloc[0:0]
            r["HB_n"] = len(hb); r["HB_avgR"] = float(hb.R.mean()) if len(hb) else np.nan
            view.append(r)
    V = pd.DataFrame(view)
    V.to_csv(RES / "v32_regime_census_view.csv", index=False)
    pd.set_option("display.width", 250)
    print(V.round(2).to_string(index=False))
    return A


if __name__ == "__main__" and sys.argv[1] == "census":
    census()


# ══ shared machinery: base = v3.1 as deployed, engine jobs on xengine32 ═════════════════════════════════════════════
import v32lib as V32                                                    # noqa: E402
BASEDIR = CACHE / "base"
VOLC_SHARE = 0.25


def setup_base():
    """M's gate machinery on the v3.1 base: TBO phase copies = the v3.1 package; money = TBO + panic + VOLC at the live
    ladder (portfolio.json x 0.95)."""
    BASEDIR.mkdir(parents=True, exist_ok=True)
    for f in PKG.glob("base_s*.pkl"):
        dst = BASEDIR / f.name
        if not dst.exists():
            dst.symlink_to(f)
    V = pd.read_pickle(C.D.CACHE / "volc_trades_v31.pkl")
    m = lambda c: V[c].values.astype("datetime64[m]").astype(np.int64)
    VR = np.c_[m("entry_time"), m("exit_time"), m("entry_time"), V.dir.to_numpy(float), V.R.to_numpy(float), np.full(len(V), 6.0), np.ones(len(V))]
    panic = W.sleeve30()
    W.sleeve30 = lambda: np.r_[panic, VR]                              # panic + VOLC as the sleeves of every money run
    _bp = W.base_policy
    W.base_policy = lambda **kw: _bp(**dict(dict(extra_risk=[(5, 0.5), (6, VOLC_SHARE)]), **kw))
    M.CACHE = BASEDIR; M._BASE.clear(); M._BS.clear(); M._MB.clear()
    M.job = job32
    b = M.money_base()
    log(f"v3.2 base (v3.1 as deployed): {dict((k, round(v, 2)) for k, v in b.items())}")
    return b


_Q = {}


def dev_q():
    """Dev (2020-23, DEV12 pooled) terciles of the regime features (frozen before any 2024-26 look)."""
    if not _Q:
        rows = pd.concat([R.daily(s) for s in R.DEV12])
        dev = rows[rows.index < R.DEV_END]
        for c in ("Bofu", "Bofd", "Ovl10", "Er20", "Bo4u", "Bo4d", "VolReg"):
            _Q[c] = (float(dev[c].quantile(1 / 3)), float(dev[c].quantile(2 / 3)))
    return _Q


def regime_cond(sym, name):
    """(long, short) boolean daily Series: the 'hostile' regime `name` for a trade of that side."""
    r = R.regimes(sym); q = dev_q()
    lo = lambda c: r[c] <= q[c][0]; hi = lambda c: r[c] >= q[c][1]
    L_, S_ = {
        "all": (r.c > 0, r.c > 0),
        "lowft": (lo("Bofu"), lo("Bofd")),
        "hiovl": (hi("Ovl10"), hi("Ovl10")),
        "lower": (lo("Er20"), lo("Er20")),
        "overext": (r.Dir20 >= 2.5, r.Dir20 <= -2.5),
        "counter": (r.Chg5 < 0, r.Chg5 > 0),
        "chop": (hi("Ovl10") & lo("Er20"), hi("Ovl10") & lo("Er20")),
        "rbchop": (~r.RB.isin(["UpClean", "DownClean"]), ~r.RB.isin(["UpClean", "DownClean"])),
        "lowbo4": (lo("Bo4u"), lo("Bo4d")),
        "hotvol": (hi("VolReg"), hi("VolReg")),
        "btcchop": tuple([R.regimes("BTCUSDT").RB.isin(["UpChop", "DownChop", "FlatWild"]).reindex(r.index).fillna(False)] * 2),
    }[name]
    return L_.fillna(False), S_.fillna(False)


def mask_fn(sym, name):
    if not name:
        return None
    cl, cs = regime_cond(sym, name)
    return lambda t: (V32.minute_mask(sym, t, cl), V32.minute_mask(sym, t, cs))


_BT = {}


def job32(args):
    """One engine run: (spec, sym, shift) -> trades (BTC's own run is repeated in the worker for the cascade)."""
    spec, sym, shift = args
    if M._CUR["sym"] != sym:
        L._M.clear(); W._ORD.clear(); W._FA.clear(); R._R.clear(); _BT.clear()
        M._CUR["sym"] = sym
    kw = dict(spec.get("kw", {}))
    em, dm, rb = spec.get("emask"), spec.get("dmask"), spec.get("rmaskB")

    def run(s, btc=None):
        k = dict(kw)
        if em:
            k["emask"] = mask_fn(s, em)
        if dm:
            k["dmask"] = mask_fn(s, dm)
        if rb:
            f = mask_fn(s, rb[0]); side = rb[1]
            k["rmaskB"] = (lambda t, f=f, side=side: (lambda ml_ms: ml_ms[0] if side == "long" else ml_ms[1] if side == "short" else ml_ms[0] | ml_ms[1])(f(t))) if f else None
        return V32.trades32(s, shift, btc=btc, **k)
    if sym == "BTCUSDT":
        x = run(sym)
    else:
        key = (spec["id"], shift)
        if key not in _BT:
            _BT.clear(); _BT[key] = run("BTCUSDT")
        x = run(sym, _BT[key])
    return spec["id"], sym, shift, x[[c for c in M.KEEP if c in x]]


def evaluate(name, specs, ords, cats, dev=M.P20, **kw):
    R_, runs, X0 = M.evaluate(name, specs, ords, cats, dev, **kw)
    Mo = M.money_for(name, R_, X0, specs=specs, mult_fn=kw.get("mult_fn"))
    return M.finish(name, R_, Mo, ["id"])


# ══ STAGE 2 — regime-conditional profit harvesting ══════════════════════════════════════════════════════════════
REGS = ["all", "lowft", "hiovl", "lower", "overext", "counter", "chop", "rbchop", "lowbo4"]


def s2():
    setup_base()
    specs = []
    for reg, (X, Lk) in itertools.product(REGS, itertools.product((2.0, 2.5, 3.0, 3.5), (0.75, 1.0, 1.25, 1.5))):
        if Lk >= X - 0.5:
            continue
        p = dict(reg=reg, mode="entry", act="lock", X=X, L=Lk, TP=0, H=0)
        specs.append(dict(id=f"s2_{reg}_entry_lock{X}>{Lk}", p=p, emask=reg, kw=dict(exL2=dict(L3=X, L3T=Lk), exS2=dict(L3=X, L3T=Lk))))
        if reg != "all":
            p = dict(p, mode="now")
            specs.append(dict(id=f"s2_{reg}_now_lock{X}>{Lk}", p=p, dmask=reg, kw=dict(dyn={"l": [X, Lk, 0], "s": [X, Lk, 0]})))
    for reg, tp in itertools.product(REGS, (2.5, 3.0, 3.5, 4.0)):
        p = dict(reg=reg, mode="entry", act="tp", X=0, L=0, TP=tp, H=0)
        specs.append(dict(id=f"s2_{reg}_entry_tp{tp}", p=p, emask=reg, kw=dict(exL2=dict(TPR=tp), exS2=dict(TPR=tp))))
        if reg != "all":
            specs.append(dict(id=f"s2_{reg}_now_tp{tp}", p=dict(p, mode="now"), dmask=reg, kw=dict(dyn={"l": [0, 0, tp], "s": [0, 0, tp]})))
    for reg, Hh in itertools.product(REGS, (48, 72)):
        specs.append(dict(id=f"s2_{reg}_entry_hold{Hh}", p=dict(reg=reg, mode="entry", act="hold", X=0, L=0, TP=0, H=Hh), emask=reg,
                          kw=dict(exL2={}, exS2={}, hold2=Hh)))
    log(f"[S2] {len(specs)} regime-conditional exit configs")
    evaluate("v32_S2_regime_exits", specs, ["X", "L", "TP", "H"], ["reg", "mode", "act"], top=30)


# ══ STAGE 3 — vetoes / size-downs by regime, regime-conditional early cut, short-side exits ═════════════════════════
def s3():
    setup_base()
    A = pd.read_pickle(CACHE / "census_trades.pkl")
    A = A[A.group != "HOLD_BIG"]
    # 3a size-down / skip by regime state at entry (sizing: exact on the trade list; skip = size 0)
    specs = []
    for clf, states in (("RB", R.RB_STATES), ("HM", [f"H{k}" for k in range(6)]), ("btc_RB", R.RB_STATES),
                        ("TS", sorted(A.TS.dropna().unique()))):
        for st, side, m in itertools.product(states, ("LONG", "SHORT"), (0.0, 0.5)):
            if st == "na":
                continue
            specs.append(dict(id=f"s3a_{clf}_{st}_{side}_x{m}", p=dict(clf=clf, st=st, side=side, m=m), engine=False))
    lab = {}

    def mf(sp, X):
        key = id(X)
        if key not in lab:
            lab.clear(); lab[key] = tag(X)
        T_ = lab[key]; p = sp["p"]
        d = 1 if p["side"] == "LONG" else -1
        hit = (T_[p["clf"]].to_numpy() == p["st"]) & (T_.dir.to_numpy() == d)
        return np.where(hit, p["m"], 1.0)
    evaluate("v32_S3a_regime_veto", specs, ["m"], ["clf", "st", "side"], mult_fn=mf,
             null_fn=lambda sp, X, rng: (X, M.permute_by_coin_side(X, mf(sp, X), rng)), phase=True)
    # 3b regime-conditional early cut (rule slot B), on shorts / in hostile regimes only
    specs = []
    for reg, side, T, thr, act in itertools.product(("all", "lowft", "hiovl", "chop", "rbchop", "counter", "btcchop"), ("short", "long", "both"),
                                                    (2, 3, 4, 6), (-0.4, -0.5, -0.6), ("close", "t-0.6")):
        rk = dict(T_h=T, G=15, cont=1, mlo=-99.0, mhi=0.3, thr=thr, **({"act": 2} if act == "close" else {"act": 3, "lvl": -0.6}))
        specs.append(dict(id=f"s3b_{reg}_{side}_T{T}_c{thr}_{act}", p=dict(reg=reg, side=side, T=T, thr=thr, act=act),
                          rmaskB=(reg, side), kw=dict(ruleB=rk)))
    log(f"[S3b] {len(specs)} early-cut configs")
    evaluate("v32_S3b_regime_early_cut", specs, ["T", "thr"], ["reg", "side", "act"], top=25)
    # 3c short-side exit physics
    specs = []
    for H, lk, tp in itertools.product((36, 48, 60, 72, 120), ((0, 0), (2.5, 1.0), (3.0, 1.0), (3.0, 1.5), (3.5, 1.5)), (0, 3.5, 4.5, 6.0)):
        if (H, lk, tp) == (120, (0, 0), 0):
            continue
        ex = dict(L3=lk[0], L3T=lk[1], TPR=tp)
        specs.append(dict(id=f"s3c_short_H{H}_lock{lk[0]}>{lk[1]}_tp{tp}", p=dict(H=H, X=lk[0], L=lk[1], TP=tp), kw=dict(exS=ex, holdS=H)))
    log(f"[S3c] {len(specs)} short-exit configs")
    evaluate("v32_S3c_short_exits", specs, ["H", "X", "L", "TP"], [], top=25)


if __name__ == "__main__" and sys.argv[1] in ("s2", "s3"):
    {"s2": s2, "s3": s3}[sys.argv[1]]()


# ══ STAGES 4 + 5 — regime-modulated risk (sizing rules: the trade list is the base's, exact) ═════════════════════════
_TG = {}


def tagged(X):
    key = id(X)
    if key not in _TG:
        _TG.clear(); _TG[key] = tag(X)
    return _TG[key]


def size_mult(p, X):
    """Per-trade risk multiplier for rule p, from regime values known at each entry."""
    T_ = tagged(X); q = dev_q(); d = T_.dir.to_numpy()
    kind = p["kind"]
    if kind == "btcchop":                                             # BTC (market) in a chop state -> m_chop, clean trend -> m_trend
        st = T_.btc_RB.to_numpy()
        chop = np.isin(st, p["states"].split("+"))
        clean = np.isin(st, ["UpClean", "DownClean"])
        return np.where(chop, p["m"], np.where(clean, p["boost"], 1.0))
    if kind == "breadth":                                             # market breadth extreme against / with the trade
        b = T_.btc_breadth50.to_numpy()
        hostile = np.where(d > 0, b <= p["lo"], b >= 1 - p["lo"])
        return np.where(hostile, p["m"], 1.0)
    if kind == "volreg":                                              # own coin's (or BTC's) daily ATR14 / ATR100
        v = T_.VolReg.to_numpy() if p["src"] == "own" else R.at("BTCUSDT", X.entry_time, ["VolReg"]).VolReg.to_numpy()
        lo, hi = q["VolReg"]
        cut = {"q67": hi, "q80": p.get("q80", hi)}[p["thr"]] if p["thr"] != "q50" else (lo + hi) / 2
        return np.where(v >= cut, p["m"], np.where(v <= lo, p["boost"], 1.0))
    if kind == "funding":                                             # funding rank at an extreme (either tail)
        f = T_.fund_rank90.to_numpy()
        return np.where((f <= p["tail"]) | (f >= 1 - p["tail"]), p["m"], 1.0)
    raise ValueError(kind)


def s4():
    setup_base()
    specs = []
    for states, m, boost in itertools.product(("FlatWild", "FlatWild+UpChop+DownChop", "UpChop+DownChop", "FlatWild+FlatCalm"),
                                              (0.5, 0.65, 0.75, 1.0), (1.0, 1.1)):
        if m == 1.0 and boost == 1.0:
            continue
        specs.append(dict(id=f"s4_btcchop_{states}_m{m}_b{boost}", p=dict(kind="btcchop", states=states, m=m, boost=boost), engine=False))
    for lo, m in itertools.product((0.1, 0.2, 0.3), (0.5, 0.65, 0.75)):
        specs.append(dict(id=f"s4_breadth_lo{lo}_m{m}", p=dict(kind="breadth", lo=lo, m=m, states="", boost=1.0), engine=False))
    mf = lambda sp, X: size_mult(sp["p"], X)
    nf = lambda sp, X, rng: (X, M.permute_by_coin_side(X, mf(sp, X), rng))
    evaluate("v32_S4_regime_risk", [s for s in specs if s["p"]["kind"] == "btcchop"], ["m", "boost"], ["states"], mult_fn=mf, null_fn=nf)
    evaluate("v32_S4b_breadth_risk", [s for s in specs if s["p"]["kind"] == "breadth"], ["lo", "m"], [], mult_fn=mf, null_fn=nf)


def s5():
    setup_base()
    specs = []
    for src, thr, m, boost in itertools.product(("own", "btc"), ("q50", "q67"), (0.5, 0.65, 0.75, 1.0), (1.0, 1.15, 1.3)):
        if m == 1.0 and boost == 1.0:
            continue
        specs.append(dict(id=f"s5_volreg_{src}_{thr}_m{m}_b{boost}", p=dict(kind="volreg", src=src, thr=thr, m=m, boost=boost), engine=False))
    mf = lambda sp, X: size_mult(sp["p"], X)
    nf = lambda sp, X, rng: (X, M.permute_by_coin_side(X, mf(sp, X), rng))
    evaluate("v32_S5a_volreg_size", specs, ["m", "boost"], ["src", "thr"], mult_fn=mf, null_fn=nf)
    specs = [dict(id=f"s5_funding_t{t}_m{m}", p=dict(kind="funding", tail=t, m=m), engine=False)
             for t, m in itertools.product((0.05, 0.1, 0.2), (0.5, 0.65, 0.75))]
    evaluate("v32_S5b_funding_tails", specs, ["tail", "m"], [], dev=M.P22, mult_fn=mf, null_fn=nf)


if __name__ == "__main__" and sys.argv[1] in ("s4", "s5"):
    {"s4": s4, "s5": s5}[sys.argv[1]]()


def quintiles():
    """research/results/v32_quintiles.json: avg R by quintile of each feature at entry, 2020-23 vs 2024-26 (core 5)."""
    import json
    A = pd.read_pickle(CACHE / "census_trades.pkl"); A = A[A.group != "HOLD_BIG"]
    out = {}
    for col, nm in (("VolReg", "coin ATR14/ATR100"), ("Ovl10", "coin bar overlap (10 d)"), ("Bofu", "coin up follow-through"),
                    ("Er20", "coin efficiency (20 d)"), ("Dir20", "coin 20-day move (ATR)"), ("Bo4u", "coin 4h breakout follow-through"),
                    ("btc_breadth50", "market breadth (EMA50)"), ("btc_corr7", "correlation with BTC (7 d)"), ("fund_rank90", "funding rank (90 d)"),
                    ("oi_rank90", "open interest rank (90 d)")):
        x = A.dropna(subset=[col]).copy()
        x["q"] = pd.qcut(x[col].rank(method="first"), 5, labels=False)
        t = x.groupby(["q", (x.entry_time >= "2024-01-01").map({False: "dev", True: "oos"})]).R.mean().unstack()
        out[nm] = {"dev": [round(float(v), 3) for v in t["dev"]], "oos": [round(float(v), 3) for v in t["oos"]]}
    (RES / "v32_quintiles.json").write_text(json.dumps(out, indent=1))
    return out


if __name__ == "__main__" and sys.argv[1] == "quintiles":
    quintiles()


def s3b2():
    """Stage 3b again, with the side restriction done right: the early-cut rule (slot B) goes into the chosen side's exit
    vector only (the first run applied it to both sides where the mask was on)."""
    setup_base()
    specs = []
    for reg, side, T, thr, act in itertools.product(("all", "lowft", "hiovl", "chop", "rbchop", "counter", "btcchop"), ("short", "long"),
                                                    (2, 3, 4, 6), (-0.4, -0.5, -0.6), ("close", "t-0.6")):
        rk = dict(T_h=T, G=15, cont=1, mlo=-99.0, mhi=0.3, thr=thr, **({"act": 2} if act == "close" else {"act": 3, "lvl": -0.6}))
        kw = dict(exL=dict(B=rk)) if side == "long" else dict(exS=dict(B=rk))
        specs.append(dict(id=f"s3b2_{reg}_{side}_T{T}_c{thr}_{act}", p=dict(reg=reg, side=side, T=T, thr=thr, act=act),
                          rmaskB=(reg, side), kw=kw))
    log(f"[S3b2] {len(specs)} side-specific early-cut configs")
    evaluate("v32_S3b2_regime_early_cut_side", specs, ["T", "thr"], ["reg", "side", "act"], top=25)


if __name__ == "__main__" and sys.argv[1] == "s3b2":
    s3b2()
