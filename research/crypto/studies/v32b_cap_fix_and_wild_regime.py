"""v3.2b (Nov 2026): the open-risk cap under size multipliers, and four surgical follow-ups to v3.2. Read-only on cryptobot/.

THE CAP QUESTION. core/v31lib._money31 (and the live bot) counts each open TBO trade in the 1.1 x BTC open-risk cap at its
actual (scaled) risk. A size-down (x0.75 on a wild day, x0.5 brake) therefore frees cap room that the next coins of a
cluster fill, and a boost (x1.15 on BTC, exempt) eats the alts' room. v3.1 has no TBO size multipliers, so the live bot is
not affected today; every size rule tested in v3.1 / v3.1b / v3.2 was money-tested under this counting.
cap_basis = "base" (new, opt-in, v31lib.money31 via the policy): the cap counts each trade at its un-scaled base risk and
the multiplier acts after the cap. With no multipliers both modes are identical (checked: the v3.1 base reproduces).

GATES (v3.2's, plus the capped account in E1):
  E1  fixed-unit ratio x > 1 in 2020-23 AND 2024-26 with net >= 92% of the reference (uncapped units, as before)
      AND the capped non-compounding account (money31 fixed=True, TBO only, cap_basis base) ratio x > 1 in both periods.
  E2  plateau: >= 60% of grid neighbours pass E1.
  E3  >= 95% of 200 coin/side-shuffled nulls (uncapped AND capped min-x) and x > 1 on >= 75% of the 40 phase copies
      (uncapped AND capped, each period).
  E4  money from $300 (cap_basis base): 2022 / 2024 money >= reference, 2024 drop < reference, Sep 15 - Nov 6 2026 drop
      <= reference, bootstrap dd90 < / p10 > / median > reference (1,000 two-year journeys). G6 (drawdown-matched) shown.
  Reference = v3.1 as deployed, or the stated overlay (the sizing winner) for "on top of" families.

    python v32b_cap_fix_and_wild_regime.py t1a | t1 | t2 | t3 | t4 | final        (results/v32b_*.csv)"""
import itertools, json, os, sys, time
from multiprocessing import Pool
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v31")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import common as C, v31lib as W
import crypto_regimes as R
import v31_drawdown_and_sleeves as M
import v32_market_regimes_and_alpha as S

RES = M.RES
P20, P24 = M.P20, M.P24
PROCS = int(os.environ.get("V31_PROCS", 5))
log = M.log
OVERLAY_F = RES / "v32b_overlay.json"
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 60); pd.set_option("display.max_rows", 400)


# ══ setup ══════════════════════════════════════════════════════════════════════════════════════════════════════════
def setup():
    S.setup_base()
    _tg = {}

    def tagged(X):                                   # S.tagged keeps one frame; the phase loops need all 41
        k = id(X)
        if k not in _tg:
            _tg[k] = S.tag(X)
        return _tg[k]
    S.tagged = tagged


def pol(cap="base", **kw):
    return dict(W.base_policy(**kw), cap_basis=cap)


_F = {}


def feats(X):
    """Own coin's VolReg / Chg5 / Ovl10 at entry (last daily close before the entry), aligned to X's rows."""
    k = id(X)
    if k not in _F:
        out = np.full((len(X), 3), np.nan)
        for s, idx in X.groupby("sym").groups.items():
            pos = X.index.get_indexer(idx)
            out[pos] = R.at(s, X.entry_time.iloc[pos], ["VolReg", "Chg5", "Ovl10"]).to_numpy(float)
        _F[k] = pd.DataFrame(out, columns=["VolReg", "Chg5", "Ovl10"])
    return _F[k]


# ══ size rules ═════════════════════════════════════════════════════════════════════════════════════════════════════
VR_LO, VR_HI = 0.790012611842446, 1.0657081970093196              # v3.2 frozen 2020-23 DEV12 terciles of VolReg
S5A = dict(kind="volreg", src="own", thr="q50", m=0.75, boost=1.15)  # the v3.2 candidate (median = (lo + hi) / 2)


def tier3(p, X):
    v = feats(X).VolReg.to_numpy()
    return np.where(v >= p["q_hi"], p["w_wild"], np.where(v >= p["q_med"], p["w_med"], np.where(v <= p["q_lo"], p["w_calm"], 1.0)))


def overlay_p():
    if OVERLAY_F.exists():
        return json.loads(OVERLAY_F.read_text())
    return dict(name="S5a x1.15 / x0.75", kind="tier2", q_lo=VR_LO, w_calm=1.15, q_med=(VR_LO + VR_HI) / 2, w_med=0.75, q_hi=99.0, w_wild=0.75)


def overlay_mult(X):
    return tier3(overlay_p(), X)


def pullback(p, X):
    F = feats(X); d = X.dir.to_numpy()
    c1 = F.VolReg.to_numpy() >= p["vr"]
    c2 = (d * F.Chg5.to_numpy() <= p["c"]) if p["kind"] == "pull" else (F.Ovl10.to_numpy() >= p["c"])
    return np.where(c1 & c2, p["m"], 1.0)


def cluster_windows(X, K, Wh, H):
    """v3.1b 2a: from each stop-out (R <= -0.5) completing >= K distinct coins' stop-outs within Wh hours, for H hours."""
    s = X[X.R <= -0.5].sort_values("exit_time")
    et = M._mins(s.exit_time); sy = s.sym.to_numpy(); out = []
    for i in range(len(s)):
        w = (et >= et[i] - Wh * 60) & (et <= et[i])
        if len(set(sy[w])) >= K:
            out.append((et[i], et[i] + H * 60))
    return np.array(out, np.int64).reshape(-1, 2)


def csize(p, X):
    iv = cluster_windows(X, 2, p["W"], p["H"]); t = M._mins(X.entry_time)
    if not len(iv):
        return np.ones(len(X))
    k = np.searchsorted(iv[:, 0], t, side="right") - 1
    ends = np.maximum.accumulate(iv[:, 1])
    hit = (k >= 0) & (t < ends[np.clip(k, 0, None)])
    return np.where(hit, p["m"], 1.0)


# ══ the capped non-compounding account ═════════════════════════════════════════════════════════════════════════════
def fixed_ratio(A, p, mk=None):
    out = {}
    for per in (P20, P24):
        a, b = W.PERIODS[per]
        r = W.money31(W.window(A, a, b), p, eq0=1e6, fixed=True, **(mk or {}))
        out[per] = (r["final"] - 1e6) / r["dd_abs"] if r["dd_abs"] > 0 else np.nan
    return out


# ══ money (pool) ═══════════════════════════════════════════════════════════════════════════════════════════════════
def _g6_job(a):
    i, A, p, base, mk = a
    return i, W.g6(A, p, base, **mk)


def g6_pool(items):
    if not items:
        return pd.DataFrame()
    with Pool(PROCS) as pool:
        res = pool.map(_g6_job, items, chunksize=1)
    return pd.DataFrame([dict(id=i, **r) for i, r in res]).set_index("id")


def money_rows(X, mult=None, share=0.25, lev=0.0):
    """TBO rows (with multipliers) + panic + VOLC; lev > 0 caps each VOLC position at lev x the balance (column 10)."""
    A = W.pad(W.rows(X, half=True, mult=mult), 11)
    Sl = W.pad(W.pad_sleeve(W.sleeve30(), 9), 11)
    if lev > 0:
        V = pd.read_pickle(C.D.CACHE / "volc_trades_v31.pkl")
        Sl[-len(V):, 10] = lev * (V.sl_dist / V.entry).to_numpy()
    B = np.r_[A, Sl]
    return B[np.lexsort((B[:, 5], B[:, 0]))]


_RM = {}


def ref_money(key, X, mult, p, mk=None):
    if key not in _RM:
        _RM[key] = W.money_all(W.with_sleeve(W.rows(X, half=True, mult=mult), W.sleeve30()), p, **(mk or {}))
    return _RM[key]


# ══ sizing-rule evaluator (the trade list is v3.1's; exact) ════════════════════════════════════════════════════════
def sz_eval(name, specs, ords, cats, mfn, m0fn=None, mk_fn=None, rows_mult=True, cap="base", top=30, money_top=20, null_n=200):
    """mfn(p, X) -> rule multipliers; m0fn(X) -> the reference's multipliers (overlay) or None (v3.1).
    rows_mult False: the rule acts in the money kernel (mk_fn(p), the loss brake), mfn is only its fixed-unit stand-in."""
    t0 = time.time()
    p_ = pol(cap); X = M.base_at(0)
    m0 = m0fn(X) if m0fn else np.ones(len(X))
    sb = W.score(X, mult=m0); fb = fixed_ratio(W.rows(X, half=True, mult=m0), p_)
    rows = []
    for sp in specs:
        mr = mfn(sp["p"], X); m = mr * m0
        s = W.score(X, mult=m); x = W.xr(s, sb)
        f = fixed_ratio(W.rows(X, half=True, mult=m if rows_mult else m0), p_, mk_fn(sp["p"]) if mk_fn else None)
        rows.append(dict(id=sp["id"], **sp["p"], x_dev=x[P20], x_oos=x[P24], netr_dev=s[P20]["net"] / sb[P20]["net"],
                         netr_oos=s[P24]["net"] / sb[P24]["net"], cx_dev=f[P20] / fb[P20], cx_oos=f[P24] / fb[P24],
                         share_scaled=float((mr != 1.0).mean())))
    Rr = pd.DataFrame(rows)
    Rr["E1u"] = (Rr.x_dev > 1) & (Rr.x_oos > 1) & (Rr.netr_dev >= M.NET_MIN) & (Rr.netr_oos >= M.NET_MIN)
    Rr["E1c"] = (Rr.cx_dev > 1) & (Rr.cx_oos > 1)
    Rr["E1"] = Rr.E1u & Rr.E1c
    Rr["plateau"] = M.plateau(Rr, ords, cats, "E1"); Rr["E2"] = Rr.plateau >= 0.6
    Rr["minx"] = Rr[["x_dev", "x_oos", "cx_dev", "cx_oos"]].min(axis=1)
    show = list(dict.fromkeys(list(Rr[Rr.E1 & Rr.E2].sort_values("minx", ascending=False).id.head(top)) +
                              list(Rr.sort_values("minx", ascending=False).id.head(3))))
    byid = {s["id"]: s for s in specs}
    for c in ("null_u", "null_c", "ph_dev", "ph_oos", "phc_dev", "phc_oos"):
        Rr[c] = np.nan
    base_sh = {}
    for i in show:
        sp = byid[i]; mr = mfn(sp["p"], X); mk = mk_fn(sp["p"]) if mk_fn else None
        r = Rr[Rr.id == i].iloc[0]
        rng = np.random.default_rng(abs(hash(i)) % 2 ** 32); du, dc = [], []
        for _ in range(null_n):
            mn = M.permute_by_coin_side(X, mr, rng) * m0
            x = W.xr(W.score(X, mult=mn), sb); du.append(min(x[P20], x[P24]))
            if rows_mult:
                f = fixed_ratio(W.rows(X, half=True, mult=mn), p_); dc.append(min(f[P20] / fb[P20], f[P24] / fb[P24]))
        Rr.loc[Rr.id == i, "null_u"] = float(np.mean(np.array(du) < min(r.x_dev, r.x_oos)))
        if rows_mult:
            Rr.loc[Rr.id == i, "null_c"] = float(np.mean(np.array(dc) < min(r.cx_dev, r.cx_oos)))
        w = []
        for sh in M.SH:
            Xs = M.base_at(sh)
            if sh not in base_sh:
                m0s = m0fn(Xs) if m0fn else np.ones(len(Xs))
                base_sh[sh] = (m0s, W.score(Xs, mult=m0s), fixed_ratio(W.rows(Xs, half=True, mult=m0s), p_))
            m0s, sbs, fbs = base_sh[sh]
            ms = mfn(sp["p"], Xs) * m0s
            x = W.xr(W.score(Xs, mult=ms), sbs)
            f = fixed_ratio(W.rows(Xs, half=True, mult=ms if rows_mult else m0s), p_, mk)
            w.append((x[P20] > 1, x[P24] > 1, f[P20] / fbs[P20] > 1, f[P24] / fbs[P24] > 1))
        w = np.array(w, float).mean(axis=0)
        Rr.loc[Rr.id == i, ["ph_dev", "ph_oos", "phc_dev", "phc_oos"]] = w
    Rr["E3"] = ((Rr.null_u >= 0.95) & (Rr.null_c.fillna(1.0) >= 0.95) & (Rr.ph_dev >= M.PH_MIN) & (Rr.ph_oos >= M.PH_MIN) &
                (Rr.phc_dev >= M.PH_MIN) & (Rr.phc_oos >= M.PH_MIN))
    # money
    ref = ref_money(("ref", name if m0fn else "v31", cap), X, m0 if m0fn else None, p_) if m0fn else M.money_base()
    ids = list(dict.fromkeys(list(Rr[Rr.E1 & Rr.E2 & Rr.E3].sort_values("minx", ascending=False).id.head(money_top)) +
                             list(Rr.sort_values("minx", ascending=False).id.head(3))))
    items = []
    for i in ids:
        sp = byid[i]; m = mfn(sp["p"], X) * m0
        items.append((i, W.with_sleeve(W.rows(X, half=True, mult=m if rows_mult else m0), W.sleeve30()), p_, ref,
                      mk_fn(sp["p"]) if mk_fn else {}))
    Mo = g6_pool(items)
    Rr = attach_money(Rr, Mo, ref)
    Rr.to_csv(RES / f"v32b_{name}.csv", index=False)
    log(f"[{name}] {len(Rr)} -> E1u {int(Rr.E1u.sum())}, E1c {int(Rr.E1c.sum())}, E1 {int(Rr.E1.sum())} -> +E2 {int((Rr.E1 & Rr.E2).sum())} -> "
        f"+E3 {int((Rr.E1 & Rr.E2 & Rr.E3).sum())} -> PASS {int(Rr.PASS.sum())} (G6 {int(Rr.PASS_dd_matched.sum())})  [{time.time() - t0:.0f}s]")
    show_table(Rr, ords + cats)
    return Rr, ref


def attach_money(Rr, Mo, ref):
    if len(Mo):
        Mo = Mo.copy(); Mo["E4"] = [M.e4_literal(r, ref) for _, r in Mo.iterrows()]
        Rr = Rr.merge(Mo.add_prefix("M_"), left_on="id", right_index=True, how="left")
        Rr["E4"] = Rr.M_E4.fillna(False).astype(bool); Rr["G6"] = Rr.M_G6.fillna(False).astype(bool)
    else:
        Rr["E4"] = False; Rr["G6"] = False
    Rr["PASS"] = Rr.E1 & Rr.E2 & Rr.E3 & Rr.E4
    Rr["PASS_dd_matched"] = Rr.E1 & Rr.E2 & Rr.E3 & Rr.G6
    return Rr


def show_table(Rr, keys, n=15):
    sh = Rr.sort_values(["PASS", "PASS_dd_matched", "E3", "minx"], ascending=False).head(n)
    cols = [c for c in keys + ["x_dev", "x_oos", "cx_dev", "cx_oos", "plateau", "null_u", "null_c", "ph_dev", "ph_oos", "phc_dev", "phc_oos",
                               "M_k1_m2022", "M_k1_m2024", "M_k1_dd2024", "M_k1_dd_fall26", "M_k1_boot_med", "M_k1_boot_p10",
                               "M_k1_boot_dd90", "E1", "E2", "E3", "E4", "G6", "PASS"] if c in sh]
    print(sh[cols].round(3).to_string(index=False), flush=True)


# ══ TEST 1a — S5a's 44 settings: live cap vs base cap ══════════════════════════════════════════════════════════════
def t1a():
    setup()
    old = pd.read_csv(RES / "v31_v32_S5a_volreg_size.csv")
    X = M.base_at(0)
    specs = []
    for src, thr, m, boost in itertools.product(("own", "btc"), ("q50", "q67"), (0.5, 0.65, 0.75, 1.0), (1.0, 1.15, 1.3)):
        if m == 1.0 and boost == 1.0:
            continue
        specs.append((f"s5_volreg_{src}_{thr}_m{m}_b{boost}", dict(kind="volreg", src=src, thr=thr, m=m, boost=boost)))
    rows, items = [], []
    for cap in ("live", "base"):
        p_ = pol(cap); fb = fixed_ratio(W.rows(X, half=True), p_)
        for i, p in specs:
            m = S.size_mult(p, X)
            f = fixed_ratio(W.rows(X, half=True, mult=m), p_)
            rows.append(dict(id=i, cap=cap, cx_dev=f[P20] / fb[P20], cx_oos=f[P24] / fb[P24]))
            items.append((f"{i}|{cap}", W.with_sleeve(W.rows(X, half=True, mult=m), W.sleeve30()), p_, M.money_base(), {}))
    log(f"[T1a] money for {len(items)} (44 settings x 2 cap modes)")
    Mo = g6_pool(items)
    Mo["E4"] = [M.e4_literal(r, M.money_base()) for _, r in Mo.iterrows()]
    C_ = pd.DataFrame(rows)
    keep = ["k1_m2022", "k1_m2024", "k1_dd2024", "k1_dd_fall26", "k1_boot_med", "k1_boot_p10", "k1_boot_dd90", "E4", "G6", "k"]
    out = old[["id", "src", "thr", "m", "boost", "x_dev", "x_oos", "plateau", "null_pct", "phase_dev", "phase_oos", "E1", "E2", "E3", "PASS"]].copy()
    out = out.rename(columns={"PASS": "PASS_v32"})
    for cap in ("live", "base"):
        c = C_[C_.cap == cap].set_index("id")[["cx_dev", "cx_oos"]].add_suffix(f"_{cap}")
        mm = Mo[Mo.index.str.endswith(f"|{cap}")].copy(); mm.index = mm.index.str.split("|").str[0]
        out = out.join(c, on="id").join(mm[keep].add_suffix(f"_{cap}"), on="id")
        out[f"PASS_{cap}"] = out.E1 & out.E2 & out.E3 & (out[f"cx_dev_{cap}"] > 1) & (out[f"cx_oos_{cap}"] > 1) & out[f"E4_{cap}"].fillna(False).astype(bool)
    out.to_csv(RES / "v32b_T1a_S5a_cap_before_after.csv", index=False)
    cols = ["id", "x_dev", "x_oos", "E1", "E2", "E3", "cx_dev_live", "cx_oos_live", "k1_m2024_live", "k1_dd2024_live", "k1_boot_med_live",
            "k1_boot_dd90_live", "E4_live", "cx_dev_base", "cx_oos_base", "k1_m2024_base", "k1_dd2024_base", "k1_boot_med_base",
            "k1_boot_dd90_base", "E4_base", "PASS_live", "PASS_base"]
    print(out.sort_values("x_oos", ascending=False)[cols].round(3).to_string(index=False), flush=True)
    log(f"[T1a] PASS live cap {int(out.PASS_live.sum())} | base cap {int(out.PASS_base.sum())}")


# ══ TEST 1 — 3-tier VolReg sizing on the base-cap simulator ═════════════════════════════════════════════════════════
def t1():
    setup()
    specs = []
    for ql, wc, qm, wm, qh, ww in itertools.product((0.75, 0.79, 0.83), (1.00, 1.10, 1.15, 1.20, 1.25), (0.90, 0.93, 0.96), (0.70, 0.75, 0.80),
                                                    (1.08, 1.12, 1.18, 1.25), (0.35, 0.45, 0.55)):
        specs.append(dict(id=f"t3_lo{ql}x{wc}_med{qm}x{wm}_hi{qh}x{ww}", p=dict(q_lo=ql, w_calm=wc, q_med=qm, w_med=wm, q_hi=qh, w_wild=ww)))
    log(f"[T1] {len(specs)} three-tier VolReg settings")
    Rr, ref = sz_eval("T1_volreg_3tier", specs, ["q_lo", "w_calm", "q_med", "w_med", "q_hi", "w_wild"], [], tier3, top=30, money_top=24)
    # reference rows: the 2-tier S5a candidate on both cap modes (same gates)
    X = M.base_at(0)
    for cap in ("live", "base"):
        m = S.size_mult(S5A, X)
        r = W.g6(W.with_sleeve(W.rows(X, half=True, mult=m), W.sleeve30()), pol(cap), M.money_base())
        log(f"[T1] S5a 2-tier, cap {cap}: " + ", ".join(f"{k}={r[k]:.2f}" for k in ("k1_m2022", "k1_m2024", "k1_dd2024", "k1_dd_fall26",
                                                                                    "k1_boot_med", "k1_boot_p10", "k1_boot_dd90")))
    P = Rr[Rr.PASS]
    if len(P):
        b = P.sort_values("minx", ascending=False).iloc[0]
        ov = dict(name=b.id, kind="tier3", **{k: float(b[k]) for k in ("q_lo", "w_calm", "q_med", "w_med", "q_hi", "w_wild")})
        OVERLAY_F.write_text(json.dumps(ov, indent=1))
        log(f"[T1] overlay for T2-T4 / final = {ov}")
    else:
        log("[T1] no 3-tier PASS: overlay stays the 2-tier S5a candidate")


# ══ TEST 2 — wild VolReg x 5-day pullback (or overlap), continuous ═══════════════════════════════════════════════════
def t2():
    setup()
    specs = []
    for vr, c, m in itertools.product((0.93, 0.98, 1.05, 1.12), (0.25, 0.0, -0.25, -0.5), (0.0, 0.35, 0.5)):
        specs.append(dict(id=f"pull_vr{vr}_c{c}_m{m}", p=dict(kind="pull", vr=vr, c=c, m=m)))
    for vr, c, m in itertools.product((0.93, 0.98, 1.05, 1.12), (0.45, 0.5, 0.55), (0.0, 0.35, 0.5)):
        specs.append(dict(id=f"ovl_vr{vr}_c{c}_m{m}", p=dict(kind="ovl", vr=vr, c=c, m=m)))
    log(f"[T2] {len(specs)} settings, on v3.1 and on the overlay {overlay_p()['name']}")
    sz_eval("T2_wild_pullback_on_v31", specs, ["vr", "c", "m"], ["kind"], pullback)
    sz_eval("T2_wild_pullback_on_overlay", specs, ["vr", "c", "m"], ["kind"], pullback, m0fn=overlay_mult)


# ══ TEST 3 — cluster size-down, BTC-regime risk and the loss brake on the base-cap simulator ════════════════════════
def t3():
    setup()
    cl = [dict(id=f"csize_K2_W{w}_H{h}_m{m}", p=dict(W=w, H=h, m=m)) for w, h, m in itertools.product((6, 12, 24), (12, 16, 24), (0.4, 0.5, 0.65))]
    s4 = []
    for states, m, boost in itertools.product(("FlatWild", "FlatWild+UpChop+DownChop", "UpChop+DownChop", "FlatWild+FlatCalm"),
                                              (0.5, 0.65, 0.75, 1.0), (1.0, 1.1)):
        if m == 1.0 and boost == 1.0:
            continue
        s4.append(dict(id=f"s4_btcchop_{states}_m{m}_b{boost}", p=dict(kind="btcchop", states=states, m=m, boost=boost)))
    br = [dict(id=f"brake_D{D}_X{Xu}_m{m}_reset{rs}", p=dict(D=D, X=Xu, m=m, reset=rs))
          for D, Xu, m, rs in itertools.product((3, 5, 7, 10), (2.5, 3.5, 4.5), (0.5, 0.65, 0.75), (0, 1))]
    bm = lambda p, X: M.brake_mult_units(X, p["D"], p["X"], p["m"], p["reset"])
    bk = lambda p: dict(brake=(p["D"], p["X"], p["m"], p["reset"]))
    for tag, m0 in (("on_v31", None), ("on_overlay", overlay_mult)):
        sz_eval(f"T3a_cluster_size_{tag}", cl, ["W", "H", "m"], [], csize, m0fn=m0)
        sz_eval(f"T3b_btc_regime_risk_{tag}", s4, ["m", "boost"], ["states"], S.size_mult, m0fn=m0)
        sz_eval(f"T3c_loss_brake_{tag}", br, ["D", "X", "m"], ["reset"], bm, m0fn=m0, mk_fn=bk, rows_mult=False)


# ══ TEST 4 — VolReg-conditioned profit lock / hold (engine) ═════════════════════════════════════════════════════════
def t4():
    setup()
    _rc = S.regime_cond

    def regime_cond(sym, name):
        if name.startswith("vr"):
            c = (R.regimes(sym).VolReg >= float(name[2:])).fillna(False)
            return c, c
        return _rc(sym, name)
    S.regime_cond = regime_cond
    specs = []
    for thr in (1.05, 1.12, 1.20):
        for X_, L_ in ((2.5, 1.0), (3.0, 1.0), (3.0, 1.5), (3.5, 1.5)):
            specs.append(dict(id=f"t4_vr{thr}_lock{X_}>{L_}", p=dict(thr=thr, act="lock", X=X_, L=L_, H=0), emask=f"vr{thr}",
                              kw=dict(exL2=dict(L3=X_, L3T=L_), exS2=dict(L3=X_, L3T=L_))))
        for H in (48, 72, 96):
            specs.append(dict(id=f"t4_vr{thr}_hold{H}", p=dict(thr=thr, act="hold", X=0, L=0, H=H), emask=f"vr{thr}",
                              kw=dict(exL2={}, exS2={}, hold2=H)))
    log(f"[T4] {len(specs)} VolReg-conditioned lock / hold settings (engine)")
    Rr, runs, X0 = M.evaluate("v32b_T4_volreg_lock", specs, ["thr", "X", "L", "H"], ["act"], P20, top=30)
    # capped account + money (alone vs v3.1; and with the overlay sizing vs the overlay)
    p_ = pol("base"); B0 = M.base_at(0); fb = fixed_ratio(W.rows(B0, half=True), p_)
    for i in Rr.id:
        f = fixed_ratio(W.rows(X0[i], half=True), p_)
        Rr.loc[Rr.id == i, ["cx_dev", "cx_oos"]] = [f[P20] / fb[P20], f[P24] / fb[P24]]
    Rr["E1u"] = Rr.E1; Rr["E1c"] = (Rr.cx_dev > 1) & (Rr.cx_oos > 1); Rr["E1"] = Rr.E1u & Rr.E1c
    Rr["plateau"] = M.plateau(Rr, ["thr", "X", "L", "H"], ["act"], "E1"); Rr["E2"] = Rr.plateau >= 0.6
    Rr["minx"] = Rr[["x_dev", "x_oos", "cx_dev", "cx_oos"]].min(axis=1)
    ids = list(dict.fromkeys(list(Rr[Rr.E1].sort_values("minx", ascending=False).id.head(12)) + list(Rr.sort_values("minx", ascending=False).id.head(3))))
    ref_ov = ref_money(("ref", "overlay", "base"), B0, overlay_mult(B0), p_)
    Mo = g6_pool([(i, W.with_sleeve(W.rows(X0[i], half=True), W.sleeve30()), p_, M.money_base(), {}) for i in ids])
    Mo2 = g6_pool([(i, W.with_sleeve(W.rows(X0[i], half=True, mult=overlay_mult(X0[i])), W.sleeve30()), p_, ref_ov, {}) for i in ids])
    Rr = attach_money(Rr, Mo, M.money_base())
    if len(Mo2):
        Mo2["E4"] = [M.e4_literal(r, ref_ov) for _, r in Mo2.iterrows()]
        Rr = Rr.merge(Mo2[["k1_m2022", "k1_m2024", "k1_dd2024", "k1_dd_fall26", "k1_boot_med", "k1_boot_p10", "k1_boot_dd90", "E4"]].add_prefix("OV_"),
                      left_on="id", right_index=True, how="left")
    Rr.to_csv(RES / "v32b_T4_volreg_lock.csv", index=False)
    log(f"[T4] {len(Rr)} -> E1u {int(Rr.E1u.sum())}, E1c {int(Rr.E1c.sum())}, E1 {int(Rr.E1.sum())} -> +E2 {int((Rr.E1 & Rr.E2).sum())} -> "
        f"+E3 {int((Rr.E1 & Rr.E2 & Rr.E3).sum())} -> PASS {int(Rr.PASS.sum())}")
    show_table(Rr, ["id"])
    if "OV_k1_m2024" in Rr:
        print(Rr.dropna(subset=["OV_k1_m2024"])[["id", "x_dev", "x_oos", "cx_dev", "cx_oos", "OV_k1_m2024", "OV_k1_dd2024", "OV_k1_dd_fall26",
                                                  "OV_k1_boot_med", "OV_k1_boot_p10", "OV_k1_boot_dd90", "OV_E4"]].round(3).to_string(index=False))
        log(f"[T4] overlay reference: {dict((k, round(v, 2)) for k, v in ref_ov.items())}")


# ══ FINAL — the comparison table ═══════════════════════════════════════════════════════════════════════════════════
DEPLOYED_K = 0.95                                                 # portfolio.json = the v3.0 ladder x 0.95


def money_full(A, p):
    out = {}
    for nm, a in (("2022", "2022-01-01"), ("2024", "2024-01-01"), ("sep26", "2026-09-15"), ("oct26", "2026-10-01")):
        r = W.money31(W.window(A, a), p, path=(nm == "2024")); out[f"m_{nm}"] = r["final"]; out[f"dd_{nm}"] = r["dd"]
        if nm == "2024":
            pt, pe, _ = r["path"]
            t0 = pd.Timestamp(a).value // 60_000_000_000
            s = pd.Series(pe, index=pd.to_datetime((pt + t0) * 60_000_000_000)).sort_index()
            me = s.resample("ME").last().ffill(); ret = me.pct_change(); ret.iloc[0] = me.iloc[0] / 300.0 - 1
            out["lose_months_2024_26"] = int((ret < 0).sum()); out["months"] = len(ret)
    b = W.boot31(A, p)
    out.update(boot_med=b["med"], boot_p10=b["p10"], boot_dd90=b["dd90"])
    return out


def _final_job(a):
    nm, A, p, meta = a
    return dict(name=nm, **meta, **money_full(A, p))


def best_pass(f):
    fp = RES / f
    if not fp.exists():
        return None
    d = pd.read_csv(fp); d = d[d.PASS]
    return d.sort_values("minx", ascending=False).iloc[0] if len(d) else None


def final():
    """Finalists: (A) the best Test-2 rule alone on v3.1; (B) the overlay (S5a / Test-1 winner) + the best Test-2 rule on top
    of it. Each across k (v3.0 ladder x k; deployed 0.95) and VOLC 0.25 / 0.35 with and without a 1.5 / 1.8 x leverage cap."""
    setup()
    X = M.base_at(0)
    ov = overlay_p(); mo = overlay_mult(X)
    pp = lambda r: {k: r[k] for k in ("kind", "vr", "c", "m")}
    fins = []
    a = best_pass("v32b_T2_wild_pullback_on_v31.csv")
    if a is not None:
        fins.append((f"A: {a.id}", pullback(pp(a), X)))
    b = best_pass("v32b_T2_wild_pullback_on_overlay.csv")
    fins.append((f"B: {ov['name']}" + (f" + {b.id}" if b is not None else ""), mo * (pullback(pp(b), X) if b is not None else 1.0)))
    items = []
    s5 = S.size_mult(S5A, X)
    items.append(("v3.2 S5a candidate", money_rows(X, s5), pol("live"), dict(cap="live", k=0.95, volc=0.25, lev=0)))
    items.append(("v3.2 S5a candidate", money_rows(X, s5), pol("base"), dict(cap="base", k=0.95, volc=0.25, lev=0)))
    for k in (0.85, 0.90, 0.95, 1.00):
        items.append(("v3.1 deployed", money_rows(X), dict(pol("live"), mult=k / DEPLOYED_K), dict(cap="live", k=k, volc=0.25, lev=0)))
        for nm, mw in fins:
            for share, lev in ((0.25, 0), (0.25, 1.5), (0.35, 0), (0.35, 1.5), (0.35, 1.8)):
                p_ = dict(pol("base", extra_risk=[(5, 0.5), (6, share)]), mult=k / DEPLOYED_K)
                items.append((nm, money_rows(X, mw, share, lev), p_, dict(cap="base", k=k, volc=share, lev=lev)))
    log(f"[final] {len(items)} rows; finalists = {[f for f, _ in fins]}")
    with Pool(PROCS) as pool:
        res = pool.map(_final_job, items, chunksize=1)
    T = pd.DataFrame(res)
    T.to_csv(RES / "v32b_final_comparison.csv", index=False)
    fm = {c: "{:.0f}".format for c in T if c.startswith(("m_", "boot_med", "boot_p10"))}
    fm.update({c: "{:.1f}".format for c in T if c.startswith("dd") or c == "boot_dd90"})
    fm.update({"k": "{:.2f}".format, "volc": "{:.2f}".format, "lev": "{:.1f}".format})
    print(T.to_string(index=False, formatters=fm), flush=True)


if __name__ == "__main__":
    {"t1a": t1a, "t1": t1, "t2": t2, "t3": t3, "t4": t4, "final": final}[sys.argv[1]]()
