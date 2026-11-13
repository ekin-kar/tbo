"""
volc.py edge cases on a stub exchange (no history needed), v3.2.1 audit:
  1. hand-over after the take-profit limit already filled part / all of the sleeve's quantity: only what the sleeve still
     holds goes back at market (never a piece of the trend bot's position);
  2. hand-over with the take-profit fill unreadable: the sleeve's last known quantity (previous behaviour, logged);
  3. tie guard on a poll: the sleeve's stop is cancelled and forgotten; if it triggered first (cancel refused), it is kept
     so the fill check adopts the position (no orphan without a stop);
  4. tie guard keys: real Binance openAlgoOrders rows (triggerPrice as a string, no "trig" key);
  5. a stop loss Binance keeps refusing: closed at market after 3 polls (never left without a stop); a take-profit error
     does not abort the poll;
  6. one coin's exchange error does not stop the other coins being managed in the same poll.

    python cryptobot/dev/test_volc_edges.py
"""
import logging
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import volc as VO                                    # noqa: E402
from binance_futures import BinanceError             # noqa: E402


class Stub:
    def __init__(self):
        self.markets, self.algos, self.lims, self.cancelled = [], {}, {}, []
        self.refuse_cancel = set()

    def exchange_info(self, s):
        return dict(tick=0.1, step=0.001, min_qty=0.001, mkt_step=0.001, mkt_max=1000, min_notional=5, status="TRADING")

    def now_ms(self):
        return 1_700_000_000_000

    def last_price(self, s):
        return 100.0

    def market(self, s, side, qty, reduce_only=False, client_id=None):
        self.markets.append((s, side, float(qty), reduce_only))

    def cancel_algo(self, algo_id=None, client_id=None):
        if algo_id in self.refuse_cancel:
            raise BinanceError(400, -2011, "Unknown order")
        self.algos[algo_id]["algoStatus"] = "CANCELED"; self.cancelled.append(algo_id)

    def algo_order(self, algo_id=None, client_id=None):
        return self.algos[algo_id]

    def open_algo_orders(self, s=None):
        return [o for o in self.algos.values() if o["algoStatus"] == "NEW"]

    def cancel_order(self, s, oid):
        if self.lims[oid]["status"] != "NEW":
            raise BinanceError(400, -2011, "Unknown order")
        self.lims[oid]["status"] = "CANCELED"

    def get_order(self, s, oid):
        if oid == "boom":
            raise BinanceError(500, None, "unavailable")
        return self.lims[oid]

    def user_trades(self, *a, **k):
        return []

    def position(self, s):
        return self.pos.get(s, (0.0, 0.0)) if hasattr(self, "pos") else (0.0, 0.0)

    def stop_market(self, s, side, trig, qty=None, close_position=False, client_id=None):
        if getattr(self, "sl_error", None):
            raise BinanceError(400, self.sl_error, "refused")
        aid = f"sl{len(self.algos)}"; self.algos[aid] = dict(algoId=aid, algoStatus="NEW"); return {"algoId": aid}

    def limit_order(self, s, side, qty, price, reduce_only=True, post_only=True, client_id=None):
        if getattr(self, "tp_error", None):
            raise BinanceError(400, self.tp_error, "refused")
        oid = f"tp{len(self.lims)}"; self.lims[oid] = dict(status="NEW", executedQty="0"); return {"orderId": oid}


def sleeve(x):
    cfg = VO.load_cfg(); cfg["coins"] = ["BTCUSDT"]
    return VO.Sleeve(cfg, x=x, state_dir=tempfile.mkdtemp())


def trade(sv, tp_oid="tp1", tp_q=1.0, qty=1.0):
    sv.st["trades"]["BTCUSDT"] = dict(entry_ms=0, entry=100.0, qty=qty, side=1, dist=1.0, stop=99.0, tp=101.5, sl_id="sl1",
                                      tp_oid=tp_oid, tp_q=tp_q)


def run():
    ok = True

    def check(name, cond, info=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"  [{'OK  ' if cond else 'FAIL'}] {name} {info}")

    # 1a. take-profit filled 0.4 of 1.0, then the trend bot's long filled (position 0.6 + 2.0): 0.6 goes back
    x = Stub(); sv = sleeve(x); trade(sv)
    x.algos["sl1"] = dict(algoId="sl1", algoStatus="NEW"); x.lims["tp1"] = dict(status="PARTIALLY_FILLED", executedQty="0.4")
    sv.hand_over("BTCUSDT", 2.6)
    check("hand-over after a partial take-profit fill sends only the rest", x.markets == [("BTCUSDT", "SELL", 0.6, False)], x.markets)
    # 1b. take-profit fully filled seconds before (position = the trend bot's 2.0 only): nothing goes back
    x = Stub(); sv = sleeve(x); trade(sv)
    x.algos["sl1"] = dict(algoId="sl1", algoStatus="NEW"); x.lims["tp1"] = dict(status="FILLED", executedQty="1.0")
    sv.hand_over("BTCUSDT", 2.0)
    check("hand-over after a full take-profit fill sends nothing", x.markets == [], x.markets)
    # 1c. no fill: the whole 1.0 goes back
    x = Stub(); sv = sleeve(x); trade(sv)
    x.algos["sl1"] = dict(algoId="sl1", algoStatus="NEW"); x.lims["tp1"] = dict(status="NEW", executedQty="0")
    sv.hand_over("BTCUSDT", 3.0)
    check("hand-over without a fill sends the sleeve's quantity", x.markets == [("BTCUSDT", "SELL", 1.0, False)], x.markets)
    # 2. unreadable take-profit: last known quantity
    x = Stub(); sv = sleeve(x); trade(sv, tp_oid="boom")
    x.algos["sl1"] = dict(algoId="sl1", algoStatus="NEW"); x.lims["boom"] = dict(status="NEW", executedQty="0")
    sv.hand_over("BTCUSDT", 3.0)
    check("hand-over with the fill unreadable sends the last known quantity", x.markets == [("BTCUSDT", "SELL", 1.0, False)], x.markets)
    # 3a + 4. tie on a poll (real Binance row fields): cancelled and forgotten
    x = Stub(); sv = sleeve(x)
    x.algos["v1"] = dict(algoId="v1", clientAlgoId="vc_in_BTC_1", side="BUY", triggerPrice="28539.10", algoStatus="NEW")
    x.algos["t1"] = dict(algoId="t1", clientAlgoId="tbo_in_BTC_2", side="BUY", triggerPrice="28539.10", algoStatus="NEW")
    sv.st["orders"]["BTCUSDT"] = {"long": "v1"}; sv.st["pending"]["BTCUSDT"] = {"dist": 1.0}
    sv.drop_ties("BTCUSDT")
    check("tie on a poll: sleeve stop cancelled and forgotten", x.cancelled == ["v1"] and "BTCUSDT" not in sv.st["orders"], sv.st["orders"])
    # 3b. it triggered first (cancel refused, status TRIGGERED): kept for the fill check
    x = Stub(); sv = sleeve(x)
    x.algos["v1"] = dict(algoId="v1", clientAlgoId="vc_in_BTC_1", side="BUY", triggerPrice="28539.10", algoStatus="NEW")
    x.algos["t1"] = dict(algoId="t1", clientAlgoId="tbo_in_BTC_2", side="BUY", triggerPrice="28539.10", algoStatus="NEW")
    x.refuse_cancel.add("v1")
    sv.st["orders"]["BTCUSDT"] = {"long": "v1"}; sv.st["pending"]["BTCUSDT"] = {"dist": 1.0}
    _oa = x.open_algo_orders
    x.open_algo_orders = lambda s=None: (x.algos["v1"].update(algoStatus="NEW") or _oa(s))
    x.algo_order = lambda algo_id=None, client_id=None: dict(x.algos[algo_id], algoStatus="TRIGGERED") if algo_id == "v1" else x.algos[algo_id]
    sv.drop_ties("BTCUSDT")
    check("tie, but the sleeve stop triggered first: kept for the fill check", sv.st["orders"].get("BTCUSDT") == {"long": "v1"}, sv.st["orders"])
    # 4b. a trend-bot order one tick further (BUY 28539.2 > sleeve 28539.1) is not a tie
    x = Stub(); sv = sleeve(x)
    x.algos["t1"] = dict(algoId="t1", clientAlgoId="tbo_in_BTC_2", side="BUY", triggerPrice="28539.20", algoStatus="NEW")
    check("trend bot one tick further is not a tie", sv.tbo_tie("BTCUSDT", 1, 28539.1) is None)
    check("trend bot at the same level is a tie", sv.tbo_tie("BTCUSDT", 1, 28539.2) == 28539.2)
    check("opposite side is never a tie", sv.tbo_tie("BTCUSDT", -1, 28539.2) is None)
    # 5a. stop loss refused 3 times: closed at market (reduce-only), trade finished
    x = Stub(); sv = sleeve(x); trade(sv); x.pos = {"BTCUSDT": (1.0, 100.0)}; x.sl_error = -4045
    sv.st["trades"]["BTCUSDT"].update(sl_id=None, tp_oid=None)
    for _ in range(3):
        sv.place_exits("BTCUSDT")
    check("stop loss refused 3 polls: closed at market", x.markets == [("BTCUSDT", "SELL", 1.0, True)] and "BTCUSDT" not in sv.st["trades"], x.markets)
    # 5b. take-profit refused (other than -5022): no exception, the stop is placed
    x = Stub(); sv = sleeve(x); trade(sv); x.pos = {"BTCUSDT": (1.0, 100.0)}; x.tp_error = -1111
    sv.st["trades"]["BTCUSDT"].update(sl_id=None, tp_oid=None)
    try:
        sv.place_exits("BTCUSDT"); raised = False
    except BinanceError:
        raised = True
    check("take-profit refused: no exception, stop loss in place", not raised and sv.st["trades"]["BTCUSDT"]["sl_id"], sv.st["trades"]["BTCUSDT"])
    # 6. one coin raising does not stop the other coin's management
    x = Stub(); cfg = VO.load_cfg(); cfg["coins"] = ["BTCUSDT", "ETHUSDT"]
    sv = VO.Sleeve(cfg, x=x, state_dir=tempfile.mkdtemp()); seen = []
    sv.st["trades"] = {"BTCUSDT": {}, "ETHUSDT": {}}

    def mt(sym, now):
        seen.append(sym)
        if sym == "BTCUSDT":
            raise BinanceError(503, -1001, "internal error")
    sv.manage_trade = mt
    sv.manage()
    check("one coin's error does not stop the others", seen == ["BTCUSDT", "ETHUSDT"], seen)
    print("RESULT:", "all passed" if ok else "FAILURES")
    return ok


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    sys.exit(0 if run() else 1)
