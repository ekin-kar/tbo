"""
TBO live bot for Binance USD-M futures (one symbol per process). See README.md.

    python bot.py config_btc.json            # live (keys from env BINANCE_API_KEY / BINANCE_API_SECRET)
    python bot.py config_btc.json --testnet  # Binance futures testnet / demo
    python bot.py config_btc.json --dry-run  # no orders: prints what it would do at each 4h close

Loop (every `poll_s` seconds):
  * at each 4h close (+ a few seconds): trail exit -> cancel the old entry order -> if flat, new stop order
  * after an entry fills: place the server-side stop loss at once (closePosition STOP_MARKET)
  * time exit after max_hold_h; if a position has no stop loss (e.g. after a restart) one is placed
  * open-risk cap (v2.5, portfolio.json): a coin's new trade is shrunk (or skipped) so that the risk of all open
    positions not yet at breakeven stays <= the cap; BTC is exempt (never shrunk) but its risk counts for the others
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

VERSION = "2.5"
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
        self.dir, self.suffix = path.parent, ("_testnet" if testnet else "")
        self.state_path = self.dir / f"state_{self.sym}{self.suffix}.json"
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

    def size(self, sl_dist, price, side=1, quiet=False):
        """(quantity, cap note, no_room). Raises if the cap applies and the account cannot be read."""
        eq = self.equity()
        want = eq * self.risk_now(eq) * (self.short_mult if side < 0 else 1.0)
        risk, note = self.capped(eq, want)
        if risk <= 0:
            return 0.0, note, True
        qty = risk / sl_dist
        qty = min(qty, eq * self.max_lev / price, self.f["mkt_max"])
        qty = floor_step(qty, max(self.f["step"], self.f["mkt_step"]))
        if qty < self.f["min_qty"] or qty * price < self.f["min_notional"]:
            if not quiet:
                log.warning(f"size {qty} below the exchange minimum (equity {eq:.2f}): no order")
            return 0.0, note, False
        return qty, note, False

    # ── open-risk cap (whole account) ──
    def portfolio(self):
        """portfolio.json next to the configs; re-read every time, so an edit applies without a restart."""
        p = self.dir / "portfolio.json"
        try:
            return json.loads(p.read_text()) if p.exists() else {}
        except ValueError as e:
            log.warning(f"portfolio.json unreadable ({e}): no open-risk cap")
            return {}

    def ladder_row(self, eq, pf=None):
        """portfolio.json "risk_ladder": the row for this balance (risk steps down as the account grows), or None."""
        row = None
        for r in sorted((pf or self.portfolio()).get("risk_ladder") or [], key=lambda r: float(r["from_usdt"])):
            if eq >= float(r["from_usdt"]):
                row = r
        return row

    def risk_now(self, eq):
        """This coin's risk per trade: from the ladder row for the balance if there is one, else risk_pct."""
        row = self.ladder_row(eq)
        return float(row[self.sym]) / 100 if row and self.sym in row else self.risk

    def cap_frac(self, eq=None):
        """The cap as a fraction of equity, 0 when it does not apply to this coin (off, or exempt like BTC).
        With a risk ladder the cap comes from the balance's row (cap_pct)."""
        pf = self.portfolio()
        if self.sym in pf.get("cap_exempt", []):
            return 0.0
        if pf.get("risk_ladder"):
            row = self.ladder_row(self.equity() if eq is None else eq, pf)
            if row and "cap_pct" in row:
                return max(0.0, float(row["cap_pct"])) / 100
        return max(0.0, float(pf.get("open_risk_cap_pct", 0) or 0)) / 100

    def coin_state(self, sym):
        try:
            return json.loads((self.dir / f"state_{sym}{self.suffix}.json").read_text())
        except (OSError, ValueError):
            return None

    def open_risk(self, filled_before=None):
        """USDT lost if every OTHER open position not yet at breakeven hit its stop now (every symbol on the account).
        filled_before (ms): count only positions that filled before it (the first to fill keeps its size)."""
        pos = self.x.positions()
        pos.pop(self.sym, None)
        if not pos:
            return 0.0, ""
        stops = {}
        try:
            orders = self.x.open_algo_orders()
        except BinanceError:                            # all-symbol query refused: ask per symbol
            orders = [o for sym in pos for o in self.x.open_algo_orders(sym)]
        for o in orders:
            if str(o.get("closePosition")).lower() == "true" or str(o.get("reduceOnly")).lower() == "true":
                stops.setdefault(o["symbol"], []).append((o.get("side"), float(o.get("triggerPrice") or 0)))
        total, parts = 0.0, []
        for sym, (amt, entry) in sorted(pos.items()):
            side = 1 if amt > 0 else -1
            st = self.coin_state(sym)
            if filled_before and st is not None and (st.get("entry_ms") or 0) == 0 and st.get("entry_side"):
                continue                                # its bot has not even seen the fill yet: it filled after ours
            if filled_before and st is not None and (st.get("entry_ms") or 0) > filled_before:
                continue
            trig = [t for sd, t in stops.get(sym, []) if sd == ("SELL" if side == 1 else "BUY") and t > 0]
            if trig:                                    # the stop that would close it first
                stop = max(trig) if side == 1 else min(trig)
                r = max(0.0, side * (entry - stop)) * abs(amt)
            elif st is not None and st.get("sl_dist"):  # stop not placed yet (filled seconds ago): its bot's distance
                r = 0.0 if st.get("be_done") else float(st["sl_dist"]) * abs(amt)
            else:
                log.warning(f"{sym} position {amt} has no stop loss and no bot state: not counted in the open risk")
                r = 0.0
            total += r
            parts.append(f"{sym[:-4]} {r:.2f}" if r > 0 else f"{sym[:-4]} at breakeven")
        return total, ", ".join(parts)

    def capped(self, eq, want, filled_before=None):
        """Risk (USDT) this coin may take now under the cap (0 = no room) and a note for the log."""
        cap = self.cap_frac(eq)
        if cap <= 0:
            return want, ""
        used, parts = self.open_risk(filled_before)
        room = cap * eq - used
        note = f"open risk of the other coins {used:.2f} ({parts or 'none open'}), cap {cap * 100:.2f}% = {cap * eq:.2f}"
        if want <= room:
            return want, note
        if room > float(self.portfolio().get("cap_min_fraction", 0.25)) * want:
            return room, note + f": trade shrunk to {room / want * 100:.0f}% of its normal size"
        return 0.0, note + ": no room"

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

    def place_entry(self, side, trig, qty):
        """Stop-market entry at trig; at market if the price is already beyond it (the backtest fills at the open)."""
        q, bs = fmt(qty, self.f["step"]), ("BUY" if side == 1 else "SELL")
        self.st.update(entry_trig=trig, entry_qty=qty)
        last = self.x.last_price(self.sym)
        if (side == 1 and last >= trig) or (side == -1 and last <= trig):
            log.info(f"price {last} already beyond the level: market entry (as the backtest fills at the open)")
            self.x.market(self.sym, bs, q, client_id=f"{PREFIX}_mk_{int(time.time())}")
            return
        try:
            r = self.x.stop_market(self.sym, bs, fmt(trig, self.f["tick"]), qty=q, client_id=f"{PREFIX}_in_{int(time.time())}")
            self.st["entry_id"] = r["algoId"]
        except BinanceError as e:
            if e.code != -2021:
                raise
            log.info("price already beyond the level: market entry (as the backtest fills at the open)")
            self.x.market(self.sym, bs, q, client_id=f"{PREFIX}_mk_{int(time.time())}")

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
        self.st.update(entry_trig=0.0, entry_qty=0.0)    # (also ends an entry waiting for room under the cap)
        for o in self.my_algo_orders():                 # stray entry orders (e.g. after a crash)
            if "_in_" in o["clientAlgoId"]:
                self.cancel(o["algoId"])
        # open-interest filter (no new order while open interest is falling)
        blocked = False
        if self.p.oi_lookback_h > 0:
            try:
                hist = self.x.open_interest_hist(self.sym, limit=self.p.oi_lookback_h + 12)
                chg = S.oi_change(hist, open_ms + self.p.tf_min * 60_000, self.p.oi_lookback_h)
            except Exception as e:                     # never let missing data stop the bot: no filter then
                chg = None
                log.warning(f"open interest unavailable ({e}): filter not applied this candle")
            blocked = S.oi_blocks(self.p, chg)
            if chg is not None:
                log.info(f"open interest {chg * 100:+.1f}% over {self.p.oi_lookback_h} h"
                         + (f" (<= {self.p.oi_min_chg * 100:.0f}%: no new entry order)" if blocked else ""))
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
                if trig is None or blocked:
                    continue
                trig = ceil_step(trig, self.f["tick"]) if side == 1 else floor_step(trig, self.f["tick"])
                if not (trig > 0 and dec.sl_dist > 0 and math.isfinite(trig)):
                    log.warning(f"invalid level {trig} / stop distance {dec.sl_dist}: no order")
                    continue
                try:
                    qty, note, no_room = self.size(dec.sl_dist, trig, side)
                except Exception as e:                  # cap on but the account cannot be read: add no risk blind
                    log.warning(f"open risk unavailable ({e}): no new entry order this candle")
                    break
                if note:
                    log.info(note)
                if no_room:                             # the cap is full: wait, re-checked every minute until the next close
                    log.info(f"no entry order for now ({'BUY' if side == 1 else 'SELL'} stop {fmt(trig, self.f['tick'])}): "
                             f"placed if room opens before the price gets there, until the next 4h close")
                    self.st.update(sl_dist=dec.sl_dist, entry_side=side, entry_trig=trig, entry_qty=0.0,
                                   entry_from=open_ms + self.p.tf_min * 60_000)
                    break
                if qty <= 0:
                    continue
                log.info(f"ENTRY ORDER {'BUY' if side == 1 else 'SELL'} {fmt(qty, self.f['step'])} stop "
                         f"{fmt(trig, self.f['tick'])}  (SL dist {dec.sl_dist:.2f} = {dec.sl_dist / trig * 100:.2f}%, "
                         f"risk {qty * dec.sl_dist:.2f} USDT, valid until the next 4h close)")
                self.st.update(sl_dist=dec.sl_dist, entry_side=side, entry_from=open_ms + self.p.tf_min * 60_000)
                if self.dry:
                    break
                self.place_entry(side, trig, qty)
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
                lvl, side = self.st.get("entry_trig") or 0.0, (1 if amt > 0 else -1)
                slip = f", level {lvl:g}, slippage {side * (entry_px / lvl - 1) * 100:+.3f}%" if lvl else ""
                risk = abs(amt) * (self.st.get("sl_dist") or 0)
                self.st.update(entry_id=None, entry_trig=0.0, entry_qty=0.0)   # the entry order has triggered
                self.st["cap_check"] = self.cap_frac() > 0
                log.info(f"FILLED {amt} @ {entry_px:.2f}{slip}, risk {risk:.2f} USDT")
                self.save()
            if not self.sl_alive():
                self.place_sl(amt, entry_px)
            if self.st.get("cap_check") and self.st.get("entry_ms"):
                self.trim_to_cap(amt)
                amt, entry_px = self.x.position(self.sym)
            if self.st.get("entry_ms"):                 # (place_sl may have closed it: price already past the stop)
                self.check_breakeven(amt, entry_px)
            if self.st.get("entry_ms") and now - self.st["entry_ms"] >= self.p.max_hold_h * 3600_000:
                self.close_position(amt, f"time ({self.p.max_hold_h:.0f}h)")
        elif self.st.get("entry_ms"):
            log.info("position closed (stop loss hit or closed by hand)")
            self.cancel(self.st.get("sl_id"))
            self.st.update(sl_id=None, entry_side=0, entry_ms=0, best=0.0, be_done=False)
            self.save()
        elif self.st.get("entry_trig") and now - self.st.get("cap_seen_ms", 0) >= 60_000:
            self.st["cap_seen_ms"] = now
            self.resize_entry()

    def resize_entry(self):
        """Once a minute while an entry order waits: keep it inside the open-risk cap as the other coins fill, reach
        breakeven or close (as if the cap were checked at the fill), and place a held-back order once room opens."""
        if self.cap_frac() <= 0 or not self.st.get("sl_dist") or self.paused():
            return
        side, trig, old = self.st["entry_side"], self.st["entry_trig"], self.st.get("entry_qty") or 0.0
        if not old:                                     # held back: give up if the breakout happened meanwhile
            bars = self.x.klines(self.sym, "1m", 1000, start_ms=self.st.get("entry_from"))
            if bars and ((side == 1 and max(k[2] for k in bars) >= trig) or (side == -1 and min(k[3] for k in bars) <= trig)):
                log.info("the breakout happened while the cap was full: no trade this candle")
                self.st.update(entry_trig=0.0); self.save()
                return
        try:
            qty, note, _ = self.size(self.st["sl_dist"], trig, side, quiet=True)
        except Exception as e:
            log.warning(f"open risk unavailable ({e}): entry order left as it is")
            return
        step = max(self.f["step"], self.f["mkt_step"])
        if abs(qty - old) < max(step, 0.05 * old) - 1e-12:
            return
        log.info(f"CAP: entry order {fmt(old, self.f['step'])} -> {fmt(qty, self.f['step'])} ({note})")
        if self.st.get("entry_id"):
            self.cancel(self.st["entry_id"])
            amt, _ = self.x.position(self.sym)
            if amt != 0:                                # it filled just before the cancel: the fill check takes over
                log.info("the entry order filled before the change")
                return
            self.st["entry_id"] = None
        if qty > 0:
            self.place_entry(side, trig, qty)
        else:
            self.st["entry_qty"] = 0.0
        self.save()

    def trim_to_cap(self, amt):
        """Right after a fill: if coins that filled earlier left less room than this order was sized for (fills in the
        same minute), cut the position to fit, or close it if less than cap_min_fraction would remain."""
        try:
            eq = self.equity()
            want = abs(amt) * self.st["sl_dist"]
            allowed, note = self.capped(eq, want, filled_before=self.st["entry_ms"])
        except Exception as e:
            log.warning(f"open risk unavailable ({e}): cap check after the fill retried next poll")
            return
        self.st["cap_check"] = False
        self.save()
        if allowed >= want * 0.95:                      # (5% slack: equity moves a little between order and fill)
            return
        step = max(self.f["step"], self.f["mkt_step"])
        keep = floor_step(allowed / self.st["sl_dist"], step)
        px = self.x.last_price(self.sym)
        if allowed <= 0 or keep < self.f["min_qty"] or keep * px < self.f["min_notional"]:
            log.info(f"CAP after the fill: {note}")
            self.close_position(amt, "open-risk cap (other coins filled first)")
            return
        cut = floor_step(abs(amt) - keep, step)
        if cut <= 0:
            return
        log.info(f"CAP after the fill: {note}: position cut by {fmt(cut, self.f['step'])} to {fmt(keep, self.f['step'])}")
        self.x.market(self.sym, "SELL" if amt > 0 else "BUY", fmt(cut, self.f["step"]), reduce_only=True,
                      client_id=f"{PREFIX}_cap_{int(time.time())}")

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
            # exchange leverage only sets the margin locked per position (cross margin); position size is still
            # capped at max_leverage x equity by size(). Higher here = less margin locked when all coins are open.
            self.x.set_leverage(self.sym, int(self.cfg.get("exchange_leverage", max(1, math.ceil(self.max_lev)))))
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
