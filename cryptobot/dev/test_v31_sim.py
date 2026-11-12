"""
v3.1 parity test: the five coin bots (bot.py) AND the VOLC sleeve (volc.py) run together on ONE simulated account fed
with historical 1m bars (the open-risk cap off, so every trade the rules allow is taken). Their trades are compared with
the research twin, research/crypto/core/v31deploy.py (cache/portfolio_trades_v31.pkl + volc_trades_v31.pkl, built by
`python research/crypto/core/build_trades.py v31`): same entry minute, same exit minute, prices.
This exercises the failed-breakout stop tighten, the BTC stop-out cascade (BTC's state file -> the other bots), the
cooldown after it, and the VOLC / trend-bot hand-over on the same coin.

    python cryptobot/dev/test_v31_sim.py [2024-01-01] [2024-07-01]
"""
import json
import logging
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(HERE), str(Path(__file__).resolve().parent)]
import bot as B                                      # noqa: E402
import strategy as S                                 # noqa: E402
import volc as VO                                    # noqa: E402
from replay import C                                 # noqa: E402
from test_bot_sim import FakeFutures, FakeOIHistory  # noqa: E402
from binance_futures import BinanceError             # noqa: E402

COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
EQ = 10_000.0


class Router:
    """The VOLC sleeve's one client for the whole account: calls with a symbol go to that coin's simulated exchange."""

    def __init__(self, fxs):
        self.fx = {f.sym: f for f in fxs}

    def __getattr__(self, name):
        def call(sym=None, *a, **k):
            return getattr(self.fx[sym], name)(sym, *a, **k)
        return call

    def now_ms(self):
        return next(iter(self.fx.values())).now_ms()

    def account(self):
        return {"totalMarginBalance": str(EQ)}

    def open_algo_orders(self, sym=None):
        return self.fx[sym].open_algo_orders(sym)

    def _owner(self, aid):
        for f in self.fx.values():
            if aid in f.orders:
                return f
        raise BinanceError(400, -2011, "Unknown order")

    def algo_order(self, algo_id=None, client_id=None):
        return self._owner(algo_id).algo_order(algo_id=algo_id)

    def cancel_algo(self, algo_id=None, client_id=None):
        return self._owner(algo_id).cancel_algo(algo_id=algo_id)


def run(start, end):
    tmp = Path(f"/tmp/claude_tbo_v31sim_{os.getpid()}"); shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
    pf = json.loads((HERE / "portfolio.json").read_text())
    for r in pf["risk_ladder"]:
        r["cap_pct"] = 0                                  # cap off: every trade taken (the research lists are uncapped)
    pf["open_risk_cap_pct"] = 0
    (tmp / "portfolio.json").write_text(json.dumps(pf))
    for f in HERE.glob("config_*.json"):
        shutil.copy(f, tmp / f.name)
    fxs, bots = [], []
    for i, sym in enumerate(COINS):
        cfg = json.loads((HERE / f"config_{sym[:-4].lower()}.json").read_text())
        fx = FakeFutures(C.load(sym), tick=FakeFutures.exchange_info(None, sym)["tick"], sym=sym)
        fx.next_id = 1 + i * 100_000_000; fx.tag_fills = True
        b = B.Bot.__new__(B.Bot)
        b.cfg, b.dry, b.p, b.sym = cfg, False, S.Params(**cfg["strategy"]), sym
        b.risk, b.short_mult = cfg["risk_pct"] / 100, cfg.get("short_risk_mult", 1.0)
        b.max_lev, b.poll, b.dir, b.suffix = 50, 0, tmp, ""
        b.state_path = tmp / f"state_{sym}.json"; b.x = fx; b.f = fx.exchange_info(sym)
        b.st = dict(last_candle=0, entry_id=None, entry_side=0, sl_dist=0.0, sl_id=None, entry_ms=0)
        b.oi_hist = FakeOIHistory(fx, sym) if b.p.oi_low_days > 0 else None
        fxs.append(fx); bots.append(b)
    for fx in fxs:
        fx.group = fxs
        fx.account = lambda: {"totalMarginBalance": str(EQ)}
    vcfg = VO.load_cfg(); vcfg["max_leverage"] = 50
    vs = VO.Sleeve(vcfg, x=Router(fxs), state_dir=tmp)
    t0, t1 = C.D.minutes(start), C.D.minutes(end)
    clock = fxs[0].m["t"]; clock = clock[(clock >= t0) & (clock < t1)]
    idx = [np.searchsorted(fx.m["t"], clock) for fx in fxs]
    tf_ms = 240 * 60_000
    for k, t in enumerate(clock):
        live = []
        for i, fx in enumerate(fxs):
            j = idx[i][k]
            if j < len(fx.m["t"]) and fx.m["t"][j] == t:
                fx.j = j; live.append(i)
        if len(live) < len(fxs):
            continue                                       # (a minute missing on one coin: skipped for all)
        for b in bots:
            now = b.x.now_ms(); last_open = (now // tf_ms) * tf_ms - tf_ms
            if b.st["last_candle"] < last_open:
                b.on_candle_close(last_open)
            b.check_position()
        vs.manage()                                        # (as volc.run: fills first, then the 4h close, then fills again)
        now = fxs[0].now_ms(); close = (now // tf_ms) * tf_ms
        if vs.st["last_candle"] < close:
            vs.on_close(close)
            vs.manage()
        for fx in fxs:
            fx.process_bar()
    return fxs


def trips(fx, prefix):
    """Round trips of one strategy (orders whose client id starts with prefix) on one coin."""
    out, cur = [], None
    for t, d, q, px, kind, cid in [f for f in fx.fills if len(f) == 6]:
        if not str(cid).startswith(prefix):
            continue
        if cur is None:
            cur = dict(sym=fx.sym, t=t, dir=d, entry=px, qty=q)
        elif d == cur["dir"]:
            cur["qty"] += q
        else:
            cur["qty"] -= q
            if cur["qty"] <= 1e-9:
                cur.update(x=t, exit=px, how=kind); out.append(cur); cur = None
    return out


def compare(name, sim, ref, start, end):
    ref = ref[(ref.entry_time >= pd.Timestamp(start) + pd.Timedelta(days=2)) & (ref.exit_time < end)]
    S_ = {(s["sym"], s["t"]): s for s in sim}
    rm = lambda c: ref[c].values.astype("datetime64[m]").astype(np.int64)
    same = exit_same = 0; px_diff = []; miss = []
    for sym, e, x, ep, xp in zip(ref.sym, rm("entry_time"), rm("exit_time"), ref.entry, ref.exit):
        s = S_.get((sym, e))
        if s is None:
            miss.append((sym, C.D.to_datetime([e])[0])); continue
        same += 1; exit_same += s.get("x") == x
        px_diff.append(abs(s["entry"] / ep - 1))
    extra = [(s["sym"], C.D.to_datetime([s["t"]])[0]) for s in sim if s["t"] >= C.D.minutes(start) + 2 * 1440
             and s.get("x", 10 ** 12) < C.D.minutes(end) and (s["sym"], s["t"]) not in set(zip(ref.sym, rm("entry_time")))]
    print(f"{name}: research {len(ref)} trades | simulated bots: same entry minute {same}, same exit minute {exit_same}; "
          f"max entry price diff {max(px_diff) * 100 if px_diff else 0:.4f}% | only in research {len(miss)}, only in the bots {len(extra)}")
    for m in miss[:10]:
        print("   only in research:", m)
    for m in extra[:10]:
        print("   only in the bots:", m)
    return same, len(ref)


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    start = sys.argv[1] if len(sys.argv) > 1 else "2024-01-01"
    end = sys.argv[2] if len(sys.argv) > 2 else "2024-07-01"
    fxs = run(start, end)
    cache = Path(os.environ.get("TRADING_CACHE", HERE.parent / "cache"))
    import pickle
    T = pd.concat(pickle.load(open(cache / "portfolio_trades_v31.pkl", "rb")).values(), ignore_index=True)
    P = pd.read_pickle(cache / "trade_prices_v31.pkl")
    T = T.merge(P[["sym", "entry_time", "entry", "exit"]], on=["sym", "entry_time"], how="left")
    V = pd.read_pickle(cache / "volc_trades_v31.pkl")
    compare("TBO v3.1 (5 bots)", [t for fx in fxs for t in trips(fx, "tbo")], T, start, end)
    compare("VOLC sleeve", [t for fx in fxs for t in trips(fx, "vc")], V, start, end)
