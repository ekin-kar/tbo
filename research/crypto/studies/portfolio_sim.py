import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import pickle, sys
import numpy as np, pandas as pd
import common as C
from portfolio import simulate, report, COINS, A, B

ALL = pickle.load(open(C.D.CACHE / "portfolio_trades.pkl", "rb"))
T12 = pd.concat([ALL[(s, 0.0003)] for s in COINS])
T2 = pd.concat([ALL[(s, 0.0003)] for s in ("BTCUSDT", "ETHUSDT")])
TS = pd.concat([ALL[(s, 0.0005)] for s in COINS])
print("Full period Mar 2020 - Sep 2026 (79 months), $1,000 start:")
report(*simulate(T2, risk=0.01, cap=0.03), "BTC+ETH 1% each", 79)
for risk, cap, dc in [(0.003, 0.03, 99), (0.004, 0.03, 99), (0.005, 0.03, 99), (0.005, 0.04, 99), (0.0075, 0.04, 99),
                      (0.005, 0.03, 5), (0.005, 99, 99)]:
    report(*simulate(T12, risk=risk, cap=cap, dir_cap=dc), f"12 coins {risk*100:.2g}% cap {cap*100:.0f}% dir<={dc if dc<99 else '-'}", 79)
report(*simulate(TS, risk=0.005, cap=0.03), "12 coins 0.5% cap 3%, STRESS fees", 79)
print("\nOnly 2024-01 .. 2026-09 (33 months, fresh $1,000):")
report(*simulate(T2, risk=0.01, cap=0.03, start="2024-01-01"), "BTC+ETH 1% each", 33)
for risk, cap in [(0.004, 0.03), (0.005, 0.03), (0.0075, 0.04)]:
    report(*simulate(T12, risk=risk, cap=cap, start="2024-01-01"), f"12 coins {risk*100:.2g}% cap {cap*100:.0f}%", 33)
cv, tk = simulate(T12, risk=0.005, cap=0.03)
print(f"\n12 coins 0.5%/cap 3%: trades taken {len(tk)} of {len(T12)} signals; open positions: median {cv.n_open.median():.0f}, max {cv.n_open.max()}; "
      f"trades/coin: {tk.sym.str[:-4].value_counts().to_dict()}")
pickle.dump(dict(cv=cv, tk=tk), open(C.D.CACHE / "portfolio_main.pkl", "wb"))
