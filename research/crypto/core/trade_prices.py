"""Entry / exit prices, stop distance and exit reason for the bot's v2.4 trades (the list in
cache/portfolio_trades_v24.pkl has times and R only). Same engine and settings as grid_v25.trades (live structure:
4h, channel 20, 1.0 ATR stop, breakeven 1.5R, 120 h, OI filter 72 h <= -3%; slippage BTC/ETH 0.01%, alts 0.03%).
Writes cache/trade_prices_v24.pkl: one row per trade, keyed (sym, entry_time)."""
import pickle
import pandas as pd
import common as C, families as F
import grid_v25 as G
from wf2 import V21

COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
LIVE = dict(tf=240, n=20, stop=1, be_R=1.5, hold_h=120)


def prices(sym):
    m = C.load(sym)
    C.SLIP = 0.0001 if sym in ("BTCUSDT", "ETHUSDT") else 0.0003
    kw = dict(V21, tf=240, n=20, be_R=1.5, hold_h=120, **G.STOPS[LIVE["stop"]][1])
    kw["skip_fn"] = G.oi_skip(sym, 240)
    x = C.between(F.channel_breakout(m, **kw), "2020-01-01", "2026-10-01")
    return x.assign(sym=sym)[["sym", "entry_time", "exit_time", "dir", "entry", "exit", "sl_dist", "reason", "R"]]


if __name__ == "__main__":
    P = pd.concat([prices(s) for s in COINS], ignore_index=True)
    ALL = pickle.load(open(C.D.CACHE / "portfolio_trades_v24.pkl", "rb"))
    V = pd.concat([ALL[(s, 0.0003)] for s in COINS], ignore_index=True)
    M = V.merge(P, on=["sym", "entry_time"], how="left", suffixes=("", "_p"))
    ok = M.entry.notna() & (M.exit_time == M.exit_time_p) & ((M.R - M.R_p).abs() < 1e-6)
    print(f"v2.4 trades {len(V)}, rebuilt {len(P)}, matched (same entry, exit, R) {ok.sum()}")
    if ok.sum() < len(V):
        print(M[~ok][["sym", "entry_time", "exit_time", "exit_time_p", "R", "R_p"]].head(10).to_string())
    M[["sym", "entry_time", "entry", "exit", "sl_dist", "reason"]].to_pickle(C.D.CACHE / "trade_prices_v24.pkl")
