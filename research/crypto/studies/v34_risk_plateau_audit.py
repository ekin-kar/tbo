"""v3.4 joint risk-grid and plateau audit (Nov 2026) of the complete v3.2.1 system: TBO v3.2.1 (the v3.1 trade list x the
wild-pullback size) + panic v3.0 + 4h VOLC on one account. Read-only on cryptobot/ (portfolio.json, panic.json, volc.json
are read, never written).

EVERY setting is evaluated jointly in the exact chronological multi-coin capped simulator (v31lib._money31: the coins share
the open-risk cap in fill order, BTC exempt but counted, the cap counts the actual scaled risk, sleeves outside the cap).
Speed: the events of each run (bootstrap journey, window, phase copy) are sorted once; a parallel numba kernel runs every
policy through _money31 (the function behind every money figure since v3.1).

  stage1   coupled marginal sweeps (each coin's weight, short multiplier, cap ratio, VOLC share / coin weighting, panic
           units / extra share / max extra open) + per-coin full / shrunk / skipped counts (botsim, same rule)
  stage2   joint grid: BTC risk x ETH / BTC x alt / BTC x alt pattern x short mult x cap / BTC x VOLC share x panic units
  stage2b  ladder structure and cap_min_fraction on the stage-2 candidates
  stage3   era consistency (fixed-size capped account, ret / max DD, 2020-23 and 2024-26, 41 phase copies) and 1-step
           neighbour plateaus
  stage4   five plateau options, full metrics

    python v34_risk_plateau_audit.py check | stage1 | stage2 | stage2b | stage4"""
import itertools, json, os, sys, time
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v32")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from numba import njit, prange
import common as C, v29lib as L, v30lib as V0, v31lib as W
import v31_drawdown_and_sleeves as M
import v32b_cap_fix_and_wild_regime as B
import panic_sleeve as PSL

RES = M.RES
CDIR = C.D.CACHE / "v34"
LOG = RES / "v34_stage_output.txt"
END = W.END
P20, P24 = M.P20, M.P24
V32P = dict(kind="pull", vr=0.98, c=-0.25, m=0.25)
NJ = int(os.environ.get("V34_BOOT", 1000))
pd.set_option("display.width", 320); pd.set_option("display.max_columns", 80); pd.set_option("display.max_rows", 500)


def out(*a):
    """Print and append to the stage log (research/results/v34_stage_output.txt)."""
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    with open(LOG, "a") as f:
        f.write(s + "\n")


# ══ inputs ═════════════════════════════════════════════════════════════════════════════════════════════════════════
def setup():
    base = CDIR / "base"; base.mkdir(parents=True, exist_ok=True)
    for f in (W.CACHE / "pkg").glob("base_s*.pkl"):
        if not (base / f.name).exists():
            (base / f.name).symlink_to(f)
    M.CACHE = base; M._BASE.clear(); M._BS.clear(); M._MB.clear()


def m32(X):
    return B.pullback(V32P, X)


def volc_rows(V, weights=None):
    m = lambda c: V[c].values.astype("datetime64[m]").astype(np.int64)
    w = np.ones(len(V)) if weights is None else V.sym.map(weights).to_numpy(float)
    return np.c_[m("entry_time"), m("exit_time"), m("entry_time"), V.dir.to_numpy(float), V.R.to_numpy(float), np.full(len(V), 6.0), w]


_PE = {}


def panic_rows(extra_share=0.75, max_extra_open=2):
    k = (extra_share, max_extra_open)
    if k not in _PE:
        f = CDIR / f"panic_{extra_share}_{max_extra_open}.pkl"
        if f.exists():
            _PE[k] = pd.read_pickle(f)
        else:
            ev = PSL.events(extra_share=extra_share, max_extra_open=max_extra_open)
            r = PSL.sleeve_rows(ev); _PE[k] = np.c_[r, np.ones(len(r))]
            pd.to_pickle(_PE[k], f)
    return _PE[k]


def rows_full(X, panic=None, volc_w=None):
    V = pd.read_pickle(C.D.CACHE / "volc_trades_v32.pkl")
    S = np.r_[panic_rows() if panic is None else panic, volc_rows(V, volc_w)]
    return W.with_sleeve(W.rows(X, half=True, mult=m32(X)), S)


# ══ event preparation (exactly money31's) ══════════════════════════════════════════════════════════════════════════
def prep(x):
    x = np.asarray(x, float); n = len(x)
    e = x[:, 0]; be = np.maximum(x[:, 2], e + 1e-3); xx = np.maximum(x[:, 1], e + 2e-3)
    idx = np.arange(n)
    t = np.r_[e, be, xx]; kind = np.r_[np.ones(n, np.int64), np.zeros(n, np.int64), np.full(n, 2, np.int64)]
    ii = np.r_[idx, idx, idx]; rank = np.r_[np.full(n, 2), np.ones(n), np.zeros(n)]
    tie = np.r_[3 * idx, 3 * idx + 1, 3 * idx + 2]
    o = np.lexsort((tie, rank, t))
    return dict(t=t[o].astype(float), k=kind[o], i=ii[o].astype(np.int64), d=x[:, 3].copy(), R=x[:, 4].copy(),
                c=x[:, 5].astype(np.int64), m=(x[:, 6] if x.shape[1] > 6 else np.ones(n)).copy())


class Runs:
    """A set of runs (each: events + rows, start balance, fixed sizing flag), concatenated for the numba kernel."""
    def __init__(self, parts, eq0, fixed):
        self.n = len(parts)
        self.et = np.concatenate([p["t"] for p in parts]); self.ek = np.concatenate([p["k"] for p in parts])
        self.ei = np.concatenate([p["i"] for p in parts])
        self.eoff = np.r_[0, np.cumsum([len(p["t"]) for p in parts])].astype(np.int64)
        self.d = np.concatenate([p["d"] for p in parts]); self.R = np.concatenate([p["R"] for p in parts])
        self.c = np.concatenate([p["c"] for p in parts]); self.m = np.concatenate([p["m"] for p in parts])
        self.roff = np.r_[0, np.cumsum([len(p["d"]) for p in parts])].astype(np.int64)
        self.eq0 = np.broadcast_to(np.asarray(eq0, float), (self.n,)).copy()
        self.fixed = np.broadcast_to(np.asarray(fixed, np.bool_), (self.n,)).copy()


@njit(parallel=True, cache=True)
def kernel(et, ek, ei, eoff, d, R, c, m, roff, eq0, fixed, THR, RISK, CAPV, EXL, EXS, SM, MINF, EXTRA, out):
    """out[j, r] = (final, dd %, dd_abs, skipped) of policy j on run r (v31lib._money31, no brake / half / cap_base)."""
    nc = THR.shape[0]; nr = len(eoff) - 1
    csl = np.zeros(16, np.bool_)
    for j in prange(nc):
        for r in range(nr):
            a, b = eoff[r], eoff[r + 1]; ra, rb = roff[r], roff[r + 1]; nrow = rb - ra
            res = W._money31(et[a:b], ek[a:b], ei[a:b], d[ra:rb], R[ra:rb], c[ra:rb], m[ra:rb], eq0[r], THR[j], RISK[j], CAPV[j],
                             EXL[j], EXS[j], SM[j], False, MINF[j], 1.0, EXTRA[j], 1.0, np.zeros(nrow), 1.0, 0.0, 0.0, 1.0,
                             RISK[j][:, 0].copy(), 0, fixed[r], np.ones(nrow), csl, 0.0, False, np.zeros(nrow))
            out[j, r, 0] = res[0]; out[j, r, 1] = res[1]; out[j, r, 2] = res[3]; out[j, r, 3] = res[2]


def run_kernel(runs, P):
    o = np.zeros((len(P["THR"]), runs.n, 4))
    kernel(runs.et, runs.ek, runs.ei, runs.eoff, runs.d, runs.R, runs.c, runs.m, runs.roff, runs.eq0, runs.fixed,
           P["THR"], P["RISK"], P["CAPV"], P["EXL"], P["EXS"], P["SM"], P["MINF"], P["EXTRA"], o)
    return o


# ══ policies ═══════════════════════════════════════════════════════════════════════════════════════════════════════
BASE = dict(btc=5.0, eth_r=0.66, alt_r=0.166, w_bnb=1.0, w_sol=1.0, w_ada=1.0, s_maj=0.5, s_alt=0.5, cap_r=1.10, minf=0.25,
            volc=0.25, units=3.0, ladder=((0, 1.0), (1000, 1.0), (10000, 0.5)))


TOP_ETH, TOP_ALT = 1.7 / (2.5 * 0.66), 0.42 / (2.5 * 0.166)


def portfolio_policy():
    """The live portfolio.json + configs exactly (Option 1)."""
    pf = json.loads((C.ROOT / "cryptobot" / "portfolio.json").read_text())
    rows = [(float(r["from_usdt"]), [float(r[s]) for s in W.COINS], float(r["cap_pct"])) for r in sorted(pf["risk_ladder"], key=lambda r: r["from_usdt"])]
    return dict(rows=rows, minf=float(pf.get("cap_min_fraction", 0.25)), smult=[0.5] * 5, extra={5: 3.0 / 6, 6: 0.25})


def policy(p):
    p = dict(BASE, **p)
    rows = []
    for f, k in p["ladder"]:
        b = p["btc"] * k
        te, ta = (TOP_ETH, TOP_ALT) if k < 1.0 else (1.0, 1.0)   # the live top row keeps v3.0's rounding (ETH 1.7, alts 0.42)
        rows.append((float(f), [b, b * p["eth_r"] * te, b * p["alt_r"] * p["w_bnb"] * ta, b * p["alt_r"] * p["w_sol"] * ta,
                                b * p["alt_r"] * p["w_ada"] * ta], b * p["cap_r"]))
    cw = p.get("coin_w")
    if cw:                                                   # stage 1: one coin's weight x w (the cap unchanged)
        rows = [(f, [v * cw.get(i, 1.0) for i, v in enumerate(rk)], cp) for f, rk, cp in rows]
    return dict(rows=rows, minf=p["minf"], smult=[p["s_maj"], p["s_maj"], p["s_alt"], p["s_alt"], p["s_alt"]],
                extra={5: p["units"] / 6, 6: p["volc"]})


def pack(pols, nrow=3):
    n = len(pols)
    THR = np.full((n, nrow), 1e18); RISK = np.zeros((n, nrow, 5)); CAPV = np.zeros((n, nrow))
    EXL = np.zeros((n, 5), np.bool_); EXS = np.zeros((n, 5), np.bool_); EXL[:, 0] = True; EXS[:, 0] = True
    SM = np.zeros((n, 5)); MINF = np.zeros(n); EXTRA = np.zeros((n, 16))
    for j, q in enumerate(pols):
        rows = q["rows"]
        assert len(rows) <= nrow
        for r, (f, rk, cp) in enumerate(rows):
            THR[j, r] = f; RISK[j, r] = rk; CAPV[j, r] = cp
        for r in range(len(rows), nrow):                    # (unused rows: never reached; same values as the last)
            RISK[j, r] = rows[-1][1]; CAPV[j, r] = rows[-1][2]
        SM[j] = q["smult"]; MINF[j] = q["minf"]
        for k_, v in q["extra"].items():
            EXTRA[j, k_] = v
    THR[:, 0] = np.minimum(THR[:, 0], 0.0)
    return dict(THR=THR, RISK=RISK, CAPV=CAPV, EXL=EXL, EXS=EXS, SM=SM, MINF=MINF, EXTRA=EXTRA)


# ══ the run sets ═══════════════════════════════════════════════════════════════════════════════════════════════════
WINS = (("2020", "2020-01-01"), ("2022", "2022-01-01"), ("2024", "2024-01-01"), ("sep26", "2026-09-15"), ("oct26", "2026-10-01"))
ERA_EQ = 5000.0                                            # fixed-size account in the $1,000-10,000 row (scale-free ratio)


def run_sets(A, phase=True, panic=None, volc_w=None):
    """windows (5, from $300), bootstrap journeys (NJ, from $300, 2 years), era fixed accounts (shift 0 + 40 phase copies,
    2020-23 and 2024-26)."""
    win = Runs([prep(W.window(A, a)) for _, a in WINS], 300.0, False)
    paths = V0.boot_paths(NJ, seed=0)
    boot = Runs([prep(W.path_rows(A, us)) for us in paths], 300.0, False)
    era = None
    if phase:
        parts = []
        for sh in [0] + list(M.SH):
            As = A if sh == 0 else rows_full(M.base_at(sh), panic, volc_w)
            for per in (P20, P24):
                a, b = W.PERIODS[per]
                parts.append(prep(W.window(As, a, b)))
        era = Runs(parts, ERA_EQ, True)
    return win, boot, era


def evaluate(pols, win, boot, era, chunk=500):
    rows = []
    for s in range(0, len(pols), chunk):
        P = pack(pols[s:s + chunk])
        ow = run_kernel(win, P); ob = run_kernel(boot, P); oe = run_kernel(era, P) if era is not None else None
        for j in range(len(P["THR"])):
            r = {}
            for k, (nm, _) in enumerate(WINS):
                r[f"m_{nm}"] = ow[j, k, 0]; r[f"dd_{nm}"] = ow[j, k, 1]
            fb = ob[j, :, 0]; db = ob[j, :, 1]
            r.update(boot_med=float(np.median(fb)), boot_p10=float(np.percentile(fb, 10)), boot_dd90=float(np.percentile(db, 90)),
                     p_10k=float((fb >= 10_000).mean()), skipped_2022=ow[j, 1, 3])
            if oe is not None:
                ratio = (oe[j, :, 0] - ERA_EQ) / np.maximum(oe[j, :, 2], 1e-9)
                r["era_dev"], r["era_oos"] = ratio[0], ratio[1]
                r["_era"] = ratio                            # (all shifts: dev, oos interleaved)
            rows.append(r)
    return rows


# ══ check ══════════════════════════════════════════════════════════════════════════════════════════════════════════
def check():
    setup()
    X = M.base_at(0); A = rows_full(X)
    ref = pd.read_pickle(C.D.CACHE / "v33" / "ref_money_v32.pkl")
    t0 = time.time()
    win, boot, _ = run_sets(A, phase=False)
    out(f"[check] run sets built: windows {win.n}, journeys {boot.n} [{time.time() - t0:.1f}s]")
    pols = [portfolio_policy(), policy({})]
    t0 = time.time(); r = evaluate(pols, win, boot, None)
    out(f"[check] kernel (2 policies x {win.n + boot.n} runs) [{time.time() - t0:.1f}s]")
    for nm, q in zip(("portfolio.json exact", "grid generator at the base point"), r):
        out(f"[check] {nm}: 2022 ${q['m_2022']:,.0f} / {q['dd_2022']:.2f}%, 2024 ${q['m_2024']:,.0f} / {q['dd_2024']:.2f}%, "
            f"boot ${q['boot_med']:,.0f} / ${q['boot_p10']:,.0f} / {q['boot_dd90']:.2f}%")
    out(f"[check] reference (v33, money31): 2022 ${ref['m2022']:,.0f} / {ref['dd2022']:.2f}%, 2024 ${ref['m2024']:,.0f} / {ref['dd2024']:.2f}%, "
        f"boot ${ref['boot_med']:,.0f} / ${ref['boot_p10']:,.0f} / {ref['boot_dd90']:.2f}%")
    P = pack([policy({})] * 2000)
    t0 = time.time(); run_kernel(boot, P)
    out(f"[check] speed: 2000 policies x {boot.n} journeys [{time.time() - t0:.1f}s]")




# ══ shared tables ══════════════════════════════════════════════════════════════════════════════════════════════════
SHOW = ["m_2022", "dd_2022", "m_2024", "dd_2024", "dd_sep26", "dd_oct26", "boot_med", "boot_p10", "boot_dd90", "p_10k"]


def era_cols(rows, base_era):
    """x of the fixed-size capped account's ret / max DD vs the baseline (shift 0, 2020-23 and 2024-26) and the share of
    the 41 trade lists (shift 0 + 40 phase copies) with x > 1 in both periods."""
    for r in rows:
        e = r.pop("_era", None)
        if e is None:
            continue
        x = e / base_era
        r["era_x_dev"], r["era_x_oos"] = x[0], x[1]
        r["era_phase"] = float(np.mean((x[0::2] > 1 + 1e-9) & (x[1::2] > 1 + 1e-9)))
    return rows


def fmt_table(df, cols):
    f = {c: "{:,.0f}".format for c in cols if c.startswith(("m_", "boot_med", "boot_p10"))}
    f.update({c: "{:.2f}".format for c in cols if c.startswith(("dd_", "boot_dd", "era_x"))})
    f.update({c: "{:.3f}".format for c in cols if c in ("p_10k", "era_phase")})
    return df[cols].to_string(index=False, formatters=f)


def bs_policy(q):
    """botsim policy (scalar short multiplier) from a stage policy, for the per-coin counts."""
    import botsim as BS
    pol = dict(rows=[(f, list(rk), cp) for f, rk, cp in q["rows"]], exempt={0}, minf=q["minf"], smult=q["smult"][0], mult=1.0)
    return BS.full_policy(pol)


def coin_counts(q, a="2024-01-01"):
    """Per coin: TBO entries taken at full size / shrunk by the cap / skipped by the cap, one $300 account from a (botsim, the
    same rule as money31)."""
    import botsim as BS
    x, t0, t1, nb = BS.window_full(a, "2026-11-07"); x = x.copy(); x[:, :3] -= t0
    r = BS.run(x, bs_policy(q), 300.0, keep="trades")
    out_ = {}
    for i in range(nb):
        if i not in r["full"] or x[i, 1] >= x[:, 1].max():
            continue
        c = int(x[i, 5]); want = r["full"][i][0]
        st = "skipped" if i not in r["amts"] else ("shrunk" if r["amts"][i] < 0.995 * want else "full")
        out_.setdefault(W.COINS[c][:-4], {"full": 0, "shrunk": 0, "skipped": 0})[st] += 1
    return out_


# ══ STAGE 1 ════════════════════════════════════════════════════════════════════════════════════════════════════════
def stage1():
    setup(); X = M.base_at(0); A = rows_full(X)
    out("\n=== STAGE 1: coupled marginal sweeps (each change alone, inside the joint capped portfolio) ===")
    win, boot, era = run_sets(A)
    specs = [("baseline v3.2.1", {})]
    for i, nm in enumerate(["BTC", "ETH", "BNB", "SOL", "ADA"]):
        for w in (0.0, 0.5, 0.75, 1.25, 1.5, 2.0):
            specs.append((f"{nm} weight x{w}", dict(coin_w={i: w})))
    for sm in (0.35, 0.65, 0.8, 1.0):
        specs.append((f"short mult {sm} (all)", dict(s_maj=sm, s_alt=sm)))
    for sm in (0.35, 0.65, 0.8, 1.0):
        specs.append((f"short mult {sm} (BTC/ETH only)", dict(s_maj=sm)))
    for sm in (0.35, 0.65, 0.8, 1.0):
        specs.append((f"short mult {sm} (alts only)", dict(s_alt=sm)))
    for cr in (1.00, 1.15, 1.20, 1.25, 1.35, 1.50):
        specs.append((f"cap {cr:.2f} x BTC", dict(cap_r=cr)))
    for v in (0.0, 0.15, 0.20, 0.30, 0.35, 0.40):
        specs.append((f"VOLC share {v}", dict(volc=v)))
    for u in (0.0, 2.0, 2.5, 3.5, 4.0):
        specs.append((f"panic units {u}", dict(units=u)))
    t0 = time.time()
    rows = evaluate([policy(p) for _, p in specs], win, boot, era)
    base_era = rows[0]["_era"].copy()
    rows = era_cols(rows, base_era)
    T = pd.DataFrame(rows); T.insert(0, "setting", [n for n, _ in specs])
    # sleeve variants that change the trade rows: panic extra pool / max extra open, VOLC coin-weighted
    vw = {"BTCUSDT": 1.0, "ETHUSDT": 0.66, "BNBUSDT": 0.166, "SOLUSDT": 0.166, "ADAUSDT": 0.166}
    V = pd.read_pickle(C.D.CACHE / "volc_trades_v32.pkl"); norm = 1.0 / V.sym.map(vw).mean()
    extra = [("panic extra_share 0.0", dict(panic=panic_rows(0.0, 2))), ("panic extra_share 0.5", dict(panic=panic_rows(0.5, 2))),
             ("panic extra_share 1.0", dict(panic=panic_rows(1.0, 2))), ("panic max_extra_open 1", dict(panic=panic_rows(0.75, 1))),
             ("panic max_extra_open 3", dict(panic=panic_rows(0.75, 3))),
             ("VOLC coin-weighted (TBO ratios)", dict(volc_w=vw)),
             ("VOLC coin-weighted, same total", dict(volc_w={k: v * norm for k, v in vw.items()}))]
    xr = []
    for nm, kw in extra:
        A2 = rows_full(X, kw.get("panic"), kw.get("volc_w"))
        w2, b2, e2 = run_sets(A2, panic=kw.get("panic"), volc_w=kw.get("volc_w"))
        r = era_cols(evaluate([policy({})], w2, b2, e2), base_era)[0]; r["setting"] = nm; xr.append(r)
    T = pd.concat([T, pd.DataFrame(xr)], ignore_index=True)
    b = T.iloc[0]
    for c in ("m_2022", "m_2024", "boot_med", "boot_p10"):
        T[f"d_{c}"] = (T[c] / b[c] - 1) * 100
    for c in ("dd_2024", "boot_dd90"):
        T[f"d_{c}"] = T[c] - b[c]
    T.drop(columns=[c for c in T if c.startswith("_")]).to_csv(RES / "v34_stage1_marginal.csv", index=False)
    cols = ["setting"] + SHOW + ["era_x_dev", "era_x_oos", "era_phase"]
    out(f"[stage1] {len(T)} settings [{time.time() - t0:.0f}s]")
    out(fmt_table(T, cols))
    out("\n[stage1] per-coin TBO entries, one $300 account from Jan 2024 (full size / shrunk by the cap / skipped by the cap):")
    rows_c = []
    for nm, p in [("baseline v3.2.1", {})] + [(f"cap {cr:.2f} x BTC", dict(cap_r=cr)) for cr in (1.00, 1.20, 1.35, 1.50)] + \
                 [("ETH weight x0.75", dict(coin_w={1: 0.75})), ("ETH weight x1.25", dict(coin_w={1: 1.25}))]:
        for a in ("2022-01-01", "2024-01-01"):
            cc = coin_counts(policy(p), a)
            rows_c.append(dict(setting=nm, start=a[:4], **{f"{k}_{s_}": v[s_] for k, v in cc.items() for s_ in ("full", "shrunk", "skipped")}))
    Cc = pd.DataFrame(rows_c); Cc.to_csv(RES / "v34_stage1_cap_counts.csv", index=False)
    out(Cc.to_string(index=False))
    pd.to_pickle(base_era, CDIR / "base_era.pkl")


# ══ STAGE 2 ════════════════════════════════════════════════════════════════════════════════════════════════════════
AX = dict(btc=[4.0, 4.5, 5.0, 5.5, 6.0], eth_r=[0.50, 0.60, 0.66, 0.75, 0.85], alt_r=[0.12, 0.166, 0.20, 0.25], altpat=[0, 1, 2],
          short=[0.40, 0.50, 0.65], cap_r=[1.10, 1.15, 1.22, 1.30, 1.40], volc=[0.20, 0.25, 0.30, 0.35], units=[2.5, 3.0, 3.5])
PAT = {0: (1.0, 1.0, 1.0), 1: (1.25, 1.25, 0.75), 2: (1.5, 1.5, 0.5)}        # (BNB, SOL, ADA) x the alt unit
BASE_IDX = dict(btc=2, eth_r=2, alt_r=1, altpat=0, short=1, cap_r=0, volc=1, units=1)
STRUCT = ["eth_r", "alt_r", "altpat", "short", "cap_r", "volc", "units"]      # (btc: a pure scale, the ratio is unchanged)
OPT = {  # name: (dd_2024 band, dd90 band, extra floors); neighbours count if dd_2024 / dd90 <= the band's top + 1 and
         # their 2024 money and bootstrap median >= 90% of the setting's
    "O2 max profit at <= current drawdown": ((0.0, 26.2015), (0.0, 44.43), {}),   # (v3.2.1: 26.2015% / 44.43%)
    "O3 balanced sweet spot": ((23.0, 24.5), (40.0, 42.0), dict(m_2024=74_000.0, boot_med=28_800.0)),
    "O4 low-drawdown shield": ((20.0, 22.0), (0.0, 40.0), {}),
    "O5 high-growth compounder": ((28.0, 30.0), (46.0, 48.0), {}),
}


def grid_params(ix):
    p = {k: AX[k][ix[k]] for k in AX}
    w = PAT[p.pop("altpat")]
    sm = p.pop("short")
    return dict(p, w_bnb=w[0], w_sol=w[1], w_ada=w[2], s_maj=sm, s_alt=sm)


def plateau_cols(G, keys, sizes):
    """Per option: share of the 1-step neighbours (+-1 on one axis) inside the option's drawdown limit (+1 pt) with 2024 money
    and bootstrap median >= 90% of the setting's."""
    code = np.zeros(len(G), np.int64); mul = 1
    for k, n in zip(keys[::-1], sizes[::-1]):
        code += G[f"i_{k}"].to_numpy() * mul; mul *= n
    pos = pd.Series(np.arange(len(G)), index=code)
    strides = {}; mul = 1
    for k, n in zip(keys[::-1], sizes[::-1]):
        strides[k] = mul; mul *= n
    nb = []
    for k, n in zip(keys, sizes):
        ik = G[f"i_{k}"].to_numpy()
        for dlt in (-1, 1):
            ok = (ik + dlt >= 0) & (ik + dlt < n)
            tgt = np.where(ok, code + dlt * strides[k], -1)
            nb.append(np.where(ok, pos.reindex(tgt).fillna(-1).to_numpy(np.int64), -1))
    nb = np.stack(nb, axis=1)                               # (n, 2 x axes), -1 = none
    d24, d90, m24, bm = (G[c].to_numpy() for c in ("dd_2024", "boot_dd90", "m_2024", "boot_med"))
    for name, ((_, hi24), (_, hi90), _) in OPT.items():
        ok_n = np.zeros(nb.shape, bool); has = nb >= 0
        j = np.where(has, nb, 0)
        ok_n = has & (d24[j] <= hi24 + 1.0) & (d90[j] <= hi90 + 1.0) & (m24[j] >= 0.9 * m24[:, None]) & (bm[j] >= 0.9 * bm[:, None])
        G[f"plateau_{name[:2]}"] = ok_n.sum(1) / np.maximum(has.sum(1), 1)
    G["n_neighbours"] = (nb >= 0).sum(1)
    return G


def stage2(ladder=None, minf=None, tag="v34_stage2_grid"):
    setup(); X = M.base_at(0); A = rows_full(X)
    base_era = pd.read_pickle(CDIR / "base_era.pkl")
    keys = list(AX); sizes = [len(AX[k]) for k in keys]
    idx = list(itertools.product(*[range(n) for n in sizes]))
    out(f"\n=== STAGE 2: joint grid {' x '.join(f'{k} {len(AX[k])}' for k in keys)} = {len(idx):,} settings"
        + (f" (ladder {ladder}, cap_min_fraction {minf})" if ladder else " (ladder and cap_min_fraction as live)") + " ===")
    win, boot, era = run_sets(A)
    pols = []
    for ix in idx:
        p = grid_params(dict(zip(keys, ix)))
        if ladder:
            p["ladder"] = ladder
        if minf:
            p["minf"] = minf
        pols.append(policy(p))
    t0 = time.time()
    rows = era_cols(evaluate(pols, win, boot, era, chunk=2000), base_era)
    out(f"[stage2] evaluated {len(rows):,} settings x {win.n + boot.n + era.n} runs [{time.time() - t0:.0f}s]")
    G = pd.DataFrame(rows)
    for k, i in zip(keys, np.array(idx).T):
        G[f"i_{k}"] = i; G[k] = np.array(AX[k])[i]
    G["structural"] = np.zeros(len(G), bool)
    for k in STRUCT:
        G["structural"] |= G[f"i_{k}"] != BASE_IDX[k]
    G["era_ok"] = ~G.structural | ((G.era_x_dev > 1) & (G.era_x_oos > 1) & (G.era_phase >= 0.8))
    G = plateau_cols(G, keys, sizes)
    G.to_pickle(CDIR / f"{tag}.pkl")
    G.drop(columns=[c for c in G if c.startswith("i_")]).to_csv(RES / f"{tag}.csv.gz", index=False, compression="gzip")
    return G


def pick(G, name):
    (lo24, hi24), (lo90, hi90), floors = OPT[name]
    c = G[(G.dd_2024 >= lo24) & (G.dd_2024 <= hi24) & (G.boot_dd90 >= lo90) & (G.boot_dd90 <= hi90) & G.era_ok]
    for k, v in floors.items():
        c = c[c[k] >= v]
    return c


def stage2_report(G, tag="stage2"):
    b = G[(G.btc == 5.0) & (G.eth_r == 0.66) & (G.alt_r == 0.166) & (G.altpat == 0) & (G.short == 0.5) & (G.cap_r == 1.10) & (G.volc == 0.25) & (G.units == 3.0)]
    out(f"[{tag}] baseline point in the grid: " + ", ".join(f"{k} {b.iloc[0][k]:.4g}" for k in SHOW) +
        " | plateaus " + ", ".join(f"{c} {b.iloc[0][c]:.2f}" for c in G if c.startswith("plateau_")))
    out(f"[{tag}] era gate: {int(G.structural.sum()):,} structural settings, {int((G.structural & G.era_ok).sum()):,} improve ret / max DD in "
        f"2020-23 AND 2024-26 with >= 80% of the 41 trade lists")
    for k in STRUCT:                                         # one axis at a time from the baseline: the era read
        sub = G[np.all([G[f"i_{o}"] == BASE_IDX[o] for o in AX if o != k], axis=0)].sort_values(k)
        out(f"[{tag}] era read, {k} alone: " + "; ".join(f"{v:g}: x {a:.3f} / {c:.3f} ({ph:.0%})" for v, a, c, ph in
                                                         zip(sub[k], sub.era_x_dev, sub.era_x_oos, sub.era_phase)))
    cols = list(AX) + SHOW + ["era_x_dev", "era_x_oos", "era_phase", "era_ok"]
    for name in OPT:
        c = pick(G, name); pc = f"plateau_{name[:2]}"
        good = c[c[pc] >= 0.8].sort_values(["boot_med", "m_2024"], ascending=False)
        out(f"\n[{tag}] {name}: {len(c):,} settings in the band (era-ok), {len(good):,} on a >= 80% plateau; best 8:")
        out(fmt_table(good.head(8), cols + [pc]) if len(good) else "   (none)")


# ══ STAGE 2b: ladder and cap_min_fraction ══════════════════════════════════════════════════════════════════════════
LADDERS = {
    "live: 10k x0.5": ((0, 1.0), (1000, 1.0), (10000, 0.5)),
    "5k x0.5": ((0, 1.0), (5000, 0.5)), "25k x0.5": ((0, 1.0), (25000, 0.5)), "1k x0.5": ((0, 1.0), (1000, 0.5)),
    "10k x0.45": ((0, 1.0), (10000, 0.45)), "10k x0.6": ((0, 1.0), (10000, 0.6)),
    "5k x0.6": ((0, 1.0), (5000, 0.6)), "25k x0.45": ((0, 1.0), (25000, 0.45)), "25k x0.6": ((0, 1.0), (25000, 0.6)),
    "5k x0.75, 25k x0.5": ((0, 1.0), (5000, 0.75), (25000, 0.5)), "5k x0.75, 10k x0.5": ((0, 1.0), (5000, 0.75), (10000, 0.5)),
    "10k x0.6, 25k x0.45": ((0, 1.0), (10000, 0.6), (25000, 0.45)), "no step-down": ((0, 1.0),),
}


def stage2b():
    setup(); X = M.base_at(0); A = rows_full(X)
    base_era = pd.read_pickle(CDIR / "base_era.pkl")
    G = pd.read_pickle(CDIR / "v34_stage2_grid.pkl")
    win, boot, era = run_sets(A)
    seeds = {"baseline": G[(G.btc == 5.0) & (G.eth_r == 0.66) & (G.alt_r == 0.166) & (G.altpat == 0) & (G.short == 0.5) & (G.cap_r == 1.10) &
                           (G.volc == 0.25) & (G.units == 3.0)].iloc[0]}
    for name in OPT:
        c = pick(G, name); c = c[c[f"plateau_{name[:2]}"] >= 0.8].sort_values(["boot_med", "m_2024"], ascending=False)
        if len(c):
            seeds[name[:2]] = c.iloc[0]
    out("\n=== STAGE 2b: ladder structure x cap_min_fraction on the baseline and each stage-2 option ===")
    rows = []
    for sn, r in seeds.items():
        ix = {k: int(r[f"i_{k}"]) for k in AX}
        for (ln, lad), mf in itertools.product(LADDERS.items(), (0.20, 0.25)):
            p = grid_params(ix); p["ladder"] = lad; p["minf"] = mf
            rows.append(dict(seed=sn, ladder=ln, minf=mf, _p=p))
    res = era_cols(evaluate([policy(r["_p"]) for r in rows], win, boot, era), base_era)
    T = pd.DataFrame([dict({k: v for k, v in a.items() if k != "_p"}, **b) for a, b in zip(rows, res)])
    T.to_csv(RES / "v34_stage2b_ladder_minf.csv", index=False)
    for sn in seeds:
        out(f"\n[stage2b] seed {sn}:")
        out(fmt_table(T[T.seed == sn], ["ladder", "minf"] + SHOW))


# ══ STAGE 4 ════════════════════════════════════════════════════════════════════════════════════════════════════════
def full_metrics(q, A):
    import v32c_exact_engine_and_ladder as V32C
    pol = dict(rows=q["rows"], exempt={0}, exempt_s={0}, minf=q["minf"], smult_c=list(q["smult"]), cap_short=None, mult=1.0,
               extra=[(k, v) for k, v in q["extra"].items()])
    r = V32C.money_full(A, pol)
    w = W.money31(W.window(A, "2024-01-01"), pol, path=True); pt, pe, _ = w["path"]
    t0 = pd.Timestamp("2024-01-01").value // 60_000_000_000
    sr = pd.Series(pe, index=pd.to_datetime((pt + t0) * 60_000_000_000)).sort_index()
    me = sr.resample("ME").last().ffill(); ret = me.pct_change(); ret.iloc[0] = me.iloc[0] / 300.0 - 1
    r["losing_months"] = int((ret < 0).sum()); r["months"] = len(ret)
    return r


def stage4():
    setup(); X = M.base_at(0); A = rows_full(X)
    G = pd.read_pickle(CDIR / "v34_stage2_grid.pkl")
    out("\n=== STAGE 4: five options (full metrics; plateau = share of 1-step neighbours inside the option's limits) ===")
    opts = [("O1 current v3.2.1 (26f07bf)", portfolio_policy(), G[(G.btc == 5.0) & (G.eth_r == 0.66) & (G.alt_r == 0.166) & (G.altpat == 0) &
                                                                    (G.short == 0.5) & (G.cap_r == 1.10) & (G.volc == 0.25) & (G.units == 3.0)].iloc[0])]
    for name in OPT:
        c = pick(G, name); c = c[c[f"plateau_{name[:2]}"] >= 0.8].sort_values(["boot_med", "m_2024"], ascending=False)
        if len(c):
            r = c.iloc[0]; opts.append((name, policy(grid_params({k: int(r[f"i_{k}"]) for k in AX})), r))
        else:
            out(f"[stage4] {name}: no setting in the band on a >= 80% plateau")
    rows = []
    for name, q, g in opts:
        fm = full_metrics(q, A)
        prm = {f"{c}_{w}": rk[i] for (f_, rk, cp), w in zip(q["rows"], ("r0", "r1", "r2")) for i, c in enumerate(["BTC", "ETH", "BNB", "SOL", "ADA"])}
        prm.update({f"cap_{w}": cp for (f_, rk, cp), w in zip(q["rows"], ("r0", "r1", "r2"))})
        rows.append(dict(option=name, short=q["smult"][0], volc=q["extra"][6], panic_units=q["extra"][5] * 6, minf=q["minf"],
                         **{f"plateau_{k}": g[f"plateau_{k}"] for k in ("O2", "O3", "O4", "O5")},
                         era_x_dev=g.get("era_x_dev", 1.0), era_x_oos=g.get("era_x_oos", 1.0), era_phase=g.get("era_phase", np.nan),
                         **{k: g[k] for k in AX}, **prm, **fm))
    T = pd.DataFrame(rows); T.to_csv(RES / "v34_stage4_options.csv", index=False)
    out(T.T.to_string(header=False))


# ══ STAGE 3: the risk dial on the era-robust structure, ladders, cap_min_fraction, explicit 1-step plateaus ══════════
DIAL = [round(x, 2) for x in np.arange(3.5, 6.51, 0.1)]
LAD_ORDER = list(LADDERS)


def neighbours(c):
    """+-1 step of the stage-2 grid on each of its 8 axes around the setting c (BTC: +-0.5 points)."""
    out_ = []
    for k in AX:
        if k == "btc":
            for d in (-0.5, 0.5):
                out_.append(dict(c, btc=round(c["btc"] + d, 2)))
            continue
        i = AX[k].index(c[k])
        for d in (-1, 1):
            if 0 <= i + d < len(AX[k]):
                out_.append(dict(c, **{k: AX[k][i + d]}))
    return out_


def to_policy(c):
    w = PAT[c["altpat"]]
    return policy(dict(btc=c["btc"], eth_r=c["eth_r"], alt_r=c["alt_r"], w_bnb=w[0], w_sol=w[1], w_ada=w[2], s_maj=c["short"],
                       s_alt=c["short"], cap_r=c["cap_r"], volc=c["volc"], units=c["units"], ladder=LADDERS[c["ladder"]], minf=c["minf"]))


def in_band(r, name):
    (lo24, hi24), (lo90, hi90), floors = OPT[name]
    return lo24 <= r["dd_2024"] <= hi24 and lo90 <= r["boot_dd90"] <= hi90 and all(r[k] >= v for k, v in floors.items())


def stage3():
    setup(); X = M.base_at(0); A = rows_full(X)
    base_era = pd.read_pickle(CDIR / "base_era.pkl")
    win, boot, era = run_sets(A)
    out("\n=== STAGE 3: risk dial (BTC 3.5-6.5% by 0.1, the era-robust v3.2.1 structure) x 13 ladders x cap_min_fraction 0.20 / 0.25 ===")
    base_c = dict(btc=5.0, eth_r=0.66, alt_r=0.166, altpat=0, short=0.5, cap_r=1.10, volc=0.25, units=3.0)
    cands = [dict(base_c, btc=b, ladder=ln, minf=mf) for b in DIAL for ln in LAD_ORDER for mf in (0.25, 0.20)]
    t0 = time.time()
    res = era_cols(evaluate([to_policy(c) for c in cands], win, boot, era, chunk=1000), base_era)
    D = pd.DataFrame([dict(c, **r) for c, r in zip(cands, res)])
    D["era_ok"] = (D.minf == 0.25) | ((D.era_x_dev > 1) & (D.era_x_oos > 1) & (D.era_phase >= 0.8))   # (scale / ladder: ratio unchanged)
    out(f"[stage3] {len(D):,} dial settings [{time.time() - t0:.0f}s]; cap_min_fraction 0.20 era read at BTC 5%, live ladder: "
        + str(D[(D.btc == 5.0) & (D.ladder == LAD_ORDER[0]) & (D.minf == 0.20)][["era_x_dev", "era_x_oos", "era_phase"]].round(3).to_dict("records")))
    D.to_csv(RES / "v34_stage3_dial.csv", index=False)
    # ladder read at the live BTC level
    out("\n[stage3] ladders at BTC 5%, cap_min_fraction 0.25:")
    out(fmt_table(D[(D.btc == 5.0) & (D.minf == 0.25)], ["ladder"] + SHOW))
    out("\n[stage3] the BTC dial on the live ladder (cap_min_fraction 0.25):")
    out(fmt_table(D[(D.ladder == LAD_ORDER[0]) & (D.minf == 0.25) & (D.btc.isin([3.5, 4.0, 4.3, 4.5, 4.7, 5.0, 5.3, 5.5, 6.0, 6.5]))], ["btc"] + SHOW))
    # options: best bootstrap median in the band, then the explicit 1-step plateau (stage-2 axes) of the top candidates
    picks = {}
    for name in OPT:
        c = D[D.era_ok & D.apply(lambda r: in_band(r, name), axis=1)].sort_values(["boot_med", "m_2024"], ascending=False)
        out(f"\n[stage3] {name}: {len(c)} dial settings in the band (all scored; the 12 best by bootstrap median shown, then the pick)")
        best = None; scored = []
        for n_, (_, r) in enumerate(c.iterrows()):
            cen = {k: r[k] for k in list(base_c) + ["ladder", "minf"]}
            nbs = neighbours(cen)
            nr = evaluate([to_policy(n) for n in nbs], win, boot, None)
            (_, hi24), (_, hi90), _ = OPT[name]
            ok = [n["dd_2024"] <= hi24 + 1 and n["boot_dd90"] <= hi90 + 1 and n["m_2024"] >= 0.9 * r["m_2024"] and n["boot_med"] >= 0.9 * r["boot_med"]
                  for n in nr]
            pl = float(np.mean(ok))
            fails = [f"{k}{'+' if (n[k] > cen[k]) else '-'}" for n, o in zip(nbs, ok) if not o for k in AX if n[k] != cen[k]]
            line = (f"   BTC {r['btc']:.1f} {r['ladder']:<20} minf {r['minf']:.2f}: 2024 ${r['m_2024']:,.0f} / {r['dd_2024']:.2f}%, boot ${r['boot_med']:,.0f} / "
                    f"${r['boot_p10']:,.0f} / {r['boot_dd90']:.2f}%  plateau {pl:.0%} (fails: {' '.join(fails) or '-'})")
            if n_ < 12:
                out(line)
            scored.append((pl, r["boot_med"], dict(cen, plateau=pl, fails=" ".join(fails)), line))
            if pl >= 0.8 and best is None:
                best = dict(cen, plateau=pl, fails=" ".join(fails), flag="")
                out("   PICK (best bootstrap median on a >= 80% plateau):" + line[2:])
        if best is None and scored:
            pl, _, cen_, line = sorted(scored, key=lambda z: (-z[0], -z[1]))[0]
            best = dict(cen_, flag=f"no setting in the band reaches an 80% plateau; highest plateau found {pl:.0%}")
            out(f"   PICK (none >= 80%: the highest plateau in the band):" + line[2:])
        picks[name] = best
    pd.to_pickle(picks, CDIR / "stage3_picks.pkl")
    # the baseline's own plateau under each option rule
    cen = dict(base_c, ladder=LAD_ORDER[0], minf=0.25); nbs = neighbours(cen)
    nr = evaluate([to_policy(n) for n in nbs], win, boot, None); b = evaluate([to_policy(cen)], win, boot, None)[0]
    for name in OPT:
        (_, hi24), (_, hi90), _ = OPT[name]
        ok = [n["dd_2024"] <= hi24 + 1 and n["boot_dd90"] <= hi90 + 1 and n["m_2024"] >= 0.9 * b["m_2024"] and n["boot_med"] >= 0.9 * b["boot_med"] for n in nr]
        out(f"[stage3] baseline plateau under the {name[:2]} rule: {np.mean(ok):.0%}")
    NB = pd.DataFrame([dict(n, **{k: v for k, v in r.items() if not k.startswith("_")}) for n, r in zip(nbs, nr)])
    NB.to_csv(RES / "v34_stage3_baseline_neighbours.csv", index=False)
    out("\n[stage3] the baseline's 16 one-step neighbours:")
    out(fmt_table(NB, list(AX) + SHOW))


def stage4b():
    """Full metrics for O1 (live) and the stage-3 picks."""
    setup(); X = M.base_at(0); A = rows_full(X)
    picks = pd.read_pickle(CDIR / "stage3_picks.pkl")
    out("\n=== STAGE 4: the five options, full metrics ===")
    opts = [("O1 current v3.2.1 (26f07bf)", portfolio_policy(), dict(btc=5.0, eth_r=0.66, alt_r=0.166, altpat=0, short=0.5, cap_r=1.10, volc=0.25,
                                                                   units=3.0, ladder=LAD_ORDER[0], minf=0.25, plateau=np.nan))]
    for name, c in picks.items():
        if c is not None:
            opts.append((name, to_policy(c), c))
    rows = []
    for name, q, c in opts:
        fm = full_metrics(q, A)
        prm = {}
        for (f_, rk, cp), w in zip(q["rows"], ("r0", "r1", "r2")):
            prm[f"{w}_from"] = f_
            prm.update({f"{w}_{cn}": round(rk[i], 4) for i, cn in enumerate(["BTC", "ETH", "BNB", "SOL", "ADA"])})
            prm[f"{w}_cap"] = round(cp, 4)
        rows.append(dict(option=name, ladder=c["ladder"], minf=c["minf"], short=q["smult"][0], volc=q["extra"][6], panic_units=q["extra"][5] * 6,
                         plateau=c.get("plateau"), **prm, **fm))
    T = pd.DataFrame(rows); T.to_csv(RES / "v34_stage4_options.csv", index=False)
    out(T.set_index("option").T.to_string())


if __name__ == "__main__":
    {"check": check, "stage1": stage1, "stage2": lambda: stage2_report(stage2()), "stage2b": stage2b, "stage4": stage4,
     "report2": lambda: stage2_report(pd.read_pickle(CDIR / "v34_stage2_grid.pkl")), "stage3": stage3, "stage4b": stage4b}[sys.argv[1]]()
