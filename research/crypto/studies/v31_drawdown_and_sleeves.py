"""v3.1 campaign (Nov 2026): drawdown controls for TBO v3.0 (Part 1, Tracks 1-4) and orthogonal sleeves for chop /
range regimes (Part 2, Tracks 5-8). Data to 2026-11-06. Engine core/xengine31.py (exact v3.0 parity, v31lib.parity).

BASE = the deployed TBO v3.0 (1,333 trades) + Panic v3.0 (5 core + 7 extra DEV12 coins, 0.75 share, max 2 extra open).

PROTOCOL (fixed before any run; inherits v3.0's, made stricter where the brief says so):
  E1 fixed-unit   ratio (net / max closed drawdown, units BTC 6 / ETH 4 / others 0.83, shorts x 0.5) relative to the base:
                  x_dev > 1 AND x_oos > 1 AND net units >= 92% of the base in both periods. dev = 2020-23 (price rules) or
                  2022-23 (rules that read OI / premium / funding); oos = 2024-01-01 .. 2026-11-06.
                  Rules acting only through the open-risk cap: the same ratio on a capped, non-compounding account (money31
                  fixed=True: worst-case drawdown incl. open risk).
  E2 plateau      >= 60% of the grid neighbours pass E1 (ordinal axes Chebyshev 1; categorical: one category differs).
  E3 luck         engine rules: x > 1 in BOTH periods on >= 75% of 40 phase-shifted copies of the 4h / daily candles;
                  removal / sizing rules: min(x_dev, x_oos) above >= 95% of 200 random nulls (same number removed / same
                  multipliers shuffled per coin and side). Alt-only rules: also shown on HOLD_BIG (14 untouched coins).
  E4 money        bot + panic from $300 (2020 / 2022 / 2024 starts, and Oct 1 - Nov 6 2026 = the live chop) and 1,000 paired
                  2-year block-bootstrap journeys (4-week blocks, 2022-01 .. 2026-11):
                  E4  (literal, at the live risk): 2022 and 2024 money >= base, 2024-26 max drop < base, Oct-Nov 2026 drop
                       <= base, bootstrap dd90 < base, p10 > base, median > base;
                  G6  (v3.0's drawdown-matched read): risks x k (1.00 .. 0.85) until dd90 <= base, then median > base, p10 >=
                       base, 2022 / 2024 money > base, window drops <= base + 1 pt. Shown for every money row.
  PASS = E1 + E2 + E3 + E4.  Sleeves: S1 avg R > 0, PF >= 1.25, N >= 30 in each period; S2 plateau 60%; S3 >= 95% vs 200
  random-entry copies; S4 HOLD39 avg R > 0 both periods; S5 monthly corr with TBO <= 0.15 and net R > 0 over TBO's losing
  months in 2022-23 AND 2024-26, no entry within 12 h after a panic trigger; S6 = E4 next to bot + panic.

    python v31_drawdown_and_sleeves.py base | t1 | t2 | t3 | t4 | t5 | t6 | t7 | t8 | combo     (results/v31_*.csv)"""
import functools, itertools, os, pickle, sys, time
from multiprocessing import Pool
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v30")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import common as C, v29lib as L, v30lib as V, v31lib as W, xengine31 as X31

RES = C.ROOT / "research" / "results"
CACHE = W.CACHE
PROCS = int(os.environ.get("V31_PROCS", 7))
COINS = W.COINS
MAJ, ALT = ["BTCUSDT", "ETHUSDT"], ["BNBUSDT", "SOLUSDT", "ADAUSDT"]
P20, P22, P24 = W.P20, W.P22, W.P24
SH = W.SHIFTS
KEEP = W.KEEP
NET_MIN = 0.92
PH_MIN = 0.75
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 400)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def _mins(s):
    return s.values.astype("datetime64[m]").astype(np.int64)


# ══ engine jobs ═══════════════════════════════════════════════════════════════════════════════════════════════════
_BASE = {}


def base_at(shift):
    if shift not in _BASE:
        _BASE[shift] = pd.read_pickle(CACHE / f"base_s{shift}.pkl")
    return _BASE[shift]


# ── extra 4h-candle skip filters (module level: picklable) ──
_DAY = {}


def _daily(sym):
    """Daily candles (real time) of a coin: close, EMA50, ATR14, ER10, and the minute each day closes."""
    if sym not in _DAY:
        m = L.m1(sym)
        d = C.D.resample(m, 1440)
        e = C.I.ema(d["c"], 50); a = C.I.atr(d["h"], d["l"], d["c"], 14)
        cc = d["c"]; er = np.full(len(cc), np.nan)
        num = np.abs(cc[10:] - cc[:-10]); den = np.convolve(np.abs(np.diff(cc)), np.ones(10), "valid")
        er[10:] = num / np.maximum(den, 1e-12)
        _DAY[sym] = dict(tc=d["t"] + 1440, ext=np.abs(cc - e) / a, er=er)
    return _DAY[sym]


def skip_chop_ext(sym, c, a, hi, lo, s, er_thr=0.25, ext=3.0, sides=0):
    """No order when the last closed day's ER10 < er_thr AND its distance from EMA50 > ext daily ATR (v3.0 limit is 4)."""
    D = _daily(sym)
    k = np.searchsorted(D["tc"], c["t"] + 240, side="right") - 1
    kk = np.clip(k, 0, None)
    hit = (k >= 0) & (D["er"][kk] < er_thr) & (D["ext"][kk] > ext)
    return hit & ((sides == 0) | (s == sides))


def skip_width(sym, c, a, hi, lo, s, K=6.0, sides=0):
    """No order when the 20-candle channel height (hi - lo) > K x ATR(4h)."""
    with np.errstate(invalid="ignore"):
        hit = (hi - lo) / a > K
    return hit & ((sides == 0) | (s == sides))


SKIPS = {"chop_ext": skip_chop_ext, "width": skip_width}


def engine_kwargs(spec, sym):
    pc = spec.get("per_coin", {}).get(sym, {})
    g = lambda k, d=None: pc.get(k, spec.get(k, d))
    kw = dict(kwL=g("kwL"), kwS=g("kwS"), exL=g("exL"), exS=g("exS"), fa_tf=g("fa_tf", 0), valid_min=g("valid_min", 0))
    sk = g("skp")
    if sk:
        nm, prm = sk
        kw["skipx"] = functools.partial(SKIPS[nm], **dict(prm)); kw["skey"] = (nm, tuple(sorted(dict(prm).items())))
    if "cool" in spec:
        kw["cool"] = spec["cool"]
    return kw


def _ctrl_from(iv_l, iv_s):
    def f(t):
        return {"fill_l": ~_mask(t, iv_l), "fill_s": ~_mask(t, iv_s)}
    return f


def _mask(t, iv):
    m = np.zeros(len(t), np.bool_)
    iv = np.asarray(iv, np.int64).reshape(-1, 2)
    if len(iv):
        a = np.searchsorted(t, iv[:, 0]); b = np.searchsorted(t, iv[:, 1])
        d = np.zeros(len(t) + 1, np.int64); np.add.at(d, a, 1); np.add.at(d, b, -1)
        m = np.cumsum(d)[:-1] > 0
    return m


_CUR = {"sym": None}


def job(args):
    spec, sym, shift = args
    if _CUR["sym"] != sym:
        L._M.clear(); W._ORD.clear(); W._FA.clear(); _DAY.clear()
        import families as F
        F._rs.cache_clear(); F._M1.clear()
        import gc; gc.collect()
        _CUR["sym"] = sym
    kw = engine_kwargs(spec, sym)
    blk = spec.get("block", {}).get((sym, shift))
    ctrl = _ctrl_from(*blk) if blk is not None else None
    cf = spec.get("ctrlfn")
    if cf is not None:                                   # named per-coin controls (Track 8): masks / tightening / rule regime
        nm, prm = cf
        import v31_sleeves as S8
        out = S8.CTRLS[nm](sym, shift, L.m1(sym)["t"], **dict(prm))
        kw["rmask"] = out.pop("rmask", None)
        if out:
            ctrl = (lambda t, out=out: out)
    x = W.trades31(sym, shift=shift, ctrl=ctrl, **kw)
    return spec["id"], sym, shift, x[KEEP]


def run_jobs(specs, shifts=(0,)):
    tasks = []
    for sp in specs:
        for s in sp.get("coins", COINS):
            for sh in shifts:
                tasks.append((sp, s, sh))
    tasks.sort(key=lambda z: (z[1], z[2]))
    out = {}
    with Pool(PROCS) as pool:
        for k, (i, s, sh, x) in enumerate(pool.imap_unordered(job, tasks, chunksize=8)):
            out.setdefault(i, {}).setdefault(sh, []).append(x)
            if (k + 1) % 5000 == 0:
                log(f"  {k + 1}/{len(tasks)} runs")
    return {i: {sh: pd.concat(v, ignore_index=True) for sh, v in d.items()} for i, d in out.items()}


def portfolio(var, coins, shift):
    B = base_at(shift)
    return pd.concat([B[~B.sym.isin(coins)], var[var.sym.isin(coins)]], ignore_index=True)


# ══ scoring ═══════════════════════════════════════════════════════════════════════════════════════════════════════
_BS = {}


def base_score(shift):
    if shift not in _BS:
        _BS[shift] = W.score(base_at(shift))
    return _BS[shift]


def xpair(X, shift, dev, mult=None):
    s = W.score(X, mult=mult); b = base_score(shift)
    x = W.xr(s, b)
    return x[dev], x[P24], s


def plateau(df, ords, cats, flag):
    vals = {a: sorted(df[a].dropna().unique().tolist(), key=lambda v: (str(type(v)), v)) for a in ords}
    pos = {a: {v: i for i, v in enumerate(vals[a])} for a in ords}
    keys = df[ords + cats].to_records(index=False)
    fl = df[flag].to_numpy()
    out = np.full(len(df), np.nan)
    ko = np.array([[pos[a].get(k[q], -99) if not pd.isna(k[q]) else -99 for q, a in enumerate(ords)] for k in keys]) if ords else np.zeros((len(df), 0))
    kc = np.array([[str(k[len(ords) + q]) for q in range(len(cats))] for k in keys]) if cats else np.zeros((len(df), 0))
    for i in range(len(df)):
        dc = (kc != kc[i]).sum(axis=1) if cats else np.zeros(len(df), int)
        do = np.abs(ko - ko[i]).max(axis=1) if ords else np.zeros(len(df), int)
        nb = ((dc == 0) & (do == 1)) | ((dc == 1) & (do == 0))
        nb[i] = False
        out[i] = fl[nb].mean() if nb.any() else np.nan
    return out


def phase_win(get_X, dev, mult_fn=None):
    w = []
    for sh in SH:
        X = get_X(sh)
        m = mult_fn(X) if mult_fn else None
        xd, xo, _ = xpair(X, sh, dev, mult=m)
        w.append((xd > 1, xo > 1, (xd > 1) and (xo > 1)))
    w = np.array(w, float)
    return float(w[:, 0].mean()), float(w[:, 1].mean()), float(w[:, 2].mean())


# ══ money ═════════════════════════════════════════════════════════════════════════════════════════════════════════
_MB = {}


def money_base():
    if "b" not in _MB:
        f = CACHE / "money_base.pkl"
        if f.exists():
            _MB["b"] = pd.read_pickle(f)
        else:
            A = W.with_sleeve(W.rows(base_at(0)), W.sleeve30())
            _MB["b"] = W.money_all(A, W.base_policy()); pd.to_pickle(_MB["b"], f)
    return _MB["b"]


def g6_job(args):
    name, A, pol, mk = args
    return name, W.g6(A, pol, money_base(), **mk)


def g6_many(items):
    money_base()
    items = [(it + ({},))[:4] for it in items]
    with Pool(PROCS) as pool:
        res = pool.map(g6_job, items, chunksize=1)
    return pd.DataFrame([dict(id=n, **r) for n, r in res]).set_index("id")


def e4_literal(r, b):
    return bool(r["k1_m2022"] >= b["m2022"] and r["k1_m2024"] >= b["m2024"] and r["k1_dd2024"] < b["dd2024"] and
                r["k1_dd_fall26"] <= b["dd_fall26"] + 1e-9 and r["k1_boot_dd90"] < b["boot_dd90"] and r["k1_boot_p10"] > b["boot_p10"]
                and r["k1_boot_med"] > b["boot_med"])


# ══ generic evaluation ════════════════════════════════════════════════════════════════════════════════════════════
def evaluate(name, specs, ords, cats, dev, runs=None, mult_fn=None, null_fn=None, phase=True, top=30, get0=None, getsh=None):
    """specs: dicts with id, p (grid params), coins and engine keys. mult_fn(spec, X) -> per-trade risk multipliers.
    null_fn(spec, X, rng) -> (X', mult') random null. get0(spec) / getsh(spec, shift) override how trades are obtained
    (e.g. iterated cross-coin runs)."""
    log(f"[{name}] {len(specs)} configs")
    runs = dict(runs or {})
    eng = [s for s in specs if s.get("engine", True) and s["id"] not in runs and get0 is None]
    if eng:
        runs.update(run_jobs(eng))
    X0 = {}
    for sp in specs:
        if get0 is not None:
            X0[sp["id"]] = get0(sp)
        elif sp.get("engine", True):
            X0[sp["id"]] = portfolio(runs[sp["id"]][0], sp.get("coins", COINS), 0)
        else:
            X0[sp["id"]] = base_at(0)
    b = base_score(0)
    rows = []
    for sp in specs:
        X = X0[sp["id"]]
        m = mult_fn(sp, X) if mult_fn else None
        xd, xo, s = xpair(X, 0, dev, mult=m)
        rows.append(dict(id=sp["id"], **sp["p"], x_dev=xd, x_oos=xo, net_dev=s[dev]["net"], dd_dev=s[dev]["dd"], net_oos=s[P24]["net"],
                         dd_oos=s[P24]["dd"], n_dev=s[dev]["n"], n_oos=s[P24]["n"], netr_dev=s[dev]["net"] / b[dev]["net"],
                         netr_oos=s[P24]["net"] / b[P24]["net"]))
    R = pd.DataFrame(rows)
    R["E1"] = (R.x_dev > 1) & (R.x_oos > 1) & (R.netr_dev >= NET_MIN) & (R.netr_oos >= NET_MIN)
    R["plateau"] = plateau(R, ords, cats, "E1")
    R["E2"] = R.plateau >= 0.6
    R["minx"] = R[["x_dev", "x_oos"]].min(axis=1)
    cand = R[R.E1 & R.E2].sort_values("minx", ascending=False).head(top)
    show = list(dict.fromkeys(list(cand.id) + list(R.sort_values("minx", ascending=False).id.head(3))))
    byid = {s["id"]: s for s in specs}
    R["phase_dev"] = np.nan; R["phase_oos"] = np.nan; R["phase_both"] = np.nan
    if phase and show:
        log(f"[{name}] phase copies for {len(show)} configs")
        if getsh is not None:
            for i in show:
                pw = phase_win(lambda sh, i=i: getsh(byid[i], sh), dev, (lambda X, i=i: mult_fn(byid[i], X)) if mult_fn else None)
                R.loc[R.id == i, ["phase_dev", "phase_oos", "phase_both"]] = pw
        else:
            ph_specs = [byid[i] for i in show if byid[i].get("engine", True)]
            ph = run_jobs(ph_specs, shifts=SH) if ph_specs else {}
            for i in show:
                sp = byid[i]
                gx = (lambda sh, sp=sp: portfolio(ph[sp["id"]][sh], sp.get("coins", COINS), sh)) if sp.get("engine", True) else base_at
                pw = phase_win(gx, dev, (lambda X, sp=sp: mult_fn(sp, X)) if mult_fn else None)
                R.loc[R.id == i, ["phase_dev", "phase_oos", "phase_both"]] = pw
    R["null_pct"] = np.nan
    if null_fn is not None and show:
        log(f"[{name}] nulls for {len(show)} configs")
        for i in show:
            sp = byid[i]; X = X0[i]
            rng = np.random.default_rng(abs(hash(i)) % 2 ** 32)
            real = float(R.loc[R.id == i, "minx"].iloc[0]); d = []
            for _ in range(200):
                Xn, mn = null_fn(sp, X, rng)
                a_, b_, _ = xpair(Xn, 0, dev, mult=mn); d.append(min(a_, b_))
            R.loc[R.id == i, "null_pct"] = float(np.mean(np.array(d) < real))
    if null_fn is not None:
        R["E3"] = R.null_pct >= 0.95
        if phase:
            R["E3"] &= (R.phase_dev >= PH_MIN) & (R.phase_oos >= PH_MIN)
    else:
        R["E3"] = (R.phase_dev >= PH_MIN) & (R.phase_oos >= PH_MIN)
    return R, runs, X0


def money_for(name, R, X0, mult_fn=None, mk_fn=None, rows_fn=None, ids=None, specs=None):
    byid = {s["id"]: s for s in (specs or [])}
    ids = ids if ids is not None else list(dict.fromkeys(list(R[R.E1 & R.E2 & R.E3].id) + list(R.sort_values("minx", ascending=False).id.head(3))))
    items = []
    for i in ids:
        sp = byid.get(i, {"id": i}); X = X0[i]
        m = mult_fn(sp, X) if mult_fn else None
        A = rows_fn(sp, X, m) if rows_fn else W.rows(X, mult=m)
        A = W.with_sleeve(A, W.sleeve30())
        items.append((i, A, W.base_policy(), mk_fn(sp) if mk_fn else {}))
    if not items:
        return pd.DataFrame()
    log(f"[{name}] money for {len(items)} configs")
    return g6_many(items)


def finish(name, R, M, cols_first):
    b = money_base()
    if len(M):
        M = M.copy(); M["E4"] = [e4_literal(r, b) for _, r in M.iterrows()]
        R = R.merge(M.add_prefix("M_"), left_on="id", right_index=True, how="left")
        R["E4"] = R.M_E4.fillna(False).astype(bool)
        R["G6"] = R.M_G6.fillna(False).astype(bool)
    else:
        R["E4"] = False; R["G6"] = False
    R["PASS"] = R.E1 & R.E2 & R.E3 & R.E4
    R["PASS_dd_matched"] = R.E1 & R.E2 & R.E3 & R.G6
    R.to_csv(RES / f"v31_{name}.csv", index=False)
    log(f"[{name}] funnel: {len(R)} -> E1 {int(R.E1.sum())} -> +E2 {int((R.E1 & R.E2).sum())} -> +E3 {int((R.E1 & R.E2 & R.E3).sum())} -> "
        f"+E4 PASS {int(R.PASS.sum())} (dd-matched G6 instead of E4: {int(R.PASS_dd_matched.sum())})")
    show = R.sort_values(["PASS", "PASS_dd_matched", "minx"], ascending=False).head(12)
    cols = [c for c in cols_first + ["x_dev", "x_oos", "netr_dev", "netr_oos", "plateau", "phase_dev", "phase_oos", "null_pct", "E1", "E2",
                                     "E3", "M_k1_m2022", "M_k1_m2024", "M_k1_dd2024", "M_k1_dd_fall26", "M_k1_boot_med", "M_k1_boot_p10",
                                     "M_k1_boot_dd90", "E4", "M_k", "G6", "PASS"] if c in show]
    print(show[cols].round(3).to_string(index=False), flush=True)
    return R


# ══ BASE ═════════════════════════════════════════════════════════════════════════════════════════════════════════
def stage_base():
    CACHE.mkdir(parents=True, exist_ok=True)
    log("parity: sim31 (controls off) vs deployed v3.0")
    P = W.parity(); print(P.to_string(index=False))
    assert P.identical.all() and (P.be_time_equal == 1).all()
    log("base: 5 coins x 41 phases")
    r = run_jobs([dict(id="base", p={})], shifts=[0] + SH)["base"]
    for sh, X in r.items():
        X.to_pickle(CACHE / f"base_s{sh}.pkl")
    f = CACHE / "money_base.pkl"
    if f.exists():
        f.unlink()
    b = money_base()
    log(f"base money: {b}")
    X0 = r[0]
    s = W.score(X0)
    pd.DataFrame([dict(id="BASE v3.0+panic v3.0", n=len(X0), **{f"{p}_{k}": v for p, d in s.items() for k, v in d.items()}, **b)]) \
        .to_csv(RES / "v31_base.csv", index=False)


# ══ TRACK 1 — failed-breakout scratch / early cut / dead start ═════════════════════════════════════════════════════
MARKS = np.array([0.25, 0.4, 0.5, 0.6, 0.75, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5])


def anatomy(X):
    """1m MFE / MAE anatomy of the base trades."""
    out = []
    for s in COINS:
        x = X[X.sym == s].reset_index(drop=True)
        m = L.m1(s); t = m["t"]
        ei = np.searchsorted(t, _mins(x.entry_time)); xi = np.searchsorted(t, _mins(x.exit_time))
        mfe, mae, first, mae_after = X31.path_stats(t, m["h"], m["l"], m["c"], ei, xi, x.dir.to_numpy(np.int64), x.entry.to_numpy(float),
                                                    x.sl_dist.to_numpy(float), MARKS)
        d = x.assign(mfe_path=mfe, mae_path=mae)
        for q, mk in enumerate(MARKS):
            d[f"t_{mk}"] = np.where(first[:, q] >= 0, first[:, q] / 60.0, np.nan); d[f"maeafter_{mk}"] = np.where(first[:, q] >= 0, mae_after[:, q], np.nan)
        out.append(d)
    return pd.concat(out, ignore_index=True)


def t1_anatomy():
    A = anatomy(base_at(0))
    A.to_pickle(CACHE / "anatomy.pkl")
    stop = A[A.R < -0.5]; win = A[A.R >= 2]; tex = A[A.reason.isin(["TIME", "END"])]
    rows = [dict(group="full stop-outs (R < -0.5)", n=len(stop), sum_R=stop.R.sum(), med_h=stop.hours.median(), p95_h=stop.hours.quantile(.95),
                 share_lt48=(stop.hours < 48).mean()),
            dict(group="120 h time exits (+ open at end)", n=len(tex), sum_R=tex.R.sum(), med_h=tex.hours.median()),
            dict(group="winners R >= 2", n=len(win), sum_R=win.R.sum(), med_h=win.hours.median()),
            dict(group="all", n=len(A), sum_R=A.R.sum())]
    for mk in (0.4, 0.6, 0.8, 1.0, 1.25):
        rows.append(dict(group=f"stop-outs that first reached +{mk}R", n=int(stop[f"t_{mk}"].notna().sum()), share=stop[f"t_{mk}"].notna().mean(),
                         sum_R=stop[stop[f"t_{mk}"].notna()].R.sum(), med_h=stop[f"t_{mk}"].median()))
    for mk in (0.5, 0.75, 1.0, 1.25):
        reached = win[win[f"t_{mk}"].notna()]
        for dip in (-0.4, -0.6, -0.75):
            rows.append(dict(group=f"winners >= 2R: after +{mk}R dipped below {dip}R", n=int((reached[f"maeafter_{mk}"] < dip).sum()),
                             share=(reached[f"maeafter_{mk}"] < dip).mean(), base_n=len(reached)))
        allr = A[A[f"t_{mk}"].notna()]
        for dip in (-0.4, -0.6):
            g = allr[allr[f"maeafter_{mk}"] < dip]
            rows.append(dict(group=f"ALL trades: after +{mk}R dipped below {dip}R", n=len(g), share=len(g) / max(len(allr), 1), sum_R=g.R.sum(),
                             win_share=(g.R >= 2).mean(), base_n=len(allr)))
    T = pd.DataFrame(rows)
    T.to_csv(RES / "v31_T1_anatomy.csv", index=False)
    print(T.round(3).to_string(index=False))
    # sample sizes per bucket of MFE before stop for the brief's question
    bins = [-1, 0.25, 0.4, 0.6, 0.8, 1.0, 1.25, 1.5, 99]
    H = pd.cut(A.mfe_path, bins).value_counts().sort_index().rename("all").to_frame()
    H["stop_outs"] = pd.cut(stop.mfe_path, bins).value_counts().sort_index()
    H["winners_2R"] = pd.cut(win.mfe_path, bins).value_counts().sort_index()
    H.to_csv(RES / "v31_T1_mfe_hist.csv")
    print(H.to_string())


RULE_ACT = {"tp0": dict(act=1, lvl=0.0), "tp-0.05": dict(act=1, lvl=-0.05), "close": dict(act=2), "tight-0.35": dict(act=3, lvl=-0.35),
            "tight-0.5": dict(act=3, lvl=-0.5), "sl-0.4": dict(act=3, lvl=-0.4), "sl0": dict(act=3, lvl=0.0)}
SCOPES = {"all": (COINS, "both"), "majors": (MAJ, "both"), "alts": (ALT, "both"), "longs": (COINS, "long"), "shorts": (COINS, "short")}


def rule_spec(sid, p, rule_kw, slot="A", scope="all", stale_off=False, rcool=1, extra=None):
    coins, side = SCOPES[scope]
    ex = dict(**{slot: rule_kw}, rcool=rcool)
    if stale_off:
        ex["stale_h"] = 0
    if extra:
        ex.update(extra)
    sp = dict(id=sid, p=dict(p, scope=scope), coins=coins)
    if side in ("both", "long"):
        sp["exL"] = ex
    if side in ("both", "short"):
        sp["exS"] = ex
    return sp


def t1():
    t1_anatomy()
    # 1b failed-breakout 4D grid (1h-close checks, continuous after T, cooldown after a rule exit)
    specs = []
    for T, M, thr, act in itertools.product((2, 4, 6, 8, 12, 16, 24, 36), (0.4, 0.6, 0.75, 0.9, 1.1, 1.25), (0.1, 0.0, -0.1, -0.2, -0.3),
                                             ("tp0", "close", "tight-0.35", "tight-0.5")):
        rk = dict(T_h=T, G=60, cont=1, mlo=M, mhi=99.0, thr=thr, **RULE_ACT[act])
        specs.append(rule_spec(f"fb_T{T}_M{M}_c{thr}_{act}", dict(T=T, M=M, thr=thr, act=act), rk))
    R, runs, X0 = evaluate("T1b_failed_breakout", specs, ["T", "M", "thr"], ["act"], P20, top=30)
    M_ = money_for("T1b_failed_breakout", R, X0, specs=specs)
    R = finish("T1b_failed_breakout", R, M_, ["id"])
    # 1c check granularity / single check / TP -0.05 / no cooldown on rule exits, around the 20 best of 1b
    top = R.sort_values("minx", ascending=False).head(20)
    specs2 = []
    for _, r in top.iterrows():
        for G, cont, act, rc in itertools.product((1, 15, 60), (0, 1), (r.act, "tp-0.05" if r.act == "tp0" else r.act), (1, 0)):
            if (G, cont, rc) == (60, 1, 1) and act == r.act:
                continue
            rk = dict(T_h=r["T"], G=G, cont=cont, mlo=r.M, mhi=99.0, thr=r.thr, **RULE_ACT[act])
            specs2.append(rule_spec(f"fb_T{r['T']}_M{r.M}_c{r.thr}_{act}_G{G}_cont{cont}_rc{rc}", dict(T=r["T"], M=r.M, thr=r.thr, act=act, G=G,
                                    cont=cont, rc=rc), rk, rcool=rc))
    specs2 = list({s["id"]: s for s in specs2}.values())
    R2, runs2, X02 = evaluate("T1c_fb_variants", specs2, ["T", "M", "thr", "G"], ["act", "cont", "rc"], P20, top=20)
    M2 = money_for("T1c_fb_variants", R2, X02, specs=specs2)
    finish("T1c_fb_variants", R2, M2, ["id"])
    # 1d scope: the 10 best of 1b on majors / alts / longs / shorts only
    specs3 = []
    for _, r in R.sort_values("minx", ascending=False).head(10).iterrows():
        rk = dict(T_h=r["T"], G=60, cont=1, mlo=r.M, mhi=99.0, thr=r.thr, **RULE_ACT[r.act])
        for sc in ("majors", "alts", "longs", "shorts"):
            specs3.append(rule_spec(f"fb_T{r['T']}_M{r.M}_c{r.thr}_{r.act}@{sc}", dict(T=r["T"], M=r.M, thr=r.thr, act=r.act), rk, scope=sc))
    R3, runs3, X03 = evaluate("T1d_fb_scope", specs3, ["T", "M", "thr"], ["act", "scope"], P20, top=20)
    M3 = money_for("T1d_fb_scope", R3, X03, specs=specs3)
    finish("T1d_fb_scope", R3, M3, ["id"])
    # 1e early dead-start rule (slot B), supplementing or replacing the 60 h stale stop
    specs4 = []
    for T, N, thr, act, mode in itertools.product((12, 18, 24, 30, 36, 48), (0.5, 0.75, 1.0, 1.5), (0.0, -0.15, -0.25), ("tp0", "sl-0.4", "sl0"),
                                                   ("add", "replace")):
        rk = dict(T_h=T, G=60, cont=0, mlo=-99.0, mhi=N, thr=thr, **RULE_ACT[act])
        specs4.append(rule_spec(f"stale_T{T}_N{N}_c{thr}_{act}_{mode}", dict(T=T, N=N, thr=thr, act=act, mode=mode), rk, slot="B",
                                stale_off=(mode == "replace")))
    R4, runs4, X04 = evaluate("T1e_early_stale", specs4, ["T", "N", "thr"], ["act", "mode"], P20, top=30)
    M4 = money_for("T1e_early_stale", R4, X04, specs=specs4)
    R4 = finish("T1e_early_stale", R4, M4, ["id"])
    specs5 = []
    for _, r in R4.sort_values("minx", ascending=False).head(8).iterrows():
        rk = dict(T_h=r["T"], G=60, cont=0, mlo=-99.0, mhi=r.N, thr=r.thr, **RULE_ACT[r.act])
        for sc in ("majors", "alts", "longs", "shorts"):
            specs5.append(rule_spec(f"stale_T{r['T']}_N{r.N}_c{r.thr}_{r.act}_{r['mode']}@{sc}", dict(T=r["T"], N=r.N, thr=r.thr, act=r.act,
                                    mode=r["mode"]), rk, slot="B", scope=sc, stale_off=(r["mode"] == "replace")))
    R5, _, X05 = evaluate("T1f_stale_scope", specs5, ["T", "N", "thr"], ["act", "mode", "scope"], P20, top=20)
    M5 = money_for("T1f_stale_scope", R5, X05, specs=specs5)
    finish("T1f_stale_scope", R5, M5, ["id"])


# ══ TRACK 2 — fill-time re-anchor and soft ratchet ══════════════════════════════════════════════════════════════════
RA_KIND = {"1h/1h": dict(fa=60, den=0), "15m/15m": dict(fa=15, den=0), "1h/(4h/2)": dict(fa=60, den=1, k=2.0)}


def t2():
    specs = []
    for kind, lo, alpha, anchor in itertools.product(RA_KIND, (0.70, 0.75, 0.80, 0.85), (0.25, 0.35, 0.5, 0.65), (0, 1)):
        k = RA_KIND[kind]; ra = dict(mode=1, lo=lo, alpha=alpha, anchor=anchor, den=k["den"], k=k.get("k", 2.0), rmin=0.3)
        specs.append(dict(id=f"ra_tight_{kind}_lo{lo}_a{alpha}_anc{anchor}", p=dict(mode="tight", kind=kind, lo=lo, hi=np.nan, alpha=alpha,
                          anchor=anchor), exL=dict(ra=ra), exS=dict(ra=ra), fa_tf=k["fa"]))
    for kind, hi, alpha, anchor in itertools.product(RA_KIND, (1.25, 1.40, 1.60), (0.25, 0.35, 0.5, 0.65), (0, 1)):
        k = RA_KIND[kind]; ra = dict(mode=2, hi=hi, alpha=alpha, anchor=anchor, den=k["den"], k=k.get("k", 2.0), rmax=2.0)
        specs.append(dict(id=f"ra_widen_{kind}_hi{hi}_a{alpha}_anc{anchor}", p=dict(mode="widen", kind=kind, lo=np.nan, hi=hi, alpha=alpha,
                          anchor=anchor), exL=dict(ra=ra), exS=dict(ra=ra), fa_tf=k["fa"]))
    for kind, lo, hi, alpha, anchor in itertools.product(RA_KIND, (0.75, 0.85), (1.25, 1.40, 1.60), (0.25, 0.35, 0.5, 0.65), (0, 1)):
        k = RA_KIND[kind]; ra = dict(mode=3, lo=lo, hi=hi, alpha=alpha, anchor=anchor, den=k["den"], k=k.get("k", 2.0), rmax=2.0, rmin=0.3)
        specs.append(dict(id=f"ra_both_{kind}_lo{lo}_hi{hi}_a{alpha}_anc{anchor}", p=dict(mode="both", kind=kind, lo=lo, hi=hi, alpha=alpha,
                          anchor=anchor), exL=dict(ra=ra), exS=dict(ra=ra), fa_tf=k["fa"]))
    for sp in specs:                                                # NaN axes -> sentinel for the plateau
        sp["p"] = {k: (-1 if (isinstance(v, float) and np.isnan(v)) else v) for k, v in sp["p"].items()}
    R, runs, X0 = evaluate("T2a_reanchor", specs, ["lo", "hi", "alpha"], ["mode", "kind", "anchor"], P20, top=30)
    M = money_for("T2a_reanchor", R, X0, specs=specs)
    finish("T2a_reanchor", R, M, ["id"])
    # 2b soft pre-breakeven ratchet
    specs = []
    for at, to, sc in itertools.product((0.6, 0.8, 1.0, 1.2), (-0.75, -0.6, -0.5, -0.35, -0.2), SCOPES):
        coins, side = SCOPES[sc]
        sp = dict(id=f"sr_at{at}_to{to}@{sc}", p=dict(at=at, to=to, scope=sc), coins=coins)
        if side in ("both", "long"):
            sp["exL"] = dict(sr_at=at, sr_to=to)
        if side in ("both", "short"):
            sp["exS"] = dict(sr_at=at, sr_to=to)
        specs.append(sp)
    R, runs, X0 = evaluate("T2b_soft_ratchet", specs, ["at", "to"], ["scope"], P20, top=30)
    M = money_for("T2b_soft_ratchet", R, X0, specs=specs)
    finish("T2b_soft_ratchet", R, M, ["id"])


# ══ TRACK 3 — portfolio heat: cluster cooldown, staggered release, dynamic cap, closed-loss brake ═════════════════════
def cluster_blocks(X, p):
    """Block intervals (minutes) per coin and side from the trades X (all coins) for rule p.
    kind 'glob': >= N distinct coins closed below lossR within W hours -> block B hours (scope all / same direction);
    kind 'btctrap': a BTC trade closed below lossR within h hours of its fill -> block B hours (all coins / same dir)."""
    lossR = p.get("lossR", -0.5)
    L_ = X[X.R < lossR].sort_values("exit_time")
    ev = []
    if p["kind"] == "glob":
        et = _mins(L_.exit_time); sy = L_.sym.to_numpy(); dr = L_.dir.to_numpy()
        for i in range(len(L_)):
            lo = et[i] - p["W"] * 60
            w = (et >= lo) & (et <= et[i])
            if p["scope"] == "dir":
                w &= dr == dr[i]
            if len(set(sy[w])) >= p["N"]:
                ev.append((et[i], et[i] + p["B"] * 60, dr[i]))
    elif p["kind"] == "btctrap":
        b = L_[(L_.sym == "BTCUSDT") & (L_.hours < p["h"])]
        for et_, d_ in zip(_mins(b.exit_time), b.dir):
            ev.append((et_, et_ + p["B"] * 60, d_))
    out = {}
    for s in COINS:
        il, is_ = [], []
        for a, z, d in ev:
            if p["scope"] == "all" or d == 1:
                il.append((a, z))
            if p["scope"] == "all" or d == -1:
                is_.append((a, z))
        out[s] = (np.array(il, np.int64).reshape(-1, 2), np.array(is_, np.int64).reshape(-1, 2))
    return out


def _key(X):
    return set(zip(X.sym, _mins(X.entry_time)))


def iterate_cluster(specs, shift=0, max_it=8):
    """Fixed point of the cross-coin rule: blocks from the current trades -> rerun all coins -> repeat until the trade
    lists stop changing. Returns {id: (X, iterations, converged)}."""
    cur = {sp["id"]: base_at(shift) for sp in specs}
    done = {}
    todo = list(specs)
    for it in range(1, max_it + 1):
        if not todo:
            break
        js = []
        for sp in todo:
            bl = cluster_blocks(cur[sp["id"]], sp["p"])
            js.append(dict(sp, block={(s, shift): bl[s] for s in COINS}))
        rr = run_jobs(js, shifts=[shift])
        nxt = []
        for sp in todo:
            Xn = rr[sp["id"]][shift]
            if _key(Xn) == _key(cur[sp["id"]]) and np.isclose(Xn.R.sum(), cur[sp["id"]].R.sum()):
                done[sp["id"]] = (Xn, it, True)
            else:
                cur[sp["id"]] = Xn; nxt.append(sp)
        todo = nxt
    for sp in todo:
        done[sp["id"]] = (cur[sp["id"]], max_it, False)
    return done


def null_remove(sp, X, rng):
    """From the base, remove the same number of trades per coin and side at random (trades the rule adds are kept)."""
    B = base_at(0)
    key = lambda Z: list(zip(Z.sym, _mins(Z.entry_time)))
    kept = set(key(X)); keyB = key(B)
    gone = np.array([k not in kept for k in keyB])
    added = X[[k not in set(keyB) for k in key(X)]]
    drop = np.zeros(len(B), bool)
    for (s, d), g in B[gone].groupby(["sym", "dir"]):
        pool = np.flatnonzero((B.sym == s).to_numpy() & (B.dir == d).to_numpy())
        drop[rng.choice(pool, len(g), replace=False)] = True
    return pd.concat([B[~drop], added], ignore_index=True), None


def btc_cool_intervals(X, hours, lossR=-0.5):
    b = X[(X.sym == "BTCUSDT") & (X.R < lossR)]
    return [(e, e + hours * 60, d) for e, d in zip(_mins(b.exit_time), b.dir)]


def stagger_mult(p, X):
    """Per-trade multiplier: ETH / alt entries in BTC's stopped direction while BTC 'cools' (p['H'] h after a BTC loss)."""
    iv = btc_cool_intervals(X, p["H"])
    et = _mins(X.entry_time); d = X.dir.to_numpy(); sy = X.sym.to_numpy()
    tgt = np.isin(sy, ALT if p["tgt"] == "alts" else MAJ[1:] + ALT)
    m = np.ones(len(X))
    for a, z, dd in iv:
        hit = tgt & (et >= a) & (et < z) & ((d == dd) | (p["dir"] == "any"))
        m[hit] = p["m"]
    return m


def brake_mult_units(X, days, Xu, mm, reset=0):
    """Fixed-unit version of the closed-loss brake: trades in entry order, units P&L (BTC-risk units = units / 6)."""
    u = W.L.units(X) / 6.0
    et = _mins(X.entry_time); xt = _mins(X.exit_time); bt = _mins(X.be_time); R = X.R.to_numpy(); c5 = np.zeros(len(X), bool)
    S = W.sleeve30(); st, sx, sR = S[:, 0], S[:, 1], S[:, 4]
    ev = [(xt[i], 0, i) for i in range(len(X))] + [(bt[i], 1, i) for i in range(len(X)) if bt[i] < xt[i]] + \
         [(et[i], 2, i) for i in range(len(X))]
    if reset == 0:
        ev += [(sx[k], 3, k) for k in range(len(S)) if sR[k] > 0]
    ev.sort()
    mult = np.ones(len(X)); armed = False; win = []
    for t, kd, i in ev:
        win = [(a, b) for a, b in win if a >= t - days * 1440]
        if kd == 0:
            pu = u[i] * mult[i]
            win.append((t, pu))
            if reset == 1 and R[i] > 0:
                armed = False
            if pu < 0 and sum(b for _, b in win) <= -Xu:
                armed = True
        elif kd in (1, 3) and reset == 0:
            armed = False
        elif kd == 2:
            mult[i] = mm if armed else 1.0
    return mult


def btc_uw_flags(X, thr):
    """Per trade: 1 if it is a non-BTC entry while an open BTC trade (not yet at its risk-free stop) is below thr R."""
    m = L.m1("BTCUSDT"); t = m["t"]
    b = X[X.sym == "BTCUSDT"]
    be_, bx, bb = _mins(b.entry_time), _mins(b.exit_time), _mins(b.be_time)
    bd, bE, bD = b.dir.to_numpy(), b.entry.to_numpy(), b.sl_dist.to_numpy()
    out = np.zeros(len(X))
    for k, (s, e) in enumerate(zip(X.sym, _mins(X.entry_time))):
        if s == "BTCUSDT":
            continue
        o = np.flatnonzero((be_ < e) & (bx > e) & (bb > e))
        for q in o:
            j = min(np.searchsorted(t, e) - 1, len(t) - 1)
            if (m["c"][j] - bE[q]) * bd[q] / bD[q] < thr:
                out[k] = 1.0
    return out


def t3():
    # 3a / 3a' cross-coin cluster cooldown (iterated to a fixed point)
    specs = []
    for N, Wh, B, sc, lr in itertools.product((2, 3), (4, 6, 12, 24), (4, 8, 12, 16, 24), ("all", "dir"), (-0.5, 0.0)):
        specs.append(dict(id=f"glob_N{N}_W{Wh}_B{B}_{sc}_L{lr}", p=dict(kind="glob", N=N, W=Wh, B=B, scope=sc, lossR=lr)))
    for h, B, sc in itertools.product((2, 4, 6, 8), (4, 8, 12, 16, 24), ("all", "dir")):
        specs.append(dict(id=f"btctrap_h{h}_B{B}_{sc}", p=dict(kind="btctrap", h=h, B=B, scope=sc, lossR=-0.5, N=0, W=0)))
    log(f"[T3a] {len(specs)} cluster rules: iterating at shift 0")
    it0 = iterate_cluster(specs)
    conv = pd.DataFrame([dict(id=i, iters=v[1], converged=v[2]) for i, v in it0.items()])
    _PH = {}

    def getsh(sp, sh):
        if (sp["id"], sh) not in _PH:
            raise KeyError
        return _PH[(sp["id"], sh)]

    for grp, nm in (("glob", "T3a_cluster_cooldown"), ("btctrap", "T3a_btc_trap")):
        ss = [s for s in specs if s["p"]["kind"] == grp]
        ords = ["N", "W", "B"] if grp == "glob" else ["h", "B"]
        cats = ["scope", "lossR"] if grp == "glob" else ["scope"]
        R, _, X0 = evaluate(nm, ss, ords, cats, P20, phase=False, get0=lambda sp: it0[sp["id"]][0], null_fn=null_remove)
        top = list(dict.fromkeys(list(R[R.E1 & R.E2].sort_values("minx", ascending=False).id.head(12)) + list(R.sort_values("minx", ascending=False).id.head(3))))
        byid = {s["id"]: s for s in ss}
        if top:
            log(f"[{nm}] phase copies (iterated) for {len(top)} configs")
            for sh in SH:
                r_ = iterate_cluster([byid[i] for i in top], shift=sh)
                for i in top:
                    _PH[(i, sh)] = r_[i][0]
            for i in top:
                R.loc[R.id == i, ["phase_dev", "phase_oos", "phase_both"]] = phase_win(lambda sh, i=i: _PH[(i, sh)], P20)
        R["E3"] = (R.null_pct >= 0.95) & (R.phase_dev >= PH_MIN) & (R.phase_oos >= PH_MIN)
        R = R.merge(conv, on="id", how="left")
        M = money_for(nm, R, X0, specs=ss)
        finish(nm, R, M, ["id", "iters"])
    # 3b staggered release: ETH / alts in BTC's stopped direction while BTC cools
    specs = []
    for H, tgt, dr, m in itertools.product((8, 12, 16), ("eth+alts", "alts"), ("same", "any"), (0.5, 0.65)):
        specs.append(dict(id=f"stagger_H{H}_{tgt}_{dr}_m{m}", p=dict(H=H, tgt=tgt, dir=dr, m=m), engine=False))
    nf = lambda sp, X, rng: (X, permute_by_coin_side(X, stagger_mult(sp["p"], X), rng))
    R, _, X0 = evaluate("T3b_stagger_size", specs, ["H", "m"], ["tgt", "dir"], P20, mult_fn=lambda sp, X: stagger_mult(sp["p"], X), null_fn=nf,
                        phase=True)
    M = money_for("T3b_stagger_size", R, X0, mult_fn=lambda sp, X: stagger_mult(sp["p"], X), specs=specs)
    finish("T3b_stagger_size", R, M, ["id"])
    # blocking version in the engine: BTC is never blocked, so BTC's trades are the base ones and one pass is exact
    def stagger_blocks(p, shift):
        iv = btc_cool_intervals(base_at(shift), p["H"])
        tg = ALT if p["tgt"] == "alts" else MAJ[1:] + ALT
        il = np.array([(a, z) for a, z, d in iv if d == 1 or p["dir"] == "any"], np.int64).reshape(-1, 2)
        is_ = np.array([(a, z) for a, z, d in iv if d == -1 or p["dir"] == "any"], np.int64).reshape(-1, 2)
        return {(s, shift): (il, is_) for s in tg}
    specs = []
    for H, tgt, dr in itertools.product((8, 12, 16), ("eth+alts", "alts"), ("same", "any")):
        p = dict(H=H, tgt=tgt, dir=dr)
        blk = {}
        for sh in [0] + SH:
            blk.update(stagger_blocks(p, sh))
        specs.append(dict(id=f"stagger_H{H}_{tgt}_{dr}_block", p=p, coins=ALT if tgt == "alts" else MAJ[1:] + ALT, block=blk))
    R, _, X0 = evaluate("T3b_stagger_block", specs, ["H"], ["tgt", "dir"], P20, null_fn=null_remove)
    M = money_for("T3b_stagger_block", R, X0, specs=specs)
    finish("T3b_stagger_block", R, M, ["id"])
    # 3c dynamic open-risk cap: BTC counted x k while underwater; half of a trade's risk freed once its stop is <= -0.5R
    #     (soft ratchet), on a capped non-compounding account (E1) and in money (E4)
    B0 = base_at(0)
    rows = []
    srX = {}
    for at in (0.75, 1.0):
        sp = dict(id=f"sr_at{at}_to-0.5", p={}, exL=dict(sr_at=at, sr_to=-0.5), exS=dict(sr_at=at, sr_to=-0.5))
        srX[at] = run_jobs([sp])[sp["id"]][0]
    cfgs = []
    for k, thr in itertools.product((1.25, 1.5), (-0.25, -0.5)):
        cfgs.append((f"btcuw_k{k}_thr{thr}", B0, dict(btc_k=k), btc_uw_flags(B0, thr), dict(k=k, thr=thr, sr=0, hfrac=1.0)))
    for at in (0.75, 1.0):
        cfgs.append((f"sr{at}_nofree", srX[at], {}, None, dict(k=1.0, thr=0, sr=at, hfrac=1.0)))
        cfgs.append((f"sr{at}_free50", srX[at], dict(hfrac=0.5), None, dict(k=1.0, thr=0, sr=at, hfrac=0.5)))
        cfgs.append((f"sr{at}_free50_btcuw1.25", srX[at], dict(hfrac=0.5, btc_k=1.25), btc_uw_flags(srX[at], -0.25),
                     dict(k=1.25, thr=-0.25, sr=at, hfrac=0.5)))
    cfgs.append(("base", B0, {}, None, dict(k=1.0, thr=0, sr=0, hfrac=1.0)))
    pol = W.base_policy()
    fx = {}
    for nm, X, mk, flag, p in cfgs:
        A = W.rows(X, half=True, btc_uw=flag)
        r = {}
        for per, (a, b) in W.PERIODS.items():
            Aw = W.window(A, a, b)
            mm = W.money31(Aw, pol, eq0=1e6, fixed=True, **mk)
            r[per] = (mm["final"] - 1e6) / mm["dd_abs"]
        fx[nm] = r
        rows.append(dict(id=nm, **p, ratio_dev=r[P20], ratio_oos=r[P24]))
    R = pd.DataFrame(rows)
    R["x_dev"] = R.ratio_dev / fx["base"][P20]; R["x_oos"] = R.ratio_oos / fx["base"][P24]
    R["E1"] = (R.x_dev > 1) & (R.x_oos > 1); R["minx"] = R[["x_dev", "x_oos"]].min(axis=1)
    R["E2"] = np.nan; R["E3"] = np.nan
    items = [(nm, W.with_sleeve(W.rows(X, half=True, btc_uw=flag), W.sleeve30()), pol, mk) for nm, X, mk, flag, p in cfgs if nm != "base"]
    M = g6_many(items)
    b = money_base(); M["E4"] = [e4_literal(r, b) for _, r in M.iterrows()]
    R = R.merge(M.add_prefix("M_"), left_on="id", right_index=True, how="left")
    R.to_csv(RES / "v31_T3c_dynamic_cap.csv", index=False)
    print(R[["id", "x_dev", "x_oos", "E1", "M_k1_m2022", "M_k1_m2024", "M_k1_dd2024", "M_k1_boot_med", "M_k1_boot_dd90", "M_E4", "M_G6"]].round(3).to_string(index=False))
    # 3d rolling closed-loss brake (reset the instant an open TBO trade reaches its risk-free stop or a sleeve trade wins)
    specs = []
    for D, Xu, m, rs in itertools.product((3, 5, 7, 10), (2.5, 3.5, 4.5), (0.5, 0.65, 0.75), (0, 1)):
        specs.append(dict(id=f"brake_D{D}_X{Xu}_m{m}_reset{rs}", p=dict(D=D, X=Xu, m=m, reset=rs), engine=False))
    mf = lambda sp, X: brake_mult_units(X, sp["p"]["D"], sp["p"]["X"], sp["p"]["m"], sp["p"]["reset"])
    R, _, X0 = evaluate("T3d_loss_brake", specs, ["D", "X", "m"], ["reset"], P20, mult_fn=mf,
                        null_fn=lambda sp, X, rng: (X, permute_by_coin_side(X, mf(sp, X), rng)), phase=True)
    M = money_for("T3d_loss_brake", R, X0, specs=specs, mk_fn=lambda sp: dict(brake=(sp["p"]["D"], sp["p"]["X"], sp["p"]["m"], sp["p"]["reset"])))
    finish("T3d_loss_brake", R, M, ["id"])


def permute_by_coin_side(X, m, rng):
    m2 = np.asarray(m, float).copy()
    for (s, d), g in X.groupby(["sym", "dir"]).groups.items():
        g = np.asarray(list(g))
        pos = np.flatnonzero(X.index.isin(g))
        m2[pos] = rng.permutation(m2[pos])
    return m2


# ══ TRACK 4 — entry microstructure ═════════════════════════════════════════════════════════════════════════════════
def width_at(X):
    """20-candle channel height in units of the order's ATR (the stop distance) at the moment the order was placed, from
    1m data (valid for any phase shift)."""
    out = np.full(len(X), np.nan)
    for s in COINS:
        idx = np.flatnonzero((X.sym == s).to_numpy())
        if not len(idx):
            continue
        m = L.m1(s); t = m["t"]
        for k in idx:
            a = int(np.searchsorted(t, _mins(X.arm_time.iloc[[k]])[0]))
            lo = max(0, a - 20 * 240)
            out[k] = (m["h"][lo:a].max() - m["l"][lo:a].min()) / X.sl_dist.iat[k]
    return out


def t4():
    B0 = base_at(0)
    fm = (_mins(B0.entry_time) - _mins(B0.arm_time))
    B0 = B0.assign(fill_min=fm, bucket=pd.cut(fm, [-1, 59, 119, 179, 240], labels=["0-59", "60-119", "120-179", "180-240"]))
    rows = []
    for per, (a, b) in W.PERIODS.items():
        x = B0[(B0.entry_time >= a) & (B0.entry_time < b)]
        for bk, g in x.groupby("bucket", observed=True):
            rows.append(dict(period=per, bucket=bk, n=len(g), avg_R=g.R.mean(), win=(g.R > 0).mean(), sum_R=g.R.sum(), stop_share=(g.R < -0.5).mean()))
    T = pd.DataFrame(rows); T.to_csv(RES / "v31_T4_fill_minute.csv", index=False); print(T.round(3).to_string(index=False))
    # 4a order validity window
    specs = []
    for vm, sc in itertools.product((60, 90, 120, 150, 180), SCOPES):
        coins, side = SCOPES[sc]
        if side != "both":
            continue
        specs.append(dict(id=f"valid{vm}@{sc}", p=dict(vm=vm, scope=sc), coins=coins, valid_min=vm))
    R, runs, X0 = evaluate("T4a_validity", specs, ["vm"], ["scope"], P20, null_fn=null_remove)
    M = money_for("T4a_validity", R, X0, specs=specs)
    finish("T4a_validity", R, M, ["id"])
    # 4b tighter max_ext in a choppy macro regime (daily ER10 < er)
    specs = []
    for er, ext, sc in itertools.product((0.15, 0.2, 0.25, 0.3, 0.35), (2.0, 2.5, 3.0, 3.5), ("all", "majors", "alts")):
        coins = SCOPES[sc][0]
        specs.append(dict(id=f"chopext_er{er}_ext{ext}@{sc}", p=dict(er=er, ext=ext, scope=sc), coins=coins,
                          skp=("chop_ext", (("er_thr", er), ("ext", ext)))))
    R, runs, X0 = evaluate("T4b_chop_ext", specs, ["er", "ext"], ["scope"], P20, null_fn=null_remove)
    M = money_for("T4b_chop_ext", R, X0, specs=specs)
    finish("T4b_chop_ext", R, M, ["id"])
    # 4c wide 20-candle box: skip (engine) or size x m
    specs = []
    for K, sc in itertools.product((4, 5, 6, 7, 8, 10), ("all", "majors", "alts")):
        coins = SCOPES[sc][0]
        specs.append(dict(id=f"width_K{K}_skip@{sc}", p=dict(K=K, act="skip", scope=sc), coins=coins, skp=("width", (("K", float(K)),))))
    R, runs, X0 = evaluate("T4c_width_skip", specs, ["K"], ["scope"], P20, null_fn=null_remove)
    M = money_for("T4c_width_skip", R, X0, specs=specs)
    finish("T4c_width_skip", R, M, ["id"])
    WB = width_at(base_at(0))
    log(f"channel height / ATR at the order: median {np.nanmedian(WB):.2f}, p25 {np.nanpercentile(WB, 25):.2f}, p75 {np.nanpercentile(WB, 75):.2f}")
    specs = []
    for K, m, sc in itertools.product((4, 5, 6, 7, 8, 10), (0.5, 0.65), ("all", "majors", "alts")):
        specs.append(dict(id=f"width_K{K}_m{m}@{sc}", p=dict(K=K, m=m, scope=sc), engine=False))
    _WC = {}

    def wmult(sp, X):
        key = id(X)
        if key not in _WC:
            _WC.clear(); _WC[key] = width_at(X)
        w = _WC[key]; cs = SCOPES[sp["p"]["scope"]][0]
        return np.where((w > sp["p"]["K"]) & X.sym.isin(cs).to_numpy(), sp["p"]["m"], 1.0)
    R, _, X0 = evaluate("T4d_width_size", specs, ["K", "m"], ["scope"], P20, mult_fn=wmult,
                        null_fn=lambda sp, X, rng: (X, permute_by_coin_side(X, wmult(sp, X), rng)))
    M = money_for("T4d_width_size", R, X0, mult_fn=wmult, specs=specs)
    finish("T4d_width_size", R, M, ["id"])


if __name__ == "__main__":
    stage = sys.argv[1]
    t0 = time.time()
    if stage in ("t5", "t6", "t7", "t8"):
        import v31_sleeves as S8
        getattr(S8, stage)()
    else:
        {"base": stage_base, "t1": t1, "t2": t2, "t3": t3, "t4": t4}[stage]()
    log(f"{stage} done in {(time.time() - t0) / 60:.1f} min")
