"""v2.9 structural-upgrade study (Nov 2026) on TBO v2.8 (data to 2026-11-06). U1-U3 here, U4 (panic) in panic_rank_v29.py.

U1  short size per tier (btc_s, eth_s, alt_s) and a directional open-risk cap (shorts capped at 1.1 x the BTC SHORT risk;
    ETH instead of BTC exempt on shorts)                                   -> sizing only (trade list unchanged)
U2  asymmetric hold (long 120-192 h, short 60-120 h); 2nd / 3rd profit-lock steps (+8R -> 3.5/4.5R, +12R -> 7/8R);
    runners past the time limit (>= run_R at 120 h: chandelier best - k x risk, or 4h EMA10 close exit; cap 240 h);
    stale-trade decay (never +1.5R by 36/48/60 h and unrealized > -0.3R -> stop to -0.5R / breakeven)   -> engine re-run
U3  fee-aware sizing (risk / (stop + c x 2 x (taker + slip)) x entry), c 0.5-2   -> sizing only;
    stop floor max(1 ATR, p x price), p 0.6 / 0.8 / 1.0%                                               -> engine re-run

Accounts: FIXED-UNIT (BTC 6, ETH 4, alts 0.83 units per R, shorts x0.5 unless U1 changes it; no cap; ordered by exit),
ratio = net / max drawdown; x = variant ratio / base ratio. Periods 2020-23, 2022-23, 2024-26 (to 2026-11-06).
GATES (fixed before any result was seen):
  G1 dev       x(2022-23) >= 1.05, x(2020-23) >= 1.00, net x >= 0.90 in both dev periods
  G2 holdout   x(2024-26) > 1.00 and net x >= 0.90
  G3 plateau   >= 60% of the surrounding grid points (Chebyshev distance 1 in the family's grid) have x > 1 in 2022-23 AND
               2024-26
  G4 luck      engine variants: x > 1 on >= 70% of 40 phase-shifted 4h-candle copies in 2022-23 AND 2024-26 (paired: the
               same variant vs base on each copy); sizing variants: also beats >= 95% of 200 random draws (U1: coin labels
               of the short trades shuffled; U3: the same size factors shuffled over the trades) on min(x 2022-23, x 2024-26)
  G5 untouched 14 big coins never used to tune TBO (HOLD_BIG, weight 1 each, shorts x0.5): x > 1 in 2022-23 AND 2024-26
               (U1: only the alt tier can be checked there)
  G6 money     bot sizing (ladder + cap, botsim rules) from $300, starts 2020 / 2022 / 2024: more money in all three and
               worst drop at most +1 point; 1,000 paired block-bootstrapped 2-year journeys (2022-26 blocks): median end
               higher and 1-in-10 drop at most +1 point
    python quant_upgrades_v29.py build     # engine runs -> cache/v29/<SYM>.pkl  (5 coins x 40 phases + 14 big coins)
    python quant_upgrades_v29.py eval      # all tables -> research/results/v29_U1.csv, v29_U2.csv, v29_U3.csv, v29_summary.txt
"""
import itertools, os, pickle, sys
from multiprocessing import Pool
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v28nov")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
import numpy as np, pandas as pd
import common as C
import v29lib as L

OUT = C.D.CACHE / "v29"; RES = C.ROOT / "research" / "results"
HOLD_BIG = ["BCHUSDT", "XLMUSDT", "SUIUSDT", "HBARUSDT", "1000SHIBUSDT", "1000PEPEUSDT", "NEARUSDT", "UNIUSDT", "ETCUSDT",
            "APTUSDT", "AAVEUSDT", "ATOMUSDT", "FILUSDT", "ICPUSDT"]
SHIFTS = [int(round(240 * k / 41)) for k in range(1, 41)]            # 40 distinct phases inside the 4h candle
P1, P2, P3 = "2020-23", "2022-23", "2024-26"


# ── engine variants (U2, U3 floor) ────────────────────────────────────────────────────────────────────────────────
def _cfgs():
    out = [dict(id="base", fam="base", ax=(), ex={})]
    for i, hl in enumerate((120, 144, 168, 192)):
        for j, hs in enumerate((60, 72, 96, 120)):
            if (hl, hs) != (120, 120):
                out.append(dict(id=f"hold_L{hl}_S{hs}", fam="U2hold", ax=(i, j), ex=dict(hs=hs, hl=hl)))
    L2 = [None, (8, 3.5), (8, 4.5)]; L3 = [None, (12, 7.0), (12, 8.0)]
    for i, a in enumerate(L2):
        for j, b in enumerate(L3):
            if a or b:
                ex = {}
                if a: ex.update(lock2_R=a[0], lock2_to=a[1])
                if b: ex.update(lock3_R=b[0], lock3_to=b[1])
                out.append(dict(id=f"lock_{a}_{b}".replace(" ", ""), fam="U2lock", ax=(i, j), ex=ex))
    for i, rr in enumerate((3.0, 4.0, 6.0)):
        for j, (mode, k) in enumerate(((1, 2.0), (1, 3.0), (2, 0.0))):
            out.append(dict(id=f"run_R{rr:g}_{'ema10' if mode == 2 else f'k{k:g}'}", fam="U2run", ax=(i, j),
                            ex=dict(run_mode=mode, run_R=rr, run_k=k, run_max_h=240, run_ema=10)))
    for i, h in enumerate((36, 48, 60)):
        for j, to in enumerate((-0.5, 0.0)):
            out.append(dict(id=f"stale_{h}h_to{to:g}", fam="U2stale", ax=(i, j), ex=dict(stale_h=h, stale_thr=-0.3, stale_to=to)))
    for i, p in enumerate((0.006, 0.008, 0.010)):
        out.append(dict(id=f"floor_{p*100:g}pct", fam="U3floor", ax=(i + 1,), ex=dict(sl_min_pct=p)))
    return out


CFGS = _cfgs()
CFG = {c["id"]: c for c in CFGS}


def _engine_extra(ex):
    e = dict(ex); kw = {}
    if "hl" in e:
        kw["hold_h"] = e.pop("hl"); e["hold_s_h"] = e.pop("hs")
    return e, kw


def build_coin(args):
    sym, shifts = args
    f = OUT / f"{sym}.pkl"
    have = pickle.load(open(f, "rb")) if f.exists() else {}
    for sh in shifts:
        for c in CFGS:
            key = (c["id"], sh)
            if key in have:
                continue
            ex, kw = _engine_extra(c["ex"])
            x = L.trades(sym, extra=ex, shift=sh, kw=kw)
            x["be_time"] = L.be_times(x, sym)
            have[key] = x[["sym", "entry_time", "exit_time", "be_time", "dir", "R", "entry", "sl_dist", "reason", "hours"]]
        pickle.dump(have, open(f, "wb"))
        L._M.clear() if sh == shifts[-1] else None
    return sym


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = [(s, [0] + SHIFTS) for s in L.COINS] + [(s, [0]) for s in HOLD_BIG]
    with Pool(6, maxtasksperchild=1) as p:
        for s in p.imap_unordered(build_coin, jobs):
            print("built", s, flush=True)


# ── evaluation helpers ───────────────────────────────────────────────────────────────────────────────────────────
_D = {}


def data(sym):
    if sym not in _D:
        _D[sym] = pickle.load(open(OUT / f"{sym}.pkl", "rb"))
    return _D[sym]


def X(cid, shift=0, coins=L.COINS):
    return pd.concat([data(s)[(cid, shift)] for s in coins], ignore_index=True)


def sc(Xd, pnl=None, w=None, smult=0.5):
    return L.score(Xd, L.units(Xd, w=w, smult=smult) if pnl is None else pnl)


def neighbours(fam_cfgs, ax):
    return [c for c in fam_cfgs if c["ax"] != ax and len(c["ax"]) == len(ax) and max(abs(a - b) for a, b in zip(c["ax"], ax)) <= 1]


def money(A_list, pols, label):
    """G6 for (A, pol) pairs, the first being the base."""
    rows = []
    for a in ("2020-01-01", "2022-01-01", "2024-01-01"):
        r = [L.money_window(A, a, L.END, p) for A, p in zip(A_list, pols)]
        rows.append([(x["final"], x["dd"]) for x in r])
    bt = L.boot_money(A_list, pols, n=int(os.environ.get("V29_BOOT", 1000)))
    out = []
    for k in range(len(A_list)):
        d = {f"m{a[:4]}": rows[i][k][0] for i, a in enumerate(("2020", "2022", "2024"))}
        d.update({f"dd{a[:4]}": rows[i][k][1] for i, a in enumerate(("2020", "2022", "2024"))})
        d.update({f"boot_{kk}": v for kk, v in bt[k].items()})
        out.append(d)
    b = out[0]
    for d in out:
        d["G6"] = all(d[f"m{y}"] > b[f"m{y}"] and d[f"dd{y}"] <= b[f"dd{y}"] + 1 for y in ("2020", "2022", "2024")) and \
            d["boot_med"] > b["boot_med"] and d["boot_dd90"] <= b["boot_dd90"] + 1
    return out


def gate_row(cid, sv, sb, nb_x, shift_x, hold_x, extra=None):
    x = L.ratio_x(sv, sb)
    netx = {k: (sv[k]["net"] / sb[k]["net"] if sb[k]["net"] else np.nan) for k in sv}
    r = dict(id=cid, x2020=x[P1], x2022=x[P2], x2024=x[P3], net_x2020=netx[P1], net_x2022=netx[P2], net_x2024=netx[P3],
             net2022=sv[P2]["net"], dd2022=sv[P2]["dd"], net2024=sv[P3]["net"], dd2024=sv[P3]["dd"], n2024=sv[P3]["n"])
    r["G1"] = x[P2] >= 1.05 and x[P1] >= 1.0 and netx[P1] >= 0.9 and netx[P2] >= 0.9
    r["G2"] = x[P3] > 1.0 and netx[P3] >= 0.9
    r["plateau"] = np.mean(nb_x) if len(nb_x) else np.nan
    r["G3"] = bool(len(nb_x)) and np.mean(nb_x) >= 0.6
    if shift_x is not None:
        r["shift_win2022"], r["shift_win2024"] = shift_x
        r["G4"] = shift_x[0] >= 0.7 and shift_x[1] >= 0.7
    if hold_x is not None:
        r["hold_x2022"], r["hold_x2024"] = hold_x
        r["G5"] = hold_x[0] > 1 and hold_x[1] > 1
    r.update(extra or {})
    return r


# ── U2 + U3 floor (engine variants) ───────────────────────────────────────────────────────────────────────────────
def eval_engine():
    base = {sh: sc(X("base", sh)) for sh in [0] + SHIFTS}
    hb = sc(X("base", 0, HOLD_BIG), w={s: 1.0 for s in HOLD_BIG})
    xs = {c["id"]: L.ratio_x(sc(X(c["id"])), base[0]) for c in CFGS if c["id"] != "base"}
    rows = []
    for c in CFGS:
        if c["id"] == "base":
            continue
        fam = [d for d in CFGS if d["fam"] == c["fam"]]
        if c["fam"] == "U3floor":                                       # the base (no floor) is the floor grid's point 0
            fam = fam + [dict(id="base", ax=(0,))]
        nb = neighbours(fam, c["ax"])
        nb_x = [(xs[d["id"]][P2] > 1 and xs[d["id"]][P3] > 1) if d["id"] != "base" else False for d in nb]
        sw = []
        for sh in SHIFTS:
            xx = L.ratio_x(sc(X(c["id"], sh)), base[sh]); sw.append((xx[P2] > 1, xx[P3] > 1))
        sw = np.array(sw).mean(axis=0)
        hx = L.ratio_x(sc(X(c["id"], 0, HOLD_BIG), w={s: 1.0 for s in HOLD_BIG}), hb)
        rows.append(gate_row(c["id"], sc(X(c["id"])), base[0], nb_x, (sw[0], sw[1]), (hx[P2], hx[P3]), dict(fam=c["fam"])))
    R = pd.DataFrame(rows)
    # money for every config that passes G1+G2 or is the best of its family on min(x2022, x2024)
    R["minx"] = R[["x2022", "x2024"]].min(axis=1)
    pick = set(R[R.G1 & R.G2].id) | set(R.loc[R.groupby("fam").minx.idxmax(), "id"])
    pol = L.policy()
    ids = ["base"] + sorted(pick)
    mon = money([L.to_rows(X(i)) for i in ids], [pol] * len(ids), "engine")
    M = pd.DataFrame(mon, index=ids)
    R = R.merge(M, left_on="id", right_index=True, how="left")
    R["ALL6"] = R[["G1", "G2", "G3", "G4", "G5"]].all(axis=1) & R.G6.fillna(False).astype(bool)
    return R, M.loc["base"]


# ── U3 fee-aware sizing ───────────────────────────────────────────────────────────────────────────────────────────
def fee_factor(Xd, c):
    slip = np.where(Xd.sym.isin(["BTCUSDT", "ETHUSDT"]), 0.0001, 0.0003)
    cost = c * 2 * (C.TAKER + slip) * Xd.entry.to_numpy()
    return Xd.sl_dist.to_numpy() / (Xd.sl_dist.to_numpy() + cost)


def eval_fee():
    grid = (0.5, 1.0, 1.5, 2.0); rng = np.random.default_rng(29)
    X0 = X("base"); b0 = sc(X0)
    xs = {c: L.ratio_x(L.score(X0, L.units(X0) * fee_factor(X0, c)), b0) for c in grid}
    rows = []
    hbX = X("base", 0, HOLD_BIG); hw = {s: 1.0 for s in HOLD_BIG}; hb = sc(hbX, w=hw)
    for i, c in enumerate(grid):
        f = fee_factor(X0, c); u = L.units(X0)
        nb = [g for j, g in enumerate(grid) if abs(j - i) == 1]
        nb_x = [xs[g][P2] > 1 and xs[g][P3] > 1 for g in nb]
        sw = []
        for sh in SHIFTS:
            Xs = X("base", sh); xx = L.ratio_x(L.score(Xs, L.units(Xs) * fee_factor(Xs, c)), sc(Xs)); sw.append((xx[P2] > 1, xx[P3] > 1))
        sw = np.array(sw).mean(axis=0)
        null = []
        for _ in range(200):
            xx = L.ratio_x(L.score(X0, u * rng.permutation(f)), b0); null.append(min(xx[P2], xx[P3]))
        mine = min(xs[c][P2], xs[c][P3])
        hx = L.ratio_x(L.score(hbX, L.units(hbX, w=hw) * fee_factor(hbX, c)), hb)
        r = gate_row(f"fee_c{c:g}", L.score(X0, u * f), b0, nb_x, (sw[0], sw[1]), (hx[P2], hx[P3]),
                     dict(fam="U3fee", null_pct=float((np.array(null) < mine).mean()), avg_factor=float(f.mean()),
                          stop_loss_R=float((X0.R * f)[X0.reason == "SL"][X0.R < -0.5].mean())))
        r["G4"] = bool(r["G4"]) and r["null_pct"] >= 0.95
        rows.append(r)
    R = pd.DataFrame(rows)
    A0 = L.to_rows(X0); pol = L.policy()
    As = [A0]
    for c in grid:
        Xf = X0.assign(R=X0.R * fee_factor(X0, c)); As.append(L.to_rows(Xf))
    mon = money(As, [pol] * len(As), "fee")
    M = pd.DataFrame(mon, index=["base"] + [f"fee_c{c:g}" for c in grid])
    R = R.merge(M, left_on="id", right_index=True, how="left")
    R["ALL6"] = R[["G1", "G2", "G3", "G4", "G5", "G6"]].all(axis=1)
    return R


# ── U1 short tiers + directional cap ──────────────────────────────────────────────────────────────────────────────
U1B, U1E, U1A = (0.5, 0.75, 1.0), (0.5, 0.75, 1.0), (0.0, 0.25, 0.5)


def smap(b, e, a):
    return {"BTCUSDT": b, "ETHUSDT": e, "alt": a}


def eval_u1():
    rng = np.random.default_rng(291)
    X0 = X("base"); b0 = sc(X0)
    grid = list(itertools.product(range(3), range(3), range(3)))
    xs = {g: L.ratio_x(L.score(X0, L.units(X0, smult=smap(U1B[g[0]], U1E[g[1]], U1A[g[2]]))), b0) for g in grid}
    base_g = (0, 0, 2)
    shX = {sh: X("base", sh) for sh in SHIFTS}; shb = {sh: sc(shX[sh]) for sh in SHIFTS}
    hbX = X("base", 0, HOLD_BIG); hw = {s: 1.0 for s in HOLD_BIG}; hb = sc(hbX, w=hw)
    short = (X0.dir < 0).to_numpy(); syms = X0.sym.to_numpy()
    rows = []
    for g in grid:
        if g == base_g:
            continue
        sm = smap(U1B[g[0]], U1E[g[1]], U1A[g[2]])
        nb = [h for h in grid if h != g and max(abs(a - b) for a, b in zip(h, g)) <= 1]
        nb_x = [(xs[h][P2] > 1 and xs[h][P3] > 1) if h != base_g else False for h in nb]
        sw = []
        for sh in SHIFTS:
            xx = L.ratio_x(L.score(shX[sh], L.units(shX[sh], smult=sm)), shb[sh]); sw.append((xx[P2] > 1, xx[P3] > 1))
        sw = np.array(sw).mean(axis=0)
        null = []
        for _ in range(200):                                          # coin labels of the short trades shuffled
            s2 = syms.copy(); s2[short] = rng.permutation(s2[short])
            # P&L: the trade's own coin weight, the multiplier of the shuffled label
            cw = X0.sym.map(lambda s: L.BOT_W.get(s, 0.83)).to_numpy(float)
            m = pd.Series(s2).map(lambda s: sm.get(s, sm["alt"])).to_numpy(float)
            pn = X0.R.to_numpy() * cw * np.where(short, m, 1.0)
            xx = L.ratio_x(L.score(X0, pn), b0); null.append(min(xx[P2], xx[P3]))
        mine = min(xs[g][P2], xs[g][P3])
        hx = L.ratio_x(L.score(hbX, L.units(hbX, w=hw, smult=U1A[g[2]])), hb) if U1A[g[2]] != 0.5 else {P2: np.nan, P3: np.nan}
        r = gate_row(f"btc{U1B[g[0]]:g}_eth{U1E[g[1]]:g}_alt{U1A[g[2]]:g}", L.score(X0, L.units(X0, smult=sm)), b0, nb_x,
                     (sw[0], sw[1]), (hx[P2], hx[P3]), dict(fam="U1", null_pct=float((np.array(null) < mine).mean())))
        r["G4"] = bool(r["G4"]) and r["null_pct"] >= 0.95
        r["G5"] = True if U1A[g[2]] == 0.5 else r["G5"]               # alt tier unchanged: nothing to check
        rows.append(r)
    R = pd.DataFrame(rows)
    R["minx"] = R[["x2022", "x2024"]].min(axis=1)
    # money: the 6 best grid points (fixed-unit) x cap options, + the cap options alone
    top = R.sort_values("minx", ascending=False).id.head(6).tolist()
    A0 = L.to_rows(X0)
    pols, labels = [L.policy()], ["base"]
    def mk(idn, cap, ex):
        b, e, a = (float(t[3:]) for t in idn.split("_"))
        return L.policy(smult=[b, e, a, a, a], cap_short=cap, exempt_short=ex)
    for idn in top + ["btc0.5_eth0.5_alt0.5"]:
        for cap, ex, nm in ((None, None, ""), ("short", None, "+capS"), (None, {1}, "+ETHexS"), ("short", {1}, "+capS+ETHexS")):
            if idn == "btc0.5_eth0.5_alt0.5" and nm == "":
                continue
            pols.append(mk(idn, cap, ex)); labels.append(idn + nm)
    mon = money([A0] * len(pols), pols, "u1")
    M = pd.DataFrame(mon, index=labels)
    return R, M


# ── report ───────────────────────────────────────────────────────────────────────────────────────────────────────
def evaluate():
    RES.mkdir(exist_ok=True)
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 50); pd.set_option("display.max_rows", 200)
    base = sc(X("base")); hb = sc(X("base", 0, HOLD_BIG), w={s: 1.0 for s in HOLD_BIG})
    lines = ["BASE v2.8 fixed-unit: " + ", ".join(f"{k} net {v['net']:.1f} dd {v['dd']:.1f} ratio {v['ratio']:.2f} n {v['n']}" for k, v in base.items()),
             "BASE HOLD_BIG (w 1): " + ", ".join(f"{k} net {v['net']:.1f} dd {v['dd']:.1f} ratio {v['ratio']:.2f} n {v['n']}" for k, v in hb.items())]
    cols = ["id", "x2020", "x2022", "x2024", "net_x2022", "net_x2024", "plateau", "shift_win2022", "shift_win2024", "hold_x2022",
            "hold_x2024", "G1", "G2", "G3", "G4", "G5"]
    E, mb = eval_engine(); E.to_csv(RES / "v29_U2_U3floor.csv", index=False)
    mcols = ["m2020", "dd2020", "m2022", "dd2022", "m2024", "dd2024", "boot_med", "boot_dd90", "G6", "ALL6"]
    lines += ["", "U2 + U3 floor (engine variants)", E[cols + ["null_pct"] * 0 + [c for c in mcols if c in E]].round(3).to_string(index=False),
              "base money: " + pd.to_numeric(mb, errors="coerce").round(1).to_string().replace("\n", ", ")]
    Fe = eval_fee(); Fe.to_csv(RES / "v29_U3fee.csv", index=False)
    lines += ["", "U3 fee-aware sizing", Fe[cols + ["null_pct", "avg_factor", "stop_loss_R"] + [c for c in mcols if c in Fe]].round(3).to_string(index=False)]
    U, M = eval_u1(); U.to_csv(RES / "v29_U1.csv", index=False); M.to_csv(RES / "v29_U1_money.csv")
    lines += ["", "U1 short tiers (fixed-unit gates)", U.sort_values("minx", ascending=False)[cols + ["null_pct"]].round(3).to_string(index=False),
              "", "U1 money (bot sizing, $300) incl. directional cap / ETH-exempt-on-shorts", M.round(2).to_string()]
    txt = "\n".join(lines); open(RES / "v29_summary_U1_U3.txt", "w").write(txt); print(txt)


if __name__ == "__main__":
    {"build": build, "eval": evaluate}[sys.argv[1]]()
