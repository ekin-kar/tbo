"""U4 (v2.9 round, Nov 2026): the v2.7 panic sleeve on more coins with a cap on open sleeve positions, ranked by flush
severity, and a runner tranche. Hourly data: core/hourly51.py (51 coins, to 2026-11-06).

Candidates: every hour where the frozen v2.7 signal fires on a coin that has no open sleeve trade (panic_signal, same
code as the bot). Selection each hour: free slots = max_open - open sleeve positions; if more coins trigger than slots,
keep the top ones by
  A  OI drop (most negative doi),  B  premium z (most negative pz),  C  |doi| x |pz|,  R  random (null, 200 draws).
Size: v2.7 per-event rule (units per signal hour split over the coins entered that hour; 1 unit = 1/6 of the ladder's BTC
risk per 5% move). Exits v2.7 (TP 3 ATR, stop 4 ATR max -20%, breakeven at +2 ATR, 12 h; hourly bars, stop checked first)
or a runner tranche: `frac` of the position exits at TP 3 ATR, the rest has its stop moved to +lock ATR at +3 ATR and
exits at TP run_tp ATR or after run_h hours.
Universes: OUR5 (live), DEV12, LIQ26 = DEV12 + HOLD_BIG; untouched check HOLD_SMALL (25).
Fixed-unit account: P&L per trade = ret / 5% x units / n_hour (as botsim's sleeve rows); ratio = net / max drawdown.
GATES (fixed in advance; x vs the live v2.7 on OUR5 unless stated):
  G1 DEV12 / LIQ26 with the cap: ratio x >= 1.05 in 2022-23 AND 2024-26 and net x >= 1
  G2 plateau: >= 60% of neighbours (max_open +-1, units 2/3/4) have ratio x > 1 in both periods
  G3 luck: ranking variants beat >= 95% of 200 random selections (same cap) on min(period ratio); runner: x > 1 on >= 70% of
     40 random 1-12 h entry delays... (not used: hourly entries have no phase) -> runner judged on G1, G2, G4, G5
  G4 untouched HOLD_SMALL: the same rule (cap, ranking) on HOLD_SMALL alone: avg trade > 0 and ratio x >= 1 vs HOLD_SMALL
     uncapped, both periods
  G5 money: bot (v2.8) + this sleeve from $300 (starts 2022, 2024) vs bot + v2.7 OUR5: more money, drop at most +1 point;
     1,000 paired 2-year block-bootstrap journeys: median end higher, 1-in-10 drop at most +1 point
    python panic_rank_v29.py           -> research/results/v29_U4.csv, v29_U4_runner.csv (+ printed)"""
import itertools, os, sys
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v28nov")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
import numpy as np, pandas as pd
import common as C, v29lib as L, hourly51 as H, botsim as B
sys.path.insert(0, str(C.ROOT / "cryptobot"))
import panic_signal as PS                                          # noqa: E402

RES = C.ROOT / "research" / "results"
P0 = dict(PS.DEFAULTS)
PER = {"2022-23": ("2022-01-01", "2024-01-01"), "2024-26": ("2024-01-01", L.END)}
SLIP = {"BTCUSDT": 0.0001, "ETHUSDT": 0.0001}
LIQ26 = H.DEV12 + H.HOLD_BIG


def candidates(sym, runner=None):
    """Every signal hour of `sym` with the trade it would give (entry next open). runner = (frac, lock, run_tp, run_h)."""
    df = H.hourly(sym); o, h, l, c = (df[k].to_numpy(float) for k in "ohlc")
    f = PS.features(h, l, c, df.oi.to_numpy(float), df.prem.to_numpy(float), P0["window_h"])
    sig = np.flatnonzero(PS.signal(f, **P0)); a_ = f["atr"]; Hh = int(P0["hold_h"])
    cost = 2 * (0.0005 + SLIP.get(sym, 0.0003)); rows = []
    for i in sig:
        if i + 1 + max(Hh, runner[3] if runner else 0) + 1 >= len(o):
            continue
        e = o[i + 1]; a = a_[i]; st = max(e - P0["stop_atr"] * a, e * (1 - P0["stop_max"])); tg = e + P0["tp_atr"] * a
        def leg(stop, tp, hold, lock=None, lock_at=None, be=True):
            best = e; s = stop
            for jj in range(i + 1, i + 1 + hold):
                if l[jj] <= s:
                    return s, jj, ("stop" if s < e else "breakeven" if s == e else "lock")
                if h[jj] >= tp:
                    return tp, jj, "take profit"
                best = max(best, h[jj])
                if be and best >= e + P0["be_atr"] * a:
                    s = max(s, e)
                if lock is not None and best >= e + lock_at * a:
                    s = max(s, e + lock * a)
            return o[i + 1 + hold], i + 1 + hold, "time"
        px, j, why = leg(st, tg, Hh)
        ret = px / e - 1 - cost
        if runner:
            frac, lk, rtp, rh = runner
            px2, j2, why2 = leg(st, e + rtp * a, rh, lock=lk, lock_at=P0["tp_atr"])
            ret = frac * ret + (1 - frac) * (px2 / e - 1 - cost)
            j = max(j, j2)
        rows.append((df.index[i + 1], df.index[j], sym, ret, f["doi"][i], f["pz"][i]))
    return pd.DataFrame(rows, columns=["t", "t_exit", "sym", "ret", "doi", "pz"])


def select(cands, max_open=None, rank="A", rng=None, units=3.0):
    """Hour by hour: free coins (no open sleeve trade) that trigger, top-N by the ranking into the free slots."""
    if cands.empty:
        return cands.assign(n=[], w=[])
    cands = cands.sort_values(["t", "sym"]).reset_index(drop=True)
    busy = {}; opened = []; out = []
    for t, g in cands.groupby("t", sort=True):
        opened = [x for x in opened if x >= t]
        g = g[[busy.get(s, pd.Timestamp(0)) + pd.Timedelta(hours=1) < t for s in g.sym]]   # as v2.7: signal after the exit hour
        if g.empty:
            continue
        if max_open is not None:
            free = max_open - len(opened)
            if free <= 0:
                continue
            if len(g) > free:
                if rank == "A":
                    g = g.sort_values("doi").head(free)
                elif rank == "B":
                    g = g.sort_values("pz").head(free)
                elif rank == "C":
                    g = g.assign(_s=-(g.doi.abs() * g.pz.abs())).sort_values("_s").head(free).drop(columns="_s")
                else:
                    g = g.iloc[rng.permutation(len(g))[:free]]
        for _, r in g.iterrows():
            busy[r.sym] = r.t_exit; opened.append(r.t_exit)
        out.append(g.assign(n=len(g)))
    E = pd.concat(out, ignore_index=True)
    E["w"] = units / E.n                                        # units of this trade (per-event split)
    return E


def fixed(E, a, b):
    m = (E.t >= a) & (E.t < b)
    g = E[m].sort_values("t_exit")
    p = (g.ret / 0.05 * g.w).to_numpy(); e = np.cumsum(p)
    dd = float(np.max(np.maximum.accumulate(np.r_[0, e])[1:] - e)) if len(e) else np.nan
    net = float(e[-1]) if len(e) else 0.0
    return dict(net=net, dd=dd, ratio=net / dd if dd else np.nan, n=int(m.sum()), avg=float(g.ret.mean() * 100) if len(g) else np.nan,
                win=float((g.ret > 0).mean() * 100) if len(g) else np.nan)


def scores(E):
    return {k: fixed(E, *v) for k, v in PER.items()}


def sleeve_rows(E):
    m = lambda s: s.values.astype("datetime64[m]").astype(np.int64)
    return np.c_[m(E.t), m(E.t_exit), m(E.t), np.ones(len(E)), (E.ret / 0.05 * E.w / 3.0).to_numpy(), np.full(len(E), 5)]


def combo(E, units=3.0):
    """botsim rows: bot v2.8 + the sleeve (coin 5, R per 1 unit-of-3 so the policy's 3/6 x BTC risk = v2.7 sizing)."""
    A = np.r_[B.TR, sleeve_rows(E)]
    return A[np.lexsort((A[:, 5], A[:, 0]))]


def money_gate(Es, names):
    pol = L.policy(extra_risk=[(5, 3.0 / 6)])
    As = [combo(E) for E in Es]
    rows = {}
    for a in ("2022-01-01", "2024-01-01"):
        for nm, A in zip(names, As):
            r = L.money_window(A, a, L.END, pol); rows.setdefault(nm, {}).update({f"m{a[:4]}": r["final"], f"dd{a[:4]}": r["dd"]})
    bt = L.boot_money(As, [pol] * len(As), n=int(os.environ.get("V29_BOOT", 1000)))
    for nm, b in zip(names, bt):
        rows[nm].update({f"boot_{k}": v for k, v in b.items()})
    M = pd.DataFrame(rows).T; b = M.iloc[0]
    M["G5"] = (M.m2022 > b.m2022) & (M.m2024 > b.m2024) & (M.dd2022 <= b.dd2022 + 1) & (M.dd2024 <= b.dd2024 + 1) & \
              (M.boot_med > b.boot_med) & (M.boot_dd90 <= b.boot_dd90 + 1)
    return M


def main():
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 300)
    allc = {s: candidates(s) for s in H.ALL51}
    cand = lambda coins: pd.concat([allc[s] for s in coins], ignore_index=True)
    live = select(cand(H.OUR5))
    import panic_sleeve as PSL
    ref = PSL.events(start="2022-01-01", end="2026-10-01", extra_coins=())
    lv = live[(live.t >= "2022-01-01") & (live.t < "2026-10-01")]
    same = len(set(zip(ref.t, ref.sym)) & set(zip(lv.t, lv.sym)))
    print(f"parity: v2.7 OUR5 here {len(lv)} trades vs panic_sleeve.events {len(ref)}, same (hour, coin) {same}, avg ret {lv.ret.mean()*100:.2f}% vs {ref.ret.mean()*100:.2f}%")
    b = scores(live)
    rows = [dict(univ="OUR5", cap="none", rank="-", units=3, **{f"{k}_{m}": v[m] for k, v in b.items() for m in v})]
    S = {}
    for univ, coins in (("DEV12", H.DEV12), ("LIQ26", LIQ26), ("HOLD_SMALL", H.HOLD_SMALL)):
        cc = cand(coins)
        for cap, rank, u in itertools.product((None, 2, 3, 4, 5), ("A", "B", "C"), (2.0, 3.0, 4.0)):
            if cap is None and rank != "A":
                continue
            E = select(cc, cap, rank, units=u); s = scores(E); S[(univ, cap, rank, u)] = (E, s)
            rows.append(dict(univ=univ, cap=cap or "none", rank=rank if cap else "-", units=u, **{f"{k}_{m}": v[m] for k, v in s.items() for m in v}))
    T = pd.DataFrame(rows)
    for k in PER:
        T[f"x{k[:4]}"] = T[f"{k}_ratio"] / b[k]["ratio"]
    # G2 plateau, G3 null, G4 untouched
    rng = np.random.default_rng(294)
    def key(r):
        return (r.univ, None if r.cap == "none" else int(r.cap), r["rank"] if r.cap != "none" else "A", float(r.units))
    xs = {key(r): (r.x2022, r.x2024) for _, r in T.iterrows() if r.univ != "OUR5"}
    T["plateau"] = np.nan; T["null_pct"] = np.nan; T["hs_avg22"] = np.nan; T["hs_avg24"] = np.nan; T["hs_x22"] = np.nan; T["hs_x24"] = np.nan
    hs0 = S[("HOLD_SMALL", None, "A", 3.0)][1]; NULL = {}
    for i, r in T.iterrows():
        if r.univ in ("OUR5", "HOLD_SMALL") or r.cap == "none":
            continue
        cap, rk, u = int(r.cap), r["rank"], float(r.units)
        nb = [(r.univ, c2, rk, u2) for c2 in (cap - 1, cap, cap + 1) for u2 in (2.0, 3.0, 4.0) if (c2, u2) != (cap, u) and (r.univ, c2, rk, u2) in xs]
        T.at[i, "plateau"] = np.mean([xs[n][0] > 1 and xs[n][1] > 1 for n in nb])
        if u == 3.0:
            if (r.univ, cap) not in NULL:
                cc = cand(H.DEV12 if r.univ == "DEV12" else LIQ26); null = []
                for _ in range(200):
                    s = scores(select(cc, cap, "R", rng=rng, units=u)); null.append(min(s["2022-23"]["ratio"] / b["2022-23"]["ratio"], s["2024-26"]["ratio"] / b["2024-26"]["ratio"]))
                NULL[(r.univ, cap)] = np.array(null)
            T.at[i, "null_pct"] = float((NULL[(r.univ, cap)] < min(r.x2022, r.x2024)).mean())
        hs = S.get(("HOLD_SMALL", cap, rk, u))
        if hs:
            T.at[i, "hs_avg22"] = hs[1]["2022-23"]["avg"]; T.at[i, "hs_avg24"] = hs[1]["2024-26"]["avg"]
            T.at[i, "hs_x22"] = hs[1]["2022-23"]["ratio"] / hs0["2022-23"]["ratio"]; T.at[i, "hs_x24"] = hs[1]["2024-26"]["ratio"] / hs0["2024-26"]["ratio"]
    T["G1"] = (T.x2022 >= 1.05) & (T.x2024 >= 1.05) & (T["2022-23_net"] >= b["2022-23"]["net"]) & (T["2024-26_net"] >= b["2024-26"]["net"])
    T["G2"] = T.plateau >= 0.6
    T["G3"] = T.null_pct >= 0.95
    T["G4"] = (T.hs_avg22 > 0) & (T.hs_avg24 > 0) & (T.hs_x22 >= 1) & (T.hs_x24 >= 1)
    T.loc[T.univ.isin(["OUR5", "HOLD_SMALL"]), ["G1", "G2", "G3", "G4"]] = False
    # G5 money for the best points (G1-G4 passers, else the best by min x per universe)
    T["minx"] = T[["x2022", "x2024"]].min(axis=1)
    cand_rows = T[(T.univ.isin(["DEV12", "LIQ26"])) & (T.cap != "none")]
    pick = cand_rows[cand_rows.G1 & cand_rows.G2 & cand_rows.G3 & cand_rows.G4]
    if len(pick) < 4:
        pick = pd.concat([pick, cand_rows.sort_values("minx", ascending=False).head(4)]).drop_duplicates()
    unc = T[(T.univ.isin(["DEV12", "LIQ26"])) & (T.cap == "none") & (T.units == 3.0)]
    names = ["v2.7 OUR5"] + [f"{r.univ} cap{r.cap} {r['rank']} u{r.units:g}" for _, r in pick.iterrows()] + [f"{r.univ} uncapped u3" for _, r in unc.iterrows()]
    Es = [live] + [S[key(r)][0] for _, r in pick.iterrows()] + [S[key(r)][0] for _, r in unc.iterrows()]
    M = money_gate(Es, names)
    T.to_csv(RES / "v29_U4.csv", index=False); M.to_csv(RES / "v29_U4_money.csv")
    show = ["univ", "cap", "rank", "units", "2022-23_n", "2022-23_avg", "2022-23_net", "2022-23_dd", "x2022", "2024-26_n", "2024-26_avg",
            "2024-26_net", "2024-26_dd", "x2024", "plateau", "null_pct", "hs_avg22", "hs_avg24", "hs_x22", "hs_x24", "G1", "G2", "G3", "G4"]
    print(T[show].round(3).to_string(index=False))
    print("\nmoney (bot v2.8 + sleeve from $300):\n" + M.round(2).to_string())
    # runner tranche on OUR5 (v2.7 rule) and on the best capped universe
    rr = []
    best = pick.iloc[0] if len(pick) else None
    for frac, lk, rtp, rh in itertools.product((0.5,), (1.0, 1.5, 2.0), (4.0, 5.0, 6.0), (12, 18, 24)):
        candR = {s: candidates(s, runner=(frac, lk, rtp, rh)) for s in H.OUR5}
        E5 = select(pd.concat([candR[s] for s in H.OUR5])); s5 = scores(E5)
        row = dict(frac=frac, lock=lk, run_tp=rtp, run_h=rh, x2022=s5["2022-23"]["ratio"] / b["2022-23"]["ratio"], x2024=s5["2024-26"]["ratio"] / b["2024-26"]["ratio"],
                   avg22=s5["2022-23"]["avg"], avg24=s5["2024-26"]["avg"], net_x22=s5["2022-23"]["net"] / b["2022-23"]["net"], net_x24=s5["2024-26"]["net"] / b["2024-26"]["net"])
        hsR = select(pd.concat([candidates(s, runner=(frac, lk, rtp, rh)) for s in H.HOLD_SMALL])); sh = scores(hsR)
        row.update(hs_x22=sh["2022-23"]["ratio"] / hs0["2022-23"]["ratio"], hs_x24=sh["2024-26"]["ratio"] / hs0["2024-26"]["ratio"])
        rr.append(row)
    RR = pd.DataFrame(rr)
    xr = {(r.lock, r.run_tp, r.run_h): (r.x2022 > 1 and r.x2024 > 1) for _, r in RR.iterrows()}
    LK, TP, HH = (1.0, 1.5, 2.0), (4.0, 5.0, 6.0), (12, 18, 24)
    RR["plateau"] = [np.mean([xr[(a, b_, c)] for a in LK for b_ in TP for c in HH if (a, b_, c) != (r.lock, r.run_tp, r.run_h) and
                              abs(LK.index(a) - LK.index(r.lock)) <= 1 and abs(TP.index(b_) - TP.index(r.run_tp)) <= 1 and abs(HH.index(c) - HH.index(r.run_h)) <= 1])
                     for _, r in RR.iterrows()]
    RR["G1"] = (RR.x2022 >= 1.05) & (RR.x2024 >= 1.05) & (RR.net_x22 >= 1) & (RR.net_x24 >= 1)
    RR["G2"] = RR.plateau >= 0.6; RR["G4"] = (RR.hs_x22 >= 1) & (RR.hs_x24 >= 1)
    RR.to_csv(RES / "v29_U4_runner.csv", index=False)
    print("\nrunner tranche on v2.7 OUR5 (half at TP 3 ATR, half: stop +lock ATR after +3 ATR, TP run_tp ATR or run_h hours):")
    print(RR.round(3).to_string(index=False))
    pr = RR[RR.G1 & RR.G2 & RR.G4]
    if len(pr):
        r = pr.sort_values("x2024", ascending=False).iloc[0]
        E5 = select(pd.concat([candidates(s, runner=(r.frac, r.lock, r.run_tp, int(r.run_h))) for s in H.OUR5]))
        print("\nrunner money:\n" + money_gate([live, E5], ["v2.7 OUR5", f"runner lock{r.lock} tp{r.run_tp} {int(r.run_h)}h"]).round(2).to_string())


if __name__ == "__main__":
    main()
