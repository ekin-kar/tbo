"""
End-to-end test of bot.py against a simulated exchange fed with historical 1m bars.
The bot's own code places / cancels the orders; fills follow the backtest rules. The trades are compared
with replay.py (the backtest of the same logic).

    python cryptobot/dev/test_bot_sim.py [BTCUSDT] [2024-01-01] [2024-07-01]
"""
import json
import os
import logging
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parents[1]            # the cryptobot folder (this file is in cryptobot/dev)
sys.path[:0] = [str(HERE), str(Path(__file__).resolve().parent)]
import bot as B                                      # noqa: E402
import replay as RP                                  # noqa: E402
import strategy as S                                 # noqa: E402
from replay import C, F                              # noqa: E402
from binance_futures import BinanceError             # noqa: E402


class FakeFutures:
    base, key = "sim", "x"

    def __init__(self, m, tick=None, sym=None):
        if tick:                                    # serve tick-exact prices like Binance (the history is float32)
            m = dict(m, **{k: np.round(np.round(m[k] / tick) * tick, 10) for k in ("o", "h", "l", "c")})
        self.m = m
        self.c4 = F.resample(m, 240); self.d1 = F.resample(m, 1440)
        self.j = 0
        self.pos = 0.0; self.entry = 0.0
        self.orders = {}                 # algoId -> dict
        self.open_ids = set()            # ids of the orders still NEW (fast lookups on long runs)
        self.next_id = 1
        self.fills = []                  # (time, side, qty, price, kind)
        self.sym = sym
        self.group = [self]              # every coin's simulated exchange on the same account (open-risk cap)
        self.sl_log = []                 # (time, trigger) of every stop loss placed

    # clock: 3 s after the open of 1m bar j
    def now_ms(self):
        return int(self.m["t"][self.j]) * 60_000 + 3000

    def exchange_info(self, sym):
        if sym == "DOGEUSDT":                                 # Binance USD-M filters (tick / step / min notional)
            return dict(tick=0.00001, step=1.0, min_qty=1.0, mkt_step=1.0, mkt_max=30_000_000, min_notional=5, status="TRADING")
        if sym == "ADAUSDT":
            return dict(tick=0.0001, step=1.0, min_qty=1.0, mkt_step=1.0, mkt_max=3_000_000, min_notional=5, status="TRADING")
        if sym == "AVAXUSDT":
            return dict(tick=0.001, step=1.0, min_qty=1.0, mkt_step=1.0, mkt_max=100_000, min_notional=5, status="TRADING")
        if sym == "BNBUSDT":
            return dict(tick=0.01, step=0.01, min_qty=0.01, mkt_step=0.01, mkt_max=2000, min_notional=5, status="TRADING")
        if sym == "SOLUSDT":
            return dict(tick=0.01, step=1.0, min_qty=1.0, mkt_step=1.0, mkt_max=5000, min_notional=5, status="TRADING")
        if sym == "ETHUSDT":                                  # Binance USD-M ETHUSDT filters
            return dict(tick=0.01, step=0.001, min_qty=0.001, mkt_step=0.001, mkt_max=2000, min_notional=20, status="TRADING")
        return dict(tick=0.1, step=0.001, min_qty=0.001, mkt_step=0.001, mkt_max=120, min_notional=100, status="TRADING")

    def klines(self, sym, interval, limit, start_ms=None):
        if interval == "1m":                                      # closed bars + the forming one (open only)
            j = self.j; m = self.m
            i0 = max(0, j - limit + 1)
            if start_ms is not None:
                i0 = max(i0, int(np.searchsorted(m["t"], start_ms // 60_000)))
            rows = [(int(m["t"][i]) * 60_000, m["o"][i], m["h"][i], m["l"][i], m["c"][i], int(m["t"][i]) * 60_000 + 59_999)
                    for i in range(i0, j)]
            o = m["o"][j]
            return rows + [(int(m["t"][j]) * 60_000, o, o, o, o, int(m["t"][j]) * 60_000 + 59_999)]
        c = self.c4 if interval == "4h" else self.d1
        tf = 240 if interval == "4h" else 1440
        now_min = int(self.m["t"][self.j])
        k = np.searchsorted(c["t"], now_min, side="right")      # candles opened up to now (last one forming)
        rows = [(int(c["t"][i]) * 60_000, c["o"][i], c["h"][i], c["l"][i], c["c"][i], (int(c["t"][i]) + tf) * 60_000 - 1)
                for i in range(max(0, k - limit), k)]
        return rows

    def open_interest_hist(self, sym, period="1h", limit=100):
        if not hasattr(self, "oi"):
            self.oi = RP.load_oi(sym)
        now = self.now_ms()
        i = int(np.searchsorted(self.oi[0], now, side="right"))
        return [(int(t), float(v)) for t, v in zip(self.oi[0][max(0, i - limit):i], self.oi[1][max(0, i - limit):i])]

    def last_price(self, sym):
        return float(self.m["o"][self.j])

    def sync_time(self):
        pass

    def account(self):
        return {"totalMarginBalance": "10000"}

    def position(self, sym):
        return self.pos, self.entry

    def positions(self):
        return {f.sym: (f.pos, f.entry) for f in self.group if f.pos != 0}

    def hedge_mode(self):
        return False

    def set_leverage(self, *a):
        pass

    def _fill(self, side, qty, px, kind, cid=None):
        d = 1 if side == "BUY" else -1
        if self.pos == 0 or (self.pos > 0) != (d > 0) and qty > abs(self.pos):
            self.entry = px
        elif (self.pos > 0) == (d > 0):                   # adding to a position: average entry
            self.entry = (self.entry * abs(self.pos) + px * qty) / (abs(self.pos) + qty)
        self.pos = round(self.pos + d * qty, 6)
        if self.pos == 0:
            self.entry = 0.0
        self.fills.append((int(self.m["t"][self.j]), d, qty, px, kind) if cid is None else (int(self.m["t"][self.j]), d, qty, px, kind, cid))

    def market(self, sym, side, qty, reduce_only=False, client_id=None):
        qty = float(qty)
        if reduce_only:
            qty = min(qty, abs(self.pos))
        self._fill(side, qty, self.m["o"][self.j], "market", client_id if self.tag_fills else None)
        return {}

    tag_fills = False                                   # True: fills carry the order's client id (v3.1 test)

    def take_profit_market(self, sym, side, trigger, client_id=None):
        """closePosition TAKE_PROFIT_MARKET: fills at the trigger once the bar trades through it (the engine's rule)."""
        trig = float(trigger); o = self.m["o"][self.j]
        if (side == "SELL" and o >= trig) or (side == "BUY" and o <= trig):
            raise BinanceError(400, -2021, "Order would immediately trigger.")
        aid = self.next_id; self.next_id += 1
        self.orders[aid] = dict(algoId=aid, clientAlgoId=client_id, side=side, trig=trig, symbol=self.sym, triggerPrice=str(trig),
                                closePosition=True, qty=None, close=True, tp=True, algoStatus="NEW")
        self.open_ids.add(aid)
        return {"algoId": aid}

    def stop_market(self, sym, side, trigger, qty=None, close_position=False, client_id=None):
        trig = float(trigger); o = self.m["o"][self.j]
        if (side == "BUY" and o >= trig) or (side == "SELL" and o <= trig):
            raise BinanceError(400, -2021, "Order would immediately trigger.")
        aid = self.next_id; self.next_id += 1
        self.orders[aid] = dict(algoId=aid, clientAlgoId=client_id, side=side, trig=trig, symbol=self.sym, triggerPrice=str(trig),
                                closePosition=close_position, qty=None if qty is None else float(qty), close=close_position, algoStatus="NEW")
        self.open_ids.add(aid)
        if close_position:
            self.sl_log.append((int(self.m["t"][self.j]), trig))
        return {"algoId": aid}

    def open_algo_orders(self, sym=None):
        if sym is None:
            return [f.orders[i] for f in self.group for i in sorted(f.open_ids)]
        return [self.orders[i] for i in sorted(self.open_ids)]

    def algo_order(self, algo_id=None, client_id=None):
        return self.orders[algo_id]

    def cancel_algo(self, algo_id=None, client_id=None):
        o = self.orders.get(algo_id)
        if o is None or o["algoStatus"] != "NEW":
            raise BinanceError(400, -2011, "Unknown order")
        o["algoStatus"] = "CANCELED"
        self.open_ids.discard(algo_id)

    def process_bar(self):
        """Exchange side of 1m bar j: resting stops trigger on the bar's range."""
        o, h, l = self.m["o"][self.j], self.m["h"][self.j], self.m["l"][self.j]
        for od in [self.orders[i] for i in sorted(self.open_ids)]:
            if od["algoStatus"] != "NEW":
                continue
            if od.get("tp"):                                # take-profit: SELL above / BUY below, filled at the trigger
                hit = (od["side"] == "SELL" and h >= od["trig"]) or (od["side"] == "BUY" and l <= od["trig"])
                if not hit:
                    continue
                od["algoStatus"] = "FINISHED"; self.open_ids.discard(od["algoId"])
                if self.pos != 0:
                    self._fill(od["side"], abs(self.pos), od["trig"], "tp", od["clientAlgoId"] if self.tag_fills else None)
                continue
            hit = (od["side"] == "BUY" and h >= od["trig"]) or (od["side"] == "SELL" and l <= od["trig"])
            if not hit:
                continue
            px = max(od["trig"], o) if od["side"] == "BUY" else min(od["trig"], o)
            od["algoStatus"] = "FINISHED"; self.open_ids.discard(od["algoId"])
            cid = od["clientAlgoId"] if self.tag_fills else None
            if od["close"]:
                if self.pos != 0:
                    self._fill(od["side"], abs(self.pos), px, "stop", cid)
            else:
                self._fill(od["side"], od["qty"], px, "entry", cid)


class FakeOIHistory:
    """bot.oi_hist on the simulated exchange: the archive's hourly rows up to now (no downloads)."""

    def __init__(self, fx, sym):
        self.fx, self.oi = fx, RP.load_oi(sym)

    def update(self, max_days=None, **kw):              # (bot.py passes budget_s)
        return 0

    def series(self):
        i = int(np.searchsorted(self.oi[0], self.fx.now_ms(), side="right"))
        lo = max(0, i - 24 * 95)
        return [(int(t), float(v)) for t, v in zip(self.oi[0][lo:i], self.oi[1][lo:i])]

    def hours(self):
        return len(self.series())


def params(sym):
    """The coin's live strategy settings (config_xxx.json) without the v3.1 rules (fb_h, casc_src): replay.py is the v3.0
    logic; the v3.1 rules are checked by test_v31_sim.py against research/crypto/core/v31deploy.py."""
    s = dict(json.load(open(HERE / f"config_{sym[:-4].lower()}.json"))["strategy"], fb_h=0, casc_src="")
    return S.Params(**s)


def run(sym="BTCUSDT", start="2024-01-01", end="2024-07-01"):
    m = C.load(sym)
    fx = FakeFutures(m, tick=FakeFutures.exchange_info(None, sym)["tick"], sym=sym)
    cfg = dict(risk_pct=2.0, max_leverage=5, strategy=params(sym).to_dict())
    bot = B.Bot.__new__(B.Bot)
    bot.cfg, bot.dry = cfg, False
    bot.p = S.Params(**cfg["strategy"]); bot.sym = sym; bot.risk = 0.02; bot.max_lev = 5; bot.poll = 0
    bot.dir, bot.suffix = Path(f"/tmp/claude_tbo_sim_{os.getpid()}"), ""            # no portfolio.json there: cap off
    bot.dir.mkdir(exist_ok=True)
    bot.state_path = bot.dir / f"state_{sym}.json"; bot.x = fx; bot.f = fx.exchange_info(sym)
    bot.oi_hist = FakeOIHistory(fx, sym) if bot.p.oi_low_days > 0 else None
    bot.short_mult = 1.0; bot.cfg = cfg; bot.st = dict(last_candle=0, entry_id=None, entry_side=0, sl_dist=0.0, sl_id=None, entry_ms=0)
    j0, j1 = np.searchsorted(m["t"], C.D.minutes(start)), np.searchsorted(m["t"], C.D.minutes(end))
    tf_ms = 240 * 60_000
    for j in range(j0, j1):
        fx.j = j
        now = fx.now_ms()
        last_open = (now // tf_ms) * tf_ms - tf_ms
        if bot.st["last_candle"] < last_open:
            bot.on_candle_close(last_open)
        bot.check_position()
        fx.process_bar()
    # fills -> round trips
    trades, cur = [], None
    for t, d, q, px, kind in fx.fills:
        if cur is None:
            cur = dict(entry_time=t, dir=d, entry=px)
        else:
            cur.update(exit_time=t, exit=px, how=kind); trades.append(cur); cur = None
    return trades


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sym = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
    start = sys.argv[2] if len(sys.argv) > 2 else "2024-01-01"
    end = sys.argv[3] if len(sys.argv) > 3 else "2024-07-01"
    bt = run(sym, start, end)
    ref = RP.replay(C.load(sym), params(sym), start, end)
    ref = ref[ref.exit_time < end]
    bt_entries = {C.D.to_datetime([b["entry_time"]])[0]: b for b in bt}
    same = sum(1 for t in ref.entry_time if t in bt_entries)
    print(f"bot on simulated exchange: {len(bt)} trades | backtest: {len(ref)} trades | same entry minute: {same}")
    diffs = [abs(bt_entries[t]["entry"] - e) for t, e in zip(ref.entry_time, ref.entry) if t in bt_entries]
    xd = [abs((C.D.to_datetime([bt_entries[t]["exit_time"]])[0] - x).total_seconds()) / 60
          for t, x in zip(ref.entry_time, ref.exit_time) if t in bt_entries]
    print(f"max entry price diff {max(diffs):.2f}; exit time diff (min): median {np.median(xd):.0f}, max {max(xd):.0f}")
    r_bot = sum((b["exit"] - b["entry"]) * b["dir"] / s for b, s in
                zip([bt_entries[t] for t in ref.entry_time if t in bt_entries], ref.sl_dist[[t in bt_entries for t in ref.entry_time]]))
    r_ref = ((ref.exit - ref.entry) * ref.dir / ref.sl_dist).sum()
    print(f"gross R: bot {r_bot:.1f} vs backtest {r_ref:.1f}")
