"""
Live order test: places and removes real orders on Binance with the same calls the bot uses, to confirm the key,
the algo-order endpoint and the rounding all work. Run it while the bot is NOT running.
    python live_test.py                  # DOGEUSDT: stop orders far from the price, then cancel them (no fill, no cost)
    python live_test.py --fill           # also opens the minimum position, puts a stop loss on it, then closes it
                                         # (about $6 of DOGE, costs about 1 cent in fees)
    python live_test.py ADAUSDT --fill   # another coin
    python live_test.py --testnet        # on the testnet / demo keys
"""
import os, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]            # the cryptobot folder (this file is in cryptobot/dev)
sys.path[:0] = [str(HERE), str(Path(__file__).resolve().parent)]
import notify                                                   # noqa: E402
from binance_futures import Futures, BinanceError               # noqa: E402
from bot import floor_step, ceil_step, fmt                      # noqa: E402

notify.load_secrets_env(HERE)
args = [a for a in sys.argv[1:] if not a.startswith("--")]
SYM = (args[0] if args else "DOGEUSDT").upper()
FILL, TESTNET = "--fill" in sys.argv, "--testnet" in sys.argv
x = Futures(os.environ.get("BINANCE_API_KEY", ""), os.environ.get("BINANCE_API_SECRET", ""), testnet=TESTNET)
f = x.exchange_info(SYM)
tag = f"tst{int(time.time())}"          # not the bot's "tbo" prefix, so a running bot would ignore these orders


def step(n, msg):
    print(f"[{n}] {msg}")


def find(cid):
    return [o for o in x.open_algo_orders(SYM) if o.get("clientAlgoId") == cid]


def stop_order_test(n, side, trig, qty, cid):
    r = x.stop_market(SYM, side, fmt(trig, f["tick"]), qty=fmt(qty, f["step"]), client_id=cid)
    step(n, f"placed {side} STOP_MARKET {fmt(qty, f['step'])} {SYM} trigger {fmt(trig, f['tick'])}  algoId {r['algoId']}")
    time.sleep(1)
    assert find(cid), "order not found in open algo orders"
    step(n, "  found in open orders -> check the Binance app now: Open Orders / Conditional tab (5 s)")
    time.sleep(5)
    x.cancel_algo(algo_id=r["algoId"])
    time.sleep(1)
    assert not find(cid), "order still open after cancel"
    step(n, "  cancelled, gone from open orders  OK")


px = x.last_price(SYM)
bal = float(x.account()["totalMarginBalance"])
amt0, _ = x.position(SYM)
print(f"{'TESTNET' if TESTNET else 'LIVE'} {SYM}: price {px}, balance {bal:.2f} USDT, current position {amt0}")
if amt0 != 0:
    sys.exit("there is already a position on this coin; close it (or pick another coin) before testing")
# smallest quantity that clears both minimums with a 20% margin
qty = max(f["min_qty"], ceil_step(f["min_notional"] * 1.2 / px, f["step"]))
print(f"test size {fmt(qty, f['step'])} {SYM} (~${qty * px:.2f}), tick {f['tick']}, step {f['step']}")

try:
    # 1-2: entry stop orders like the bot's: buy stop above the price, sell stop below; never close enough to trigger
    stop_order_test(1, "BUY", ceil_step(px * 1.15, f["tick"]), qty, tag + "_in_L")
    stop_order_test(2, "SELL", floor_step(px * 0.85, f["tick"]), qty, tag + "_in_S")

    if FILL:
        # 3: open a long at market, as when an entry stop triggers
        r = x.market(SYM, "BUY", fmt(qty, f["step"]), client_id=tag + "_mk")
        time.sleep(1)
        amt, entry = x.position(SYM)
        step(3, f"market BUY filled: position {amt} @ {entry}")
        assert amt > 0, "no position after the market buy"
        # 4: stop loss on the whole position (closePosition), 10% below
        sl = x.stop_market(SYM, "SELL", fmt(floor_step(entry * 0.90, f["tick"]), f["tick"]), close_position=True,
                           client_id=tag + "_sl")
        time.sleep(1)
        assert find(tag + "_sl"), "stop loss not found in open algo orders"
        step(4, f"stop loss placed at {fmt(floor_step(entry * 0.90, f['tick']), f['tick'])} (algoId {sl['algoId']})"
                " -> check the app: Positions + Conditional tab (5 s)")
        time.sleep(5)
        # 5: close like the bot's time exit: cancel the stop, reduce-only market sell
        x.cancel_algo(algo_id=sl["algoId"])
        r2 = x.market(SYM, "SELL", fmt(amt, f["step"]), reduce_only=True, client_id=tag + "_cl")
        time.sleep(1)
        amt, _ = x.position(SYM)
        assert amt == 0 and not find(tag + "_sl"), f"not flat after closing: position {amt}"
        step(5, "stop loss cancelled, position closed at market, flat  OK")
        ids = {r.get("orderId"), r2.get("orderId")}
        fills = [t for t in x.user_trades(SYM, limit=20) if t["orderId"] in ids]
        cost = sum(float(t["commission"]) for t in fills) - sum(float(t["realizedPnl"]) for t in fills)
        print(f"    test cost (fees + price difference): about {cost:.4f} USDT")
    print("\nALL OK: the bot can place, see and cancel orders" + (", and open and close positions." if FILL else "."))
except (BinanceError, AssertionError) as e:
    print(f"\nFAILED: {e}")
    print("cleaning up any test orders/position ...")
    for o in x.open_algo_orders(SYM):
        if str(o.get("clientAlgoId", "")).startswith(tag):
            x.cancel_algo(algo_id=o["algoId"])
    amt, _ = x.position(SYM)
    if amt != 0 and amt0 == 0:
        x.market(SYM, "SELL" if amt > 0 else "BUY", fmt(abs(amt), f["step"]), reduce_only=True)
    print("cleanup done; check the Binance app to be sure")
    sys.exit(1)
