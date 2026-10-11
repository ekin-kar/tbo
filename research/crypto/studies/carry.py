"""Idea 10: funding-rate carry (hold the coin in spot, short the same amount of the perpetual, collect funding).
Costs per switch-on + switch-off: spot taker 0.1% x2, futures taker 0.05% x2, slippage 0.02% x4 = 0.38% of notional.
Capital: spot leg fully paid + 50% of notional as futures margin (to survive a fast rally) -> 1.5x notional."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import numpy as np, pandas as pd
import common as C
EX = C.ROOT / "data" / "extra"
COST = 2 * 0.001 + 2 * 0.0005 + 4 * 0.0002
CAP = 1.5
res = {}
for sym in ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]:
    f = pd.read_csv(EX / f"{sym}_funding.csv.gz"); f["t"] = pd.to_datetime(f.time_ms, unit="ms"); f = f.set_index("t").rate
    f = f[f.index >= "2020-03-01"]
    for name, rule in (("always on", None), ("on when 3-day avg > 0.01%", 0.0001), ("on when 3-day avg > 0.03%", 0.0003)):
        if rule is None:
            on = pd.Series(True, index=f.index)
        else:
            avg = f.rolling(9).mean().shift(1)                  # known before each payment
            on = pd.Series(False, index=f.index); st = False
            for t, a in avg.items():
                if not st and a > rule: st = True
                elif st and a < 0: st = False
                on[t] = st
        switches = (on.astype(int).diff().abs() > 0).sum() / 2 + (1 if on.iloc[0] else 0)
        inc = (f * on)                                          # per unit notional
        cost = pd.Series(0.0, index=f.index); flips = on.astype(int).diff().fillna(on.iloc[0]).abs() > 0
        cost[flips] = COST / 2
        pnl = (inc - cost) / CAP                               # on capital
        eq = (1 + pnl).cumprod()
        yr = eq.resample("YE").last().pct_change()
        yr.iloc[0] = eq.resample("YE").last().iloc[0] - 1
        dd = (1 - eq / eq.cummax()).max()
        res[(sym, name)] = (yr, dd, on.mean(), eq.resample("ME").last().pct_change())
        print(f"{sym:9s} {name:28s} time on {on.mean()*100:3.0f}%  yearly on capital: " + " ".join(f"{y.year}:{v*100:+5.1f}%" for y, v in yr.items()) + f"  | worst drop {dd*100:.1f}%")
# combined 4 coins equal capital, always on vs threshold
for name in ("always on", "on when 3-day avg > 0.01%"):
    mo = pd.concat([res[(s, name)][3] for s in ["BTCUSDT", "ETHUSDT", "DOGEUSDT", "ADAUSDT"]], axis=1).mean(axis=1)
    print(f"4 coins equal, {name}: per month avg {mo.mean()*100:.2f}%, 2024-26 {mo['2024':].mean()*100:.2f}%, months negative {(mo<0).mean()*100:.0f}%, $200 2024-26 -> ${200*(1+mo['2024':]).prod():.0f}")
