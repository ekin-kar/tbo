"""Live execution audit, 12 Oct - 6 Nov 2026 (Part 1 of the v2.9 research round).

Inputs (repo root, untracked via .git/info/exclude): Binance-Futures-Position-History-*.csv (17 closed positions) and
Binance-Futures-Trade-History-*.csv (fills with fees; the export ends 30 Oct 00:18 UTC+3), times in UTC+3.
Engine trades: cache/portfolio_trades_v28nov.pkl / v26nov.pkl (build_trades.py with TBO_END=2026-11-07).

Per position: engine match (same coin and side, entry within 10 min), live entry vs the engine fill (= stop level or the
first 1m open through it) as slippage in bps and in R (R = 1 ATR stop distance of the engine trade), exit slippage, fees
(BNB fees converted at the BNB 1m close of the fill minute; positions after the export: 0.05% USDT taker estimated), live
net R vs engine R. Then the counterfactual account from $300 on 12 Oct: botsim with pure v2.8 (+ v2.7 panic sleeve) and
v2.6, vs the live realized result (funding not in the exports, not included).
    python research/crypto/studies/live_audit_nov.py      -> research/results/live_audit_nov.csv (+ printed tables)"""
import glob, os, sys
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v28nov")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
import numpy as np, pandas as pd
import common as C, botsim as B, panic_sleeve as PSL

ROOT = C.ROOT
OUT = ROOT / "research" / "results"
START, END = "2026-10-12", "2026-11-07"
V28_LIVE = pd.Timestamp("2026-10-21 17:00")          # commit 2d08a33 (v2.8 OI-low filter), deployed after this


def load_live():
    pos = pd.read_csv(glob.glob(str(ROOT / "Binance-Futures-Position-History-*.csv"))[0], encoding="utf-8-sig")
    fil = pd.read_csv(glob.glob(str(ROOT / "Binance-Futures-Trade-History-*.csv"))[0], encoding="utf-8-sig")
    for c in ("Opened", "Closed"):
        pos[c] = pd.to_datetime(pos[c]) - pd.Timedelta(hours=3)
    fil["Time"] = pd.to_datetime(fil["Time"]) - pd.Timedelta(hours=3)
    bnb = C.load("BNBUSDT")
    def usdt_fee(row):
        v, unit = row["Fee"].split()
        v = float(v)
        if unit == "BNB":
            m = int(row["Time"].value // 60_000_000_000); j = max(0, int(np.searchsorted(bnb["t"], m)) - 1)
            return v * float(bnb["c"][j])
        return v
    fil["fee_usdt"] = fil.apply(usdt_fee, axis=1)
    fil["fee_unit"] = fil["Fee"].str.split().str[1]
    return pos, fil


def main():
    pos, fil = load_live()
    E8 = pd.concat(B.ALL.values()).merge(pd.read_pickle(C.D.CACHE / "trade_prices_v28nov.pkl"), on=["sym", "entry_time"])
    import pickle
    E6 = pd.concat(pickle.load(open(C.D.CACHE / "portfolio_trades_v26nov.pkl", "rb")).values()).merge(
        pd.read_pickle(C.D.CACHE / "trade_prices_v26nov.pkl"), on=["sym", "entry_time"])
    fills_end = fil.Time.max()
    rows, used = [], set()
    for _, p in pos.sort_values("Opened").iterrows():
        d = 1 if p["Position Side"] == "Long" else -1
        cand = E8[(E8.sym == p.Symbol) & (E8.dir == d) & ((E8.entry_time - p.Opened).abs() <= pd.Timedelta(minutes=10))]
        src = "v2.8"
        if cand.empty:
            cand = E6[(E6.sym == p.Symbol) & (E6.dir == d) & ((E6.entry_time - p.Opened).abs() <= pd.Timedelta(minutes=10))]
            src = "v2.6 only" if len(cand) else "none"
        q = float(p["Closed Vol."]); eL, xL = float(p["Entry Price"]), float(p["Avg. Close Price"])
        f = fil[(fil.Symbol == p.Symbol) & (fil.Time >= p.Opened - pd.Timedelta(seconds=5)) & (fil.Time <= p.Closed + pd.Timedelta(seconds=5))]
        if p.Closed <= fills_end:
            fee = f.fee_usdt.sum(); fee_src = "/".join(sorted(f.fee_unit.unique()))
        else:
            fee = 0.0005 * q * (eL + xL); fee_src = "est USDT 0.05%"
        r = dict(sym=p.Symbol[:-4], side=p["Position Side"], opened_utc=p.Opened, closed_utc=p.Closed, qty=q, live_entry=eL, live_exit=xL,
                 pnl_gross=float(p["Closing PNL"]), fee_usdt=fee, fee_src=fee_src, match=src,
                 version_live="v2.6" if p.Opened < V28_LIVE else "v2.8")
        if len(cand):
            e = cand.iloc[0]; used.add((e.sym, e.entry_time)); dist = float(e.sl_dist)
            r.update(eng_entry_utc=e.entry_time, eng_exit_utc=e.exit_time, eng_entry=float(e.entry), eng_exit=float(e.exit), sl_dist=dist,
                     eng_reason=e.reason, eng_R=float(e.R),
                     slip_in_bps=(eL - e.entry) * d / e.entry * 1e4, slip_in_R=(eL - e.entry) * d / dist,
                     slip_out_bps=(e.exit - xL) * d / e.exit * 1e4 if e.exit_time - p.Closed < pd.Timedelta(minutes=10) else np.nan,
                     live_R_gross=(xL - eL) * d / dist, fee_R=fee / (q * dist), live_R_net=(float(p["Closing PNL"]) - fee) / (q * dist),
                     risk_usd=q * dist, stop_pct=dist / e.entry * 100, notional=q * eL)
        rows.append(r)
    A = pd.DataFrame(rows)
    A["R_gap"] = A.live_R_net - A.eng_R
    A["exit_kind"] = np.where(A.eng_reason.eq("TIME"), "time", np.where(A.live_R_gross < -0.5, "stop", "breakeven"))
    A.loc[(A.eng_exit_utc - A.closed_utc).abs() > pd.Timedelta(minutes=10), "exit_kind"] += " (diverged)"
    OUT.mkdir(exist_ok=True)
    A.to_csv(OUT / "live_audit_nov.csv", index=False)
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40)
    show = ["sym", "side", "opened_utc", "version_live", "match", "live_entry", "eng_entry", "slip_in_bps", "slip_in_R", "live_exit", "eng_exit",
            "slip_out_bps", "exit_kind", "stop_pct", "fee_src", "fee_R", "live_R_net", "eng_R", "R_gap", "pnl_gross", "fee_usdt"]
    print(A[show].round(3).to_string(index=False))
    st = A[A.exit_kind == "stop"]; be = A[A.exit_kind.str.startswith("breakeven")]
    print(f"\nstops n={len(st)}: live net R {st.live_R_net.mean():+.3f} (gross {st.live_R_gross.mean():+.3f}, fee {st.fee_R.mean():.3f}), "
          f"engine R {st.eng_R.mean():+.3f}; breakeven exits n={len(be)}: live {be.live_R_net.mean():+.3f} vs engine {be.eng_R.mean():+.3f}")
    print(f"entry slippage: mean {A.slip_in_bps.mean():+.1f} bps ({A.slip_in_R.mean():+.3f} R), median {A.slip_in_bps.median():+.1f} bps; "
          f"exit slippage mean {A.slip_out_bps.mean():+.1f} bps")
    for u in ("BNB", "USDT"):
        g = A[A.fee_src.str.contains(u)]
        print(f"fees paid in {u}: {len(g)} positions, fee R avg {g.fee_R.mean():.3f}, fee / notional round trip {(g.fee_usdt / g.notional).mean() * 1e4:.1f} bps")
    print(f"live realized: gross {A.pnl_gross.sum():+.2f}, fees {A.fee_usdt.sum():.2f}, net {A.pnl_gross.sum() - A.fee_usdt.sum():+.2f} USDT "
          f"-> balance ${300 + A.pnl_gross.sum() - A.fee_usdt.sum():.2f} (funding excluded; open positions not included)")

    # engine trades the live account did not take
    for nm, E in (("v2.8", E8), ("v2.6", E6)):
        miss = E[(E.entry_time >= START) & (E.entry_time < END) & ~E.apply(lambda z: (z.sym, z.entry_time) in used, axis=1)]
        print(f"\n{nm} engine trades with no live position ({len(miss)}):")
        print(miss[["sym", "entry_time", "exit_time", "dir", "R", "reason"]].to_string(index=False))

    # counterfactual accounts from $300 on 12 Oct
    ev = PSL.events(start=START, end=END, extra_coins=())
    print(f"\npanic sleeve (v2.7, 5 coins) trades {START} .. now: {len(ev)}")
    if len(ev):
        print(ev[["t", "t_exit", "sym", "entry", "exit", "ret", "why"]].to_string(index=False))
    out = {}
    for nm, tag in (("v2.8", "v28nov"), ("v2.6", "v26nov")):
        import importlib
        os.environ["BOT_TRADES"] = tag; importlib.reload(B); importlib.reload(PSL)
        x, t0, t1 = B.window(START, END); x = x.copy(); x[:, :3] -= t0
        r = B.run(x, B.bot_policy(), 300.0, keep="trades")
        rp = PSL.run(START, END, ev=ev if len(ev) else None, eq0=300.0)
        out[nm] = (r["final"], r["dd"], rp["final"], rp["dd"], r["skipped"])
        sel = B.T[(B.T.entry_time >= START) & (B.T.entry_time < END)].reset_index(drop=True)
        tk = sel.loc[sorted(r["amts"])].assign(risk_usd=[r["amts"][i] for i in sorted(r["amts"])])
        tk["pnl"] = tk.risk_usd * tk.R
        print(f"\n{nm} botsim from $300 on {START}: final ${r['final']:.2f} (worst drop {r['dd']:.1f}%), skipped by cap {r['skipped']}; "
              f"+ panic sleeve ${rp['final']:.2f} ({rp['dd']:.1f}%)")
        print(tk[["sym", "entry_time", "dir", "R", "risk_usd", "pnl"]].round(3).to_string(index=False))
    os.environ["BOT_TRADES"] = "v28nov"
    pd.DataFrame(out, index=["bot_final", "bot_dd", "bot_panic_final", "bot_panic_dd", "cap_skipped"]).T.to_csv(OUT / "live_audit_nov_counterfactual.csv")


if __name__ == "__main__":
    main()
