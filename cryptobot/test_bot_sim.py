"""
End-to-end test of bot.py against a simulated exchange fed with historical 1m bars.
The bot's own code places / cancels the orders; fills follow the backtest rules. The trades are compared
with replay.py (the backtest of the same logic).

    python cryptobot/test_bot_sim.py [BTCUSDT] [2024-01-01] [2024-07-01]
"""
import logging
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import bot as B                                      # noqa: E402
import replay as RP                                  # noqa: E402
import strategy as S                                 # noqa: E402
from replay import C, F                              # noqa: E402
from binance_futures import BinanceError             # noqa: E402


class FakeFutures:
    base, key = "sim", "x"

    def __init__(self, m):
        self.m = m
        self.c4 = F.resample(m, 240); self.d1 = F.resample(m, 1440)
        self.j = 0
        self.pos = 0.0; self.entry = 0.0
        self.orders = {}                 # algoId -> dict
        self.next_id = 1
        self.fills = []                  # (time, side, qty, price, kind)

    # clock: 3 s after the open of 1m bar j
    def now_ms(self):
        return int(self.m["t"][self.j]) * 60_000 + 3000

    def exchange_info(self, sym):
        return dict(tick=0.1, step=0.001, min_qty=0.001, mkt_step=0.001, mkt_max=120, min_notional=100, status="TRADING")

    def klines(self, sym, interval, limit):
        c = self.c4 if interval == "4h" else self.d1
        tf = 240 if interval == "4h" else 1440
        now_min = int(self.m["t"][self.j])
        k = np.searchsorted(c["t"], now_min, side="right")      # candles opened up to now (last one forming)
        rows = [(int(c["t"][i]) * 60_000, c["o"][i], c["h"][i], c["l"][i], c["c"][i], (int(c["t"][i]) + tf) * 60_000 - 1)
                for i in range(max(0, k - limit), k)]
        return rows

    def account(self):
        return {"totalMarginBalance": "10000"}

    def position(self, sym):
        return self.pos, self.entry

    def hedge_mode(self):
        return False

    def set_leverage(self, *a):
        pass

    def _fill(self, side, qty, px, kind):
        d = 1 if side == "BUY" else -1
        if self.pos == 0:
            self.entry = px
        self.pos = round(self.pos + d * qty, 6)
        if self.pos == 0:
            self.entry = 0.0
        self.fills.append((int(self.m["t"][self.j]), d, qty, px, kind))

    def market(self, sym, side, qty, reduce_only=False, client_id=None):
        qty = float(qty)
        if reduce_only:
            qty = min(qty, abs(self.pos))
        self._fill(side, qty, self.m["o"][self.j], "market")
        return {}

    def stop_market(self, sym, side, trigger, qty=None, close_position=False, client_id=None):
        trig = float(trigger); o = self.m["o"][self.j]
        if (side == "BUY" and o >= trig) or (side == "SELL" and o <= trig):
            raise BinanceError(400, -2021, "Order would immediately trigger.")
        aid = self.next_id; self.next_id += 1
        self.orders[aid] = dict(algoId=aid, clientAlgoId=client_id, side=side, trig=trig,
                                qty=None if qty is None else float(qty), close=close_position, algoStatus="NEW")
        return {"algoId": aid}

    def open_algo_orders(self, sym):
        return [o for o in self.orders.values() if o["algoStatus"] == "NEW"]

    def algo_order(self, algo_id=None, client_id=None):
        return self.orders[algo_id]

    def cancel_algo(self, algo_id=None, client_id=None):
        o = self.orders.get(algo_id)
        if o is None or o["algoStatus"] != "NEW":
            raise BinanceError(400, -2011, "Unknown order")
        o["algoStatus"] = "CANCELED"

    def process_bar(self):
        """Exchange side of 1m bar j: resting stops trigger on the bar's range."""
        o, h, l = self.m["o"][self.j], self.m["h"][self.j], self.m["l"][self.j]
        for od in list(self.orders.values()):
            if od["algoStatus"] != "NEW":
                continue
            hit = (od["side"] == "BUY" and h >= od["trig"]) or (od["side"] == "SELL" and l <= od["trig"])
            if not hit:
                continue
            px = max(od["trig"], o) if od["side"] == "BUY" else min(od["trig"], o)
            od["algoStatus"] = "FINISHED"
            if od["close"]:
                if self.pos != 0:
                    self._fill(od["side"], abs(self.pos), px, "stop")
            else:
                self._fill(od["side"], od["qty"], px, "entry")


def run(sym="BTCUSDT", start="2024-01-01", end="2024-07-01"):
    m = C.load(sym)
    fx = FakeFutures(m)
    cfg = dict(risk_pct=1.0, max_leverage=3, strategy=S.Params(symbol=sym).to_dict())
    bot = B.Bot.__new__(B.Bot)
    bot.cfg, bot.dry = cfg, False
    bot.p = S.Params(**cfg["strategy"]); bot.sym = sym; bot.risk = 0.01; bot.max_lev = 3; bot.poll = 0
    bot.state_path = Path("/tmp/claude_tbo_sim_state.json"); bot.x = fx; bot.f = fx.exchange_info(sym)
    bot.st = dict(last_candle=0, entry_id=None, entry_side=0, sl_dist=0.0, sl_id=None, entry_ms=0)
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
    ref = RP.replay(C.load(sym), S.Params(symbol=sym), start, end)
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
