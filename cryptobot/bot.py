"""
TBO live bot for Binance USD-M futures (one symbol per process). See README.md.

    python bot.py config_btc.json            # live (keys from env BINANCE_API_KEY / BINANCE_API_SECRET)
    python bot.py config_btc.json --testnet  # Binance futures testnet / demo
    python bot.py config_btc.json --dry-run  # no orders: prints what it would do at each 4h close

Loop (every `poll_s` seconds):
  * at each 4h close (+ a few seconds): trail exit -> cancel the old entry order -> if flat, new stop order
  * after an entry fills: place the server-side stop loss at once (closePosition STOP_MARKET)
  * time exit after max_hold_h; if a position has no stop loss (e.g. after a restart) one is placed
State (entry time, stop distance, order ids) is kept in state_<SYMBOL>.json next to the config, so a
restart picks up where it left off; the exchange is always the source of truth for the position.
"""
import argparse
import json
import logging
import math
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import strategy as S                                   # noqa: E402
from binance_futures import Futures, BinanceError      # noqa: E402
import notify                                          # noqa: E402

VERSION = "2.3"
PREFIX = "tbo"                 # clientAlgoId / clientOrderId prefix of this bot's orders
N4H, N1D = 1000, 500           # candles fetched (the parity test uses the same windows)
log = logging.getLogger("tbo")


def floor_step(x, step):
    return round(math.floor(x / step + 1e-9) * step, 12)


def ceil_step(x, step):
    """Round UP to the step, without floating-point noise pushing an exact multiple one step higher."""
    return round(math.ceil(x / step - 1e-9) * step, 12)


def fmt(x, step):
    dec = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
    return f"{x:.{dec}f}"


def utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")


class Bot:
    def __init__(self, cfg, path, testnet=False, dry=False):
        self.cfg, self.dry = cfg, dry
        self.p = S.Params(**cfg["strategy"])
        self.sym = self.p.symbol
        self.risk = float(cfg["risk_pct"]) / 100
        self.short_mult = float(cfg.get("short_risk_mult", 1.0))   # shorts earn less: trade them smaller
        self.max_lev = float(cfg.get("max_leverage", 3))
        self.poll = float(cfg.get("poll_s", 5))
        self.state_path = path.parent / f"state_{self.sym}{'_testnet' if testnet else ''}.json"
        key = os.environ.get("BINANCE_API_KEY", cfg.get("api_key", ""))
        sec = os.environ.get("BINANCE_API_SECRET", cfg.get("api_secret", ""))
        self.x = Futures(key, sec, testnet=testnet, base_url=cfg.get("base_url"))
        self.f = self.x.exchange_info(self.sym)
        self.st = self.load_state()

    # ── state ──
    def load_state(self):
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return dict(last_candle=0, entry_id=None, entry_side=0, sl_dist=0.0, sl_id=None, entry_ms=0,
                    best=0.0, be_done=False)

    def save(self):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.st, indent=1))
        tmp.replace(self.state_path)

    # ── helpers ──
    def equity(self):
        if self.dry:
            return float(self.cfg.get("dry_run_equity", 1000))
        return float(self.x.account()["totalMarginBalance"])

    def candles(self):
        now = self.x.now_ms()
        k4 = [k for k in self.x.klines(self.sym, "4h", N4H + 1) if k[5] < now][-N4H:]
        k1 = [k for k in self.x.klines(self.sym, "1d", N1D + 1) if k[5] < now][-N1D:]
        return k4, k1

    def my_algo_orders(self):
        return [o for o in self.x.open_algo_orders(self.sym) if str(o.get("clientAlgoId", "")).startswith(PREFIX)]

    def cancel(self, algo_id):
        if algo_id is None or self.dry:
            return
        try:
            self.x.cancel_algo(algo_id=algo_id)
        except BinanceError as e:
            log.info(f"cancel {algo_id}: {e.msg} (already gone)")

    def size(self, sl_dist, price, side=1):
        eq = self.equity()
        qty = eq * self.risk * (self.short_mult if side < 0 else 1.0) / sl_dist
        qty = min(qty, eq * self.max_lev / price, self.f["mkt_max"])
        qty = floor_step(qty, max(self.f["step"], self.f["mkt_step"]))
        if qty < self.f["min_qty"] or qty * price < self.f["min_notional"]:
            log.warning(f"size {qty} below the exchange minimum (equity {eq:.2f}): no order")
            return 0.0
        return qty

    # ── actions ──
    def close_position(self, amt, why):
        side = "SELL" if amt > 0 else "BUY"
        log.info(f"EXIT {why}: {side} {abs(amt)} at market")
        if not self.dry:
            self.x.market(self.sym, side, fmt(abs(amt), self.f["step"]), reduce_only=True,
                          client_id=f"{PREFIX}_x_{int(time.time())}")
        self.cancel(self.st.get("sl_id"))
        self.st.update(sl_id=None, entry_side=0, entry_ms=0, best=0.0, be_done=False)
        self.save()

    def place_sl(self, amt, entry_px):
        side = 1 if amt > 0 else -1
        dist = self.st.get("sl_dist") or 0.0
        if dist <= 0:                                   # unknown (manual / lost state): use the current ATR
            k4, _ = self.candles()
            dist = self.p.sl_atr * S.atr([k[2] for k in k4], [k[3] for k in k4], [k[4] for k in k4], self.p.atr_n)[-1]
            self.st["sl_dist"] = dist
        trig = entry_px - side * dist
        if self.st.get("be_done"):                      # breakeven reached: stop at entry + be_off x dist
            trig = entry_px + side * self.p.be_off * dist
        trig = floor_step(trig, self.f["tick"]) if side == 1 else ceil_step(trig, self.f["tick"])
        log.info(f"STOP LOSS for {amt} @ {entry_px:.2f}: {fmt(trig, self.f['tick'])} ({dist:.2f} away)")
        if self.dry:
            return
        last = self.x.last_price(self.sym)
        if (side == 1 and last <= trig) or (side == -1 and last >= trig):
            log.warning(f"price {last} already beyond the stop {fmt(trig, self.f['tick'])}: closing at market")
            self.close_position(amt, "SL (price already past the stop)")
            return
        try:
            r = self.x.stop_market(self.sym, "SELL" if side == 1 else "BUY", fmt(trig, self.f["tick"]),
                                   close_position=True, client_id=f"{PREFIX}_sl_{int(time.time())}")
            self.st["sl_id"] = r["algoId"]
        except BinanceError as e:
            if e.code == -2021:                         # would trigger at once: price is already past the stop
                log.warning("price already beyond the stop: closing at market")
                self.close_position(amt, "SL (gap)")
                return
            raise
        self.save()

    def on_candle_close(self, open_ms):
        k4, k1 = self.candles()
        if not k4 or k4[-1][0] != open_ms:
            log.warning("latest closed 4h candle not served yet; retrying")
            return False
        h, l, c = [k[2] for k in k4], [k[3] for k in k4], [k[4] for k in k4]
        weekday = datetime.fromtimestamp((open_ms + self.p.tf_min * 60_000) / 1000, timezone.utc).weekday()
        dec = S.decide(self.p, h, l, c, [k[4] for k in k1], weekday, [k[2] for k in k1], [k[3] for k in k1])
        amt, entry_px = self.x.position(self.sym)
        log.info(f"4h close {utc(open_ms + 4 * 3600_000)}: close {c[-1]:.2f}  ATR {dec.atr:.2f}  trend "
                 f"{'up' if dec.trend > 0 else 'down' if dec.trend < 0 else 'none'}"
                 f"{'  (weekend: no new orders)' if self.p.no_weekend and weekday >= 5 else ''}  position {amt}")
        # 1. trail exit
        if (amt > 0 and dec.exit_long) or (amt < 0 and dec.exit_short):
            self.close_position(amt, "trail")
            amt = 0.0
        # 2. the previous entry order expires at this close
        if self.st.get("entry_id"):
            self.cancel(self.st["entry_id"])
            self.st["entry_id"] = None
        for o in self.my_algo_orders():                 # stray entry orders (e.g. after a crash)
            if "_in_" in o["clientAlgoId"]:
                self.cancel(o["algoId"])
        # 3. new entry order while flat (re-read: the old entry order may have filled in the meantime)
        if amt == 0 and not self.dry:
            amt, _ = self.x.position(self.sym)
            if amt != 0:
                log.info(f"the previous entry order filled just now ({amt}): no new order")
        if self.paused():
            log.info("PAUSE file present: no new entry orders (open positions are still managed)")
        if amt == 0 and not self.paused():
            self.st.update(sl_id=None, entry_side=0, entry_ms=0, best=0.0, be_done=False)
            for side, trig in ((1, dec.long_trigger), (-1, dec.short_trigger)):
                if trig is None:
                    continue
                trig = ceil_step(trig, self.f["tick"]) if side == 1 else floor_step(trig, self.f["tick"])
                if not (trig > 0 and dec.sl_dist > 0 and math.isfinite(trig)):
                    log.warning(f"invalid level {trig} / stop distance {dec.sl_dist}: no order")
                    continue
                qty = self.size(dec.sl_dist, trig, side)
                if qty <= 0:
                    continue
                log.info(f"ENTRY ORDER {'BUY' if side == 1 else 'SELL'} {fmt(qty, self.f['step'])} stop "
                         f"{fmt(trig, self.f['tick'])}  (SL dist {dec.sl_dist:.2f} = {dec.sl_dist / trig * 100:.2f}%, "
                         f"valid until the next 4h close)")
                self.st.update(sl_dist=dec.sl_dist, entry_side=side)
                if self.dry:
                    break
                last = self.x.last_price(self.sym)
                if (side == 1 and last >= trig) or (side == -1 and last <= trig):
                    log.info(f"price {last} already beyond the level: market entry (as the backtest fills at the open)")
                    self.x.market(self.sym, "BUY" if side == 1 else "SELL", fmt(qty, self.f["step"]),
                                  client_id=f"{PREFIX}_mk_{int(time.time())}")
                    break
                try:
                    r = self.x.stop_market(self.sym, "BUY" if side == 1 else "SELL", fmt(trig, self.f["tick"]),
                                           qty=fmt(qty, self.f["step"]),
                                           client_id=f"{PREFIX}_in_{int(time.time())}")
                    self.st["entry_id"] = r["algoId"]
                except BinanceError as e:
                    if e.code != -2021:
                        raise
                    log.info("price already beyond the level: market entry (as the backtest fills at the open)")
                    self.x.market(self.sym, "BUY" if side == 1 else "SELL", fmt(qty, self.f["step"]),
                                  client_id=f"{PREFIX}_mk_{int(time.time())}")
                break                                   # one entry order at a time (sides="both": trend picks one)
        self.st["last_candle"] = open_ms
        self.save()
        return True

    def sl_alive(self):
        """True while our stop loss is resting or executing (a triggered stop must not be placed again)."""
        sid = self.st.get("sl_id")
        if not sid:
            return False
        try:
            status = self.x.algo_order(algo_id=sid).get("algoStatus")
        except BinanceError:
            return any(o["algoId"] == sid for o in self.my_algo_orders())
        if status in ("NEW", "TRIGGERING"):
            self.st.pop("sl_done_ms", None)
            return True
        if status in ("TRIGGERED", "FINISHED"):           # executed: the position should be gone within seconds
            first = self.st.setdefault("sl_done_ms", self.x.now_ms())
            if self.x.now_ms() - first < 60_000:
                return True
            log.warning(f"stop loss {sid} is {status} but the position is still open after 60 s: placing a new one")
            self.st.pop("sl_done_ms", None); self.st["sl_id"] = None
            return False
        log.warning(f"stop loss {sid} is {status}: placing a new one")
        self.st["sl_id"] = None
        return False

    def paused(self):
        return (HERE / "PAUSE").exists()

    def check_position(self):
        """Every poll: protect a new fill, time exit, clean up after a stop-out."""
        amt, entry_px = self.x.position(self.sym)
        now = self.x.now_ms()
        if amt != 0:
            if not self.st.get("entry_ms"):
                fill_ms = now - 60_000                  # fallback: the fill happened since the last poll
                if self.st.get("entry_id") and not self.dry:
                    try:
                        trig = int(self.x.algo_order(algo_id=self.st["entry_id"]).get("triggerTime") or 0)
                        if 0 < trig <= now:
                            fill_ms = trig
                    except BinanceError:
                        pass
                self.st["entry_ms"] = fill_ms
                self.st["be_from"] = fill_ms - fill_ms % 60_000 + 60_000   # first full 1m candle after the fill
                self.st["entry_id"] = None              # the entry order has triggered
                log.info(f"FILLED {amt} @ {entry_px:.2f}")
                self.save()
            if not self.sl_alive():
                self.place_sl(amt, entry_px)
            self.check_breakeven(amt, entry_px)
            if now - self.st["entry_ms"] >= self.p.max_hold_h * 3600_000:
                self.close_position(amt, f"time ({self.p.max_hold_h:.0f}h)")
        elif self.st.get("entry_ms"):
            log.info("position closed (stop loss hit or closed by hand)")
            self.cancel(self.st.get("sl_id"))
            self.st.update(sl_id=None, entry_side=0, entry_ms=0, best=0.0, be_done=False)
            self.save()

    def check_breakeven(self, amt, entry_px):
        """Move the stop to entry (+ be_off) once a 1m candle after the fill went be_R x dist in favour."""
        if self.p.be_R <= 0 or self.st.get("be_done") or not self.st.get("sl_dist"):
            return
        side = 1 if amt > 0 else -1
        start = self.st.get("be_from") or (self.st["entry_ms"] - self.st["entry_ms"] % 60_000 + 60_000)
        bars = self.x.klines(self.sym, "1m", 1000, start_ms=start)    # every 1m candle not checked yet
        if bars:
            self.st["be_from"] = bars[-1][0]                            # the forming candle is re-read next time
        if not bars:
            return
        ext = max(k[2] for k in bars) if side == 1 else min(k[3] for k in bars)
        best = self.st.get("best") or entry_px
        best = max(best, ext) if side == 1 else min(best, ext)
        self.st["best"] = best
        if side * (best - entry_px) >= self.p.be_R * self.st["sl_dist"]:
            log.info(f"BREAKEVEN: price reached {best:.2f} (+{self.p.be_R}R): stop moves to entry")
            self.st["be_done"] = True
            old = self.st.get("sl_id")
            self.cancel(old)
            self.st["sl_id"] = None
            self.place_sl(amt, entry_px)
        self.save()

    def run(self):
        if not self.dry:
            if self.x.hedge_mode():
                raise SystemExit("Account is in Hedge mode; switch Binance Futures to One-way mode first.")
            self.x.set_leverage(self.sym, max(1, math.ceil(self.max_lev)))
        eq = self.equity()
        log.info(f"TBO v{VERSION} {self.sym} {'DRY RUN ' if self.dry else ''}on {self.x.base} | equity {eq:.2f} USDT | "
                 f"risk {self.risk * 100:.2f}% (shorts x{self.short_mult}) | max leverage {self.max_lev} | {self.p.to_dict()}")
        tf_ms = self.p.tf_min * 60_000
        last_sync = time.time()
        while True:
            try:
                if time.time() - last_sync > 3600:
                    self.x.sync_time(); last_sync = time.time()
                now = self.x.now_ms()
                last_open = (now // tf_ms) * tf_ms - tf_ms           # open time of the last CLOSED 4h candle
                if self.st["last_candle"] < last_open and now - (last_open + tf_ms) >= 3000:
                    if now - (last_open + tf_ms) > 15 * 60_000:
                        log.warning("4h close was missed by > 15 min (bot was off): acting on it now")
                    self.on_candle_close(last_open)
                if not self.dry:
                    self.check_position()
            except BinanceError as e:
                log.error(f"Binance: {e}")
                if e.code in (-2014, -2015, -1022):
                    raise SystemExit("API key / permission problem")
            except Exception as e:                                  # network hiccups: keep going
                log.exception(f"error: {e}")
                time.sleep(10)
            time.sleep(self.poll)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config")
    ap.add_argument("--testnet", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    path = Path(a.config).resolve()
    cfg = json.loads(path.read_text())
    notify.load_env(path.parent / ".env")
    logdir = path.parent / "logs"; logdir.mkdir(exist_ok=True)
    sym = cfg["strategy"]["symbol"]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s UTC  %(message)s", datefmt="%Y-%m-%d %H:%M:%S",
                        handlers=[logging.StreamHandler(), logging.FileHandler(logdir / f"{sym}.log", encoding="utf-8")])
    logging.Formatter.converter = time.gmtime
    logging.getLogger("tbo").addHandler(notify.TelegramHandler(sym + (" TESTNET" if a.testnet else "") + (" DRY" if a.dry_run else "")))
    while True:                                         # start-up: retry calmly while Binance is unreachable
        try:
            bot = Bot(cfg, path, testnet=a.testnet, dry=a.dry_run)
            break
        except BinanceError as e:
            if e.code in (-2014, -2015, -1022):
                raise SystemExit(f"API key / permission problem: {e}")
            logging.getLogger("tbo").warning(f"Binance error at start-up: {e}; retrying in 30 s")
        except Exception as e:
            logging.getLogger("tbo").warning(f"cannot reach Binance ({type(e).__name__}); retrying in 30 s")
        time.sleep(30)
    bot.run()


if __name__ == "__main__":
    main()
