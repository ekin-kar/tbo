"""The live panic sleeve (panic.py) on a simulated exchange fed with history, vs the research (panic_sleeve.events).
    python cryptobot/dev/test_panic_sim.py [start] [end]       # default 2022-01-01 .. 2026-10-01
1. Signal parity: Sleeve.check_hour (the live data assembly: closed hourly bars, open interest at :55, premium) at every
   research signal hour, the hours around them and 3,000 random hours -> the same coins must trigger.
2. Trades: the sleeve's real order logic (market buy, take-profit / stop orders on the exchange, stop to entry,
   12 h exit) on 1-minute prices; compared trade by trade with the research's hourly-bar simulation.
Needs the research data (data/ 1m candles + data/extra open interest / premium)."""
import sys, json, time, random
from pathlib import Path
HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / "research" / "crypto" / "core"))
import numpy as np, pandas as pd
import panic as PN
import panic_sleeve as R
import common as C
from binance_futures import BinanceError

HOUR, MIN = 3_600_000, 60_000
A, B_ = (sys.argv[1] if len(sys.argv) > 1 else "2022-01-01"), (sys.argv[2] if len(sys.argv) > 2 else "2026-10-01")


class Fake:
    """Main + sub account in one: market data from history, orders filled on the 1-minute bars."""
    def __init__(self, coins):
        self.now = 0; self.H = {}; self.M = {}
        for s in coins:
            df = R.hourly(s); self.H[s] = dict(t=df.index.values.astype("datetime64[ms]").astype(np.int64), o=df.o.values, h=df.h.values,
                                               l=df.l.values, c=df.c.values, oi=df.oi.values, prem=df.prem.values)
            m = C.load(s); self.M[s] = dict(t=m["t"].astype(np.int64) * MIN, o=m["o"], h=m["h"], l=m["l"], c=m["c"])
        self.pos = {s: 0.0 for s in coins}; self.entry = {s: 0.0 for s in coins}; self.algo = {}; self.fills = {s: [] for s in coins}
        self.next_id = 1; self.offset = 0
    # market data
    def now_ms(self): return self.now
    def exchange_info(self, s):
        tick = {"BTCUSDT": 0.1, "ETHUSDT": 0.01, "BNBUSDT": 0.01, "SOLUSDT": 0.01, "ADAUSDT": 0.0001}[s]
        step = {"BTCUSDT": 0.001, "ETHUSDT": 0.001, "BNBUSDT": 0.01, "SOLUSDT": 0.01, "ADAUSDT": 1.0}[s]
        return dict(tick=tick, step=step, min_qty=step, mkt_step=step, mkt_max=1e9, min_notional=5.0, status="TRADING")
    def klines(self, s, interval, limit, start_ms=None):
        if interval == "1h":
            d = self.H[s]; j = int(np.searchsorted(d["t"], self.now, "right"))     # includes the forming hour
            i0 = max(0, j - limit)
            return [(int(d["t"][i]), d["o"][i], d["h"][i], d["l"][i], d["c"][i], int(d["t"][i]) + HOUR - 1) for i in range(i0, j)]
        d = self.M[s]; j = int(np.searchsorted(d["t"], self.now, "left"))           # closed 1-minute bars
        i0 = int(np.searchsorted(d["t"], start_ms, "left")) if start_ms else max(0, j - limit)
        i1 = min(j, i0 + limit)
        return [(int(d["t"][i]), d["o"][i], d["h"][i], d["l"][i], d["c"][i], int(d["t"][i]) + MIN - 1) for i in range(i0, i1)]
    def premium_klines(self, s, interval="1h", limit=1000):
        d = self.H[s]; j = int(np.searchsorted(d["t"], self.now, "right")); i0 = max(0, j - limit)
        return [(int(d["t"][i]), 0, 0, 0, d["prem"][i], int(d["t"][i]) + HOUR - 1) for i in range(i0, j) if not np.isnan(d["prem"][i])]
    def open_interest_hist(self, s, period="5m", limit=500):
        d = self.H[s]; j = int(np.searchsorted(d["t"], self.now - 55 * MIN, "right")); i0 = max(0, j - limit // 12)
        return [(int(d["t"][i]) + 55 * MIN, d["oi"][i]) for i in range(i0, j) if not np.isnan(d["oi"][i])]
    def price(self, s):
        d = self.M[s]; j = max(0, int(np.searchsorted(d["t"], self.now, "right")) - 1); return float(d["o"][j]) if d["t"][j] == self.now else float(d["c"][j])
    def last_price(self, s): return self.price(s)
    # account
    def account(self): return {"totalMarginBalance": "10000"}
    def hedge_mode(self): return False
    def set_leverage(self, s, lev): return {}
    def position(self, s): return self.pos[s], self.entry[s]
    def positions(self): return {s: (q, self.entry[s]) for s, q in self.pos.items() if q}
    def market(self, s, side, qty, reduce_only=False, client_id=None):
        q = float(qty); px = self.price(s)
        if side == "BUY": self.entry[s] = px; self.pos[s] += q
        else: q = min(q, self.pos[s]); self.pos[s] -= q
        self.fills[s].append(dict(side=side, qty=q, price=px, time=self.now, realizedPnl=(px - self.entry[s]) * q if side == "SELL" else 0, commission=0))
        return dict(executedQty=q, avgPrice=px)
    def _algo(self, s, side, trig, kind):
        i = self.next_id; self.next_id += 1; self.algo[i] = dict(s=s, side=side, trig=float(trig), kind=kind, status="NEW"); return {"algoId": i}
    def stop_market(self, s, side, trig, qty=None, close_position=False, client_id=None): return self._algo(s, side, trig, "stop")
    def take_profit_market(self, s, side, trig, client_id=None): return self._algo(s, side, trig, "tp")
    def cancel_algo(self, algo_id=None, client_id=None):
        if self.algo.get(algo_id, {}).get("status") == "NEW": self.algo[algo_id]["status"] = "CANCELED"
    def algo_order(self, algo_id=None, client_id=None):
        if algo_id not in self.algo: raise BinanceError(400, -2013, "no such order")
        return {"algoStatus": self.algo[algo_id]["status"]}
    def open_algo_orders(self, symbol=None): return [dict(algoId=i, **v) for i, v in self.algo.items() if v["status"] == "NEW"]
    def user_trades(self, s, limit=100, start_ms=None, end_ms=None): return [f for f in self.fills[s] if f["time"] >= (start_ms or 0)]
    def step_minute(self):
        """Exchange-side triggers for the minute starting at self.now (stop checked before the take-profit)."""
        for i, o in list(self.algo.items()):
            if o["status"] != "NEW" or self.pos[o["s"]] <= 0: continue
            d = self.M[o["s"]]; j = int(np.searchsorted(d["t"], self.now, "left"))
            if j >= len(d["t"]) or d["t"][j] != self.now: continue
            if o["kind"] == "stop" and d["l"][j] <= o["trig"]:
                px = min(o["trig"], d["o"][j])
            elif o["kind"] == "tp" and d["h"][j] >= o["trig"]:
                px = max(o["trig"], d["o"][j])
            else:
                continue
            q = self.pos[o["s"]]; self.pos[o["s"]] = 0.0; o["status"] = "FINISHED"
            self.fills[o["s"]].append(dict(side="SELL", qty=q, price=px, time=self.now, realizedPnl=(px - self.entry[o["s"]]) * q, commission=0))


def main():
    cfg = PN.load_cfg(); coins = cfg["coins"]
    ev = R.events(coins, start=A, end=B_)
    fx = Fake(coins)
    PN.Futures = lambda *a, **k: fx
    sl = PN.Sleeve(cfg); sl.st = {"trades": {}, "last_hour": 0}; sl.save = lambda: None; sl.tg = lambda *a: None
    # 1. signal parity
    sig_hours = sorted(set(int(t.value // 10**6) - HOUR for t in ev.t))           # the hour whose close triggered
    rnd = random.Random(1); t0, t1 = pd.Timestamp(A).value // 10**6, pd.Timestamp(B_).value // 10**6
    probe = set(sig_hours) | {h + d * HOUR for h in sig_hours for d in (-2, -1, 1, 2)} | {t0 + rnd.randrange((t1 - t0) // HOUR) * HOUR for _ in range(3000)}
    want = {}
    for _, r in ev.iterrows(): want.setdefault(int(r.t.value // 10**6) - HOUR, set()).add(r.sym)
    miss = extra = 0; checked = 0
    for h in sorted(probe):
        fx.now = h + HOUR + 31_000
        sl.st["trades"] = {}
        hits = sl.check_hour(h)
        if hits is None: continue
        got = {s for s, _ in hits}; exp = want.get(h, set()); checked += 1
        # the research skips a coin while it is in a trade; the probe has no open trades, so only check expected <= got
        miss += len(exp - got)
        extra += len(got - exp) if h not in want and all(abs(h - w) > 14 * HOUR for w in want) else 0
    print(f"signal parity: {checked} hours checked, research signals missed by the live code: {miss}, live signals far from any research signal: {extra}")
    # 2. trades through the live order logic
    res = []
    for h in sig_hours:
        if any(tr for tr in sl.st["trades"].values()):
            pass
        fx.now = h + HOUR                                  # the exchange clock at the hourly close
        fx.now += 0                                       # market order fills at the next hour's open
        hits = sl.check_hour(h)
        if not hits: continue
        hits = [(s, i) for s, i in hits if s not in sl.st["trades"]]
        for s, info in hits:
            sl.open_trade(s, info, len(hits), 10000.0, 3000.0)
        end = fx.now + int(cfg["signal"]["hold_h"]) * HOUR + 2 * MIN
        while fx.now < end and sl.st["trades"]:
            fx.step_minute(); fx.now += MIN
            sl.manage()
        for s in list(sl.st["trades"]): sl.close(s, "test end")
    # the sleeve's closed trades are reported through finish(); rebuild them from the fills
    for s in coins:
        f = fx.fills[s]
        for b, x in zip(f[0::2], f[1::2]):
            res.append(dict(sym=s, t=pd.Timestamp(b["time"], unit="ms"), entry=b["price"], exit=x["price"], live_ret=x["price"] / b["price"] - 1,
                            held_h=(x["time"] - b["time"]) / HOUR))
    L = pd.DataFrame(res)
    cost = ev.sym.map(lambda s: 2 * (R.TAKER + R.SLIP.get(s, 0.0003)))
    E = ev.assign(res_ret=ev.ret + cost)[["sym", "t", "entry", "exit", "res_ret", "why"]]
    M = E.merge(L, on=["sym", "t"], how="outer", indicator=True)
    both = M[M._merge == "both"]
    same = (both.res_ret - both.live_ret).abs() < 0.002
    print(f"trades: research {len(E)}, live {len(L)}, matched {len(both)} | same result (within 0.2%) {same.sum()} of {len(both)} | "
          f"avg return research {both.res_ret.mean() * 100:+.2f}% vs live {both.live_ret.mean() * 100:+.2f}% (before costs)")
    d = both[~same]
    if len(d):
        print("differences (live exits on 1-minute prices, the research on hourly bars):")
        print(d[["sym", "t", "why", "res_ret", "live_ret", "held_h"]].round({"res_ret": 4, "live_ret": 4, "held_h": 1}).to_string(index=False))


if __name__ == "__main__":
    main()
