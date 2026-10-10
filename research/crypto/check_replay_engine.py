"""Full check: the live decision code (cryptobot/replay.py, the bot's strategy.decide on the same candle windows) vs the
research engine trade list every page uses (cache/portfolio_trades_<BOT_TRADES>.pkl), per coin, 2021-01 .. 2026-09
(replay needs 1000 4h candles of warm-up). Same costs as the engine (taker + slippage per side, funding)."""
import json, pickle, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "cryptobot")); sys.path.insert(0, str(ROOT / "research" / "crypto"))
import replay as RP, strategy as S, common as C, botsim as BS

SLIP = {"BTCUSDT": 0.0001, "ETHUSDT": 0.0001, "BNBUSDT": 0.0003, "SOLUSDT": 0.0003, "ADAUSDT": 0.0003}
if __name__ == "__main__":
    for sym in BS.COINS:
        p = S.Params(**json.load(open(ROOT / "cryptobot" / f"config_{sym[:-4].lower()}.json"))["strategy"])
        tr = RP.replay(C.load(sym), p, "2021-01-01", "2026-10-01", fee=0.0005 + SLIP[sym])
        eng = BS.ALL[(sym, 0.0003)]; eng = eng[eng.entry_time >= "2021-01-01"]
        j = tr.set_index("entry_time").join(eng.set_index("entry_time"), how="inner", lsuffix="_r", rsuffix="_e")
        same_x = (j.exit_time_r == j.exit_time_e).sum(); dR = np.abs(j.R_r - j.R_e).max()
        print(f"{sym}: replay {len(tr)}, engine {len(eng)}, same entry {len(j)}, same exit {same_x}, max R diff {dR:.4f}, "
              f"R sum {tr.R.sum():.1f} vs {eng.R.sum():.1f}, lock reached {(tr.lock_time < tr.exit_time).sum()}", flush=True)
