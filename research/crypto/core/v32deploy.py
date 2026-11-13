"""TBO v3.2 as deployed (13 Nov 2026): the research twin of cryptobot/ for build_trades.py v32.

  TBO    v3.1 exactly (core/v31deploy.py: the failed-breakout stop tighten, the BTC cascade), plus the wild-pullback size
         (research/results/v32c_REPORT.md): at the 4h close that arms the entry order, if the coin's last CLOSED daily
         candle has VolReg = ATR14 / ATR100 >= vr_min and dir x Chg5 <= vr_chg5 (crypto_regimes.py; cryptobot/strategy.py
         vol_regime / size_mult), the trade's risk is x vr_mult. The trade is still taken, so the trade list (entries,
         exits, cooldowns, cascade, VOLC hand-overs) is v3.1's: the rule is a per-trade size multiplier (column size_mult).
         The arming close is the 4h close at or before the fill minute (the order lives one 4h candle); daily closes are
         4h closes, so its last closed day is the last daily close at or before the fill.
  VOLC   unchanged (v31deploy).
  Money  botsim (TAG v32): TR column 6 = size_mult, applied before the open-risk cap (the cap counts the actual, scaled
         risk, as bot.py); portfolio.json = the v3.0 ladder at k 1.00 with the < $1,000 row at the $1,000-10,000 risks."""
import json
import numpy as np, pandas as pd
import common as C
import crypto_regimes as R
import v31deploy as D

_CFG = json.loads((C.ROOT / "cryptobot" / "config_btc.json").read_text())["strategy"]
SIZE = dict(vr_mult=float(_CFG.get("vr_mult", 0.25)), vr_min=float(_CFG.get("vr_min", 0.98)), vr_chg5=float(_CFG.get("vr_chg5", -0.25)))


def regime_at_arm(T):
    """(VolReg, Chg5) of the last closed daily candle at each trade's arming close."""
    out = np.full((len(T), 2), np.nan)
    e = T.entry_time.values.astype("datetime64[m]").astype(np.int64)
    arm = e - e % 240
    for s in T.sym.unique():
        pos = np.flatnonzero(T.sym.to_numpy() == s)
        out[pos] = R.at(s, C.D.to_datetime(arm[pos]), ["VolReg", "Chg5"]).to_numpy(float)
    return out


def size_mult(T, p=None):
    p = dict(SIZE, **(p or {}))
    F = regime_at_arm(T)
    with np.errstate(invalid="ignore"):
        hit = (F[:, 0] >= p["vr_min"]) & (T.dir.to_numpy() * F[:, 1] <= p["vr_chg5"])
    return np.where(hit, p["vr_mult"], 1.0), F


def build(log=print):
    """(TBO trades with size_mult / vr / chg5, VOLC trades, 1)."""
    T, V, it = D.build(log=log)
    m, F = size_mult(T)
    T = T.assign(size_mult=m, vr=F[:, 0], chg5=F[:, 1])
    log(f"v32deploy: {int((m < 1).sum())} of {len(T)} TBO trades at x{SIZE['vr_mult']:g} (wild pullback)")
    return T, V, it
