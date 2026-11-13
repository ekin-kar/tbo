"""v3.3 Track 0: the two VOLC trades that only the live code makes (BTC 2023-04-10 15:41, BNB 2023-07-24 04:06).

Finding: at a 4h close the VOLC sleeve armed its 10-candle stop at EXACTLY the trend bot's 20-candle stop (the 10-candle
high was also the 20-candle high), both orders triggered in the same minute, and volc.py traded its part back at market
the next minute (two taker fees + slippage for a 1-minute trade). The research twin (v31deploy) blocks VOLC fills from a
TBO fill's minute on, so it never had these trades.
VOLC's long level (10-candle high) can never be above TBO's (20-candle high), and vice versa for shorts, so the guard
"no VOLC stop when the trend bot's resting entry order on that side is at a level the price reaches first or at the same
time (buy: tbo <= volc, sell: tbo >= volc)" only removes exact ties.

This script runs cryptobot/dev/test_v32_sim.py's simulated account WITH that guard applied to VOLC's stop orders (a
test-time patch of the simulated client: cryptobot/ is not modified) and reports the parity with the research lists.
    python v33_t0_volc_collision.py 2021-01-01 2023-01-01"""
import os, sys, logging
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "cryptobot"), str(ROOT / "cryptobot" / "dev")]
import test_v32_sim as T32                         # noqa: E402
import test_v31_sim as T31                         # noqa: E402
import bot as B                                    # noqa: E402

SKIPPED = []


def stop_market(self, sym, side, trigger, qty=None, close_position=False, client_id=None):
    fx = self.fx[sym]
    if str(client_id).startswith("vc") and not close_position and os.environ.get("V33_GUARD", "1") == "1":
        trig = float(trigger)
        for o in fx.open_algo_orders(sym):
            cid = str(o.get("clientAlgoId", ""))
            if cid.startswith("tbo") and "_in_" in cid and o["side"] == side and (
                    (side == "BUY" and float(o["trig"]) <= trig + 1e-12) or (side == "SELL" and float(o["trig"]) >= trig - 1e-12)):
                SKIPPED.append((sym, B.utc(fx.now_ms()), side, trig, float(o["trig"])))
                return {"algoId": None}
    return fx.stop_market(sym, side, trigger, qty=qty, close_position=close_position, client_id=client_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    T31.Router.stop_market = stop_market
    start, end = sys.argv[1], sys.argv[2]
    sys.argv = [sys.argv[0], start, end]
    import runpy
    g = runpy.run_path(str(ROOT / "cryptobot" / "dev" / "test_v32_sim.py"), run_name="__main__")
    print(f"guard {'on' if os.environ.get('V33_GUARD', '1') == '1' else 'off'}: VOLC stop orders not placed (tie with the trend bot's "
          f"resting entry): {len(SKIPPED)}")
    for s in SKIPPED:
        print("   ", s)
