"""v3.0 deep campaign (Nov 2026): six tracks on TBO v2.8 + Panic v2.7, data to 2026-11-06, all 8 CPU threads.

PROTOCOL (fixed before any run; "base" = live v2.8 + v2.7, exact engine parity in core/v30lib.parity):
  E1 fixed-unit   ratio (net / max drawdown, closed trades, units BTC 6 / ETH 4 / others 0.83, shorts x 0.5) relative to the
                  base: x_dev > 1 AND x_oos > 1. dev = 2020-23 for price-only rules, 2022-23 for rules that read open interest,
                  premium, funding or spot volume (that data starts Dec 2021); oos = 2024-01-01 .. 2026-11-06.
  E2 plateau      >= 60% of the grid neighbours also have x > 1 in both periods (ordinal axes: Chebyshev distance 1;
                  categorical axes: the members that differ in exactly one category).
  E3 luck         engine rules: x > 1 on >= 70% of 40 phase-shifted copies of the 4h / daily candles, in each period;
                  rules that remove or resize trades also: min(x_dev, x_oos) above >= 95% of 200 random nulls (the same number
                  of trades removed / the same multipliers shuffled, per coin and side).
  E4 money (G6)   drawdown-matched: bot + panic sleeve from $300 (2022, 2024 starts) and 1,000 paired 2-year block-bootstrap
                  journeys (4-week blocks, 2022-01 .. 2026-11). The candidate is run with every risk x k for k = 1.00, 0.96,
                  0.93, 0.90; the first k whose bootstrap 1-in-10 drop (dd90) <= the base dd90 is used. PASS if there: bootstrap
                  median > base, bootstrap 10th percentile >= base, money in 2022 and 2024 > base, window drops <= base + 1 pt.
  PASS = E1 + E2 + E3 + E4. Shown, not gated: 2020 money, untouched coins (HOLD_BIG, where the rule applies to alts).
  Sleeves (Track 5) instead: S-G1 DEV12 avg R > 0, PF >= 1.2, >= 30 trades in each period; S-G2 plateau (avg R > 0 both);
  S-G3 >= 95% vs 200 random-entry and 40 time-shifted copies, both periods; S-G4 HOLD39 avg R > 0 both periods;
  S-G5 monthly correlation with TBO <= 0.15 AND net R > 0 over TBO's losing months; S-G6 = E4 (sleeve next to bot + panic).
Multiple testing: ~4,000 configurations are scored; E2 / E3 / E4 exist because some will pass E1 by chance.

    python v30_deep_campaign.py base | t1 | t2 | t3 | t4 | t5 | t6      (results in research/results/v30_*.csv)"""
import itertools, os, pickle, sys, time
from multiprocessing import Pool
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v28nov")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import common as C, v29lib as L, v30lib as V, hourly51 as H
sys.path.insert(0, str(C.ROOT / "cryptobot"))
import panic_signal as PS                                          # noqa: E402

RES = C.ROOT / "research" / "results"
CACHE = C.D.CACHE / "v30"
PROCS = int(os.environ.get("V30_PROCS", 8))
COINS = V.COINS
MAJ, ALT = ["BTCUSDT", "ETHUSDT"], ["BNBUSDT", "SOLUSDT", "ADAUSDT"]
P20, P22, P24 = V.P20, V.P22, V.P24
SH = V.SHIFTS
KEEP = ["entry_time", "exit_time", "be_time", "dir", "R", "sym", "entry", "sl_dist", "reason"]
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 400)


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ══ engine jobs ═══════════════════════════════════════════════════════════════════════════════════════════════════
_BASE = {}


def base_at(shift):
    """Base v2.8 trades of the 5 coins at a phase shift (cached on disk by `base`)."""
    if shift not in _BASE:
        _BASE[shift] = pd.read_pickle(CACHE / f"base_s{shift}.pkl")
    return _BASE[shift]


def _mask(t, iv):
    """Per-minute bool: True inside any [a, b) interval (minutes)."""
    m = np.zeros(len(t), np.bool_)
    if len(iv):
        a = np.searchsorted(t, iv[:, 0]); b = np.searchsorted(t, iv[:, 1])
        d = np.zeros(len(t) + 1, np.int64); np.add.at(d, a, 1); np.add.at(d, b, -1)
        m = np.cumsum(d)[:-1] > 0
    return m


def _mins(s):
    return s.values.astype("datetime64[m]").astype(np.int64)


def leaders_for(sym, leader):
    if leader == "BTC":
        return [] if sym == "BTCUSDT" else ["BTCUSDT"]
    if leader == "BTC+ETH":
        return {"BTCUSDT": [], "ETHUSDT": ["BTCUSDT"]}.get(sym, ["BTCUSDT", "ETHUSDT"])
    raise ValueError(leader)


def make_ctrl(spec, sym, shift):
    """Cross-coin masks / cooldown for one coin, built from the base trades of the leaders at the same phase shift."""
    kind = spec.get("ctrl")
    if not kind:
        return None
    p = spec["p"]
    B = base_at(shift)
    if kind == "veto":
        def f(t):
            lead = leaders_for(sym, p["leader"])
            if sym == "BTCUSDT" and p["to_btc"]:
                lead = []                                     # BTC: blocked when ETH and >= 1 alt are open the other way
                X = B[B.sym != "BTCUSDT"]
                out = {}
                for side, nm in ((1, "fill_s"), (-1, "fill_l")):  # an open LONG cluster blocks BTC shorts, and vice versa
                    e = X[X.sym == "ETHUSDT"]; a = X[X.sym.isin(ALT)]
                    st = lambda Z: np.c_[_mins(Z.be_time if p["cond"] == "be" else Z.entry_time), _mins(Z.exit_time)]
                    me = _mask(t, st(e[e.dir == side])); ma = _mask(t, st(a[a.dir == side]))
                    out[nm] = ~(me & ma)
                return out
            if not lead:
                return {}
            X = B[B.sym.isin(lead)]
            st = lambda Z: np.c_[_mins(Z.be_time if p["cond"] == "be" else Z.entry_time), _mins(Z.exit_time)]
            return {"fill_l": ~_mask(t, st(X[X.dir < 0])), "fill_s": ~_mask(t, st(X[X.dir > 0]))}
        return f
    if kind == "active":
        def f(t):
            lead = leaders_for(sym, p["leader"])
            if not lead:
                return {}
            X = B[B.sym.isin(lead)]
            out = {}
            for side, nm in ((-1, "l"), (1, "s")):            # a new leader SHORT acts on open LONGS, and vice versa
                j = np.searchsorted(t, _mins(X[X.dir == side].entry_time)) + 1
                m = np.zeros(len(t), np.bool_); m[j[j < len(t)]] = True
                if p["action"] == "close":
                    out["exit_long" if nm == "l" else "exit_short"] = m
                else:
                    out["tight_" + nm] = m
            out["tight_to"] = {"be": 0.0, "m03": -0.3, "close": 0.0}[p["action"]]
            return out
        return f
    if kind == "cool":
        return lambda t: {"cool": (int(p["cool_h"] * 60), p["cool_R"], int(p["mode"]), 0.25)}
    if kind == "randexit":                                    # null for 'active': the same number of actions at random minutes
        def f(t):
            rng = np.random.default_rng(p["seed"] * 1000 + COINS.index(sym))
            out = {}
            for nm, k in (("l", p["n_l"].get(sym, 0)), ("s", p["n_s"].get(sym, 0))):
                m = np.zeros(len(t), np.bool_)
                if k:
                    m[rng.choice(len(t), k, replace=False)] = True
                if p["action"] == "close":
                    out["exit_long" if nm == "l" else "exit_short"] = m
                else:
                    out["tight_" + nm] = m
            out["tight_to"] = {"be": 0.0, "m03": -0.3, "close": 0.0}[p["action"]]
            return out
        return f
    raise ValueError(kind)


_FEAT = {}


def hfeat(sym):
    """Hourly features for the Track 3 filters, indexed by the minute each hour CLOSES (known from then on)."""
    if sym in _FEAT:
        return _FEAT[sym]
    df = H.hourly(sym)
    h, l, c = (df[k].to_numpy(float) for k in "hlc")
    f = PS.features(h, l, c, df.oi.to_numpy(float), df.prem.to_numpy(float), 4)
    sr = pd.Series(df.spot_v4.to_numpy(float) / df.perp_v4.to_numpy(float))
    oi = df.oi.ffill()
    q4 = df[["h", "l", "c"]].resample("4h").agg({"h": "max", "l": "min", "c": "last"}).dropna()
    pc = q4.c.shift(1)
    tr4 = np.fmax(q4.h - q4.l, np.fmax((q4.h - pc).abs(), (q4.l - pc).abs()))
    vr = (tr4.ewm(alpha=1 / 14, adjust=False).mean() / tr4.ewm(alpha=1 / 100, adjust=False).mean())
    vr[np.arange(len(vr)) < 100] = np.nan
    end4 = (q4.index + pd.Timedelta(hours=4)).values
    tclose = (df.index + pd.Timedelta(hours=1)).values
    k4 = np.searchsorted(end4, tclose, side="right") - 1
    F_ = dict(t=tclose.astype("datetime64[m]").astype(np.int64), pz=f["pz"], fund=df.fund.to_numpy(float),
              sr7=sr.rolling(168, min_periods=84).rank(pct=True).to_numpy(), sr30=sr.rolling(720, min_periods=360).rank(pct=True).to_numpy(),
              rank90=oi.rolling(2160, min_periods=1080).rank(pct=True).to_numpy(),
              vr=np.where(k4 >= 0, vr.to_numpy()[np.clip(k4, 0, None)], np.nan))
    _FEAT[sym] = F_
    return F_


def feat_at(sym, T):
    F_ = hfeat(sym)
    q = np.searchsorted(F_["t"], T, side="right") - 1
    ok = q >= 0
    out = {k: np.where(ok, v[np.clip(q, 0, None)], np.nan) for k, v in F_.items() if k != "t"}
    return out


def t3_hit(sym, p, T, side):
    """True where Track 3 rule p fires for a trade of `side` decided at minutes T."""
    f = feat_at(sym, T)
    with np.errstate(invalid="ignore"):
        r = p["rule"]
        if r == "spot_low":
            return (side > 0) & (f["sr7" if p["win"] == 7 else "sr30"] <= p["q"]) & (f["pz"] > 1.0)
        if r == "spot_high":
            return (side > 0) & (f["sr7" if p["win"] == 7 else "sr30"] >= p["q"])
        if r == "crowd_long":
            hot = (f["pz"] > p["z"]) if p["trig"] == "prem" else (f["fund"] > 0.0003)
            return (side > 0) & (f["rank90"] > p["r"]) & hot
        if r == "squeeze_short":
            return (side < 0) & (f["pz"] < -p["z"])
        if r == "vol":
            return f["vr"] > p["v"]
    raise ValueError(r)


def make_skip(spec, sym):
    if spec.get("t3") is None or spec["p"].get("act") != "skip":
        return None
    p = spec["p"]
    return lambda c, s: t3_hit(sym, p, c["t"] + 240, s)


def job(args):
    """One engine run: (spec, sym, shift) -> trades."""
    spec, sym, shift = args
    if any(s != sym for s in L._M):
        L._M.clear()
        import families as F
        F._rs.cache_clear(); F._M1.clear()
        import gc; gc.collect()
    pc = spec.get("per_coin", {}).get(sym, {})
    g = lambda k: pc.get(k, spec.get(k))
    sk = None
    if spec.get("t3list"):
        rules = spec["t3list"]
        sk = lambda c, sd: np.any([t3_hit(sym, r, c["t"] + 240, sd) for r in rules], axis=0)
    x = V.trades30(sym, kwL=g("kwL"), kwS=g("kwS"), exL=g("exL"), exS=g("exS"), shift=shift,
                   ctrl=make_ctrl(spec, sym, shift), skipx=sk or make_skip(spec, sym))
    return spec["id"], sym, shift, x[KEEP]


def run_jobs(specs, shifts=(0,), coins_of=None):
    """All (spec, coin, shift) engine runs in parallel; returns {id: {shift: DataFrame of the spec's coins}}."""
    tasks = []
    for sp in specs:
        for s in (coins_of(sp) if coins_of else sp.get("coins", COINS)):
            for sh in shifts:
                tasks.append((sp, s, sh))
    tasks.sort(key=lambda z: (z[1], z[2]))
    out = {}
    with Pool(PROCS) as pool:
        for k, (i, s, sh, x) in enumerate(pool.imap_unordered(job, tasks, chunksize=4)):
            out.setdefault(i, {}).setdefault(sh, []).append(x)
            if (k + 1) % 2000 == 0:
                log(f"  {k + 1}/{len(tasks)} runs")
    return {i: {sh: pd.concat(v, ignore_index=True) for sh, v in d.items()} for i, d in out.items()}


def portfolio(var, coins, shift):
    """The 5-coin list at a shift: the spec's coins from `var`, the others from the base."""
    B = base_at(shift)
    return pd.concat([B[~B.sym.isin(coins)], var[var.sym.isin(coins)]], ignore_index=True)


# ══ scoring ═══════════════════════════════════════════════════════════════════════════════════════════════════════
_BS = {}


def base_score(shift, mult=None):
    if shift not in _BS:
        _BS[shift] = V.score(base_at(shift))
    return _BS[shift]


def xpair(X, shift, dev, mult=None, smult=0.5):
    s = V.score(X, mult=mult, smult=smult); b = base_score(shift)
    x = V.xr(s, b)
    return x[dev], x[P24], s


def plateau(df, ords, cats, flag):
    """Share of grid neighbours with flag True (ordinal: Chebyshev 1; categorical: differ in exactly one)."""
    vals = {a: sorted(df[a].dropna().unique().tolist(), key=lambda v: (str(type(v)), v)) for a in ords}
    pos = {a: {v: i for i, v in enumerate(vals[a])} for a in ords}
    keys = df[ords + cats].to_records(index=False)
    fl = df[flag].to_numpy()
    out = np.full(len(df), np.nan)
    for i, ki in enumerate(keys):
        nb = []
        for j, kj in enumerate(keys):
            if i == j:
                continue
            dc = sum(ki[len(ords) + q] != kj[len(ords) + q] for q in range(len(cats)))
            if any(pd.isna(ki[q]) != pd.isna(kj[q]) for q in range(len(ords))):
                continue
            do = max([abs(pos[a][ki[q]] - pos[a][kj[q]]) for q, a in enumerate(ords) if not pd.isna(ki[q])] or [0])
            if (dc == 0 and do == 1) or (dc == 1 and do == 0):
                nb.append(fl[j])
        out[i] = np.mean(nb) if nb else np.nan
    return out


def phase_win(get_X, dev, mult_fn=None):
    """Share of the 40 phase copies with x > 1, per period. get_X(shift) -> trades."""
    w = []
    for sh in SH:
        X = get_X(sh)
        m = mult_fn(X) if mult_fn else None
        xd, xo, _ = xpair(X, sh, dev, mult=m)
        w.append((xd > 1, xo > 1))
    w = np.array(w, float)
    return float(w[:, 0].mean()), float(w[:, 1].mean())


# ══ money ═════════════════════════════════════════════════════════════════════════════════════════════════════════
_MB = {}


def money_base():
    if "b" not in _MB:
        f = CACHE / "money_base.pkl"
        if f.exists():
            _MB["b"] = pd.read_pickle(f)
        else:
            A = V.with_sleeve(V.rows(base_at(0)))
            _MB["b"] = V.money_all(A, V.base_policy()); pd.to_pickle(_MB["b"], f)
    return _MB["b"]


def g6_job(args):
    name, A, pol = args
    return name, V.g6(A, pol, money_base())


def g6_many(items):
    """items: [(name, rows incl. sleeve, policy)] -> DataFrame of drawdown-matched money rows."""
    money_base()
    with Pool(PROCS) as pool:
        res = pool.map(g6_job, items, chunksize=1)
    return pd.DataFrame([dict(id=n, **r) for n, r in res]).set_index("id")


def money_row_base():
    b = money_base()
    return pd.DataFrame([dict(id="BASE v2.8+v2.7", k=1.0, G6=np.nan, matched=np.nan, **b)]).set_index("id")


# ══ generic evaluation of engine / sizing candidates ═════════════════════════════════════════════════════════════
def evaluate(name, specs, ords, cats, dev, runs=None, mult_fn=None, null_fn=None, phase=True, top=30, extra_cols=None):
    """specs: dicts with id, p (grid params), coins, and engine keys. runs: {id: {0: trades}} (else run here).
    mult_fn(spec, X) -> per-trade risk multipliers (sizing rules). null_fn(spec, X, rng) -> (X', mult') random null."""
    log(f"[{name}] {len(specs)} configs: shift-0 runs")
    engine_specs = [s for s in specs if s.get("engine", True)]
    runs = dict(runs or {})
    todo = [s for s in engine_specs if s["id"] not in runs]
    if todo:
        runs.update(run_jobs(todo))
    rows = []
    for sp in specs:
        X = portfolio(runs[sp["id"]][0], sp.get("coins", COINS), 0) if sp.get("engine", True) else base_at(0)
        m = mult_fn(sp, X) if mult_fn else None
        xd, xo, s = xpair(X, 0, dev, mult=m)
        rows.append(dict(id=sp["id"], **sp["p"], x_dev=xd, x_oos=xo, net_dev=s[dev]["net"], dd_dev=s[dev]["dd"], net_oos=s[P24]["net"],
                         dd_oos=s[P24]["dd"], n_dev=s[dev]["n"], n_oos=s[P24]["n"]))
    R = pd.DataFrame(rows)
    R["E1"] = (R.x_dev > 1) & (R.x_oos > 1)
    R["plateau"] = plateau(R, ords, cats, "E1")
    R["E2"] = R.plateau >= 0.6
    R["minx"] = R[["x_dev", "x_oos"]].min(axis=1)
    cand = R[R.E1 & R.E2].sort_values("minx", ascending=False).head(top)
    show = set(cand.id) | set(R.sort_values("minx", ascending=False).id.head(3))
    byid = {s["id"]: s for s in specs}
    if phase and show:
        log(f"[{name}] phase copies for {len(show)} configs")
        ph_specs = [byid[i] for i in show if byid[i].get("engine", True)]
        ph = run_jobs(ph_specs, shifts=SH) if ph_specs else {}
        for i in show:
            sp = byid[i]
            if sp.get("engine", True):
                gx = lambda sh, sp=sp: portfolio(ph[sp["id"]][sh], sp.get("coins", COINS), sh)
            else:
                gx = base_at
            pw = phase_win(gx, dev, (lambda X, sp=sp: mult_fn(sp, X)) if mult_fn else None)
            R.loc[R.id == i, ["phase_dev", "phase_oos"]] = pw
    if null_fn is not None and show:
        log(f"[{name}] nulls for {len(show)} configs")
        for i in show:
            sp = byid[i]
            X = portfolio(runs[i][0], sp.get("coins", COINS), 0) if sp.get("engine", True) else base_at(0)
            rng = np.random.default_rng(abs(hash(i)) % 2 ** 32)
            real = float(R.loc[R.id == i, "minx"].iloc[0]); d = []
            for _ in range(200):
                Xn, mn = null_fn(sp, X, rng)
                a, b, _ = xpair(Xn, 0, dev, mult=mn); d.append(min(a, b))
            R.loc[R.id == i, "null_pct"] = float(np.mean(np.array(d) < real))
    if "phase_dev" not in R:
        R["phase_dev"] = np.nan; R["phase_oos"] = np.nan
    R["E3"] = (R.phase_dev >= 0.7) & (R.phase_oos >= 0.7)
    if null_fn is not None:
        if "null_pct" not in R:
            R["null_pct"] = np.nan
        R["E3"] &= R.null_pct >= 0.95
    return R, runs


def money_for(name, R, specs, runs, mult_fn=None, pol_fn=None, ids=None):
    """E4 for the E1-E3 passers (+ the best 3 by minx, for the record)."""
    byid = {s["id"]: s for s in specs}
    ids = ids if ids is not None else list(dict.fromkeys(list(R[R.E1 & R.E2 & R.E3].id) + list(R.sort_values("minx", ascending=False).id.head(3))))
    items = []
    for i in ids:
        sp = byid[i]
        X = portfolio(runs[i][0], sp.get("coins", COINS), 0) if sp.get("engine", True) else base_at(0)
        m = mult_fn(sp, X) if mult_fn else None
        A = V.with_sleeve(V.rows(X, mult=m))
        pol = pol_fn(sp) if pol_fn else V.base_policy()
        items.append((i, A, pol))
    if not items:
        return pd.DataFrame()
    log(f"[{name}] money (drawdown-matched) for {len(items)} configs")
    M = g6_many(items)
    return M


def finish(name, R, M, cols_first):
    if len(M):
        R = R.merge(M.add_prefix("M_"), left_on="id", right_index=True, how="left")
        R["E4"] = R.get("M_G6", False).fillna(False).astype(bool)
    else:
        R["E4"] = False
    R["PASS"] = R.E1 & R.E2 & R.E3 & R.E4
    R.to_csv(RES / f"v30_{name}.csv", index=False)
    n = len(R)
    log(f"[{name}] funnel: {n} -> E1 {int(R.E1.sum())} -> +E2 {int((R.E1 & R.E2).sum())} -> +E3 {int((R.E1 & R.E2 & R.E3).sum())} -> "
        f"+E4 PASS {int(R.PASS.sum())}")
    show = R.sort_values(["PASS", "minx"], ascending=False).head(12)
    cols = [c for c in cols_first + ["x_dev", "x_oos", "plateau", "phase_dev", "phase_oos", "null_pct", "E1", "E2", "E3", "M_k",
                                     "M_m2022", "M_dd2022", "M_m2024", "M_dd2024", "M_boot_med", "M_boot_p10", "M_boot_dd90", "E4", "PASS"] if c in show]
    print(show[cols].round(3).to_string(index=False), flush=True)
    return R


# ══ BASE: phase-shifted base trades + base money ═════════════════════════════════════════════════════════════════
def stage_base():
    CACHE.mkdir(parents=True, exist_ok=True)
    log("base: 5 coins x 41 phases")
    r = run_jobs([dict(id="base", p={})], shifts=[0] + SH)["base"]
    for sh, X in r.items():
        X.to_pickle(CACHE / f"base_s{sh}.pkl")
    import botsim as B
    X0 = r[0]
    same = len(X0) == len(B.T) and np.allclose(np.sort(X0.R.values), np.sort(B.T.R.values))
    log(f"base shift 0: {len(X0)} trades, equal to the v2.8 list: {same}")
    f = CACHE / "money_base.pkl"
    if f.exists():
        f.unlink()
    log(f"base money: {money_base()}")


# ══ TRACK 1 — cross-coin interaction ════════════════════════════════════════════════════════════════════════════
def breadth_mult(p, X):
    """Per-trade multiplier: boost when another coin of `ref` entered the same direction within W hours BEFORE this trade
    (W = 0: since the start of this trade's 4h candle); solo alt trades (BTC and ETH both flat at the entry) x solo."""
    X = X.reset_index(drop=True)
    et = _mins(X.entry_time); xt = _mins(X.exit_time); d = X.dir.to_numpy(); sym = X.sym.to_numpy()
    ref = {"any": set(COINS), "BTC": {"BTCUSDT"}, "BTC+ETH": {"BTCUSDT", "ETHUSDT"}}[p["ref"]]
    o = np.argsort(et, kind="stable")
    m = np.ones(len(X))
    for ii, i in enumerate(o):
        lo = (et[i] // 240) * 240 if p["W"] == 0 else et[i] - p["W"] * 60
        co = False
        for jj in range(ii - 1, -1, -1):
            j = o[jj]
            if et[j] < lo:
                break
            if sym[j] != sym[i] and sym[j] in ref and d[j] == d[i] and et[j] < et[i]:
                co = True; break
        if co:
            m[i] = p["boost"]
        elif sym[i] in ALT:
            lead_open = ((np.isin(sym, MAJ)) & (et < et[i]) & (xt > et[i])).any()
            if not lead_open:
                m[i] = p["solo"]
    return m


def t1():
    specs = []
    for leader, cond, to_btc in itertools.product(("BTC", "BTC+ETH"), ("open", "be"), (0, 1)):
        specs.append(dict(id=f"veto_{leader}_{cond}_{to_btc}", p=dict(leader=leader, cond=cond, to_btc=to_btc), ctrl="veto",
                          coins=COINS if to_btc else COINS[1:]))
    Rv, runs_v = evaluate("T1a_veto", specs, [], ["leader", "cond", "to_btc"], P20,
                          null_fn=lambda sp, X, rng: null_remove(sp, X, rng))
    Mv = money_for("T1a_veto", Rv, specs, runs_v)
    Rv = finish("T1a_veto", Rv, Mv, ["id"])
    # base facts behind the premise: alt / ETH entries opposite an open BTC trade
    B0 = base_at(0); bt = B0[B0.sym == "BTCUSDT"]
    rows = []
    for _, r in B0[B0.sym != "BTCUSDT"].iterrows():
        o_ = bt[(bt.entry_time < r.entry_time) & (bt.exit_time > r.entry_time) & (bt.dir != r.dir)]
        if len(o_):
            rows.append(dict(sym=r.sym, entry_time=r.entry_time, dir=r.dir, R=r.R, btc_at_be=bool((o_.be_time < r.entry_time).any())))
    Pm = pd.DataFrame(rows)
    Pm.to_csv(RES / "v30_T1_premise_opposite_btc.csv", index=False)
    log(f"premise: entries opposite an open BTC trade: n {len(Pm)}, win {(Pm.R > 0).mean():.0%}, sum R {Pm.R.sum():+.2f}; "
        f"with BTC past +1.5R: n {int(Pm.btc_at_be.sum())}, sum R {Pm[Pm.btc_at_be].R.sum():+.2f}, win {(Pm[Pm.btc_at_be].R > 0).mean():.0%}")

    specs = [dict(id=f"active_{ld}_{ac}", p=dict(leader=ld, action=ac), ctrl="active", coins=COINS[1:])
             for ld, ac in itertools.product(("BTC", "BTC+ETH"), ("close", "be", "m03"))]
    Ra, runs_a = evaluate("T1b_active", specs, [], ["leader", "action"], P20)
    Ra = active_null(Ra, specs, runs_a)
    Ma = money_for("T1b_active", Ra, specs, runs_a)
    Ra = finish("T1b_active", Ra, Ma, ["id"])

    specs = []
    for ref, W, boost, solo in itertools.product(("any", "BTC", "BTC+ETH"), (0, 4, 8, 12), (1.0, 1.15, 1.25, 1.35), (0.7, 0.8, 0.9, 1.0)):
        if boost == 1.0 and solo == 1.0:
            continue
        specs.append(dict(id=f"breadth_{ref}_W{W}_b{boost}_s{solo}", p=dict(ref=ref, W=W, boost=boost, solo=solo), engine=False))
    mf = lambda sp, X: breadth_mult(sp["p"], X)
    Rb, _ = evaluate("T1c_breadth", specs, ["W", "boost", "solo"], ["ref"], P20, mult_fn=mf,
                     null_fn=lambda sp, X, rng: (X, rng.permutation(breadth_mult(sp["p"], X))))
    Mb = money_for("T1c_breadth", Rb, specs, {}, mult_fn=mf)
    Rb = finish("T1c_breadth", Rb, Mb, ["id"])

    specs = [dict(id=f"cool_{h}h_m{mo}_R{cr}", p=dict(cool_h=h, mode=mo, cool_R=cr), ctrl="cool")
             for h, mo, cr in itertools.product((4, 8, 12, 16), (1, 2, 3), (-0.5, -0.8))]
    Rc, runs_c = evaluate("T1d_cooldown", specs, ["cool_h", "cool_R"], ["mode"], P20)
    Mc = money_for("T1d_cooldown", Rc, specs, runs_c)
    Rc = finish("T1d_cooldown", Rc, Mc, ["id"])
    pickle.dump(dict(veto=runs_v, active=runs_a, cool=runs_c), open(CACHE / "t1_runs.pkl", "wb"))


def null_remove(sp, X, rng):
    """Null for removal rules: from the base, remove the same number of trades per coin and side at random (the trades the
    rule ADDS are kept)."""
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


def active_null(R, specs, runs):
    """Null for the active-exit rules: the same number of actions per coin and side at random minutes (100 draws)."""
    R["null_pct"] = np.nan
    show = R.sort_values("minx", ascending=False).id.head(3).tolist() + R[R.E1 & R.E2].id.tolist()
    byid = {s["id"]: s for s in specs}
    B = base_at(0)
    for i in dict.fromkeys(show):
        sp = byid[i]; lead = sp["p"]["leader"]
        n_l, n_s = {}, {}
        for s in COINS[1:]:
            X = B[B.sym.isin(leaders_for(s, lead))]
            n_l[s] = int((X.dir < 0).sum()); n_s[s] = int((X.dir > 0).sum())
        nulls = [dict(id=f"{i}_null{q}", p=dict(sp["p"], seed=q, n_l=n_l, n_s=n_s), ctrl="randexit", coins=COINS[1:]) for q in range(100)]
        rr = run_jobs(nulls)
        d = []
        for ns in nulls:
            a, b, _ = xpair(portfolio(rr[ns["id"]][0], COINS[1:], 0), 0, P20); d.append(min(a, b))
        R.loc[R.id == i, "null_pct"] = float(np.mean(np.array(d) < float(R.loc[R.id == i, "minx"].iloc[0])))
    R["E3"] = R.E3 & (R.null_pct >= 0.95)
    return R


# ══ TRACK 2 — majors vs alts, long vs short geometry, short sizing ═════════════════════════════════════════════════
GROUPS = {"all": COINS, "majors": MAJ, "alts": ALT}


def t2():
    # 2a entry geometry, one joint run per config (all 5 coins), scored as all / majors-only / alts-only changes
    base_p = dict(nL=20, nS=20, eL=50, eS=50, xS=4.0)
    grid = list(itertools.product((15, 18, 20, 24, 30), (12, 15, 18, 20, 25), (40, 50, 65), (30, 40, 50), (3.0, 3.5, 4.0, 5.0)))
    eng = []
    for nL, nS, eL, eS, xS in grid:
        p = dict(nL=nL, nS=nS, eL=eL, eS=eS, xS=xS)
        eng.append(dict(id="geo_" + "_".join(f"{k}{v}" for k, v in p.items()), p=p,
                        kwL=dict(n=nL, ema_n=eL), kwS=dict(n=nS, ema_n=eS, max_ext=xS)))
    log(f"[T2a] {len(eng)} geometry configs x 5 coins")
    runs = run_jobs(eng)
    for g, coins in GROUPS.items():
        specs = [dict(sp, id=f"{sp['id']}@{g}", p=dict(sp["p"], grp=g), coins=coins) for sp in eng if sp["p"] != base_p]
        rr = {s["id"]: runs[s["id"].split("@")[0]] for s in specs}
        R, rr = evaluate(f"T2a_geometry_{g}", specs, ["nL", "nS", "eL", "eS", "xS"], ["grp"], P20, runs=rr, top=20)
        M = money_for(f"T2a_geometry_{g}", R, specs, rr)
        finish(f"T2a_geometry_{g}", R, M, ["id"])
    # 2b exit geometry per side
    eng = []
    for side, be, lk, lt, st, l2 in itertools.product(("long", "short", "both"), (1.25, 1.5, 1.75), (4.5, 5.0, 5.5), (1.5, 2.0), (0, 48, 60), (0, 1)):
        ex = dict(be_R=be, lock_R=lk, lock_to=lt, stale_h=st, stale_to=0.0, lock2_R=8.0 if l2 else 0.0, lock2_to=3.5 if l2 else 0.0)
        p = dict(side=side, be=be, lk=lk, lt=lt, st=st, l2=l2)
        if (be, lk, lt, st, l2) == (1.5, 5.0, 1.5, 0, 0):
            continue
        eng.append(dict(id="exit_" + "_".join(f"{k}{v}" for k, v in p.items()), p=p,
                        exL=ex if side in ("long", "both") else None, exS=ex if side in ("short", "both") else None))
    log(f"[T2b] {len(eng)} exit configs x 5 coins")
    runs = run_jobs(eng)
    for g, coins in GROUPS.items():
        specs = [dict(sp, id=f"{sp['id']}@{g}", p=dict(sp["p"], grp=g), coins=coins) for sp in eng]
        rr = {s["id"]: runs[s["id"].split("@")[0]] for s in specs}
        R, rr = evaluate(f"T2b_exits_{g}", specs, ["be", "lk", "lt", "st"], ["side", "l2", "grp"], P20, runs=rr, top=20)
        M = money_for(f"T2b_exits_{g}", R, specs, rr)
        finish(f"T2b_exits_{g}", R, M, ["id"])
    # 2c short sizing per tier (+ ETH exempt from the cap on shorts), drawdown-matched
    specs = []
    for b, e, a, ex in itertools.product((0.5, 0.65, 0.75, 0.85, 1.0), (0.5, 0.65, 0.75, 0.85, 1.0), (0.35, 0.5), (0, 1)):
        if (b, e, a, ex) == (0.5, 0.5, 0.5, 0):
            continue
        specs.append(dict(id=f"short_b{b}_e{e}_a{a}_ex{ex}", p=dict(btc_s=b, eth_s=e, alt_s=a, ethex=ex), engine=False))
    sm = lambda p: {"BTCUSDT": p["btc_s"], "ETHUSDT": p["eth_s"], "alt": p["alt_s"]}
    mf = lambda sp, X: np.where(X.dir.to_numpy() < 0, X.sym.map(lambda s: sm(sp["p"]).get(s, sp["p"]["alt_s"])).to_numpy(float) / 0.5, 1.0)

    def nullf(sp, X, rng):
        m = mf(sp, X); sh = (X.dir.to_numpy() < 0)
        m2 = m.copy(); m2[sh] = rng.permutation(m[sh]); return X, m2
    R, _ = evaluate("T2c_short_sizing", specs, ["btc_s", "eth_s", "alt_s"], ["ethex"], P20, mult_fn=mf, null_fn=nullf, top=40)
    polf = lambda sp: V.base_policy(smult=[sp["p"]["btc_s"], sp["p"]["eth_s"]] + [sp["p"]["alt_s"]] * 3,
                                    exempt_short={0, 1} if sp["p"]["ethex"] else None)
    ids = list(R.id)                                                   # money for ALL 100 (the point of the re-test)
    byid = {s["id"]: s for s in specs}
    items = [(i, V.with_sleeve(V.rows(base_at(0))), polf(byid[i])) for i in ids]
    log(f"[T2c] money (drawdown-matched) for {len(items)} sizing policies")
    M = g6_many(items)
    finish("T2c_short_sizing", R, M, ["id"])


# ══ TRACK 3 — microstructure filters on TBO ══════════════════════════════════════════════════════════════════════
def t3_rules():
    out = []
    for win, q, act in itertools.product((7, 30), (0.1, 0.2), ("skip", "half")):
        out.append(dict(rule="spot_low", win=win, q=q, act=act))
    for win, q in itertools.product((7, 30), (0.7, 0.5)):
        out.append(dict(rule="spot_high", win=win, q=q, act="boost"))
    for r, z, act in itertools.product((0.85, 0.90), (1.5, 2.0), ("skip", "half")):
        out.append(dict(rule="crowd_long", r=r, z=z, trig="prem", act=act))
    for r, act in itertools.product((0.85, 0.90), ("skip", "half")):
        out.append(dict(rule="crowd_long", r=r, z=np.nan, trig="fund", act=act))
    for z, act in itertools.product((1.5, 2.0), ("skip", "half")):
        out.append(dict(rule="squeeze_short", z=z, act=act))
    for v, act in itertools.product((1.3, 1.5, 1.8, 2.0), ("skip", "half")):
        out.append(dict(rule="vol", v=v, act=act))
    return out


def t3_mult(p, X):
    if p["act"] == "skip":
        return None
    T = _mins(X.entry_time)
    m = np.ones(len(X))
    for s in X.sym.unique():
        k = (X.sym == s).to_numpy()
        hit = t3_hit(s, p, T[k], X.dir.to_numpy()[k])
        m[k] = np.where(hit, 1.25 if p["act"] == "boost" else 0.5, 1.0)
    return m


def t3():
    rules = t3_rules()
    specs = []
    for p in rules:
        nm = "_".join(f"{k}{v}" for k, v in p.items() if not (isinstance(v, float) and np.isnan(v)))
        specs.append(dict(id=nm, p=p, t3=True, engine=p["act"] == "skip"))
    mf = lambda sp, X: t3_mult(sp["p"], X)

    def nullf(sp, X, rng):
        if sp["p"]["act"] == "skip":
            return null_remove(sp, X, rng)
        m = t3_mult(sp["p"], X)
        out = m.copy()
        for (s, d), g in X.groupby(["sym", "dir"]):
            ix = g.index.to_numpy(); out[ix] = rng.permutation(m[ix])
        return X, out
    R_all = []
    for fam in ("spot_low", "spot_high", "crowd_long", "squeeze_short", "vol"):
        sp_f = [s for s in specs if s["p"]["rule"] == fam]
        ords = {"spot_low": ["q"], "spot_high": ["q"], "crowd_long": ["r", "z"], "squeeze_short": ["z"], "vol": ["v"]}[fam]
        cats = {"spot_low": ["win", "act"], "spot_high": ["win"], "crowd_long": ["trig", "act"], "squeeze_short": ["act"], "vol": ["act"]}[fam]
        R, runs = evaluate(f"T3_{fam}", sp_f, ords, cats, P22, mult_fn=lambda sp, X: t3_mult(sp["p"], X), null_fn=nullf)
        M = money_for(f"T3_{fam}", R, sp_f, runs, mult_fn=lambda sp, X: t3_mult(sp["p"], X))
        R_all.append(finish(f"T3_{fam}", R, M, ["id"]))
    t3u(specs)


def t3u(specs=None):
    if specs is None:
        specs = [dict(id='_'.join(f'{k}{v}' for k, v in p.items() if not (isinstance(v, float) and np.isnan(v))), p=p, t3=True, engine=p['act'] == 'skip') for p in t3_rules()]
    # untouched / wider universes (shown): the same rules on the 7 other DEV12 coins and the 14 HOLD_BIG coins
    other = [s for s in H.DEV12 if s not in COINS] + H.HOLD_BIG
    log(f"[T3] universes: base + {len(specs)} rules on {len(other)} coins")
    bsp = dict(id="u_base", p={}, coins=other)
    ue = [dict(s, id="u_" + s["id"], coins=other) for s in specs if s["engine"]]
    rr = run_jobs([bsp] + ue)
    Bu = rr["u_base"][0]
    rows = []
    for s in specs:
        X = rr["u_" + s["id"]][0] if s["engine"] else Bu
        m = t3_mult(s["p"], X)
        for univ, cs in (("DEV7", [c for c in H.DEV12 if c not in COINS]), ("HOLD_BIG", H.HOLD_BIG)):
            Xu, Bx = X[X.sym.isin(cs)], Bu[Bu.sym.isin(cs)]
            mu = None if m is None else m[X.sym.isin(cs).to_numpy()]
            sv = L.score(Xu, L.units(Xu, w={c: 1.0 for c in cs}) * (1 if mu is None else mu)); sb = L.score(Bx, L.units(Bx, w={c: 1.0 for c in cs}))
            x = V.xr(sv, sb)
            rows.append(dict(id=s["id"], univ=univ, x22=x[P22], x24=x[P24], base_ratio22=sb[P22]["ratio"], base_ratio24=sb[P24]["ratio"]))
    U = pd.DataFrame(rows).pivot(index="id", columns="univ", values=["x22", "x24"])
    U.columns = [f"{a}_{b}" for a, b in U.columns]
    U.to_csv(RES / "v30_T3_universes.csv")
    print(U.round(3).to_string(), flush=True)


# ══ TRACK 4 — panic sleeve: universes, hybrid shares, ranking, multi-horizon flush windows ══════════════════════════
P0 = dict(PS.DEFAULTS)
SLIP4 = {"BTCUSDT": 0.0001, "ETHUSDT": 0.0001}
EXTRA7 = [s for s in H.DEV12 if s not in COINS]
_HC = {}


def _hdata(sym):
    if sym not in _HC:
        df = H.hourly(sym)
        o, h, l, c = (df[k].to_numpy(float) for k in "ohlc")
        _HC[sym] = (df, o, h, l, c, PS.atr(h, l, c))
    return _HC[sym]


def panic_trade(sym, i):
    """v2.7 exits for an entry at the open after hour i: (t, t_exit, ret) or None (as panic_rank_v29.candidates)."""
    df, o, h, l, c, a_ = _hdata(sym)
    Hh = int(P0["hold_h"])
    if i + 1 + Hh + 1 >= len(o) or not np.isfinite(a_[i]):
        return None
    e = o[i + 1]; a = a_[i]; s = max(e - P0["stop_atr"] * a, e * (1 - P0["stop_max"])); tg = e + P0["tp_atr"] * a
    best = e; px = None
    for jj in range(i + 1, i + 1 + Hh):
        if l[jj] <= s:
            px, j = s, jj; break
        if h[jj] >= tg:
            px, j = tg, jj; break
        best = max(best, h[jj])
        if best >= e + P0["be_atr"] * a:
            s = max(s, e)
    if px is None:
        px, j = o[i + 1 + Hh], i + 1 + Hh
    return df.index[i + 1], df.index[j], px / e - 1 - 2 * (0.0005 + SLIP4.get(sym, 0.0003))


_CW = {}


def cands_mw(sym, wins):
    """Signal hours of the multi-window trigger (OR over wins = [(L hours, OI drop, premium z)]) with their v2.7 trades.
    doi column = -(severity) x 0.12, severity = max over the firing windows of |doi| / threshold (= |doi| for v2.7 alone)."""
    key = (sym, tuple(wins))
    if key in _CW:
        return _CW[key]
    df, o, h, l, c, a_ = _hdata(sym)
    sig = np.zeros(len(c), bool); sev = np.zeros(len(c)); pz = None
    for L_, thr, pzt in wins:
        f = PS.features(h, l, c, df.oi.to_numpy(float), df.prem.to_numpy(float), L_)
        s = PS.signal(f, move_k=P0["move_k"], oi_drop=thr, premium_z=pzt)
        with np.errstate(invalid="ignore"):
            sev = np.where(s, np.fmax(sev, np.abs(f["doi"]) / thr * 0.12), sev)
        sig |= s
        pz = f["pz"]
    rows = []
    for i in np.flatnonzero(sig):
        tr = panic_trade(sym, i)
        if tr:
            rows.append((tr[0], tr[1], sym, tr[2], -sev[i], pz[i]))
    out = pd.DataFrame(rows, columns=["t", "t_exit", "sym", "ret", "doi", "pz"])
    _CW[key] = out
    return out


W27 = [(4, 0.12, -1.0)]


def t4_events(p, rng=None):
    """Sleeve trades of a Track 4 config p: univ, cap, rank, share, wins."""
    import panic_rank_v29 as U4
    univ = {"OUR5": COINS, "DEV12": H.DEV12, "HYB7": H.DEV12, "LIQ26": H.DEV12 + H.HOLD_BIG, "HYB26": H.DEV12 + H.HOLD_BIG,
            "HOLD_BIG": H.HOLD_BIG}[p["univ"]]
    cd = pd.concat([cands_mw(s, p.get("wins", W27)) for s in univ], ignore_index=True)
    E = U4.select(cd, None if p["cap"] == 0 else int(p["cap"]), p["rank"], rng=rng, units=3.0)
    if p["univ"] in ("HYB7", "HYB26") and len(E):
        grp = np.where(E.sym.isin(COINS), "core", "extra")
        E = E.assign(_g=grp)
        ng = E.groupby(["t", "_g"]).sym.transform("count")
        E["w"] = 3.0 * np.where(E._g == "core", 1.0, p["share"]) / ng
        E = E.drop(columns="_g")
    return E


def ev_score(E):
    """Fixed-unit per-event-split account: P&L per trade = ret / 5% x w (w = units split over the coins of the hour)."""
    out = {}
    for k, (a, b) in {P22: ("2022-01-01", "2024-01-01"), P24: ("2024-01-01", V.END)}.items():
        g = E[(E.t >= a) & (E.t < b)].sort_values("t_exit")
        pnl = (g.ret / 0.05 * g.w).to_numpy(); e = np.cumsum(pnl)
        dd = float(np.max(np.maximum.accumulate(np.r_[0, e])[1:] - e)) if len(e) else np.nan
        ev = g.groupby("t").apply(lambda z: (z.ret / 0.05 * z.w).sum()) if len(g) else pd.Series(dtype=float)
        out[k] = dict(net=float(e[-1]) if len(e) else 0.0, dd=dd, ratio=(e[-1] / dd) if len(e) and dd else np.nan, n=len(g),
                      n_ev=int(g.t.nunique()), avg_ev=float(ev.mean()) if len(ev) else np.nan, avg_trade=float(g.ret.mean() * 100) if len(g) else np.nan)
    return out


def sleeve_rows4(E):
    m = lambda s: s.values.astype("datetime64[m]").astype(np.int64)
    return np.c_[m(E.t), m(E.t_exit), m(E.t), np.ones(len(E)), (E.ret / 0.05 * E.w / 3.0).to_numpy(), np.full(len(E), 5), np.ones(len(E))]


def t4_null_added(p, E, base_keys, rng):
    """Added-trade null: every trade not in v2.7-OUR5 is replaced by an entry at a random hour of the same coin."""
    keys = list(zip(E.sym, E.t))
    add = np.array([k not in base_keys for k in keys])
    if not add.any():
        return E
    E2 = E.copy()
    for ix in np.flatnonzero(add):
        s = E2.sym.iat[ix]; df = _hdata(s)[0]
        for _ in range(20):
            i = int(rng.integers(800, len(df) - 30))
            tr = panic_trade(s, i)
            if tr and df.index[i] >= pd.Timestamp("2022-01-01"):
                E2.iloc[ix, E2.columns.get_loc("t")] = tr[0]; E2.iloc[ix, E2.columns.get_loc("t_exit")] = tr[1]
                E2.iloc[ix, E2.columns.get_loc("ret")] = tr[2]; break
    return E2


def t4_null_job(args):
    """Null percentile (200 draws: random selection where capped + added trades at random hours) and the HOLD_BIG check."""
    cid, p, real = args
    base = dict(fam="universe", univ="OUR5", cap=0, rank="-", share=1.0, wins=W27)
    Eb = t4_events(base); sb = ev_score(Eb); base_keys = set(zip(Eb.sym, Eb.t))
    E = t4_events(p)
    rng = np.random.default_rng(int(cid.split("_")[1]))
    d = []
    for _ in range(200):
        Er = t4_events(p, rng=rng) if p["cap"] else E
        Er = t4_null_added(p, Er, base_keys, rng)
        s = ev_score(Er); d.append(min(s[P22]["ratio"] / sb[P22]["ratio"], s[P24]["ratio"] / sb[P24]["ratio"]))
    hbv = None
    if p["cap"]:
        hb = ev_score(t4_events(dict(p, univ="HOLD_BIG")))
        hu = ev_score(t4_events(dict(p, univ="HOLD_BIG", cap=0, rank="-")))
        hbv = [hb[P22]["ratio"] / hu[P22]["ratio"], hb[P24]["ratio"] / hu[P24]["ratio"], hb[P22]["avg_trade"], hb[P24]["avg_trade"]]
    return cid, float(np.mean(np.array(d) < real)), hbv


def t4_job(p):
    E = t4_events(p)
    s = ev_score(E)
    return p, E, s


def t4():
    import botsim as B
    configs = []
    for univ in ("OUR5", "DEV12", "HYB7", "LIQ26", "HYB26"):
        for cap, rank in itertools.product((0, 2, 3, 4), ("B", "C")):
            if cap == 0 and rank == "C":
                continue
            for share in ((0.5, 0.75, 1.0) if univ.startswith("HYB") else (1.0,)):
                configs.append(dict(fam="universe", univ=univ, cap=cap, rank=rank if cap else "-", share=share, wins=W27, wkey="4h"))
    wsets = {"2+4": [[(2, t2, None), (4, 0.12, -1.0)] for t2 in (0.08, 0.10)],
             "4+8": [[(4, 0.12, -1.0), (8, t8, None)] for t8 in (0.16, 0.18)],
             "4+12": [[(4, 0.12, -1.0), (12, t12, None)] for t12 in (0.20, 0.22)],
             "2+4+8": [[(2, t2, None), (4, 0.12, -1.0), (8, t8, None)] for t2 in (0.08, 0.10) for t8 in (0.16, 0.18)],
             "2+4+8+12": [[(2, t2, None), (4, 0.12, -1.0), (8, t8, None), (12, t12, None)] for t2 in (0.08, 0.10) for t8 in (0.16, 0.18) for t12 in (0.20, 0.22)]}
    for wk, lst in wsets.items():
        for w0 in lst:
            for pza in (-1.0, -1.5):
                w = [(L_, th, pza if pz_ is None else pz_) for L_, th, pz_ in w0]
                for univ, share in (("OUR5", 1.0), ("HYB7", 0.5), ("HYB7", 1.0)):
                    for cap in (0, 3):
                        configs.append(dict(fam="horizon", univ=univ, cap=cap, rank="C" if cap else "-", share=share, wins=w, wkey=wk,
                                            t2=next((th for L_, th, _ in w if L_ == 2), np.nan), t8=next((th for L_, th, _ in w if L_ == 8), np.nan),
                                            t12=next((th for L_, th, _ in w if L_ == 12), np.nan), pza=pza))
    log(f"[T4] {len(configs)} sleeve configs")
    for s in H.DEV12 + H.HOLD_BIG:
        _hdata(s)
    with Pool(PROCS) as pool:
        res = pool.map(t4_job, configs, chunksize=2)
    base = next(r for r in res if r[0]["fam"] == "universe" and r[0]["univ"] == "OUR5" and r[0]["cap"] == 0)
    Eb, sb = base[1], base[2]
    base_keys = set(zip(Eb.sym, Eb.t))
    rows, events = [], {}
    for k, (p, E, s) in enumerate(res):
        cid = f"T4_{k}"
        events[cid] = (p, E)
        x22 = s[P22]["ratio"] / sb[P22]["ratio"]; x24 = s[P24]["ratio"] / sb[P24]["ratio"]
        rows.append(dict(id=cid, **{a: v for a, v in p.items() if a != "wins"}, n22=s[P22]["n"], ev22=s[P22]["n_ev"], avg_ev22=s[P22]["avg_ev"],
                         avg_tr22=s[P22]["avg_trade"], net22=s[P22]["net"], dd22=s[P22]["dd"], n24=s[P24]["n"], avg_ev24=s[P24]["avg_ev"],
                         avg_tr24=s[P24]["avg_trade"], net24=s[P24]["net"], dd24=s[P24]["dd"], x_dev=x22, x_oos=x24))
    R = pd.DataFrame(rows)
    R = R[~((R.fam == "universe") & (R.univ == "OUR5") & (R.cap == 0))].reset_index(drop=True)
    R["E1"] = (R.x_dev > 1) & (R.x_oos > 1)
    R["minx"] = R[["x_dev", "x_oos"]].min(axis=1)
    R["capo"] = R.cap.replace(0, 9)
    pl = np.full(len(R), np.nan)
    for fam, ords, cats in (("universe", ["capo", "share"], ["univ", "rank"]), ("horizon", ["t2", "t8", "t12", "pza", "capo", "share"], ["wkey", "univ"])):
        q = R.fam == fam
        pl[q.to_numpy()] = plateau(R[q].reset_index(drop=True), ords, cats, "E1")
    R["plateau"] = pl; R["E2"] = R.plateau >= 0.6
    show = list(dict.fromkeys(R[R.E1 & R.E2].sort_values("minx", ascending=False).id.head(25).tolist() + R.sort_values("minx", ascending=False).id.head(5).tolist()))
    log(f"[T4] nulls for {len(show)} configs")
    with Pool(PROCS) as pool:
        nl = pool.map(t4_null_job, [(cid, events[cid][0], float(R.loc[R.id == cid, "minx"].iloc[0])) for cid in show], chunksize=1)
    for cid, pct, hb in nl:
        R.loc[R.id == cid, "null_pct"] = pct
        if hb is not None:
            R.loc[R.id == cid, ["hb_x22", "hb_x24", "hb_avg22", "hb_avg24"]] = hb
    R["E3"] = R.get("null_pct", pd.Series(np.nan, index=R.index)) >= 0.95
    ids = list(dict.fromkeys(R[R.E1 & R.E2 & R.E3].id.tolist() + R.sort_values("minx", ascending=False).id.head(3).tolist()
                             + R[(R.fam == "universe") & (R.univ.isin(["DEV12", "HYB7"])) & (R.cap.isin([0, 2]))].id.tolist()))
    bot = V.rows(base_at(0))
    items = []
    for cid in ids:
        A = np.r_[bot, sleeve_rows4(events[cid][1])]; A = A[np.lexsort((A[:, 5], A[:, 0]))]
        items.append((cid, A, V.base_policy()))
    log(f"[T4] money (drawdown-matched) for {len(items)} configs")
    M = g6_many(items)
    R = finish("T4_panic", R, M, ["id", "fam", "univ", "cap", "rank", "share", "wkey", "t2", "t8", "t12", "pza", "avg_ev22", "avg_ev24"])
    pickle.dump({k: events[k] for k in R[R.PASS].id}, open(CACHE / "t4_pass_events.pkl", "wb"))


# ══ TRACK 5 — three counter-cyclical sleeve archetypes (hourly, DEV12 + HOLD39) ═══════════════════════════════════
import new_sleeves_v29 as NS                                       # noqa: E402  (sim, feats, stats)
_F5 = {}
_BTCREG = {}


def btc_regime():
    """BTC daily ER20 and |close - EMA50| / ATR(1d) of the last closed day, per hour (index = hourly bars)."""
    if "r" not in _BTCREG:
        df = H.hourly("BTCUSDT")
        d1 = df[["o", "h", "l", "c"]].resample("1D").agg({"o": "first", "h": "max", "l": "min", "c": "last"}).dropna()
        cc = d1.c
        er = (cc - cc.shift(20)).abs() / cc.diff().abs().rolling(20).sum()
        e50 = cc.ewm(span=50, adjust=False).mean(); pc = cc.shift(1)
        atrd = np.fmax(d1.h - d1.l, np.fmax((d1.h - pc).abs(), (d1.l - pc).abs())).ewm(alpha=1 / 14, adjust=False).mean()
        band = (cc - e50).abs() / atrd
        _BTCREG["r"] = pd.DataFrame({"er": er, "band": band}, index=d1.index + pd.Timedelta(days=1))   # known from the day's end
    return _BTCREG["r"]


def f5(sym):
    if sym in _F5:
        return _F5[sym]
    F_ = dict(NS.feats(sym))
    df = F_["df"]; h, l, c = F_["h"], F_["l"], F_["c"]
    F_["atr1"] = PS.atr(h, l, c)
    F_["fund"] = df.fund.to_numpy(float)
    q4 = df[["c"]].resample("4h").last().dropna()
    e20 = q4.c.ewm(span=20, adjust=False).mean().to_numpy()
    end4 = (q4.index + pd.Timedelta(hours=4)).values; tclose = (df.index + pd.Timedelta(hours=1)).values
    k4 = np.searchsorted(end4, tclose, side="right") - 1
    F_["ema20_4"] = np.where(k4 >= 20, e20[np.clip(k4, 0, None)], np.nan)
    for N in (8, 16):
        F_[f"hh{N}"] = pd.Series(h).rolling(N).max().shift(1).to_numpy()
    oi = df.oi.ffill().to_numpy(float)
    for w in (2, 4):
        prev = np.r_[np.full(w, np.nan), oi[:-w]]; cp = np.r_[np.full(w, np.nan), c[:-w]]
        with np.errstate(invalid="ignore", divide="ignore"):
            F_[f"doi{w}"] = oi / prev - 1
            F_[f"mv{w}"] = (c - cp) / F_["atr1"]
    rg = btc_regime()
    kd = np.searchsorted(rg.index.values, tclose, side="right") - 1
    F_["btc_er"] = np.where(kd >= 0, rg.er.to_numpy()[np.clip(kd, 0, None)], np.nan)
    F_["btc_band"] = np.where(kd >= 0, rg.band.to_numpy()[np.clip(kd, 0, None)], np.nan)
    # panic flush events for N1: v2.7 signal / loose (4h OI <= -10% and premium z <= -1), first trigger per 24 h
    f4 = PS.features(h, l, c, df.oi.to_numpy(float), df.prem.to_numpy(float), 4)
    with np.errstate(invalid="ignore"):
        loose = (f4["doi"] <= -0.10) & (f4["pz"] <= -1.0)
    for nm, s in (("ev_v27", F_["panic"]), ("ev_loose", np.nan_to_num(loose).astype(bool))):
        idx = np.flatnonzero(s); keep = []
        for i in idx:
            if not keep or i - keep[-1] > 24:
                keep.append(i)
        F_[nm] = np.array(keep, np.int64)
    _F5[sym] = F_
    return F_


N1G = dict(trig=("v27", "loose"), hc=(6, 9, 12), m=(0.5, 1.0), slm=("low", "atr"), H=(48, 72, 96))
N2G = dict(src=("fund", "prem"), lvl=(0, 1, 2), o=(0.01, 0.02, 0.03), N=(8, 12, 16), ex=("tp3_24", "tp3_48", "run_24", "run_48"))
N3G = dict(reg=("er20", "er25", "band"), w=(2, 4), M=(2.0, 2.5, 3.0), x=(-0.03, -0.06), H=(8, 12, 16))
N_GRIDS = {"N1": N1G, "N2": N2G, "N3": N3G}
N_ORD = {"N1": ["hc", "m", "H"], "N2": ["lvl", "o", "N"], "N3": ["M", "x", "H", "w"]}
N_CAT = {"N1": ["trig", "slm"], "N2": ["src", "ex"], "N3": ["reg"]}
N2LVL = {"fund": (0.0, -0.00005, -0.0001), "prem": (-0.3, -0.6, -1.0)}


def n_exit(fam, p):
    if fam == "N1":
        return dict(tp_R=0.0, be_R=1.5, hold=p["H"])
    if fam == "N2":
        return dict(tp_R=3.0 if p["ex"].startswith("tp3") else 0.0, be_R=1.25, hold=int(p["ex"].split("_")[1]))
    return dict(tp_R=2.0 / 1.5, be_R=0.0, hold=p["H"])


def n_signals(fam, sym, p, rng=None, pre=False):
    """(i, dir, dist) at hourly decision bars; entry at the next open. rng: random-entry null from the pre-condition hours."""
    F_ = f5(sym); c = F_["c"]; A4 = F_["A4"]; n = len(c)
    with np.errstate(invalid="ignore"):
        if fam == "N1":
            ev = F_["ev_" + p["trig"]]; I, D = [], []
            for i0 in ev:
                e = F_["o"][min(i0 + 1, n - 1)]; a1 = F_["atr1"][i0]
                win = np.arange(i0 + 6, min(i0 + p["hc"] + 1, n - 1))
                if rng is not None:
                    if len(win):
                        I.append(int(rng.choice(win)))
                    continue
                for i in win:
                    if c[i] > e + p["m"] * a1 and F_["doi4"][i] >= -0.01 and F_["below"][i]:
                        lo = np.min(F_["l"][i0:i + 1])
                        D.append(max(F_["o"][min(i + 1, n - 1)] - lo, 0.3 * A4[i]) if p["slm"] == "low" else 1.5 * A4[i])
                        I.append(i); break
            I = np.array(I, np.int64)
            if rng is not None:
                D = (1.5 * A4[I]) if p["slm"] == "atr" else np.array([max(F_["o"][min(i + 1, n - 1)] - np.min(F_["l"][max(i - 12, 0):i + 1]), 0.3 * A4[i]) for i in I])
            return I, np.ones(len(I), np.int64), np.asarray(D, float)
        if fam == "N2":
            lv = N2LVL[p["src"]][p["lvl"]]
            reg = (F_["fund"] < lv) if p["src"] == "fund" else (F_["pz24"] < lv)
            reg = reg & (F_["doi4"] > p["o"]) & ~F_["near"]
            m = reg & (c > F_[f"hh{p['N']}"]) & (c > F_["ema20_4"]) & ~np.isnan(A4)
            if pre:
                return np.flatnonzero(reg & ~np.isnan(A4))
            i = np.flatnonzero(m); return i, np.ones(len(i), np.int64), 1.2 * A4[i]
        if fam == "N3":
            reg = (F_["btc_er"] < (0.20 if p["reg"] == "er20" else 0.25)) if p["reg"].startswith("er") else (F_["btc_band"] < 1.5)
            reg = reg & ~F_["near"] & np.isfinite(F_["atr1"])
            mv = F_[f"mv{p['w']}"]; do = F_[f"doi{p['w']}"]
            up = reg & (mv >= p["M"]) & (do <= p["x"]); dn = reg & (mv <= -p["M"]) & (do <= p["x"])
            if pre:
                return np.flatnonzero(reg)
            i = np.flatnonzero(up | dn); d = np.where(up[i], -1, 1)
            return i, d.astype(np.int64), 1.5 * F_["atr1"][i]
    raise ValueError(fam)


def n_run(fam, sym, i, d, dist, p):
    F_ = f5(sym); n = len(F_["o"])
    keep = (i + 1 < n) & (dist > 0) & np.isfinite(dist)
    i, d, dist = i[keep], d[keep], dist[keep]
    o_ = np.argsort(i, kind="stable"); i, d, dist = i[o_], d[o_], dist[o_]
    ex = n_exit(fam, p)
    ent = i + 1
    ok, xj, R = NS.sim(F_["o"], F_["h"], F_["l"], ent.astype(np.int64), F_["o"][ent], d.astype(np.int64), dist.astype(float),
                       float(ex["tp_R"]), float(ex["be_R"]), int(ex["hold"]), np.zeros(n, np.bool_), F_["cost"])
    t = F_["t"]
    return pd.DataFrame(dict(sym=sym, t=t[ent[ok]], t_exit=t[np.clip(xj[ok], 0, n - 1)], dir=d[ok], R=R[ok]))


def n_trades(fam, p, coins):
    return pd.concat([n_run(fam, s, *n_signals(fam, s, p), p) for s in coins], ignore_index=True)


def n_params(fam):
    G_ = N_GRIDS[fam]
    return [dict(zip(G_, v)) for v in itertools.product(*G_.values())]


def n_job(args):
    fam, k = args
    p = n_params(fam)[k]
    out = dict(fam=fam, k=k, **p)
    for univ, coins in (("DEV12", H.DEV12), ("HOLD39", H.HOLD39)):
        s = NS.stats(n_trades(fam, p, coins))
        for per, d in s.items():
            for m_, v in d.items():
                out[f"{univ}_{per}_{m_}"] = v
    return out


def n_null(args):
    """Percentiles of avg R vs 200 random entries (pre-condition hours, same count per coin) and 40 time shifts (+-6..120 h)."""
    fam, k = args
    p = n_params(fam)[k]
    rng = np.random.default_rng(k + 17)
    real = NS.stats(n_trades(fam, p, H.DEV12))
    sig = {s: n_signals(fam, s, p) for s in H.DEV12}
    rnd = {q: [] for q in NS.PER}; shf = {q: [] for q in NS.PER}
    for _ in range(200):
        out = []
        for s in H.DEV12:
            i, d, dist = sig[s]
            if not len(i):
                continue
            if fam == "N1":
                ri, rd, rdist = n_signals(fam, s, p, rng=rng)
                if len(ri) > len(i):
                    sel = np.sort(rng.choice(len(ri), len(i), replace=False)); ri, rd, rdist = ri[sel], rd[sel], rdist[sel]
            else:
                pool = n_signals(fam, s, p, pre=True)
                if not len(pool):
                    continue
                ri = np.sort(rng.choice(pool, len(i), replace=len(pool) < len(i)))
                rd = rng.permutation(d)
                base_d = f5(s)["A4"] if fam == "N2" else f5(s)["atr1"]
                rdist = dist / base_d[i] * base_d[ri]
            out.append(n_run(fam, s, ri, rd, rdist, p))
        st = NS.stats(pd.concat(out)) if out else None
        for q in NS.PER:
            rnd[q].append(st[q]["avg"] if st else np.nan)
    for sh in rng.choice(np.r_[-120:-5, 6:121], 40, replace=False):
        out = []
        for s in H.DEV12:
            i, d, dist = sig[s]; n_ = len(f5(s)["o"])
            ii = i + int(sh); m = (ii > 0) & (ii < n_ - 2)
            out.append(n_run(fam, s, ii[m], d[m], dist[m], p))
        st = NS.stats(pd.concat(out))
        for q in NS.PER:
            shf[q].append(st[q]["avg"])
    return fam, k, {q: (float(np.nanmean(np.array(rnd[q]) < real[q]["avg"])), float(np.nanmean(np.array(shf[q]) < real[q]["avg"]))) for q in NS.PER}


def t5():
    for s in H.ALL51:
        f5(s)
    jobs = [(f, k) for f in N_GRIDS for k in range(len(n_params(f)))]
    log(f"[T5] {len(jobs)} sleeve settings x DEV12 / HOLD39")
    with Pool(PROCS) as pool:
        rows = pool.map(n_job, jobs, chunksize=2)
    Q = pd.DataFrame(rows)
    d22, d24 = "DEV12_2022-23", "DEV12_2024-26"
    Q["SG1"] = (Q[f"{d22}_avg"] > 0) & (Q[f"{d24}_avg"] > 0) & (Q[f"{d22}_pf"] >= 1.2) & (Q[f"{d24}_pf"] >= 1.2) & (Q[f"{d22}_n"] >= 30) & (Q[f"{d24}_n"] >= 30)
    Q["pos"] = (Q[f"{d22}_avg"] > 0) & (Q[f"{d24}_avg"] > 0)
    pl = np.full(len(Q), np.nan)
    for fam in N_GRIDS:
        q = (Q.fam == fam).to_numpy()
        pl[q] = plateau(Q[q].reset_index(drop=True), N_ORD[fam], N_CAT[fam], "pos")
    Q["plateau"] = pl; Q["SG2"] = Q.plateau >= 0.6
    Q["SG4"] = (Q["HOLD39_2022-23_avg"] > 0) & (Q["HOLD39_2024-26_avg"] > 0)
    Q["minavg"] = Q[[f"{d22}_avg", f"{d24}_avg"]].min(axis=1)
    todo = list(dict.fromkeys(Q[Q.SG1 & Q.SG2].sort_values("minavg", ascending=False).index[:30].tolist()
                              + Q.loc[Q.groupby("fam").minavg.idxmax()].index.tolist()))
    log(f"[T5] nulls for {len(todo)} settings")
    with Pool(PROCS) as pool:
        nl = pool.map(n_null, [(Q.fam[i], int(Q.k[i])) for i in todo], chunksize=1)
    for fam, k, r in nl:
        ix = Q[(Q.fam == fam) & (Q.k == k)].index[0]
        Q.loc[ix, ["rand22", "shift22", "rand24", "shift24"]] = [r["2022-23"][0], r["2022-23"][1], r["2024-26"][0], r["2024-26"][1]]
    Q["SG3"] = (Q.get("rand22", np.nan) >= 0.95) & (Q.shift22 >= 0.95) & (Q.rand24 >= 0.95) & (Q.shift24 >= 0.95)
    # correlation with TBO and money for SG1-SG4 passers + each family's best
    Tb = base_at(0); Tb = Tb.assign(u=V.units(Tb))
    tbo_m = Tb.groupby(Tb.exit_time.dt.to_period("M")).u.sum(); tbo_m = tbo_m[tbo_m.index >= pd.Period("2022-01")]
    ids = list(dict.fromkeys(Q[Q.SG1 & Q.SG2 & Q.SG3 & Q.SG4].index.tolist() + Q.loc[Q.groupby("fam").minavg.idxmax()].index.tolist()
                             + Q[Q.SG1 & Q.SG2 & Q.SG4].sort_values("minavg", ascending=False).index[:6].tolist()))
    bot = V.rows(base_at(0)); items = []
    for ix in ids:
        p = n_params(Q.fam[ix])[int(Q.k[ix])]
        T = n_trades(Q.fam[ix], p, H.DEV12)
        sm = T.groupby(T.t_exit.dt.to_period("M")).R.sum().reindex(tbo_m.index).fillna(0.0)
        Q.loc[ix, "corr_tbo"] = float(np.corrcoef(sm.values, tbo_m.values)[0, 1])
        Q.loc[ix, "R_tbo_losing"] = float(sm[tbo_m < 0].sum()); Q.loc[ix, "R_tbo_winning"] = float(sm[tbo_m >= 0].sum())
        m = lambda c_: T[c_].values.astype("datetime64[m]").astype(np.int64)
        S = np.c_[m("t"), m("t_exit"), m("t"), T.dir.to_numpy(float), T.R.to_numpy(), np.full(len(T), 6), np.ones(len(T))]
        A = V.with_sleeve(np.r_[bot, S])
        for u in (0.5, 1.0, 2.0):
            items.append((f"{ix}|{u}", A, V.base_policy(extra_risk=[(5, 0.5), (6, u / 6)])))
    Q["SG5"] = (Q.get("corr_tbo", np.nan) <= 0.15) & (Q.get("R_tbo_losing", np.nan) > 0)
    log(f"[T5] money (drawdown-matched) for {len(items)} (setting, size) pairs")
    M = g6_many(items)
    M["ix"] = [int(i.split("|")[0]) for i in M.index]; M["u"] = [float(i.split("|")[1]) for i in M.index]
    best = M.sort_values(["G6", "boot_med"], ascending=False).groupby("ix").head(1).set_index("ix")
    for c_ in ("u", "k", "m2022", "dd2022", "m2024", "dd2024", "boot_med", "boot_p10", "boot_dd90", "G6"):
        Q.loc[best.index, "M_" + c_] = best[c_]
    Q["SG6"] = Q.get("M_G6", False).fillna(False).astype(bool)
    Q["PASS"] = Q.SG1 & Q.SG2 & Q.SG3 & Q.SG4 & Q.SG5 & Q.SG6
    Q.to_csv(RES / "v30_T5_sleeves.csv", index=False)
    M.to_csv(RES / "v30_T5_sleeves_money.csv")
    for fam in N_GRIDS:
        q = Q[Q.fam == fam]
        log(f"[T5] {fam}: {len(q)} -> SG1 {int(q.SG1.sum())} -> +SG2 {int((q.SG1 & q.SG2).sum())} -> +SG3 {int((q.SG1 & q.SG2 & q.SG3).sum())} -> "
            f"+SG4 {int((q.SG1 & q.SG2 & q.SG3 & q.SG4).sum())} -> +SG5 {int((q.SG1 & q.SG2 & q.SG3 & q.SG4 & q.SG5).sum())} -> PASS {int(q.PASS.sum())}; "
            f"median avg R {q[f'{d22}_avg'].median():+.3f} / {q[f'{d24}_avg'].median():+.3f}")
    cols = ["fam", "k"] + [a for g in N_GRIDS.values() for a in g] + [f"{d22}_n", f"{d22}_avg", f"{d22}_pf", f"{d24}_n", f"{d24}_avg", f"{d24}_pf",
            "HOLD39_2022-23_avg", "HOLD39_2024-26_avg", "plateau", "rand22", "shift22", "rand24", "shift24", "corr_tbo", "R_tbo_losing",
            "M_u", "M_k", "M_boot_med", "M_boot_dd90", "SG1", "SG2", "SG3", "SG4", "SG5", "SG6", "PASS"]
    cols = list(dict.fromkeys(c_ for c_ in cols if c_ in Q))
    print(Q.loc[ids, cols].round(3).to_string(), flush=True)


# ══ TRACK 6 — combined v3.0 package ═════════════════════════════════════════════════════════════════════════════
def _pass(name):
    f = RES / f"v30_{name}.csv"
    if not f.exists():
        return pd.DataFrame()
    R = pd.read_csv(f)
    return R[R.PASS.astype(bool)] if "PASS" in R else pd.DataFrame()


def components():
    """One representative per passing family (the passer with the best min(x_dev, x_oos), ties -> best bootstrap median):
    name -> dict(kind, spec parts). Kinds: engine (per-coin kw / exits / ctrl / t3 skip), mult (per-trade sizing), policy, sleeve."""
    comp = {}
    pick = lambda Q: Q.sort_values(["minx", "M_boot_med"], ascending=False).iloc[0]
    q = _pass("T1d_cooldown")
    if len(q):
        r = pick(q); comp["cooldown"] = dict(kind="engine", id=r.id, ctrl="cool", p=dict(cool_h=float(r.cool_h), mode=int(r["mode"]), cool_R=float(r.cool_R)))
    for nm in ("T1a_veto", "T1b_active", "T1c_breadth"):
        q = _pass(nm)
        if len(q):
            comp[nm] = dict(kind="unsupported", id=pick(q).id)
    for g in GROUPS:
        q = _pass(f"T2a_geometry_{g}")
        if len(q):
            r = pick(q); comp.setdefault("geometry", []).append(dict(kind="engine", id=r["id"], grp=g, kwL=dict(n=int(r["nL"]), ema_n=int(r["eL"])),
                                                                         kwS=dict(n=int(r["nS"]), ema_n=int(r["eS"]), max_ext=float(r["xS"])), m=r["minx"]))
        q = _pass(f"T2b_exits_{g}")
        if len(q):
            r = pick(q); ex = dict(be_R=float(r["be"]), lock_R=float(r["lk"]), lock_to=float(r["lt"]), stale_h=int(r["st"]), stale_to=0.0,
                                   lock2_R=8.0 if r["l2"] else 0.0, lock2_to=3.5 if r["l2"] else 0.0)
            comp.setdefault("exits", []).append(dict(kind="engine", id=r["id"], grp=g, exL=ex if r["side"] in ("long", "both") else None,
                                                     exS=ex if r["side"] in ("short", "both") else None, m=r["minx"]))
    for k in ("geometry", "exits"):                                    # one group per family: the best one
        if k in comp:
            comp[k] = max(comp[k], key=lambda z: z["m"])
    q = _pass("T2c_short_sizing")
    if len(q):
        r = pick(q); comp["short_sizing"] = dict(kind="policy", id=r.id, smult=[float(r.btc_s), float(r.eth_s)] + [float(r.alt_s)] * 3,
                                                 exempt_short={0, 1} if r.ethex else None)
    t3s = []
    for fam in ("spot_low", "spot_high", "crowd_long", "squeeze_short", "vol"):
        q = _pass(f"T3_{fam}")
        if len(q):
            r = pick(q); prm = {a: r[a] for a in ("rule", "win", "q", "r", "z", "trig", "act", "v") if a in r and not (isinstance(r[a], float) and np.isnan(r[a]))}
            for a in ("win",):
                if a in prm:
                    prm[a] = int(prm[a])
            t3s.append(dict(id=r.id, p=prm))
    if t3s:
        comp["t3"] = dict(kind="t3", rules=t3s)
    q = _pass("T4_panic")
    if len(q):
        r = pick(q); comp["panic"] = dict(kind="sleeve4", id=r.id)
    q = _pass("T5_sleeves")
    if len(q):
        r = q.sort_values("minavg", ascending=False).iloc[0]; comp["sleeve5"] = dict(kind="sleeve5", fam=r.fam, k=int(r.k), u=float(r.M_u))
    return comp


def build_spec(parts, sid):
    """An engine spec from engine components (+ t3 skip rules)."""
    sp = dict(id=sid, p={}, per_coin={})
    for c in parts:
        if c["kind"] == "engine" and c.get("ctrl"):
            sp["ctrl"] = c["ctrl"]; sp["p"] = dict(sp["p"], **c["p"])
        elif c["kind"] == "engine":
            for s in GROUPS[c["grp"]]:
                d = sp["per_coin"].setdefault(s, {})
                for k in ("kwL", "kwS", "exL", "exS"):
                    if c.get(k):
                        d[k] = c[k]
        elif c["kind"] == "t3":
            skips = [r["p"] for r in c["rules"] if r["p"]["act"] == "skip"]
            if skips:
                sp["t3list"] = skips
    return sp


def t6():
    comp = components()
    log(f"[T6] passing components: {list(comp)}")
    pd.to_pickle(comp, CACHE / "t6_components.pkl")
    names = [k for k in comp if comp[k]["kind"] != "unsupported"]
    combos = [(n,) for n in names] + [c for r in range(2, len(names) + 1) for c in itertools.combinations(names, r)]
    # record: cooldown beyond the grid edge (20-48 h), all-entries mode, R -0.5
    ext = [dict(id=f"cool_{h}h_m1_R-0.5", p=dict(cool_h=h, mode=1, cool_R=-0.5), ctrl="cool") for h in (12, 16, 20, 24, 32, 48)]
    specs = [build_spec([comp[n] for n in cb], "+".join(cb)) for cb in combos] + ext
    # record: the full package with the simplest exit passer instead (all coins, both sides; widest plateau)
    R2 = pd.read_csv(RES / "v30_T2b_exits_all.csv"); r = R2[R2.PASS].sort_values("plateau", ascending=False).iloc[0]
    ex_all = dict(be_R=float(r["be"]), lock_R=float(r["lk"]), lock_to=float(r["lt"]), stale_h=int(r["st"]), stale_to=0.0,
                  lock2_R=8.0 if r["l2"] else 0.0, lock2_to=3.5 if r["l2"] else 0.0)
    alt_parts = [comp[n] for n in names if n != "exits"] + [dict(kind="engine", id=r["id"], grp="all", exL=ex_all, exS=ex_all)]
    full_alt = tuple([n for n in names if n != "exits"] + ["exits_all"])
    specs.append(build_spec(alt_parts, "+".join(full_alt)))
    eng = [sp for sp in specs if sp.get("ctrl") or sp.get("per_coin") or sp.get("t3list")]
    log(f"[T6] {len(combos)} combinations + {len(ext)} cooldown-edge runs; engine runs for {len(eng)}")
    runs = run_jobs(eng, shifts=[0] + SH) if eng else {}
    uses_oi = lambda cb: any(n in ("t3", "panic", "sleeve5") for n in cb)
    rows, items = [], []
    bot0 = V.rows(base_at(0))
    for sp, cb in list(zip(specs, combos + [("cooldown_edge",)] * len(ext) + [full_alt])):
        X = runs[sp["id"]][0] if sp["id"] in runs else base_at(0)
        mult = np.ones(len(X))
        t3c = comp.get("t3") if "t3" in cb else None
        if t3c:
            for r in t3c["rules"]:
                if r["p"]["act"] != "skip":
                    mult = mult * t3_mult(r["p"], X)
        pol = dict(smult=comp["short_sizing"]["smult"], exempt_short=comp["short_sizing"]["exempt_short"]) if "short_sizing" in cb else {}
        smult = {"BTCUSDT": pol["smult"][0], "ETHUSDT": pol["smult"][1], "alt": pol["smult"][2]} if pol else 0.5
        dev = P22 if uses_oi(cb) else P20
        xd, xo, s = xpair(X, 0, dev, mult=mult, smult=smult)
        ph = []
        if sp["id"] in runs:
            for sh in SH:
                Xs = runs[sp["id"]][sh]; ms = np.ones(len(Xs))
                if t3c:
                    for r in t3c["rules"]:
                        if r["p"]["act"] != "skip":
                            ms = ms * t3_mult(r["p"], Xs)
                a, b, _ = xpair(Xs, sh, dev, mult=ms, smult=smult); ph.append((a > 1, b > 1))
        ph = np.array(ph, float) if ph else np.full((1, 2), np.nan)
        rows.append(dict(id=sp["id"], combo="+".join(cb), dev=dev, x_dev=xd, x_oos=xo, x2020=xpair(X, 0, P20, mult=mult, smult=smult)[0],
                         x2022=xpair(X, 0, P22, mult=mult, smult=smult)[0], phase_dev=ph[:, 0].mean(), phase_oos=ph[:, 1].mean(),
                         n=len(X)))
        A = V.rows(X, mult=mult)
        S = V.sleeve()
        if "panic" in cb:
            ev = pickle.load(open(CACHE / "t4_pass_events.pkl", "rb"))[comp["panic"]["id"]][1]
            S = sleeve_rows4(ev)
        A = V.with_sleeve(A, S)
        extra = [(5, 0.5)]
        if "sleeve5" in cb:
            c5 = comp["sleeve5"]; T = n_trades(c5["fam"], n_params(c5["fam"])[c5["k"]], H.DEV12)
            m = lambda c_: T[c_].values.astype("datetime64[m]").astype(np.int64)
            S5 = np.c_[m("t"), m("t_exit"), m("t"), T.dir.to_numpy(float), T.R.to_numpy(), np.full(len(T), 6), np.ones(len(T))]
            A = np.r_[A, S5]; A = A[np.lexsort((A[:, 5], A[:, 0]))]; extra.append((6, c5["u"] / 6))
        items.append((sp["id"], A, V.base_policy(extra_risk=extra, **pol)))
    R = pd.DataFrame(rows)
    log(f"[T6] money (drawdown-matched) for {len(items)}")
    M = g6_many(items)
    R = R.merge(M.add_prefix("M_"), left_on="id", right_index=True, how="left")
    R["E1"] = (R.x_dev > 1) & (R.x_oos > 1); R["E3"] = (R.phase_dev >= 0.7) & (R.phase_oos >= 0.7)
    R["E4"] = R.M_G6.fillna(False).astype(bool)
    R.to_csv(RES / "v30_T6_combined.csv", index=False)
    B0 = money_row_base().add_prefix("M_").reset_index()
    print(pd.concat([B0, R], ignore_index=True)[["id", "dev", "x2020", "x2022", "x_oos", "phase_dev", "phase_oos", "M_k", "M_m2020", "M_m2022",
          "M_dd2022", "M_m2024", "M_dd2024", "M_boot_med", "M_boot_p10", "M_boot_dd90", "E1", "E3", "E4"]].round(3).to_string(index=False), flush=True)


if __name__ == "__main__":
    stage = sys.argv[1]
    {"base": stage_base, "t1": t1, "t2": t2, "t3": t3, "t3u": t3u, "t4": t4, "t5": t5, "t6": t6}[stage]()
