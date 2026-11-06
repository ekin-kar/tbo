"""
Parity of the OI-low filter (v2.8): the live code (strategy.oi_rank / oi_low_blocks, fed exactly as bot.py feeds it)
against the research that found it (research/crypto/studies/oi_support.py), on every coin the bot trades.
  1. the block decision at every 4h close from 2022 (live rank vs the research's pandas rolling rank)
  2. the trades: replay.py (the live decision logic with the 1m fill rules) vs the research engine with the filter
     (with the v3.0 exits / cooldown switched off, as that study's engine has the v2.8 exits; v3.0 is checked by replay.py
     against research/crypto/core/v30lib and by test_bot_sim.py)

    python cryptobot/dev/test_oi_low.py [BTCUSDT,ETHUSDT,...]
"""
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(Path(__file__).resolve().parent), str(HERE.parent / "research" / "crypto" / "studies")]
import strategy as S                      # noqa: E402
import replay as RP                       # noqa: E402
import oi_support as O                    # noqa: E402

COND = dict(fam="C", p=dict(meas="oi", side="low", W=90, p=0.8))
syms = sys.argv[1].split(",") if len(sys.argv) > 1 else [json.loads(f.read_text())["strategy"]["symbol"] for f in sorted(HERE.glob("config_*.json"))]
bad = 0
for sym in syms:
    p = S.Params(**json.loads((HERE / f"config_{sym[:-4].lower()}.json").read_text())["strategy"])
    X = O.Coin(sym)
    mask, _ = X.cond(COND)
    oi = RP.load_oi(sym)
    t0 = pd.Timestamp("2022-01-01").value // 60_000_000_000
    ks = np.flatnonzero(X.c["t"] >= t0)
    live = np.zeros(len(ks), bool)
    for n, k in enumerate(ks):
        order_ms = int(X.T[k]) * 60_000
        i = int(np.searchsorted(oi[0], order_ms))
        lo = max(0, i - p.oi_low_days * 24 - 2)
        live[n] = S.oi_low_blocks(p, S.oi_rank(list(zip(oi[0][lo:i], oi[1][lo:i])), order_ms, p.oi_low_days * 24, p.oi_low_days * 12))
    diff = int((live != mask[ks]).sum())
    # trades
    m = X.m
    p28 = dataclasses.replace(p, lock_to=1.5, lock2_R=0.0, stale_h=0.0, cool_h=0.0)       # the study's v2.8 exits
    rp = RP.replay(m, p28, "2022-01-01", O.PERIODS[-1][2], fee=(O.C.TAKER + O.C.SLIP, O.C.TAKER + O.C.SLIP), oi=oi)
    L_, S_ = X.cond(COND)
    eng = X.run(L_, S_)
    e_live = rp.entry_time.values.astype("datetime64[m]").astype(np.int64)
    same = len(set(e_live) & set(eng.e.values))
    print(f"{sym}: 4h closes {len(ks)}, blocked research {int(mask[ks].sum())} / live {int(live.sum())}, different {diff} | "
          f"trades replay {len(rp)} / research {len(eng)}, same entry minute {same}, R {rp.R.sum():.1f} / {eng.R.sum():.1f}")
    bad += diff
print("BLOCK DECISIONS IDENTICAL" if bad == 0 else f"{bad} block decisions differ")
