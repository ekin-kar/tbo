"""v3.5 research (Nov 2026): more strategies on top of the deployed v3.2.1 system (O1 = the v3.2.1 settings, commit 17a6ce1).
100% read-only on cryptobot/. Every candidate is scored against O1 in the exact capped simulator (v31lib._money31, via the
v3.4 numba kernel), with the same run sets: 5 windows from $300, 1,000 two-year bootstrap journeys, and the fixed-size capped
account on the trade list + its 40 phase copies (2020-23 / 2024-26).

  t1  4h VOLC on the 7 extra DEV12 coins (live-exact v33 engine, no TBO there): per-coin audit, then extra_share x
      max_extra_open x ranking (none / squeeze ATR14/ATR100 / OI build-up) x outside-or-inside the open-risk cap
  t2  TREND-PULLBACK resumption inside the 20-bar channel (stop order at the high of the last N 4h bars, TBO flat)
  t3  SQUEEZE-EXHAUSTION shorts (forced short squeeze: OI drop on a spike; euphoria blow-off)
  t4  WEEKEND-ALPHA (Monday box breakout; CME-close stop-hunt fade)
  t5  two own ideas: BTC-confirmed laggard catch-up; post-panic secondary continuation
  Standalone gates G1 (both eras: net > 0, PF >= 1.25, corr with TBO monthly <= 0.20, >= 75% positive month-block
  bootstraps), G2 (plateau >= 60% and the same sign on the out-of-universe coins), G3 (coupled: era x > 1 in both eras on
  >= 80% of the 41 trade lists, 2022 / 2024 money, bootstrap median / p10 up, 2024 DD <= 26.20, boot dd90 <= 44.43).

    python v35_new_strategies_and_volc_extra.py check | t1 | t2 | t3 | t4 | t5"""
import itertools, os, sys, time
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v32")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from numba import njit, prange
import common as C, v29lib as L, v30lib as V0, v31lib as W, v31deploy as D
import v31_drawdown_and_sleeves as M
import v34_risk_plateau_audit as V34
import v33_structural_frontiers as V33S
import panic_sleeve as PSL
import panic_signal as PS
import crypto_regimes as R

RES = M.RES
CDIR = C.D.CACHE / "v35"; CDIR.mkdir(parents=True, exist_ok=True)
LOG = RES / "v35_stage_output.txt"
P20, P24 = M.P20, M.P24
CORE = list(W.COINS); EXTRA7 = list(PSL.EXTRA_COINS); DEV12 = CORE + EXTRA7; HB14 = list(R.HOLD_BIG)
ERAS = {"dev": ("2022-01-01", "2024-01-01"), "oos": ("2024-01-01", "2026-11-07")}
# O1 = v3.2.1 (commit 17a6ce1) reference numbers (v3.4 parity check)
O1 = dict(m_2022=2_030_648, dd_2022=24.51, m_2024=74_343, dd_2024=26.20, boot_med=28_770, boot_p10=7_672, boot_dd90=44.43)
TAKER, MAKER, FUND, TP_PAD = C.TAKER, C.MAKER, C.FUNDING_8H, D.TP_PAD
pd.set_option("display.width", 300); pd.set_option("display.max_columns", 80); pd.set_option("display.max_rows", 400)


def out(*a):
    s = " ".join(str(x) for x in a)
    print(s, flush=True)
    with open(LOG, "a") as f:
        f.write(s + "\n")


# ══ money harness: O1 + extra sleeve rows through the exact capped simulator ═══════════════════════════════════════
_ST = {}


def setup():
    if "ok" in _ST:
        return
    V34.setup()
    V = pd.read_pickle(C.D.CACHE / "volc_trades_v32.pkl")
    _ST["panic"] = V34.panic_rows(); _ST["volc"] = V34.volc_rows(V); _ST["tbo_rows"] = {}
    _ST["ok"] = True


def tbo_rows(sh):
    if sh not in _ST["tbo_rows"]:
        X = M.base_at(sh)
        _ST["tbo_rows"][sh] = W.rows(X, half=True, mult=V34.m32(X))
    return _ST["tbo_rows"][sh]


NOX = np.zeros((0, 7))


def full_rows(sh, extra=NOX):
    return W.with_sleeve(tbo_rows(sh), np.r_[_ST["panic"], _ST["volc"], extra])


def run_sets_x(extra):
    A = full_rows(0, extra)
    win = V34.Runs([V34.prep(W.window(A, a)) for _, a in V34.WINS], 300.0, False)
    boot = V34.Runs([V34.prep(W.path_rows(A, us)) for us in V0.boot_paths(V34.NJ, seed=0)], 300.0, False)
    parts = []
    for sh in [0] + list(M.SH):
        As = A if sh == 0 else full_rows(sh, extra)
        for per in (P20, P24):
            a, b = W.PERIODS[per]
            parts.append(V34.prep(W.window(As, a, b)))
    return win, boot, V34.Runs(parts, V34.ERA_EQ, True)


@njit(parallel=True, cache=True)
def kernel2(et, ek, ei, eoff, d, R_, c, m, roff, eq0, fixed, THR, RISK, CAPV, EXL, EXS, SM, MINF, EXTRA, CSL, out_):
    nc = THR.shape[0]; nr = len(eoff) - 1
    for j in prange(nc):
        for r in range(nr):
            a, b = eoff[r], eoff[r + 1]; ra, rb = roff[r], roff[r + 1]; nrow = rb - ra
            res = W._money31(et[a:b], ek[a:b], ei[a:b], d[ra:rb], R_[ra:rb], c[ra:rb], m[ra:rb], eq0[r], THR[j], RISK[j], CAPV[j],
                             EXL[j], EXS[j], SM[j], False, MINF[j], 1.0, EXTRA[j], 1.0, np.zeros(nrow), 1.0, 0.0, 0.0, 1.0,
                             RISK[j][:, 0].copy(), 0, fixed[r], np.ones(nrow), CSL[j], 0.0, False, np.zeros(nrow))
            out_[j, r, 0] = res[0]; out_[j, r, 1] = res[1]; out_[j, r, 2] = res[3]; out_[j, r, 3] = res[2]


def run_k2(runs, P):
    o = np.zeros((len(P["THR"]), runs.n, 4))
    kernel2(runs.et, runs.ek, runs.ei, runs.eoff, runs.d, runs.R, runs.c, runs.m, runs.roff, runs.eq0, runs.fixed,
            P["THR"], P["RISK"], P["CAPV"], P["EXL"], P["EXS"], P["SM"], P["MINF"], P["EXTRA"], P["CSL"], o)
    return o


def policy_x(shares=None, csl=()):
    """O1's live policy + the extra sleeve classes: shares = {class: x BTC risk}; csl = classes counted inside the cap."""
    q = V34.portfolio_policy()
    q["extra"] = {**q["extra"], **(shares or {})}
    q["csl"] = tuple(csl)
    return q


def eval_policies(extra, pols, base_era=None):
    """pols over ONE extra-row set. -> list of metric dicts (V34.evaluate fields + era_x_*)."""
    win, boot, era = run_sets_x(extra)
    P = V34.pack(pols); CSL = np.zeros((len(pols), 16), np.bool_)
    for j, q in enumerate(pols):
        for k in q.get("csl", ()):
            CSL[j, k] = True
    P["CSL"] = CSL
    ow, ob, oe = run_k2(win, P), run_k2(boot, P), run_k2(era, P)
    rows = []
    for j in range(len(pols)):
        r = {}
        for k, (nm, _) in enumerate(V34.WINS):
            r[f"m_{nm}"] = ow[j, k, 0]; r[f"dd_{nm}"] = ow[j, k, 1]
        fb, db = ob[j, :, 0], ob[j, :, 1]
        r.update(boot_med=float(np.median(fb)), boot_p10=float(np.percentile(fb, 10)), boot_dd90=float(np.percentile(db, 90)),
                 p_10k=float((fb >= 10_000).mean()))
        ratio = (oe[j, :, 0] - V34.ERA_EQ) / np.maximum(oe[j, :, 2], 1e-9)
        r["_era"] = ratio
        rows.append(r)
    return rows


def base_metrics():
    if "base" not in _ST:
        r = eval_policies(NOX, [policy_x()])[0]
        _ST["base"] = r
        out(f"[base] O1 re-run: 2022 ${r['m_2022']:,.0f} / {r['dd_2022']:.2f}%, 2024 ${r['m_2024']:,.0f} / {r['dd_2024']:.2f}%, "
            f"boot ${r['boot_med']:,.0f} / ${r['boot_p10']:,.0f} / {r['boot_dd90']:.2f}%")
    return _ST["base"]


def g3_row(r):
    b = base_metrics(); e = r.pop("_era"); x = e / b["_era"]
    r["era_x_dev"], r["era_x_oos"] = x[0], x[1]
    r["era_phase"] = float(np.mean((x[0::2] > 1 + 1e-9) & (x[1::2] > 1 + 1e-9)))
    r["d_2022"] = r["m_2022"] / b["m_2022"] - 1; r["d_2024"] = r["m_2024"] / b["m_2024"] - 1
    r["d_boot_med"] = r["boot_med"] / b["boot_med"] - 1; r["d_boot_p10"] = r["boot_p10"] / b["boot_p10"] - 1
    r["E_era"] = r["era_x_dev"] > 1 and r["era_x_oos"] > 1 and r["era_phase"] >= 0.80
    r["E_money"] = (r["m_2022"] > b["m_2022"] and r["m_2024"] > b["m_2024"] and r["boot_med"] > b["boot_med"] and r["boot_p10"] > b["boot_p10"]
                    and r["dd_2024"] <= O1["dd_2024"] + 0.005 and r["boot_dd90"] <= O1["boot_dd90"] + 0.005)
    r["G3"] = bool(r["E_era"] and r["E_money"])
    return r


def sleeve_rows_from(tr, cls, weight=1.0):
    """tr: DataFrame entry_time, exit_time, dir, R, sym -> kernel rows (be = entry, outside the cap unless the class is in csl)."""
    m = lambda s: pd.to_datetime(tr[s]).values.astype("datetime64[m]").astype(np.int64)
    n = len(tr)
    return np.c_[m("entry_time"), m("exit_time"), m("entry_time"), tr.dir.to_numpy(float), tr.R.to_numpy(float), np.full(n, float(cls)),
                 np.full(n, weight) if np.isscalar(weight) else weight]


def money_table(tr, shares=(0.15, 0.25, 0.40), cls=7):
    """O1 + the sleeve at several shares of the BTC risk (one class, outside the cap). -> DataFrame of metrics vs O1."""
    rows = eval_policies(sleeve_rows_from(tr, cls), [policy_x({cls: s}) for s in shares])
    T = pd.DataFrame([g3_row(r) for r in rows]); T.insert(0, "share", list(shares))
    return T


# ══ standalone stream statistics (G1) ══════════════════════════════════════════════════════════════════════════════
def _per(df, a, b, tcol="exit_time"):
    return df[(df[tcol] >= a) & (df[tcol] < b)].sort_values(tcol)


def pf_of(r):
    w, l = r[r > 0].sum(), -r[r < 0].sum()
    return float(w / l) if l > 0 else (np.inf if w > 0 else 0.0)


def mdd(r):
    cum = np.r_[0.0, np.cumsum(r)]
    return float(np.max(np.maximum.accumulate(cum) - cum))


_TBOM = {}


def tbo_monthly():
    if "m" not in _TBOM:
        X = M.base_at(0)
        _TBOM["m"] = X.groupby(X.exit_time.dt.to_period("M")).R.sum()
    return _TBOM["m"]


def stats(df, boots=1000, seed=0, full=True):
    """n / net R / PF / max DD in each era, corr of monthly R with TBO's, share of month-block bootstraps positive in BOTH eras."""
    o = {}
    for e, (a, b) in ERAS.items():
        r = _per(df, a, b).R.to_numpy(float) if len(df) else np.zeros(0)
        o.update({f"n_{e}": len(r), f"net_{e}": float(r.sum()), f"pf_{e}": pf_of(r), f"dd_{e}": mdd(r),
                  f"avg_{e}": float(r.mean()) if len(r) else 0.0})
    if not full or not len(df):
        return o
    mo = df.groupby(pd.to_datetime(df.exit_time).dt.to_period("M")).R.sum()
    allm = pd.period_range("2022-01", "2026-10", freq="M")
    s1 = mo.reindex(allm).fillna(0.0); s2 = tbo_monthly().reindex(allm).fillna(0.0)
    o["corr_tbo"] = float(np.corrcoef(s1, s2)[0, 1]) if s1.std() > 0 else np.nan
    rng = np.random.default_rng(seed); ok = 0
    mm = {e: pd.period_range(a, pd.Timestamp(b) - pd.Timedelta(days=1), freq="M") for e, (a, b) in ERAS.items()}
    mv = {e: s1.reindex(mm[e]).to_numpy() for e in ERAS}
    for _ in range(boots):
        ok += all(mv[e][rng.integers(0, len(mv[e]), len(mv[e]))].sum() > 0 for e in ERAS)
    o["boot_pos"] = ok / boots
    return o


G1_PF = 1.25


MIN_N = 30                                                          # trades per era (a 1,000-setting grid always has lucky 5-trade cells)


def g1_flag(o):
    return bool(o["n_dev"] >= MIN_N and o["n_oos"] >= MIN_N and o["net_dev"] > 0 and o["net_oos"] > 0 and o["pf_dev"] >= G1_PF and o["pf_oos"] >= G1_PF)


def g1_full(o):
    return bool(g1_flag(o) and o.get("corr_tbo", 1) <= 0.20 and o.get("boot_pos", 0) >= 0.75)


def plateau_col(R_, ords, cats, flag):
    return M.plateau(R_, ords, cats, flag)


# ══ 1-minute order simulator (stop / market entries, SL, maker TP, hold, BE, TBO block + kick) ═════════════════════
@njit(cache=True)
def sim_groups(o, h, l, arm, exp, trig, dirn, sl, tpd, tpa, mk, hold, beR, free, kick, res):
    """One position at a time. Group g = up to 2 legs (OCO) armed from bar arm[g] to exp[g] (exclusive). trig == 0: leg absent.
    mk: market at the open of bar arm. Stop fills at max(trig, open) (min for shorts). In the fill bar the stop is checked
    first and (for stop entries) a take-profit counts only from the next bar. SL fills at the stop (the open if gapped
    through). Take-profit needs a touch of the full target. hold: bars after the fill (exit at that open). kick[j]: exit
    at the open of bar j (TBO filled). res rows: entry bar, exit bar, dir, entry px, exit px, dist, reason
    (0 stop, 1 tp, 2 time, 3 kick, 4 breakeven stop, 5 data end)."""
    n = len(o); G = len(arm); k_out = 0; last = -1
    for g in range(G):
        a = arm[g]
        if a <= last or a >= n:
            continue
        e = min(exp[g], n); fi = -1; leg = -1; px = 0.0
        for k in range(a, e):
            if free[k] == 0:
                continue
            for lg in range(2):
                if trig[g, lg] == 0.0:
                    continue
                d = dirn[g, lg]
                if mk[g, lg]:
                    fi = k; leg = lg; px = o[k]; break
                if d > 0 and h[k] >= trig[g, lg]:
                    fi = k; leg = lg; px = max(trig[g, lg], o[k]); break
                if d < 0 and l[k] <= trig[g, lg]:
                    fi = k; leg = lg; px = min(trig[g, lg], o[k]); break
            if fi >= 0:
                break
        if fi < 0:
            continue
        d = dirn[g, leg]; dist = sl[g, leg]
        stop = px - d * dist; be_on = False
        tgt = 0.0
        if tpa[g, leg] > 0:
            tgt = tpa[g, leg]
        elif tpd[g, leg] > 0:
            tgt = px + d * tpd[g, leg]
        stop_entry = not mk[g, leg]
        xb = -1; xp = 0.0; why = 5
        end = min(fi + hold[g], n - 1)
        j = fi
        while j <= end:
            if j > fi and kick[j]:
                xb = j; xp = o[j]; why = 3; break
            if j == end and j > fi:
                xb = j; xp = o[j]; why = 2; break
            hit = False
            if d > 0 and l[j] <= stop:
                hit = True; xp = stop if j == fi else min(stop, o[j])
            elif d < 0 and h[j] >= stop:
                hit = True; xp = stop if j == fi else max(stop, o[j])
            if hit:
                xb = j; why = 4 if be_on else 0; break
            if tgt > 0 and not (stop_entry and j == fi):
                if (d > 0 and h[j] >= tgt) or (d < 0 and l[j] <= tgt):
                    xb = j; xp = tgt - d * TP_PAD * px; why = 1; break
            if beR[g] > 0 and not be_on:
                if (d > 0 and h[j] >= px + beR[g] * dist) or (d < 0 and l[j] <= px - beR[g] * dist):
                    be_on = True; stop = px
            j += 1
        if xb < 0:
            xb = min(end, n - 1); xp = o[xb]; why = 5
        res[k_out, 0] = fi; res[k_out, 1] = xb; res[k_out, 2] = d; res[k_out, 3] = px; res[k_out, 4] = xp
        res[k_out, 5] = dist; res[k_out, 6] = why
        k_out += 1; last = xb
    return k_out


SLIP = {"BTCUSDT": 0.0001, "ETHUSDT": 0.0001}
_TBO = {}


def tbo_ctx(sym, m):
    """(free mask: TBO not holding the coin, kick mask: the minute after a TBO fill) for the core coins; all free elsewhere."""
    if "b" not in _TBO:
        _TBO["b"] = V33S.tbo_blocks()
    tb, kk = _TBO["b"]; t = m["t"]; n = len(t)
    free = (~D._mask(t, tb[sym])).astype(np.uint8) if sym in tb else np.ones(n, np.uint8)
    xk = np.zeros(n, np.bool_)
    if sym in kk:
        q = np.searchsorted(t, np.asarray(kk[sym], np.int64)); xk[q[q < n]] = True
    return free, xk


def intervals_mask(t, iv):
    return (~D._mask(t, iv)).astype(np.uint8) if iv is not None and len(iv) else np.ones(len(t), np.uint8)


class Ord:
    """Order builder for one coin: add(arm_min, exp_min, hold_h, be_R, leg0, leg1); a leg = (dir, trig_price, sl_dist, tp_dist, tp_abs, market) or None."""
    def __init__(self):
        self.r = []

    def add(self, arm_min, exp_min, hold_h, beR, l0=None, l1=None):
        self.r.append((int(arm_min), int(exp_min), int(round(hold_h * 60)), float(beR), l0, l1))

    def arrays(self, t):
        self.r.sort(key=lambda x: x[0]); G = len(self.r)
        arm = np.zeros(G, np.int64); exp = np.zeros(G, np.int64); hold = np.zeros(G, np.int64); beR = np.zeros(G)
        trig = np.zeros((G, 2)); dirn = np.zeros((G, 2)); sl = np.ones((G, 2)); tpd = np.zeros((G, 2)); tpa = np.zeros((G, 2)); mk = np.zeros((G, 2), np.bool_)
        for g, (a, e, hd, b, l0, l1) in enumerate(self.r):
            arm[g] = np.searchsorted(t, a); exp[g] = np.searchsorted(t, e); hold[g] = hd; beR[g] = b
            for q, lg in enumerate((l0, l1)):
                if lg is None:
                    continue
                dirn[g, q], trig[g, q], sl[g, q], tpd[g, q], tpa[g, q], mk[g, q] = lg
                if mk[g, q]:
                    trig[g, q] = 1.0
        return arm, exp, trig, dirn, sl, tpd, tpa, mk, hold, beR


def run_coin(sym, m, ob, free, kick):
    """Simulate one coin's orders on its 1m data -> trades DataFrame (R net of fees, slippage, funding)."""
    if not ob.r:
        return pd.DataFrame(columns=["sym", "entry_time", "exit_time", "dir", "R", "reason", "hours", "dist", "entry"])
    arm, exp, trig, dirn, sl, tpd, tpa, mk, hold, beR = ob.arrays(m["t"])
    res = np.zeros((len(arm), 7))
    k = sim_groups(m["o"], m["h"], m["l"], arm, exp, trig, dirn, sl, tpd, tpa, mk, hold, beR, free, kick, res)
    r = res[:k]
    t = m["t"]
    tr = pd.DataFrame({"sym": sym, "entry_time": C.D.to_datetime(t[r[:, 0].astype(int)]), "exit_time": C.D.to_datetime(t[r[:, 1].astype(int)]),
                       "dir": r[:, 2], "entry": r[:, 3], "exit": r[:, 4], "dist": r[:, 5], "why": r[:, 6].astype(int)})
    tr = tr[tr.why != 5]
    names = {0: "SL", 1: "TP", 2: "time", 3: "kick", 4: "BE"}
    tr["reason"] = tr.why.map(names)
    fee = TAKER + SLIP.get(sym, 0.0003)
    f_out = np.where(tr.why == 1, MAKER, fee)
    hours = (tr.exit_time - tr.entry_time).dt.total_seconds() / 3600
    tr["R"] = ((tr.exit - tr.entry) * tr.dir - fee * tr.entry - f_out * tr.exit - FUND * hours / 8 * tr.entry) / tr.dist
    tr["hours"] = hours
    return tr.drop(columns=["why", "exit"]).reset_index(drop=True)


# ══ bar frames ═════════════════════════════════════════════════════════════════════════════════════════════════════
_F = {}


def frame4(sym):
    """4h / daily arrays with the indicators used by the price-only tracks (decision at the 4h close)."""
    if sym not in _F:
        m = L.m1(sym); c4 = C.D.resample(m, 240); d1 = C.D.resample(m, 1440)
        a4 = PS.atr(c4["h"], c4["l"], c4["c"], 14); a4_100 = PS.atr(c4["h"], c4["l"], c4["c"], 100)
        ad = PS.atr(d1["h"], d1["l"], d1["c"], 14)
        e = lambda x, n: pd.Series(x).ewm(span=n, adjust=False).mean().to_numpy()
        _F[sym] = dict(m=m, c4=c4, d1=d1, a4=a4, sq=a4 / a4_100, ad=ad, e50=e(d1["c"], 50), e20=e(d1["c"], 20))
    return _F[sym]


def rolling_max(x, n):
    from numpy.lib.stride_tricks import sliding_window_view as sw
    p = np.r_[np.full(n - 1, np.nan), x]
    return np.nanmax(sw(p, n), axis=1)


def rolling_min(x, n):
    from numpy.lib.stride_tricks import sliding_window_view as sw
    p = np.r_[np.full(n - 1, np.nan), x]
    return np.nanmin(sw(p, n), axis=1)


_H = {}


def hour_frame(sym):
    """Hourly OHLC + OI + premium (panic_sleeve.hourly) with the 1h ATR; data from Nov 2021."""
    if sym not in _H:
        ex = PSL.EXTRA if sym not in HB14 else Path(PSL.ROOT) / "data" / "extra2"
        df = PSL.hourly(sym, ex)
        _H[sym] = dict(df=df, a1=PS.atr(df.h.values, df.l.values, df.c.values, 14))
    return _H[sym]


def trades_coins(coins, make_orders, tbo=True, block_fn=None):
    """make_orders(sym) -> Ord; runs every coin on its 1m data (TBO block + kick on the core coins when tbo)."""
    parts = []
    for s in coins:
        try:
            ob = make_orders(s)
        except FileNotFoundError:
            continue
        if ob is None or not ob.r:
            continue
        m = L.m1(s)
        free, kick = tbo_ctx(s, m) if tbo else (np.ones(len(m["t"]), np.uint8), np.zeros(len(m["t"]), np.bool_))
        if block_fn is not None:
            free = free & intervals_mask(m["t"], block_fn(s))
        parts.append(run_coin(s, m, ob, free, kick))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=["sym", "entry_time", "exit_time", "dir", "R"])


def leverage_note(tr, risk_pct):
    """Position size as a multiple of balance when risking risk_pct of it per trade (stop distance / entry)."""
    if not len(tr):
        return np.nan, np.nan
    lev = risk_pct / 100 / (tr.dist / tr.entry)
    return float(lev.median()), float(lev.quantile(0.95))


# ══ T1: VOLC on the extra coins ════════════════════════════════════════════════════════════════════════════════════
_T1 = {}


def volc_ext_data(sym):
    """Live-exact VOLC trades of one coin (v33 engine, no TBO) + the order table with the ranking features."""
    if sym in _T1:
        return _T1[sym]
    import replay as RP
    keep_ex = RP.EXTRA
    if sym in HB14:                                                   # HOLD_BIG's OI / premium archive is in data/extra2
        RP.EXTRA = Path(PSL.ROOT) / "data" / "extra2"
    try:
        tr = V33S.volc_coin33(sym, None, None, None)
        od = V33S.volc_orders_cached(sym)
    finally:
        RP.EXTRA = keep_ex
    m = L.m1(sym); c4 = C.D.resample(m, 240)
    a14 = PS.atr(c4["h"], c4["l"], c4["c"], 14); a100 = PS.atr(c4["h"], c4["l"], c4["c"], 100)
    tcl = c4["t"] + 240
    k = np.searchsorted(tcl, od.t_place.to_numpy(np.int64))
    RP.EXTRA = Path(PSL.ROOT) / "data" / "extra2" if sym in HB14 else keep_ex
    try:
        ot, ov = D.oi_series(sym)
    finally:
        RP.EXTRA = keep_ex

    def oi_at(e):
        j = int(np.searchsorted(ot, e, side="left")) - 1
        return float(ov[j]) if j >= 0 and ot[j] >= e - 30 else np.nan
    od = od.assign(sq=a14[k] / a100[k], oi24=[oi_at(t) / oi_at(t - 1440) - 1 for t in od.t_place.to_numpy(np.int64)], sym=sym)
    tr = tr.assign(tp=(tr.entry_time.values.astype("datetime64[m]").astype(np.int64) // 240) * 240)
    _T1[sym] = (tr, od)
    return _T1[sym]


def volc_extra_select(coins, N, rank):
    """Slot-capped pool. rank 'fill': first fills win; 'squeeze' (lowest ATR14/ATR100) / 'oi' (largest 24h OI build-up) /
    'tight_oi' (squeeze rank + OI): at each 4h close the free slots go to the best-ranked orders (all orders compete,
    filled or not); only the chosen orders can fill. Returns the chosen trades (R net, entry / exit times)."""
    D_ = {s: volc_ext_data(s) for s in coins}
    allt = pd.concat([v[0].assign(sym=s) for s, v in D_.items()], ignore_index=True)
    allt["e_m"] = allt.entry_time.values.astype("datetime64[m]").astype(np.int64)
    allt["x_m"] = allt.exit_time.values.astype("datetime64[m]").astype(np.int64)
    if N is None:
        return allt
    if rank == "fill":
        keep = []; opens = []
        for r in allt.sort_values("e_m", kind="stable").itertuples():
            opens = [x for x in opens if x > r.e_m]
            if len(opens) < N:
                keep.append(r.Index); opens.append(r.x_m)
        return allt.loc[keep]
    ods = pd.concat([v[1] for v in D_.values()], ignore_index=True)
    ods = ods.drop_duplicates(["sym", "t_place"])
    key = {"squeeze": ods.sq, "oi": -ods.oi24, "tight_oi": ods.sq.rank() + (-ods.oi24).rank()}[rank]
    ods = ods.assign(_k=key.fillna(1e9)).sort_values(["t_place", "_k"], kind="stable")
    tr_by = {(r.sym, r.tp): r.Index for r in allt.itertuples()}
    keep = []; busy = {}                                                  # busy[idx] = exit minute of a chosen trade
    for tp, g in ods.groupby("t_place", sort=True):
        opn = sum(1 for i in keep if allt.at[i, "e_m"] <= tp < allt.at[i, "x_m"] + 0 and allt.at[i, "x_m"] > tp)
        # (an earlier chosen trade whose exit is after this close still holds a slot)
        free_ = N - opn
        if free_ <= 0:
            continue
        held = {allt.at[i, "sym"] for i in keep if allt.at[i, "e_m"] <= tp < allt.at[i, "x_m"]}
        for r in g[~g.sym.isin(held)].head(free_).itertuples():
            i = tr_by.get((r.sym, tp))
            if i is not None:
                keep.append(i)
    return allt.loc[keep]


def t1():
    setup(); base_metrics()
    out("\n=== T1: live-exact 4h VOLC on the 7 extra DEV12 coins (v33 engine; no TBO conflict) ===")
    t0 = time.time()
    # 1. per-coin audit
    rows = []
    for grp, coins in (("EXTRA7", EXTRA7), ("CORE5 (live VOLC, TBO-blocked list)", None)):
        if coins is None:
            V = pd.read_pickle(C.D.CACHE / "volc_trades_v32.pkl")
            for s in CORE:
                rows.append(dict(group="CORE5", sym=s, **stats(V[V.sym == s], full=False)))
            continue
        for s in coins:
            tr = volc_ext_data(s)[0]
            rows.append(dict(group=grp, sym=s, **stats(tr, full=False)))
    A = pd.DataFrame(rows)
    pool = pd.concat([volc_ext_data(s)[0] for s in EXTRA7], ignore_index=True)
    V = pd.read_pickle(C.D.CACHE / "volc_trades_v32.pkl")
    for nm, df in (("EXTRA7 pooled", pool), ("CORE5 pooled (live)", V)):
        o = stats(df)
        A.loc[len(A)] = dict(group=nm, sym="ALL", **o)
    A.to_csv(RES / "v35_T1_per_coin_audit.csv", index=False)
    out(A.round(3).to_string(index=False))
    # HOLD_BIG (out of universe)
    hb = []
    for s in HB14:
        try:
            hb.append(volc_ext_data(s)[0])
        except Exception as ex:
            out(f"[T1] HOLD_BIG {s}: skipped ({type(ex).__name__}: {str(ex)[:60]})")
    if hb:
        hb = pd.concat(hb, ignore_index=True); o = stats(hb)
        out("[T1] HOLD_BIG pooled VOLC (live params): " + ", ".join(f"{k} {v:.2f}" for k, v in o.items()))
        pd.DataFrame([o]).to_csv(RES / "v35_T1_holdbig_pooled.csv", index=False)
    out(f"[T1] audit done [{time.time() - t0:.0f}s]")
    # 2. slot-capped pool grid
    cfg = []
    for N, rk in itertools.product((1, 2, 3, 4), ("fill", "squeeze", "oi", "tight_oi")):
        cfg.append((N, rk))
    sel = {}
    for N, rk in cfg:
        sel[(N, rk)] = volc_extra_select(EXTRA7, N, rk)
    sel[(7, "all")] = volc_extra_select(EXTRA7, None, None)
    sa = {}
    for k, v in sel.items():
        o = stats(v, full=False); sa[k] = o
        out(f"[T1] pool N={k[0]} rank={k[1]}: n {len(v)}  dev {o['n_dev']} net {o['net_dev']:.1f}R dd {o['dd_dev']:.1f}  oos {o['n_oos']} net {o['net_oos']:.1f}R dd {o['dd_oos']:.1f}")
    res = []
    shares = (0.35, 0.50, 0.75, 1.00)
    for k, v in sel.items():
        for inside in (False, True):
            cls = 8 if inside else 6
            # weights: extra_share x the core VOLC unit (class 6 outside = same 0.25 x BTC; class 8 = 0.25 x BTC inside the cap)
            pols = [policy_x({8: 0.25} if inside else {}, csl=(8,) if inside else ()) for _ in shares]
            rows_ = [sleeve_rows_from(v, cls, weight=s) for s in shares]
            for s, rw, q in zip(shares, rows_, pols):
                r = eval_policies(rw, [q])[0]
                r = g3_row(r)
                r.update(N=k[0], rank=k[1], share=s, inside_cap=inside, n_tr=len(v), **{f"s_{a}": b for a, b in sa[k].items()})
                res.append(r)
        out(f"[T1] money for pool {k} done [{time.time() - t0:.0f}s]")
    T = pd.DataFrame(res)
    cols = ["N", "rank", "share", "inside_cap", "m_2022", "dd_2022", "m_2024", "dd_2024", "boot_med", "boot_p10", "boot_dd90", "p_10k",
            "era_x_dev", "era_x_oos", "era_phase", "E_era", "E_money", "G3"]
    T.to_csv(RES / "v35_T1_extra_pool_grid.csv", index=False)
    out(T[cols].sort_values(["era_phase", "era_x_oos"], ascending=False).head(25).round(3).to_string(index=False))
    out(f"[T1] settings passing G3: {int(T.G3.sum())} of {len(T)}; passing the era gate alone: {int(T.E_era.sum())}")
    return T


# ══ generic standalone grid runner ═════════════════════════════════════════════════════════════════════════════════
def run_grid(name, specs, universe, ords, cats, oou=None, top=8):
    """specs: [(id, params, make_orders(sym), block_fn or None)]; runs DEV12-style universe (+ out-of-universe coins), G1 + plateau.
    -> (table, trades dict for the top ids)."""
    t0 = time.time(); rows = []; keep = {}
    for sid, p, mo, bf in specs:
        tr = trades_coins(universe, mo, block_fn=bf)
        o = stats(tr, boots=200, full=True); o["n_core"] = int(tr.sym.isin(CORE).sum()) if len(tr) else 0
        if len(tr):
            e7 = tr[tr.sym.isin(EXTRA7)]; oc = tr[tr.sym.isin(CORE)]
            o["net_x7"] = float(e7.R.sum()); o["net_core"] = float(oc.R.sum())
        rows.append(dict(id=sid, **p, **o)); keep[sid] = tr
    T = pd.DataFrame(rows)
    T["G1a"] = [g1_flag(r) for r in T.to_dict("records")]
    T["plateau"] = plateau_col(T, ords, cats, "G1a") if len(T) > 1 else np.nan
    T["G2a"] = T.plateau >= 0.6
    out(f"[{name}] {len(T)} settings x {len(universe)} coins [{time.time() - t0:.0f}s]; G1a (net > 0 and PF >= {G1_PF} in both eras): "
        f"{int(T.G1a.sum())}; with plateau >= 0.6: {int((T.G1a & T.G2a).sum())}")
    return T, keep


def finish_track(name, T, keep, universe, oou_fn=None, ords=None, top=6):
    """G1 full + out-of-universe + G3 money for the best settings."""
    T = T.copy()
    T["minpf"] = T[["pf_dev", "pf_oos"]].replace(np.inf, 9).min(axis=1).where((T.n_dev >= MIN_N) & (T.n_oos >= MIN_N), -1)
    cand = T[T.G1a].sort_values(["G2a", "minpf"], ascending=False).head(top)
    if cand.empty:
        cand = T.sort_values("minpf", ascending=False).head(3)
        out(f"[{name}] no setting passes G1a; the 3 closest by min(PF dev, PF oos) get the money run for the record")
    mt = []
    for r in cand.itertuples():
        tr = keep[r.id]
        G1 = g1_full(r._asdict()) if hasattr(r, "_asdict") else False
        row = dict(id=r.id, G1=G1, plateau=r.plateau)
        if oou_fn is not None:
            row.update(oou_fn(r.id))
        M_ = money_table(tr, shares=(0.15, 0.25, 0.40))
        for _, q in M_.iterrows():
            mt.append(dict(row, share=q.share, **{k: q[k] for k in M_.columns if k not in ("share",)}))
    MT = pd.DataFrame(mt)
    return T, MT


def show_money(name, MT):
    if MT is None or not len(MT):
        return
    cols = ["id", "share", "G1", "plateau", "m_2022", "dd_2022", "m_2024", "dd_2024", "boot_med", "boot_p10", "boot_dd90",
            "era_x_dev", "era_x_oos", "era_phase", "E_era", "E_money", "G3"]
    cols = [c for c in cols if c in MT.columns]
    out(MT[cols].round(3).to_string(index=False))


def finalize(name, T, MT):
    T.to_csv(RES / f"v35_{name}_grid.csv", index=False)
    if MT is not None and len(MT):
        MT.to_csv(RES / f"v35_{name}_money.csv", index=False)
        show_money(name, MT)
        out(f"[{name}] G3 passes: {int(MT.G3.sum())} of {len(MT)} money runs")


# ══ T2: trend-pullback resumption ══════════════════════════════════════════════════════════════════════════════════
def t2_orders(sym, npb, pbd, room, tp, hold):
    f = frame4(sym); c4, d1, a4, ad = f["c4"], f["d1"], f["a4"], f["ad"]
    n4 = len(c4["t"]); tc = c4["t"] + 240
    jd = np.searchsorted(d1["t"] + 1440, tc, side="right") - 1
    ok = jd >= 60
    jd = np.maximum(jd, 0)
    dh, dl, dc = d1["h"], d1["l"], d1["c"]
    hh20 = rolling_max(dh, 20)[jd]; ll20 = rolling_min(dl, 20)[jd]
    dsince_h = np.zeros(n4); dsince_l = np.zeros(n4)
    from numpy.lib.stride_tricks import sliding_window_view as sw
    wh = sw(np.r_[np.full(19, -np.inf), dh], 20); wl = sw(np.r_[np.full(19, np.inf), dl], 20)
    sh_ = 19 - np.array([np.flatnonzero(x == x.max())[-1] for x in wh]); sl_ = 19 - np.array([np.flatnonzero(x == x.min())[-1] for x in wl])
    dsince_h = sh_[jd]; dsince_l = sl_[jd]
    up = (dc[jd] > f["e50"][jd]) & (f["e50"][jd] > f["e50"][np.maximum(jd - 5, 0)])
    dn = (dc[jd] < f["e50"][jd]) & (f["e50"][jd] < f["e50"][np.maximum(jd - 5, 0)])
    c, h, l = c4["c"], c4["h"], c4["l"]
    pbl = (hh20 - c) / ad[jd]; pbs = (c - ll20) / ad[jd]
    tbo_hi = rolling_max(h, 20); tbo_lo = rolling_min(l, 20)
    trig_hi = rolling_max(h, npb); trig_lo = rolling_min(l, npb)
    long_ = ok & up & (c > f["e50"][jd]) & (pbl >= pbd) & (dsince_h >= 2) & (dsince_h <= 5) & (tbo_hi - trig_hi >= room * a4)
    short_ = ok & dn & (c < f["e50"][jd]) & (pbs >= pbd) & (dsince_l >= 2) & (dsince_l <= 5) & (trig_lo - tbo_lo >= room * a4)
    ob = Ord(); T4 = 240
    for k in np.flatnonzero((long_ | short_) & (np.arange(n4) < n4 - 1)):
        d = 1 if long_[k] else -1
        dist = a4[k]
        if d > 0:
            tpd, tpa = (tp * dist, 0.0) if tp > 0 else (0.0, tbo_hi[k])
            leg = (1, trig_hi[k], dist, tpd, tpa, False)
        else:
            tpd, tpa = (tp * dist, 0.0) if tp > 0 else (0.0, tbo_lo[k])
            leg = (-1, trig_lo[k], dist, tpd, tpa, False)
        ob.add(tc[k], tc[k] + T4, hold, 0.0, leg if d > 0 else None, leg if d < 0 else None)
    return ob


def t2():
    setup(); base_metrics()
    out("\n=== T2: trend-pullback resumption (inside the 20-bar channel, TBO flat, exit if TBO fills) ===")
    specs = []; ords = ["npb", "pbd", "room", "tp", "hold"]
    for npb, pbd, room, tp, hold in itertools.product((3, 4, 6, 8), (0.75, 1.25, 1.75), (1.5, 2.0, 2.5), (1.5, 2.0, 2.5, 0), (24, 36, 48)):
        specs.append((f"pb_n{npb}_d{pbd}_r{room}_tp{tp}_h{hold}", dict(npb=npb, pbd=pbd, room=room, tp=tp, hold=hold),
                      (lambda s, a=(npb, pbd, room, tp, hold): t2_orders(s, *a)), None))
    T, keep = run_grid("T2", specs, DEV12, ords, [])
    T, MT = finish_track("T2", T, keep, DEV12)
    finalize("T2", T, MT)
    return T, MT


# ══ T3: squeeze exhaustion ═════════════════════════════════════════════════════════════════════════════════════════
_PB = {}


def panic_blocks():
    """{sym: [start, end) minutes} of every panic v3.0 trade (the sleeve never opens on a coin with an open panic trade)."""
    if "b" not in _PB:
        ev = PSL.events(extra_coins=PSL.EXTRA_COINS, max_extra_open=2)
        b = {}
        for s, g in ev.groupby("sym"):
            e = g.t.values.astype("datetime64[m]").astype(np.int64); x = g.t_exit.values.astype("datetime64[m]").astype(np.int64)
            b[s] = np.c_[e - 1, x + 1]
        _PB["b"] = (b, ev)
    return _PB["b"]


def panic_block_fn(s):
    return panic_blocks()[0].get(s)


_FT = {}


def feats_h(sym, Lh):
    key = (sym, Lh)
    if key not in _FT:
        hf = hour_frame(sym); df = hf["df"]
        f = PS.features(df.h.values, df.l.values, df.c.values, df.oi.values, df.prem.values, Lh)
        _FT[key] = f
    return _FT[key]


def t3a_orders(sym, Lh, z, oi_x, hold, slk, tpk, be):
    hf = hour_frame(sym); df = hf["df"]; a1 = hf["a1"]; f = feats_h(sym, Lh)
    o, h, l, c = df.o.values, df.h.values, df.l.values, df.c.values
    rng = np.where(h > l, h - l, np.nan); pos = (c - l) / rng
    with np.errstate(invalid="ignore"):
        sig = (f["rz"] >= z) & (f["doi"] <= -oi_x) & ((c < o) | (pos <= 0.4))
    sig = np.nan_to_num(sig).astype(bool)
    idx = df.index.values.astype("datetime64[m]").astype(np.int64)
    ob = Ord()
    for i in np.flatnonzero(sig[:-1]):
        a = a1[i]; arm = idx[i] + 60
        ob.add(arm, arm + 5, hold, (be / slk) if be > 0 else 0.0, None, (-1, 0.0, slk * a, tpk * a, 0.0, True))
    return ob


def t3b_orders(sym, Lh, z, oi_x, pz_k, hold, slk, tpk):
    hf = hour_frame(sym); df = hf["df"]; a1 = hf["a1"]; f = feats_h(sym, Lh)
    o, h, l, c, oi = df.o.values, df.h.values, df.l.values, df.c.values, df.oi.values
    with np.errstate(invalid="ignore"):
        sig = (f["rz"] >= z) & (f["doi"] >= oi_x) & (f["pz"] >= pz_k) & (np.r_[np.nan, oi[1:] - oi[:-1]] < 0)
    sig = np.nan_to_num(sig).astype(bool)
    idx = df.index.values.astype("datetime64[m]").astype(np.int64)
    ob = Ord()
    for i in np.flatnonzero(sig[:-1]):
        a = a1[i]; arm = idx[i] + 60
        ob.add(arm, arm + 60, hold, 0.0, None, (-1, l[i], slk * a, tpk * a, 0.0, False))
    return ob


def t3():
    setup(); base_metrics(); panic_blocks()
    out("\n=== T3a: forced short-squeeze exhaustion (short after a spike with falling OI and a bearish hour) ===")
    specs = []; ords = ["Lh", "z", "oi_x", "hold", "slk", "tpk", "be"]
    for Lh, z, oi_x, hold, slk, tpk, be in itertools.product((4, 8), (1.5, 2.0, 2.5), (0.05, 0.08, 0.12), (4, 8, 12), (2.0, 3.0, 4.0), (2.0, 3.0), (1.5, 2.0)):
        specs.append((f"sq_L{Lh}_z{z}_oi{oi_x}_h{hold}_sl{slk}_tp{tpk}_be{be}", dict(Lh=Lh, z=z, oi_x=oi_x, hold=hold, slk=slk, tpk=tpk, be=be),
                      (lambda s, a=(Lh, z, oi_x, hold, slk, tpk, be): t3a_orders(s, *a)), panic_block_fn))
    T, keep = run_grid("T3a", specs, DEV12, ords, [])
    T, MT = finish_track("T3a", T, keep, DEV12)
    finalize("T3a", T, MT)
    out("\n=== T3b: euphoria blow-off (OI surge + premium + prior-low break with falling OI) ===")
    specs = []; ords = ["Lh", "z", "oi_x", "pz_k", "hold", "slk", "tpk"]
    for Lh, z, oi_x, pz_k, hold, slk, tpk in itertools.product((4, 8, 12), (2.0, 2.5, 3.0), (0.08, 0.12, 0.15), (1.5, 2.0, 2.5), (4, 8, 12), (2.0, 3.0), (2.0, 3.0)):
        specs.append((f"eu_L{Lh}_z{z}_oi{oi_x}_pz{pz_k}_h{hold}_sl{slk}_tp{tpk}", dict(Lh=Lh, z=z, oi_x=oi_x, pz_k=pz_k, hold=hold, slk=slk, tpk=tpk),
                      (lambda s, a=(Lh, z, oi_x, pz_k, hold, slk, tpk): t3b_orders(s, *a)), panic_block_fn))
    T2_, keep2 = run_grid("T3b", specs, DEV12, ords, [])
    T2_, MT2 = finish_track("T3b", T2_, keep2, DEV12)
    finalize("T3b", T2_, MT2)


# ══ T4: weekend alpha ══════════════════════════════════════════════════════════════════════════════════════════════
def t4a_orders(sym, comp, oi_x, valid, mode, slmode, tp, hold):
    hf = hour_frame(sym); df = hf["df"]; f4 = frame4(sym)
    ts = df.index
    h, l, oi = df.h.values, df.l.values, df.oi.values
    rr = pd.Series(h).rolling(48).max().to_numpy() - pd.Series(l).rolling(48).min().to_numpy()
    idx = ts.values.astype("datetime64[m]").astype(np.int64)
    pos = {t: i for i, t in enumerate(ts)}
    c4, d1 = f4["c4"], f4["d1"]
    ob = Ord()
    for T0 in ts[(ts.dayofweek == 0) & (ts.hour == 0)]:
        i = pos[T0]
        if i < 48 + 5 * 24 + 1 or not np.isfinite(oi[i - 1]) or not np.isfinite(oi[i - 49]):
            continue
        box_h, box_l = h[i - 48:i].max(), l[i - 48:i].min(); box = box_h - box_l
        prior = np.nanmean([rr[i - 48 - 24 * k - 1] for k in range(5)])        # 48h ranges ending 0..4 days before Saturday 00:00
        if not box > 0 or box > comp * prior or oi[i - 1] / oi[i - 49] - 1 < oi_x:
            continue
        k4 = np.searchsorted(c4["t"] + 240, idx[i], side="right") - 1; kd = np.searchsorted(d1["t"] + 1440, idx[i], side="right") - 1
        dist = 0.5 * box if slmode == "box" else f4["a4"][k4]
        up = d1["c"][kd] > f4["e50"][kd]
        l0 = (1, box_h, dist, tp * dist, 0.0, False) if (mode == "both" or up) else None
        l1 = (-1, box_l, dist, tp * dist, 0.0, False) if (mode == "both" or not up) else None
        ob.add(idx[i], idx[i] + valid * 60, hold, 0.0, l0, l1)
    return ob


def t4b_orders(sym, z, oi_x, tpm, slk):
    hf = hour_frame(sym); df = hf["df"]; a1 = hf["a1"]
    ts = df.index; o, h, l, c, oi = df.o.values, df.h.values, df.l.values, df.c.values, df.oi.values
    idx = ts.values.astype("datetime64[m]").astype(np.int64)
    c8 = np.r_[np.full(8, np.nan), c[:-8]]
    with np.errstate(invalid="ignore", divide="ignore"):
        m8 = pd.Series(np.abs(c / c8 - 1)).rolling(720, min_periods=300).mean().shift(1).to_numpy()
    pos = {t: i for i, t in enumerate(ts)}
    ob = Ord()
    for fri in ts[(ts.dayofweek == 4) & (ts.hour == 20)]:
        i0 = pos[fri]; p0 = o[i0]; oi0 = oi[i0]
        if not (np.isfinite(oi0) and np.isfinite(m8[i0])):
            continue
        for i in range(i0 + 8, i0 + 8 + 36):                                   # Saturday 04:00 .. Sunday 16:00 (bar closes)
            if i + 1 >= len(ts):
                break
            mv = c[i] / p0 - 1
            if abs(mv) < z * m8[i0] or not oi[i] / oi0 - 1 <= -oi_x:
                continue
            if not ((mv > 0 and c[i] < o[i]) or (mv < 0 and c[i] > o[i])):
                continue
            d = -1 if mv > 0 else 1
            e = o[i + 1]; dist = slk_ = slk * a1[i]
            tpd = {"r50": 0.5, "r75": 0.75, "2R": 0.0}[tpm] * abs(e - p0) if tpm != "2R" else 2 * dist
            sun22 = idx[i0] + 26 * 60 + 24 * 60 * 0                               # Friday 20:00 + 50 h = Sunday 22:00
            sun22 = idx[i0] + 50 * 60
            hold = (sun22 - (idx[i] + 60)) / 60
            if hold < 1 or tpd <= 0:
                break
            ob.add(idx[i] + 60, idx[i] + 65, hold, 0.0, None if d > 0 else (-1, 0.0, dist, tpd, 0.0, True), (1, 0.0, dist, tpd, 0.0, True) if d > 0 else None)
            if d > 0:
                ob.r[-1] = ob.r[-1][:4] + ((1, 0.0, dist, tpd, 0.0, True), None)
            break
    return ob


def t4():
    setup(); base_metrics()
    out("\n=== T4a: Monday-00:00 weekend-compression box breakout (TBO flat on the coin) ===")
    specs = []; ords = ["comp", "oi_x", "valid", "slmode", "tp", "hold"]
    for comp, oi_x, valid, mode, slm, tp, hold in itertools.product((0.6, 0.75, 0.9), (-0.02, 0.0, 0.02), (8, 12, 24), ("both", "trend"), ("box", "atr"), (1.5, 2.0, 2.5), (12, 24, 36)):
        specs.append((f"mb_c{comp}_oi{oi_x}_v{valid}_{mode}_{slm}_tp{tp}_h{hold}", dict(comp=comp, oi_x=oi_x, valid=valid, mode=mode, slmode=slm, tp=tp, hold=hold),
                      (lambda s, a=(comp, oi_x, valid, mode, slm, tp, hold): t4a_orders(s, *a)), None))
    T, keep = run_grid("T4a", specs, DEV12, ords[:3] + ["tp", "hold"], ["mode", "slmode"])
    T, MT = finish_track("T4a", T, keep, DEV12)
    finalize("T4a", T, MT)
    out("\n=== T4b: weekend thin-book stop-hunt fade toward the Friday 20:00 UTC price ===")
    specs = []; ords = ["z", "oi_x", "slk"]
    for z, oi_x, tpm, slk in itertools.product((1.5, 2.0, 2.5), (0.03, 0.045, 0.06), ("r50", "r75", "2R"), (1.5, 2.0)):
        specs.append((f"cme_z{z}_oi{oi_x}_{tpm}_sl{slk}", dict(z=z, oi_x=oi_x, tpm=tpm, slk=slk),
                      (lambda s, a=(z, oi_x, tpm, slk): t4b_orders(s, *a)), None))
    T2_, keep2 = run_grid("T4b", specs, DEV12, ords, ["tpm"])
    T2_, MT2 = finish_track("T4b", T2_, keep2, DEV12)
    finalize("T4b", T2_, MT2)


# ══ T5: own hypotheses ═════════════════════════════════════════════════════════════════════════════════════════════
_LAG = {}


def lag_events(a_btc, nlead):
    """4h closes at which BTC has just confirmed a 20-bar breakout run >= a_btc ATR above the old high; per such close the
    candidate laggards in DEV12 (not BTC), ranked cleanest-compressed first."""
    key = (a_btc,)
    if key in _LAG:
        return _LAG[key]
    fb = frame4("BTCUSDT"); c4 = fb["c4"]; c, h = c4["c"], c4["h"]
    lvl = np.r_[np.nan, rolling_max(h, 20)[:-1]]
    ev = (c - lvl) / fb["a4"] >= a_btc
    first = ev & ~np.r_[False, ev[:-1]]
    first &= np.r_[False, ~(np.r_[False, ev[:-1]][:-1] if False else ev[:-1])]
    _LAG[key] = (c4["t"] + 240)[np.flatnonzero(first)]
    return _LAG[key]


def t5a_orders_all(a_btc, q, lag_x, topn, tp, hold):
    """-> {sym: Ord} (the cross-coin choice is made per event, orders are market buys at the next 4h open)."""
    ev = lag_events(a_btc, 0); fb = frame4("BTCUSDT")
    obs = {s: Ord() for s in DEV12 if s != "BTCUSDT"}
    for tc in ev:
        cands = []
        for s in obs:
            f = frame4(s); c4 = f["c4"]
            k = np.searchsorted(c4["t"] + 240, tc, side="left")
            if k >= len(c4["t"]) - 1 or c4["t"][k] + 240 != tc or k < 30:
                continue
            kb = np.searchsorted(fb["c4"]["t"] + 240, tc, side="left")
            rel = (c4["c"][k] / c4["c"][k - 6] - 1) - (fb["c4"]["c"][kb] / fb["c4"]["c"][kb - 6] - 1)
            lvl = rolling_max(c4["h"], 20)[k - 1] if k > 20 else np.inf
            jd = np.searchsorted(f["d1"]["t"] + 1440, tc, side="right") - 1
            if jd < 50 or f["sq"][k] > q or rel > -lag_x or c4["c"][k] >= lvl or f["d1"]["c"][jd] < f["e50"][jd]:
                continue
            cands.append((f["sq"][k], s, k))
        for _, s, k in sorted(cands)[:topn]:
            f = frame4(s); dist = f["a4"][k]
            obs[s].add(tc, tc + 5, hold, 0.0, (1, 0.0, dist, tp * dist, 0.0, True), None)
    return obs


def t5a_trades(a_btc, q, lag_x, topn, tp, hold):
    obs = t5a_orders_all(a_btc, q, lag_x, topn, tp, hold)
    return trades_coins(list(obs), lambda s: obs[s])


def t5b_orders(sym, dh, b, side, hold, slk, tpk):
    hf = hour_frame(sym); df = hf["df"]; a1 = hf["a1"]; ev = panic_blocks()[1]
    ev = ev[ev.sym == sym]
    idx = df.index
    ob = Ord()
    for r in ev.itertuples():
        i = idx.searchsorted(r.t + pd.Timedelta(hours=dh))
        if i + 1 >= len(idx):
            continue
        a = a1[i]; px = df.c.values[i]
        move = (px - r.entry) / a
        if side == "cont_long" and move >= b:
            leg = (1, 0.0, slk * a, tpk * a, 0.0, True)
        elif side == "fail_short" and move <= -b:
            leg = (-1, 0.0, slk * a, tpk * a, 0.0, True)
        else:
            continue
        arm = idx[i].value // 60_000_000_000 + 60
        ob.add(arm, arm + 5, hold, 0.0, leg if leg[0] > 0 else None, leg if leg[0] < 0 else None)
    return ob


def t5():
    setup(); base_metrics(); panic_blocks()
    out("\n=== T5a: BTC-confirmed laggard catch-up (market buy of the cleanest compressed laggard after BTC's 20-bar breakout run) ===")
    t0 = time.time(); rows = []; keep = {}
    ords = ["a_btc", "q", "lag_x", "topn", "tp", "hold"]
    for a_btc, q, lag_x, topn, tp, hold in itertools.product((0.75, 1.0), (0.7, 0.85), (0.0, 0.02), (1, 2), (1.5, 2.0), (24, 36, 48)):
        tr = t5a_trades(a_btc, q, lag_x, topn, tp, hold)
        o = stats(tr, boots=200)
        sid = f"lag_a{a_btc}_q{q}_x{lag_x}_n{topn}_tp{tp}_h{hold}"
        rows.append(dict(id=sid, a_btc=a_btc, q=q, lag_x=lag_x, topn=topn, tp=tp, hold=hold, **o)); keep[sid] = tr
    T = pd.DataFrame(rows); T["G1a"] = [g1_flag(r) for r in T.to_dict("records")]
    T["plateau"] = plateau_col(T, ords, [], "G1a"); T["G2a"] = T.plateau >= 0.6
    out(f"[T5a] {len(T)} settings [{time.time() - t0:.0f}s]; G1a {int(T.G1a.sum())}, with plateau {int((T.G1a & T.G2a).sum())}")
    T, MT = finish_track("T5a", T, keep, DEV12)
    finalize("T5a", T, MT)
    out("\n=== T5b: post-panic secondary continuation (12-24 h after a panic v3.0 entry) ===")
    specs = []; ords = ["dh", "b", "hold", "slk", "tpk"]
    for dh, b, side, hold, slk, tpk in itertools.product((12, 18, 24), (0.5, 1.0, 2.0), ("cont_long", "fail_short"), (12, 24, 36), (2.0, 3.0), (2.0, 3.0, 4.0)):
        specs.append((f"pp_dh{dh}_b{b}_{side}_h{hold}_sl{slk}_tp{tpk}", dict(dh=dh, b=b, side=side, hold=hold, slk=slk, tpk=tpk),
                      (lambda s, a=(dh, b, side, hold, slk, tpk): t5b_orders(s, *a)), None))
    T2_, keep2 = run_grid("T5b", specs, DEV12, ords, ["side"])
    T2_, MT2 = finish_track("T5b", T2_, keep2, DEV12)
    finalize("T5b", T2_, MT2)


def check():
    setup(); base_metrics()
    out("[check] money harness reproduces O1: " + ", ".join(f"{k} {_ST['base'][k]:,.2f}" for k in ("m_2022", "dd_2022", "m_2024", "dd_2024", "boot_med", "boot_p10", "boot_dd90")))
    # an empty and a tiny sleeve must leave O1 untouched; csl path runs
    r = eval_policies(NOX, [policy_x({7: 0.25}), policy_x({8: 0.25}, csl=(8,))])
    out(f"[check] empty sleeve rows change nothing: {abs(r[0]['m_2024'] - _ST['base']['m_2024']) < 1e-6 and abs(r[1]['m_2024'] - _ST['base']['m_2024']) < 1e-6}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    {"check": check, "t1": t1, "t2": t2, "t3": t3, "t4": t4, "t5": t5}[cmd]()
