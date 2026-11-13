"""
v3.2 parity test: the five coin bots (bot.py) and the VOLC sleeve (volc.py) on ONE simulated account fed with historical 1m
bars (open-risk cap off, as test_v31_sim.py), compared with the research twin research/crypto/core/v32deploy.py
(cache/portfolio_trades_v32.pkl + volc_trades_v32.pkl, built by `python research/crypto/core/build_trades.py v32`):
  1. the wild-pullback inputs: the bot's daily ATR14 / ATR100 and 5-day move (strategy.vol_regime on the daily candles it
     fetches) at EVERY 4h close vs research/crypto/core/crypto_regimes.py, and the x0.25 decision for both sides. (The
     simulated exchange rounds old prices to today's tick, e.g. SOL 0.01 where 2024 data has 0.001 steps, so its candles
     differ slightly from the research's; the formula itself is also checked exactly on the research's own candles for
     every distinct daily close.);
  2. every trade's size multiplier (the bot's, at its arming close) vs the research's size_mult column;
  3. entries and exits (same minute) as test_v31_sim.py;
  4. volc.py's tie guard (v3.2.1): every sleeve stop it did not place / cancelled because the trend bot's entry order on the
     same coin and side tied it (from volc.py's own log lines).

    python cryptobot/dev/test_v32_sim.py [2024-01-01] [2024-07-01]
"""
import logging
import os
import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(Path(__file__).resolve().parent), str(HERE.parent / "research" / "crypto" / "core")]
import bot as B                                      # noqa: E402
import strategy as S                                 # noqa: E402
import test_v31_sim as T31                           # noqa: E402
from replay import C                                 # noqa: E402
import crypto_regimes as R                           # noqa: E402

SEEN, SIZED = [], []


def record():
    """Hooks: every arming close's inputs and every sized order's multiplier."""
    def regime_seen(self, close_ms, vr, chg5):
        SEEN.append((self.sym, int(close_ms), vr, chg5))
    size0 = B.Bot.size

    def size(self, sl_dist, price, side=1, quiet=False, mult=1.0):
        SIZED.append((self.sym, int(self.x.now_ms()), side, float(mult)))
        return size0(self, sl_dist, price, side, quiet, mult)
    B.Bot.regime_seen = regime_seen
    B.Bot.size = size


def check_regimes(params):
    df = pd.DataFrame(SEEN, columns=["sym", "t", "vr", "chg5"])
    out, flips = [], 0
    for sym, g in df.groupby("sym"):
        ref = R.at(sym, pd.to_datetime(g.t.values, unit="ms"), ["VolReg", "Chg5"])
        a, b = g.vr.astype(float).to_numpy(), ref.VolReg.to_numpy(float)
        c, d = g.chg5.astype(float).to_numpy(), ref.Chg5.to_numpy(float)
        both = np.isfinite(a) & np.isfinite(b)
        nan_mismatch = int((np.isfinite(a) != np.isfinite(b)).sum())
        p = params[sym]
        for side in (1, -1):
            m_bot = np.array([S.size_mult(p, side, x if np.isfinite(x) else None, y if np.isfinite(y) else None) for x, y in zip(a, c)])
            m_ref = np.array([S.size_mult(p, side, x if np.isfinite(x) else None, y if np.isfinite(y) else None) for x, y in zip(b, d)])
            flips += int((m_bot != m_ref).sum())
        out.append(dict(sym=sym, closes=len(g), max_dvr=float(np.max(np.abs(a[both] - b[both]))) if both.any() else 0.0,
                        max_dchg5=float(np.max(np.abs(c[both] - d[both]))) if both.any() else 0.0, nan_mismatch=nan_mismatch,
                        x025_long=int(sum(S.size_mult(params[sym], 1, x, y) < 1 for x, y in zip(a, c) if np.isfinite(x))),
                        x025_short=int(sum(S.size_mult(params[sym], -1, x, y) < 1 for x, y in zip(a, c) if np.isfinite(x)))))
    return pd.DataFrame(out), flips


def check_formula():
    """strategy.vol_regime on the research's own daily candles (the bot's 1,499-candle window) at every distinct daily close
    the bots saw vs crypto_regimes: must be identical."""
    df = pd.DataFrame(SEEN, columns=["sym", "t", "vr", "chg5"])
    worst, n = 0.0, 0
    for sym, g in df.groupby("sym"):
        D = R.daily(sym); idx = D.index.values
        for day in np.unique(pd.to_datetime(g.t.values, unit="ms").floor("D").values):
            k = int(np.searchsorted(idx, day, side="right"))
            if k == 0:
                continue
            w = D.iloc[max(0, k - B.N1D):k]
            vr, ch = S.vol_regime(w.h.to_numpy(), w.l.to_numpy(), w.c.to_numpy())
            ref = D.iloc[k - 1]
            if vr is None or not np.isfinite(ref.VolReg):
                worst = max(worst, 0.0 if (vr is None) == (not np.isfinite(ref.VolReg)) else np.inf); n += 1
                continue
            worst = max(worst, abs(vr - ref.VolReg), abs(ch - ref.Chg5)); n += 1
    return n, worst


def trade_mults(sim):
    """The bot's multiplier for each simulated trade: the last order it sized on that coin and side at or before the fill."""
    sz = pd.DataFrame(SIZED, columns=["sym", "t", "side", "mult"])
    out = {}
    for s in sim:
        g = sz[(sz.sym == s["sym"]) & (sz.side == s["dir"]) & (sz.t <= s["t"] * 60_000 + 59_999)]
        out[(s["sym"], s["t"])] = float(g.mult.iloc[-1]) if len(g) else np.nan
    return out


class TieLog(logging.Handler):
    def __init__(self):
        super().__init__(); self.rows = []

    def emit(self, r):
        m = r.getMessage()
        if "(tie guard)" in m:
            self.rows.append((B.utc(T31.FakeFutures.NOW[0]()) if hasattr(T31.FakeFutures, "NOW") else "", m))


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    ties = TieLog(); vl = logging.getLogger("volc"); vl.setLevel(logging.INFO); vl.propagate = False; vl.addHandler(ties)
    _init = T31.FakeFutures.__init__

    def _init_clock(self, *a, **k):                      # (the tie lines are stamped with the simulated time)
        _init(self, *a, **k); T31.FakeFutures.NOW = [self.now_ms]
    T31.FakeFutures.__init__ = _init_clock
    start = sys.argv[1] if len(sys.argv) > 1 else "2024-01-01"
    end = sys.argv[2] if len(sys.argv) > 2 else "2024-07-01"
    record()
    fxs = T31.run(start, end)
    cache = Path(os.environ.get("TRADING_CACHE", HERE.parent / "cache"))
    T = pd.concat(pickle.load(open(cache / "portfolio_trades_v32.pkl", "rb")).values(), ignore_index=True)
    P = pd.read_pickle(cache / "trade_prices_v32.pkl")
    T = T.merge(P[["sym", "entry_time", "entry", "exit"]], on=["sym", "entry_time"], how="left")
    V = pd.read_pickle(cache / "volc_trades_v32.pkl")
    import json
    params = {s: S.Params(**json.loads((HERE / f"config_{s[:-4].lower()}.json").read_text())["strategy"]) for s in T31.COINS}
    reg, flips = check_regimes(params)
    print(f"wild-pullback inputs at {int(reg.closes.sum())} 4h closes {start}..{end}: max |VolReg bot - research| {reg.max_dvr.max():.2e}, "
          f"max |Chg5 bot - research| {reg.max_dchg5.max():.2e}, warm-up mismatches {int(reg.nan_mismatch.sum())}, "
          f"x0.25 decisions that differ (both sides) {flips}")
    print(reg.to_string(index=False))
    nf, wf = check_formula()
    print(f"formula on the research's own candles at {nf} daily closes: max |difference| {wf:.2e} (VolReg and Chg5)")
    sim = [t for fx in fxs for t in T31.trips(fx, "tbo")]
    T31.compare("TBO v3.2 (5 bots)", sim, T, start, end)
    T31.compare("VOLC sleeve", [t for fx in fxs for t in T31.trips(fx, "vc")], V, start, end)
    bm = trade_mults(sim)
    ref = T[(T.entry_time >= pd.Timestamp(start) + pd.Timedelta(days=2)) & (T.exit_time < end)]
    rm = ref.entry_time.values.astype("datetime64[m]").astype(np.int64)
    pairs = [(s, e, m, bm.get((s, e))) for s, e, m in zip(ref.sym, rm, ref.size_mult) if (s, e) in bm]
    bad = [p for p in pairs if not (p[3] == p[2])]
    print(f"size multiplier, bot vs research, on {len(pairs)} matched trades: x0.25 in research {sum(p[2] < 1 for p in pairs)}, "
          f"in the bots {sum(p[3] < 1 for p in pairs)}, different {len(bad)}")
    for p in bad[:10]:
        print("   differs:", p[0], C.D.to_datetime([p[1]])[0], "research", p[2], "bot", p[3])
    print(f"volc.py tie guard: {len(ties.rows)} sleeve stop orders not placed / cancelled (the trend bot's entry order tied them)")
    for t, m in ties.rows:
        print("   ", t, m)
