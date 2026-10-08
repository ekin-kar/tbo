"""Funding-carry market-neutral strategy: robustness, and blended with the TBO bot (Oct 2026)."""
import itertools, pickle
import numpy as np, pandas as pd
import common as C
from mn_study import panel, signals, backtest, stats, SYMS
from portfolio import simulate

D = panel(); S, r = signals(D)
f = D["fund"]; prem = D["prem"]

# ── 1. full grid around the carry idea ──
rows = []
for L, n, hold in itertools.product((1, 3, 5, 7, 10, 14, 21), (2, 3, 4, 5), (1, 3, 5, 7, 14)):
    sig = -f.rolling(L).mean()
    p, pg, _ = backtest(sig, r, f, n=n, hold=hold)
    d = stats(p.loc[:"2023-12-31"]); h = stats(p.loc["2024-01-01":])
    rows.append(dict(L=L, n=n, hold=hold, dev=d["sharpe"], ho=h["sharpe"], ho_ann=h["ann"], ho_dd=h["dd"]))
G = pd.DataFrame(rows)
print(f"=== carry grid: {len(G)} settings (lookback x coins per side x rebalance days) ===")
print(f"  Sharpe > 0 in 2020-23: {(G.dev > 0).mean()*100:.0f}%   in 2024-26: {(G.ho > 0).mean()*100:.0f}%   both: {((G.dev > 0) & (G.ho > 0)).mean()*100:.0f}%")
print(f"  median Sharpe 2020-23 {G.dev.median():.2f}, 2024-26 {G.ho.median():.2f}; correlation of a setting's dev and holdout Sharpe {np.corrcoef(G.dev, G.ho)[0,1]:.2f}")
print("  by rebalance days (median Sharpe dev / holdout):", {h: (round(g.dev.median(), 2), round(g.ho.median(), 2)) for h, g in G.groupby("hold")})
print("  by lookback:", {h: (round(g.dev.median(), 2), round(g.ho.median(), 2)) for h, g in G.groupby("L")})

# ── 2. the central setting, year by year, legs, costs, leave-one-coin-out ──
L0, N0, H0 = 7, 4, 7
sig = -f.rolling(L0).mean()
p, pg, wy = backtest(sig, r, f, n=N0, hold=H0)
print(f"\n=== central setting: funding {L0}d average, {N0} long / {N0} short, rebalance every {H0} days, gross 1x ===")
for y in range(2020, 2027):
    s = stats(p.loc[str(y)])
    print(f"  {y}: {s['ann']:+6.1f}% a year  Sharpe {s['sharpe']:5.2f}  worst drop {s['dd']:4.1f}%  months positive {s['pos_m']:3.0f}%")
price = (wy * (np.exp(r.fillna(0).loc[wy.index]) - 1)).sum(axis=1); fund_inc = -(wy * f.loc[wy.index]).sum(axis=1)
print(f"  where the money comes from (2020-26, % a year): price moves {price.mean()*365*100:+.1f}%, funding received {fund_inc.mean()*365*100:+.1f}%, costs {(p - price - fund_inc).mean()*365*100:+.1f}%")
for mult in (1.5, 2.0):
    p2, _, _ = backtest(sig, r, f.copy(), n=N0, hold=H0)
    from mn_study import COST
    print(f"  with costs x{mult}: Sharpe 2024-26 approx {stats(p.loc['2024':] - (pg - p).loc['2024':] * (mult - 1))['sharpe']:.2f}")
loo = []
for s_ in SYMS:
    cols = [c for c in SYMS if c != s_]
    pp, _, _ = backtest(sig[cols], r[cols], f[cols], n=N0 - 1 if N0 > 3 else N0, hold=H0)
    loo.append((s_[:-4], round(stats(pp.loc[:"2023"])["sharpe"], 2), round(stats(pp.loc["2024":])["sharpe"], 2)))
print("  leave one coin out (Sharpe 2020-23, 2024-26):", loo)

# ── 3. blend with TBO (5 coins, current risk) ──
ALL = pickle.load(open(C.D.CACHE / "portfolio_trades_v24.pkl", "rb"))
T5 = pd.concat([ALL[(s, 0.0003)] for s in ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]])
W = {"BTCUSDT": 1, "ETHUSDT": .5, "BNBUSDT": .166, "SOLUSDT": .166, "ADAUSDT": .166}
print("\n=== TBO + carry on the same account (daily, 2022-26 and 2024-26) ===")
print(f"{'TBO risk (BTC)':>15s} {'carry gross':>12s} | 2022-26: %/yr  Sharpe  worst drop  months+ | 2024-26: %/yr  Sharpe  worst drop  months+")
for tbo_risk in (0.05, 0.025):
    cv, _ = simulate(T5, risk=tbo_risk, cap=99, short_mult=0.5, start="2020-04-01", end="2026-10-01", eq0=1000.0, weights=W)
    rt = cv.equity.resample("1D").last().ffill().pct_change().fillna(0.0)
    rt = rt.reindex(p.index).fillna(0.0)
    print(f"  correlation TBO vs carry (daily): {np.corrcoef(rt.loc['2022':], p.loc['2022':])[0,1]:.2f}") if tbo_risk == 0.05 else None
    for g in (0.0, 1.0, 2.0, 3.0):
        comb = rt + g * p
        a = stats(comb.loc["2022":]); b = stats(comb.loc["2024":])
        print(f"{tbo_risk*100:14.1f}% {g:11.1f}x | {a['ann']:12.0f}% {a['sharpe']:7.2f} {a['dd']:10.1f}% {a['pos_m']:7.0f}% | {b['ann']:12.0f}% {b['sharpe']:7.2f} {b['dd']:10.1f}% {b['pos_m']:7.0f}%")
for g in (1.0, 2.0, 3.0):
    a = stats(g * p.loc["2022":]); b = stats(g * p.loc["2024":])
    print(f"{'carry alone':>15s} {g:11.1f}x | {a['ann']:12.0f}% {a['sharpe']:7.2f} {a['dd']:10.1f}% {a['pos_m']:7.0f}% | {b['ann']:12.0f}% {b['sharpe']:7.2f} {b['dd']:10.1f}% {b['pos_m']:7.0f}%")
