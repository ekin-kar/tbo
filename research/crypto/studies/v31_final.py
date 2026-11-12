"""v3.1 final stage (after Tracks 1-8 of v31_drawdown_and_sleeves.py): (1) every PASS / near-miss engine rule on the 14
untouched HOLD_BIG coins (TBO v3.0 entries + OI filters, equal 1-unit sizing, shorts x 0.5), (2) the passers combined,
with the full E1-E4 gates against the v3.0 baseline, (3) per-month comparison (TBO's losing months, Oct-Nov 2026).

    python v31_final.py holdbig | combo        -> research/results/v31_final_*.csv"""
import itertools, os, sys
from multiprocessing import Pool
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v30")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import common as C, v29lib as L, v31lib as W, sleeve31 as SL
import v31_drawdown_and_sleeves as M

RES, log = M.RES, M.log
FB = dict(T_h=8, G=60, cont=1, mlo=0.9, mhi=99.0, thr=-0.2, act=3, lvl=-0.5)
FB3 = dict(FB, thr=-0.3)
RULES = {
    "base": {},
    "fb_T8_M0.9_c-0.2_tight-0.5": dict(exL=dict(A=FB, rcool=1), exS=dict(A=FB, rcool=1)),
    "fb_T8_M0.9_c-0.3_tight-0.5": dict(exL=dict(A=FB3, rcool=1), exS=dict(A=FB3, rcool=1)),
    "cascade-0.75": dict(cascade=-0.75), "cascade-0.25": dict(cascade=-0.25), "cascade0.0": dict(cascade=0.0),
    "fb-0.2+cascade-0.25": dict(exL=dict(A=FB, rcool=1), exS=dict(A=FB, rcool=1), cascade=-0.25, rule=-0.2),
    "fb-0.2+cascade0.0": dict(exL=dict(A=FB, rcool=1), exS=dict(A=FB, rcool=1), cascade=0.0, rule=-0.2),
}
PERS = {"2020-23": ("2020-01-01", "2024-01-01"), "2022-23": ("2022-01-01", "2024-01-01"), "2024-26": ("2024-01-01", W.END)}


def hb_job(args):
    rid, sym = args
    W._ORD.clear(); W._FA.clear()
    for k in [k for k in L._M if k not in (sym, "BTCUSDT")]:
        L._M.pop(k)
    kw = RULES[rid]
    ctrl = None
    if "cascade" in kw:                                              # BTC stop-outs (base or with the FB rule) -> this coin
        import v31_sleeves as S8
        out = S8.btc_cascade(sym, 0, L.m1(sym)["t"], act=kw["cascade"], rule=kw.get("rule"))
        ctrl = lambda t, out=out: out
    try:
        x = W.trades31(sym, exL=kw.get("exL"), exS=kw.get("exS"), ctrl=ctrl)
    except Exception as e:                                           # no 1m / OI data for the coin
        return rid, sym, None
    return rid, sym, x[["entry_time", "exit_time", "dir", "R", "sym"]]


def holdbig(rules=None):
    rules = rules or list(RULES)
    coins = [s for s in SL.HOLD_BIG if (C.D.CACHE / f"{s}_m1.npz").exists()]
    log(f"HOLD_BIG with 1m data: {len(coins)} of {len(SL.HOLD_BIG)}")
    tasks = sorted([(r, s) for r in rules for s in coins], key=lambda z: z[1])
    out = {}
    with Pool(M.PROCS) as pool:
        for r, s, x in pool.imap_unordered(hb_job, tasks):
            if x is not None:
                out.setdefault(r, []).append(x)
    X = {r: pd.concat(v, ignore_index=True) for r, v in out.items()}
    rows = []
    for r, x in X.items():
        u = x.R.to_numpy() * np.where(x.dir.to_numpy() < 0, 0.5, 1.0)
        s = L.score(x, u, PERS)
        rows.append(dict(rule=r, n=len(x), **{f"{p}_{k}": v for p, d in s.items() for k, v in d.items()}))
    R = pd.DataFrame(rows)
    b = R[R.rule == "base"].iloc[0]
    for p in PERS:
        R[f"x_{p}"] = R[f"{p}_ratio"] / b[f"{p}_ratio"]
    R.to_csv(RES / "v31_final_holdbig.csv", index=False)
    print(R.round(3).to_string(index=False))
    return R


if __name__ == "__main__" and sys.argv[1] == "holdbig":
    holdbig()


# ── exact cross-coin cluster cooldown (time-ordered resolution instead of whole-list fixed-point iteration) ─────────
def cluster_events(X, p):
    """Block events (start, end, dir) from the trades X for rule p (as M.cluster_blocks)."""
    L_ = X[X.R < p.get("lossR", -0.5)].sort_values("exit_time")
    ev = []
    if p["kind"] == "glob":
        et = M._mins(L_.exit_time); sy = L_.sym.to_numpy(); dr = L_.dir.to_numpy()
        for i in range(len(L_)):
            w = (et >= et[i] - p["W"] * 60) & (et <= et[i])
            if p["scope"] == "dir":
                w &= dr == dr[i]
            if len(set(sy[w])) >= p["N"]:
                ev.append((int(et[i]), int(et[i] + p["B"] * 60), int(dr[i])))
    else:
        b = L_[(L_.sym == "BTCUSDT") & (L_.hours < p["h"])]
        ev = [(int(e), int(e + p["B"] * 60), int(d)) for e, d in zip(M._mins(b.exit_time), b.dir)]
    return sorted(set(ev))


def _run_blocks(ev, p, shift):
    out = []
    for s in W.COINS:
        il = np.array([(a, z) for a, z, d in ev if p["scope"] == "all" or d == 1], np.int64).reshape(-1, 2)
        is_ = np.array([(a, z) for a, z, d in ev if p["scope"] == "all" or d == -1], np.int64).reshape(-1, 2)
        out.append(W.trades31(s, shift=shift, ctrl=M._ctrl_from(il, is_))[M.KEEP])
    return pd.concat(out, ignore_index=True)


def exact_cluster(p, shift=0, max_pass=2000):
    """Block events are fixed in time order. At each pass: tau = the earliest time where the events implied by the
    current trades differ from the events used. Events before tau are final (they come from trades that closed before it,
    simulated under the same earlier blocks). Every implied event is then accepted up to F = the first entry of the
    current trades that an accepted NEW block would remove: nothing before F can change, so the events before F are
    final too. Rerun with the accepted events; repeat. Terminates (the accepted prefix grows); returns (trades, passes)."""
    used = []
    X = M.base_at(shift)
    et = lambda Z: M._mins(Z.entry_time)
    for k in range(1, max_pass + 1):
        ev = cluster_events(X, p)
        su, se = set(used), set(ev)
        cand = [e[0] for e in ev if e not in su] + [e[0] for e in used if e not in se]
        if not cand:
            return X, k
        tau = min(cand)
        e_x, d_x = et(X), X.dir.to_numpy()
        keep = [e for e in used if e[0] < tau]
        Fc = np.inf                                         # cutoff only moves earlier -> the loop ends
        while True:
            U = sorted(set(keep + [e for e in ev if e[0] < Fc or e[0] == tau]))
            Fn = Fc
            for a, z, d in (e for e in U if e not in su):
                hit = (e_x >= a) & (e_x < z) & ((p["scope"] == "all") | (d_x == d))
                if hit.any():
                    Fn = min(Fn, e_x[hit].min())
            if Fn >= Fc:
                break
            Fc = Fn
        used = sorted(set(U))
        X = _run_blocks(used, p, shift)
    return X, -1


def ec_job(args):
    pid, p, shift = args
    W.ORD_CACHE = 6
    X, k = exact_cluster(p, shift)
    return pid, shift, X, k


def cluster_exact():
    """Rerun Track 3a exactly: all 200 rules at shift 0, the best by min x with 40 phase copies, nulls, money."""
    specs = []
    for N, Wh, B, sc, lr in itertools.product((2, 3), (4, 6, 12, 24), (4, 8, 12, 16, 24), ("all", "dir"), (-0.5, 0.0)):
        specs.append(dict(id=f"glob_N{N}_W{Wh}_B{B}_{sc}_L{lr}", p=dict(kind="glob", N=N, W=Wh, B=B, scope=sc, lossR=lr)))
    for h, B, sc in itertools.product((2, 4, 6, 8), (4, 8, 12, 16, 24), ("all", "dir")):
        specs.append(dict(id=f"btctrap_h{h}_B{B}_{sc}", p=dict(kind="btctrap", h=h, B=B, scope=sc, lossR=-0.5, N=0, W=0)))
    log(f"exact cluster: {len(specs)} rules at shift 0")
    X0, PASSES = {}, {}
    with Pool(M.PROCS) as pool:
        for pid, sh, X, k in pool.imap_unordered(ec_job, [(s["id"], s["p"], 0) for s in specs]):
            X0[pid] = X; PASSES[pid] = k
    byid = {s["id"]: s for s in specs}
    for grp, nm in (("glob", "T3a_cluster_cooldown_exact"), ("btctrap", "T3a_btc_trap_exact")):
        ss = [s for s in specs if s["p"]["kind"] == grp]
        ords = ["N", "W", "B"] if grp == "glob" else ["h", "B"]
        cats = ["scope", "lossR"] if grp == "glob" else ["scope"]
        R, _, _ = M.evaluate(nm, ss, ords, cats, M.P20, phase=False, get0=lambda sp: X0[sp["id"]], null_fn=M.null_remove)
        R["passes"] = R.id.map(PASSES)
        top = list(dict.fromkeys(list(R[R.E1 & R.E2].sort_values("minx", ascending=False).id.head(10)) + list(R.sort_values("minx", ascending=False).id.head(3))))
        if top:
            log(f"[{nm}] exact phase copies for {len(top)} rules")
            PH = {}
            with Pool(M.PROCS) as pool:
                for pid, sh, X, k in pool.imap_unordered(ec_job, [(i, byid[i]["p"], sh) for i in top for sh in M.SH]):
                    PH[(pid, sh)] = X
            for i in top:
                R.loc[R.id == i, ["phase_dev", "phase_oos", "phase_both"]] = M.phase_win(lambda sh, i=i: PH[(i, sh)], M.P20)
        R["E3"] = (R.null_pct >= 0.95) & (R.phase_dev >= M.PH_MIN) & (R.phase_oos >= M.PH_MIN)
        Mo = M.money_for(nm, R, X0, specs=ss)
        M.finish(nm, R, Mo, ["id", "passes"])


if __name__ == "__main__" and sys.argv[1] == "cluster_exact":
    cluster_exact()


# ── combination of the passers (engine, all gates) ──────────────────────────────────────────────────────────────────
def combo():
    fbx = lambda thr: dict(T_h=8, G=60, cont=1, mlo=0.9, mhi=99.0, thr=thr, act=3, lvl=-0.5)
    specs = []
    for thr, act in itertools.product((-0.2, -0.3), (None, -0.75, -0.5, -0.25, 0.0)):
        ex = dict(A=fbx(thr), rcool=1)
        sp = dict(id=f"combo_fb{thr}_cascade{act}", p=dict(thr=thr, act=str(act)), exL=ex, exS=ex)
        if act is not None:
            sp["ctrlfn"] = ("btc_cascade", (("act", act), ("rule", thr)))
        specs.append(sp)
    for act in (-0.75, -0.5, -0.25, 0.0):
        specs.append(dict(id=f"combo_cascade{act}_only", p=dict(thr=0.0, act=str(act)), ctrlfn=("btc_cascade", (("act", act),))))
    R, runs, X0 = M.evaluate("final_combo", specs, ["thr"], ["act"], M.P20, top=20)
    Mo = M.money_for("final_combo", R, X0, specs=specs, ids=list(R.id))
    R = M.finish("final_combo", R, Mo, ["id"])
    # month-by-month vs the base for the best combination (TBO units) and the live window
    return R


def fill_mult(p, X):
    fm = M._mins(X.entry_time) - M._mins(X.arm_time)
    cs = M.SCOPES[p["scope"]][0]
    return np.where((fm < p["X"]) & X.sym.isin(cs).to_numpy(), p["m"], 1.0)


def fillsize():
    """H9 (suggested by the Track 4 fill-minute table, so the luck tests carry the weight): entries that fill within X
    minutes of the 4h close sized x m."""
    specs = [dict(id=f"fillsize_X{X}_m{m}@{sc}", p=dict(X=X, m=m, scope=sc), engine=False)
             for X, m, sc in itertools.product((30, 60, 90, 120), (0.5, 0.65, 0.75), ("all", "majors", "alts"))]
    mf = lambda sp, X: fill_mult(sp["p"], X)
    R, _, X0 = M.evaluate("T8_H9_fill_minute_size", specs, ["X", "m"], ["scope"], M.P20, mult_fn=mf,
                          null_fn=lambda sp, X, rng: (X, M.permute_by_coin_side(X, mf(sp, X), rng)))
    M.finish("T8_H9_fill_minute_size", R, M.money_for("T8_H9_fill_minute_size", R, X0, mult_fn=mf, specs=specs), ["id"])


def volc4h():
    """Track 5c: the 4h VOLC + OI build-up family that stood out in 5b, on a regular grid (so the plateau means something)."""
    import v31_sleeves as S
    g = S.grid(tf=(240,), sq=("atr0.6", "atr0.65", "atr0.7", "atr0.75"), N=(6, 8, 10, 12), dm=("trend", "hybrid", "range2"),
               TP=(1.5, 2.0, 2.5, 3.0), H=(24, 36, 48), oi=(-0.01, 0.0, 0.02), sc=(0,))
    S.sleeve_track("T5c_volc4h_oi", "volc", g, ["N", "TP", "H"], ["sq", "dm", "oi"], S.P22, top=12)


if __name__ == "__main__" and sys.argv[1] in ("combo", "fillsize", "volc4h"):
    {"combo": combo, "fillsize": fillsize, "volc4h": volc4h}[sys.argv[1]]()
