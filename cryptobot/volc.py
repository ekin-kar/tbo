"""
TBO VOLC sleeve (v3.1): a short breakout trade after a quiet spell (volc_signal.py), on BTC ETH BNB SOL ADA, on the MAIN
account next to the trend bots. Settings in volc.json; started by run_all.py when volc.json has "enabled": true.

    python volc.py              # live (BINANCE_API_KEY / BINANCE_API_SECRET, the main account)
    python volc.py --testnet
    python volc.py --dry-run    # no orders: logs what it would do

One coin, one position (Binance one-way mode); the trend bot always has priority:
  * at each 4h close the sleeve places its stop orders on a coin only while the trend bot has no position there
    (and cancels them as soon as the trend bot's entry fills);
  * the trend bot keeps placing its own orders while the sleeve holds a coin; when one fills (its order merges with the
    sleeve's position), the sleeve cancels its stop and take-profit and trades exactly its own quantity back at market,
    leaving the trend bot's position as if the sleeve had not been there (research/crypto/core/v31deploy.py: the same);
  * the sleeve's trades are outside the open-risk cap (the bots skip them), sized at `share` x the ladder's BTC risk on
    the balance the bots size on (main + panic sub-account).
  * v3.2.1 tie guard (research/results/v33_REPORT.md, Track 0): no sleeve stop where the trend bot's resting entry order on
    the same coin and side is at a level the price reaches first or at the same time (buy: tbo <= volc, sell: tbo >=
    volc; VOLC's 10-candle level is never beyond TBO's 20-candle one, so only exact ties): both would fill in the same
    minute and the sleeve would trade its part straight back. Checked when placing at the 4h close and at every poll
    (the trend bot may place its order a moment later): a tied sleeve stop is not placed / cancelled.
Exits on Binance: stop loss (closePosition STOP_MARKET, last price) and take-profit (a reduce-only post-only LIMIT order:
maker fee); closed at market hold_h hours after the fill.
State in state_volc.json (the exchange is the source of truth for positions).
"""
import argparse
import bisect
import json
import logging
import math
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import notify                                          # noqa: E402
import volc_signal as VS                               # noqa: E402
from binance_futures import Futures, BinanceError      # noqa: E402

PREFIX = "vc"
TBO_PREFIX = "tbo"                                     # the trend bots' order ids (bot.py PREFIX); entries contain "_in_"
HOUR, TF = 3_600_000, 4 * 3_600_000
log = logging.getLogger("volc")


def floor_step(x, step):
    return round(math.floor(x / step + 1e-9) * step, 12)


def ceil_step(x, step):
    return round(math.ceil(x / step - 1e-9) * step, 12)


def fmt(x, step):
    dec = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
    return f"{x:.{dec}f}"


def replace_retry(tmp, path, tries=10):
    """Atomic state-file swap; on Windows a reader holding the file open makes the rename fail for a moment: retry."""
    for k in range(tries):
        try:
            return tmp.replace(path)
        except PermissionError:
            if k == tries - 1:
                raise
            time.sleep(0.05)


def load_cfg(path=HERE / "volc.json"):
    cfg = json.loads(Path(path).read_text())
    cfg["signal"] = dict(VS.DEFAULTS, **cfg.get("signal", {}))
    return cfg


def oi_at(series, end_ms):
    """Open interest at the end of a candle closing at end_ms: the last sample in the half hour before it (the research
    uses the same rule); NaN if none."""
    ts = [t for t, _ in series]
    j = bisect.bisect_left(ts, end_ms) - 1
    return series[j][1] if j >= 0 and ts[j] >= end_ms - 30 * 60_000 else float("nan")


class Sleeve:
    def __init__(self, cfg, testnet=False, dry=False, x=None, state_dir=HERE):
        self.cfg, self.testnet, self.dry = cfg, testnet, dry
        self.p = cfg["signal"]; self.coins = list(cfg["coins"])
        self.x = x or Futures(os.environ.get("BINANCE_API_KEY", ""), os.environ.get("BINANCE_API_SECRET", ""), testnet=testnet)
        self.dir, self.suffix = Path(state_dir), ("_testnet" if testnet else "")
        self.f = {s: self.x.exchange_info(s) for s in self.coins}
        self.state_path = self.dir / f"state_volc{self.suffix}.json"
        self.st = json.loads(self.state_path.read_text()) if self.state_path.exists() else {}
        for k, v in (("trades", {}), ("orders", {}), ("pending", {}), ("last_candle", 0)):
            self.st.setdefault(k, v)

    # ── helpers ──
    def save(self):
        tmp = self.state_path.with_suffix(".tmp"); tmp.write_text(json.dumps(self.st, indent=1)); replace_retry(tmp, self.state_path)

    def tg(self, text):
        if notify.enabled():
            mode = " <i>(dry run)</i>" if self.dry else " <i>(testnet)</i>" if self.testnet else ""
            first, _, rest = text.partition("\n")
            notify.send(first + mode + ("\n" + rest if rest else ""))

    def cid(self, kind, sym):
        return f"{PREFIX}_{kind}_{sym[:-4]}_{int(time.time() * 1000)}"

    def P(self, sym, v):
        return notify.px(v, self.f[sym]["tick"])

    def now(self):
        return self.x.now_ms()

    def json_file(self, name):
        try:
            return json.loads((self.dir / f"{name}{self.suffix}.json").read_text())
        except (OSError, ValueError):
            return {}

    def portfolio(self):
        try:
            return json.loads((self.dir / "portfolio.json").read_text())
        except (OSError, ValueError):
            return {}

    def btc_pct(self, eq):
        row = None
        for r in sorted(self.portfolio().get("risk_ladder") or [], key=lambda r: float(r["from_usdt"])):
            if eq >= float(r["from_usdt"]):
                row = r
        if row and "BTCUSDT" in row:
            return float(row["BTCUSDT"])
        try:
            return float(json.loads((self.dir / "config_btc.json").read_text())["risk_pct"])
        except (OSError, ValueError, KeyError):
            return 0.0

    def equity(self):
        """The balance the bots size on: the main account (minus the user's own isolated trades on other coins) + the
        panic sleeve's sub-account."""
        if self.dry:
            return float(self.cfg.get("dry_run_equity", 300))
        eq = float(self.x.account()["totalMarginBalance"])
        try:
            bots = {json.loads(f.read_text())["strategy"]["symbol"] for f in self.dir.glob("config_*.json")}
            eq -= sum(v for s, v in self.x.isolated_positions().items() if s not in bots)
        except Exception as e:
            log.info(f"isolated positions unreadable ({e}): counted in the balance this time")
        if os.environ.get("PANIC_API_KEY") and os.environ.get("PANIC_API_SECRET") and self.portfolio().get("pool_panic_balance", True):
            try:
                if not hasattr(self, "_px"):
                    self._px = Futures(os.environ["PANIC_API_KEY"], os.environ["PANIC_API_SECRET"], testnet=self.testnet)
                eq += float(self._px.account()["totalMarginBalance"])
            except Exception as e:
                log.warning(f"panic sub-account balance unreadable ({e}): sizing on the main account only")
        return eq

    def tbo_filled(self, sym):
        """The trend bot's entry order on this coin has triggered (its state file names it)."""
        st = self.json_file(f"state_{sym}")
        if st.get("entry_ms"):
            return True
        if st.get("mk_ms") and self.now() - int(st["mk_ms"]) < 120_000:     # a market entry (price already past its level)
            return True
        return self.status(st.get("entry_id")) in ("TRIGGERED", "FINISHED")

    def tbo_busy(self, sym):
        """The trend bot is in a trade on this coin (its state file), or its entry has just filled."""
        st = self.json_file(f"state_{sym}")
        return bool(st.get("entry_ms")) or bool(st.get("manual"))

    def tbo_tie(self, sym, side, trig, orders=None):
        """The trend bot's resting entry order on this coin and side if it sits at `trig` or nearer (buy: tbo <= trig, sell:
        tbo >= trig): a sleeve stop there could only fill with or after it (v3.2.1 tie guard). Its level, or None."""
        if orders is None:
            try:
                orders = self.x.open_algo_orders(sym)
            except BinanceError as e:
                log.warning(f"{sym[:-4]}: open orders unreadable ({e}): tie guard skipped this time")
                return None
        bs = "BUY" if side == 1 else "SELL"
        for o in orders:
            cid = str(o.get("clientAlgoId", ""))
            if not (cid.startswith(TBO_PREFIX + "_") and "_in_" in cid) or str(o.get("side")) != bs:
                continue
            px = float(o.get("triggerPrice") or 0)
            if px > 0 and ((side == 1 and px <= trig + 1e-12) or (side == -1 and px >= trig - 1e-12)):
                return px
        return None

    def drop_ties(self, sym):
        """Every poll while the sleeve's entry orders rest: cancel one that the trend bot's entry order now ties."""
        ords = self.st["orders"].get(sym) or {}
        if not (ords.get("long") or ords.get("short")) or self.dry:
            return
        try:
            oo = self.x.open_algo_orders(sym)
        except BinanceError:
            return
        for k, side in (("long", 1), ("short", -1)):
            aid = ords.get(k)
            mine = next((o for o in oo if aid and str(o.get("algoId")) == str(aid)), None)
            if mine is None:
                continue
            trig = float(mine.get("triggerPrice") or 0)
            px = self.tbo_tie(sym, side, trig, oo)
            if px is not None:
                self.cancel(aid)
                if self.status(aid) not in ("CANCELED", "EXPIRED", "REJECTED"):
                    continue                             # triggered first, cancel failed or status unreadable: kept (the fill
                                                         # check takes over, or the next poll cancels it again)
                log.info(f"{sym[:-4]}: the trend bot's entry order {self.P(sym, px)} ties the sleeve's {'BUY' if side == 1 else 'SELL'} "
                         f"stop {self.P(sym, trig)}: sleeve order cancelled (tie guard)")
                ords.pop(k, None)
        if not any(ords.values()):
            self.st["orders"].pop(sym, None); self.st["pending"].pop(sym, None)

    def panic_triggers(self):
        return [int(t) for t, *_ in self.json_file("state_panic").get("triggers", [])]

    def cancel(self, aid):
        if aid and not self.dry:
            try:
                self.x.cancel_algo(algo_id=aid)
            except BinanceError:
                pass

    def status(self, aid):
        if not aid or self.dry:
            return None
        try:
            return self.x.algo_order(algo_id=aid).get("algoStatus")
        except BinanceError:
            return None

    def cancel_entries(self, sym):
        for aid in (self.st["orders"].pop(sym, {}) or {}).values():
            self.cancel(aid)
        self.st["pending"].pop(sym, None)

    # ── 4h close: new orders ──
    def data(self, sym, close_ms):
        now = self.now()
        k4 = [k for k in self.x.klines(sym, "4h", 1000) if k[5] < now]
        kd = [k for k in self.x.klines(sym, "1d", 500) if k[5] < now]
        if not k4 or k4[-1][0] + TF != close_ms:
            return None
        oi = self.x.open_interest_hist(sym, period="5m", limit=500)
        return ([k[2] for k in k4], [k[3] for k in k4], [k[4] for k in k4], [k[4] for k in kd],
                oi_at(oi, close_ms), oi_at(oi, close_ms - 24 * HOUR))

    def on_close(self, close_ms):
        """Returns False if the data of this close is not served yet."""
        decs = {}
        for sym in self.coins:
            d = self.data(sym, close_ms)
            if d is None:
                return False
            decs[sym] = VS.decide(*d, p=self.p)
        excl = VS.near_panic(close_ms, self.panic_triggers(), self.p["excl_h"])
        eq = None
        for sym in self.coins:
            if sym in self.st["orders"] and not self.dry and self.x.position(sym)[0] != 0:
                continue                                 # filled just before this close: manage() records the trade first
            self.cancel_entries(sym)                     # last candle's orders expire
            dec = decs[sym]; i = dec["info"]
            log.debug(f"{sym[:-4]} 4h close: ATR14/100 {i.get('ratio', float('nan')):.2f}, OI 24h {i.get('doi', float('nan')) * 100:+.1f}%, "
                      f"trend {i.get('side')}, ER {i.get('er', float('nan')):.2f} -> long {dec['long']} short {dec['short']}")
            if dec["long"] is None and dec["short"] is None:
                continue
            if sym in self.st["trades"]:
                continue
            if excl:
                log.info(f"{sym[:-4]}: VOLC setup, but a panic trigger in the last {self.p['excl_h']:g} h: no order")
                continue
            amt = 0.0 if self.dry else self.x.position(sym)[0]
            if amt != 0 or self.tbo_busy(sym):
                log.info(f"{sym[:-4]}: VOLC setup, but the trend bot holds {sym[:-4]}: no order")
                continue
            if eq is None:
                eq = self.equity()
            risk = eq * self.btc_pct(eq) / 100 * float(self.cfg.get("share", 0.25))
            dist = dec["dist"]
            orders, qtys = {}, {}
            for side, trig in ((1, dec["long"]), (-1, dec["short"])):
                if trig is None:
                    continue
                f = self.f[sym]
                trig = ceil_step(trig, f["tick"]) if side == 1 else floor_step(trig, f["tick"])
                qty = min(risk / dist, eq * float(self.cfg.get("max_leverage", 6)) / trig, f["mkt_max"])
                qty = floor_step(qty, max(f["step"], f["mkt_step"]))
                if qty < f["min_qty"] or qty * trig < f["min_notional"]:
                    log.info(f"{sym[:-4]}: VOLC size {qty} below Binance's minimum: no order")
                    continue
                tie = self.tbo_tie(sym, side, trig)
                if tie is not None:
                    log.info(f"{sym[:-4]}: the trend bot's entry order {self.P(sym, tie)} ties the sleeve's {'BUY' if side == 1 else 'SELL'} "
                             f"stop {self.P(sym, trig)}: no sleeve order (tie guard)")
                    continue
                bs = "BUY" if side == 1 else "SELL"
                log.info(f"{sym[:-4]} VOLC {bs} stop {self.P(sym, trig)} qty {fmt(qty, f['step'])} (stop {self.P(sym, trig - side * dist)}, "
                         f"risk {qty * dist:.2f} USDT)")
                if self.dry:
                    continue
                last = self.x.last_price(sym)
                if (side == 1 and last >= trig) or (side == -1 and last <= trig):
                    for aid in orders.values():          # the other side's stop placed a moment ago: gone first
                        self.cancel(aid)
                    self.st["pending"][sym] = dict(dist=dist, tp_R=dec["tp_R"], placed=close_ms, side=side, trig=trig, qty_mk=qty)
                    self.x.market(sym, bs, fmt(qty, f["step"]), client_id=self.cid("mk", sym))
                    orders = {"mk": None}
                    break
                qtys["qty_long" if side == 1 else "qty_short"] = qty
                try:
                    orders["long" if side == 1 else "short"] = self.x.stop_market(sym, bs, fmt(trig, f["tick"]), qty=fmt(qty, f["step"]),
                                                                                 client_id=self.cid("in", sym))["algoId"]
                except BinanceError as e:
                    if e.code != -2021:
                        raise
                    for aid in orders.values():          # the other side's stop placed a moment ago: gone first
                        self.cancel(aid)
                    self.x.market(sym, bs, fmt(qty, f["step"]), client_id=self.cid("mk", sym))
                    self.st["pending"][sym] = dict(dist=dist, tp_R=dec["tp_R"], placed=close_ms, side=side, trig=trig, qty_mk=qty)
                    orders = {"mk": None}
                    break
            if orders:
                self.st["orders"][sym] = orders
                self.st["pending"].setdefault(sym, dict(dist=dist, tp_R=dec["tp_R"], placed=close_ms, **qtys))
        self.st["last_candle"] = close_ms
        self.save()
        return True

    # ── every poll ──
    def manage(self):
        now = self.now()
        for sym in list(self.st["orders"]):
            self.guarded(sym, self.manage_orders, sym, now)
        for sym in list(self.st["trades"]):
            self.guarded(sym, self.manage_trade, sym, now)
        self.save()

    def guarded(self, sym, fn, *a):
        """One coin's step: an exchange error on it is logged and retried next poll without holding up the other coins
        (key / permission errors still stop the sleeve)."""
        try:
            fn(*a)
        except BinanceError as e:
            if e.code in (-2014, -2015, -1022):
                raise
            log.error(f"{sym[:-4]}: Binance: {e} (retried next poll)")

    def manage_orders(self, sym, now):
        amt, entry = self.x.position(sym)
        if amt == 0:
            if self.tbo_busy(sym):                      # (cannot happen without a position; kept for safety)
                self.cancel_entries(sym)
            else:
                self.drop_ties(sym)                      # the trend bot may have placed a tying order since
            return
        trig = {k: aid for k, aid in self.st["orders"][sym].items() if k == "mk" or self.status(aid) in ("TRIGGERED", "FINISHED")}
        ours = list(trig.values())
        if not ours:                                     # the trend bot's entry filled first: it has the coin
            log.info(f"{sym[:-4]}: the trend bot's trade started: VOLC orders cancelled")
            self.cancel_entries(sym)
            return
        if self.tbo_filled(sym):                         # both filled in the same moment: the trend bot keeps the coin
            q = sum(float((self.st["pending"].get(sym) or {}).get(f"qty_{k}", 0)) for k in trig)
            side = 1 if "long" in trig or (self.st["pending"].get(sym) or {}).get("side") == 1 else -1
            log.warning(f"{sym[:-4]}: the trend bot's order filled together with the sleeve's: the sleeve's {q:g} is closed at market")
            self.cancel_entries(sym)
            if q > 0 and not self.dry:                    # (not reduce-only: the bot may have gone the other way)
                self.x.market(sym, "SELL" if side == 1 else "BUY", fmt(q, self.f[sym]["step"]), client_id=self.cid("x", sym))
            return
        fill_ms = now - 60_000                           # fallback: the fill happened since the last poll
        if ours[0]:
            try:
                tt = int(self.x.algo_order(algo_id=ours[0]).get("triggerTime") or 0)
                if 0 < tt <= now:
                    fill_ms = tt
            except BinanceError:
                pass
        self.open_trade(sym, amt, entry, fill_ms)

    def open_trade(self, sym, amt, entry, fill_ms):
        pend = self.st["pending"].get(sym, {})
        for aid in (self.st["orders"].pop(sym, {}) or {}).values():
            self.cancel(aid)                            # the other side's order
        self.st["pending"].pop(sym, None)
        side = 1 if amt > 0 else -1
        dist = float(pend.get("dist") or 0.0)
        f = self.f[sym]
        tr = dict(entry_ms=max(int(pend.get("placed") or 0), int(fill_ms)), entry=entry, qty=abs(amt), side=side,
                  dist=dist, stop=entry - side * dist, tp=entry + side * float(pend.get("tp_R", self.p["tp_R"])) * dist, sl_id=None, tp_oid=None)
        tr["stop"] = floor_step(tr["stop"], f["tick"]) if side == 1 else ceil_step(tr["stop"], f["tick"])
        tr["tp"] -= side * float(self.cfg.get("tp_inside", 0.0001)) * entry    # the limit sits 0.01% inside the target: a touch
        tr["tp"] = floor_step(tr["tp"], f["tick"]) if side == 1 else ceil_step(tr["tp"], f["tick"])   # of the target fills it
        self.st["trades"][sym] = tr
        self.save()
        log.info(f"VOLC FILLED {'long' if side > 0 else 'short'} {abs(amt):g} {sym[:-4]} @ {self.P(sym, entry)} | stop {self.P(sym, tr['stop'])} | "
                 f"TP {self.P(sym, tr['tp'])} | closes by {notify.when(tr['entry_ms'] + int(self.p['hold_h']) * HOUR)}")
        self.place_exits(sym)
        if sym in self.st["trades"]:
            self.tg("\n".join([f"🌀 <b>{sym[:-4]} VOLC {'long' if side > 0 else 'short'}</b>",
                               f"Entry <b>{self.P(sym, entry)}</b> · stop {self.P(sym, tr['stop'])} · take profit {self.P(sym, tr['tp'])}",
                               f"Risk {notify.usd(abs(amt) * dist)} · closes by {notify.when(tr['entry_ms'] + int(self.p['hold_h']) * HOUR, day=False)} at the latest"]))

    def place_exits(self, sym):
        tr = self.st["trades"][sym]; f = self.f[sym]; side = tr["side"]
        if self.dry:
            return
        last = self.x.last_price(sym)
        if (side == 1 and last <= tr["stop"]) or (side == -1 and last >= tr["stop"]):
            self.close(sym, "stop (price already past it)"); return
        if (side == 1 and last >= tr["tp"]) or (side == -1 and last <= tr["tp"]):
            self.close(sym, "take profit (price already past it)"); return
        xs = "SELL" if side == 1 else "BUY"
        try:
            if not tr.get("sl_id"):
                tr["sl_id"] = self.x.stop_market(sym, xs, fmt(tr["stop"], f["tick"]), close_position=True, client_id=self.cid("sl", sym))["algoId"]
                tr["sl_fail"] = 0
        except BinanceError as e:
            if e.code == -2021:
                self.close(sym, "stop already passed"); return
            if e.code in (-2014, -2015, -1022):
                raise
            tr["sl_fail"] = int(tr.get("sl_fail") or 0) + 1
            log.error(f"{sym[:-4]}: VOLC stop loss not placed ({e}), attempt {tr['sl_fail']}")
            if tr["sl_fail"] >= 3:                       # never sit without a stop: out at market
                self.close(sym, f"stop loss could not be placed ({e.msg})"); return
            self.save(); return                          # retried next poll (no take-profit before the stop)
        if not tr.get("tp_oid"):
            amt = abs(self.x.position(sym)[0])
            try:
                tq = fmt(min(tr["qty"], amt), f["step"])
                tr["tp_oid"] = self.x.limit_order(sym, xs, tq, fmt(tr["tp"], f["tick"]), reduce_only=True,
                                                  post_only=True, client_id=self.cid("tp", sym))["orderId"]
                tr["tp_q"] = float(tq)                     # (the hand-over subtracts what it filled)
            except BinanceError as e:
                if e.code == -5022:                      # post-only would fill at once: the price is already past the take-profit
                    self.close(sym, "take profit (price already past it)"); return
                if e.code in (-2014, -2015, -1022):
                    raise
                log.warning(f"{sym[:-4]}: VOLC take-profit not placed ({e}): retried next poll (the stop loss is in place)")
        self.save()

    def manage_trade(self, sym, now):
        tr = self.st["trades"][sym]
        amt = tr["qty"] * tr["side"] if self.dry else self.x.position(sym)[0]
        tps = self.tp_status(sym, tr)
        if amt == 0:
            self.finish(sym, "take profit" if tps == "FILLED" else "stop"); return
        step = max(self.f[sym]["step"], self.f[sym]["mkt_step"])
        if not self.dry and (abs(amt) > tr["qty"] + 1e-9 + step or amt * tr["side"] < 0 or self.tbo_filled(sym)):
            self.hand_over(sym, amt); return              # the trend bot's order filled: it gets the coin
        if tps == "PARTIALLY_FILLED" or (tps == "FILLED" and amt != 0):
            tr["qty"] = abs(amt)                          # (partly filled take-profit: the rest keeps its stop)
        if now >= tr["entry_ms"] - tr["entry_ms"] % 60_000 + int(self.p["hold_h"]) * HOUR:
            self.close(sym, f"time exit ({int(self.p['hold_h'])} h)"); return
        if not self.dry:
            if not tr.get("sl_id") or self.status(tr["sl_id"]) not in ("NEW", "TRIGGERING", "TRIGGERED", "FINISHED"):
                tr["sl_id"] = None
            if tps in ("CANCELED", "EXPIRED", "REJECTED", None):
                tr["tp_oid"] = None
            if not tr.get("sl_id") or not tr.get("tp_oid"):
                self.place_exits(sym)

    def tp_status(self, sym, tr):
        if self.dry or not tr.get("tp_oid"):
            return None
        try:
            return self.x.get_order(sym, tr["tp_oid"]).get("status")
        except BinanceError:
            return None

    def tp_executed(self, sym, tr):
        """Quantity the take-profit limit has filled (Binance executedQty, cumulative), None if unreadable."""
        try:
            return float(self.x.get_order(sym, tr["tp_oid"]).get("executedQty") or 0)
        except (BinanceError, TypeError, ValueError):
            return None

    def cancel_tp(self, sym, tr):
        if tr.get("tp_oid") and not self.dry:
            try:
                self.x.cancel_order(sym, tr["tp_oid"])
            except BinanceError:
                pass

    def hand_over(self, sym, amt):
        """The trend bot's entry filled on top of the sleeve's position: the sleeve's stop and take-profit go, and its own
        quantity is traded back at market (not reduce-only: if the trend bot went the other way, the position has already
        flipped and the sleeve's exit adds to the bot's side), so the bot is left with exactly its own order's size."""
        tr = self.st["trades"][sym]
        self.cancel(tr.get("sl_id")); tr["sl_id"] = None
        self.cancel_tp(sym, tr)                          # first, so it cannot fill any more
        q = tr["qty"]
        if tr.get("tp_oid") and not self.dry:            # what the take-profit filled before it was cancelled (seconds
            done = self.tp_executed(sym, tr)             # ago): that part is gone, so it is not traded back again
            if done is None:
                log.warning(f"{sym[:-4]}: take-profit fill unreadable: the sleeve's last known quantity {q:g} goes back")
            else:
                q = min(q, max(0.0, float(tr.get("tp_q") or q) - done))
            q = floor_step(q, max(self.f[sym]["step"], self.f[sym]["mkt_step"]))
        tr["tp_oid"] = None
        log.info(f"{sym[:-4]}: the trend bot's trade started on this coin (position now {amt:g}): the sleeve's {q:g} goes back at market")
        if q > 0:
            self.x.market(sym, "SELL" if tr["side"] == 1 else "BUY", fmt(q, self.f[sym]["step"]), client_id=self.cid("x", sym))
        self.finish(sym, "the trend bot took the coin", px=self.x.last_price(sym))

    def close(self, sym, why, qty=None):
        tr = self.st["trades"].get(sym)
        if tr is None:
            return
        if not self.dry:
            amt, _ = self.x.position(sym)
            q = abs(amt) if qty is None else min(abs(amt), qty)
            if q > 0:
                self.x.market(sym, "SELL" if tr["side"] == 1 else "BUY", fmt(q, self.f[sym]["step"]), reduce_only=True,
                              client_id=self.cid("x", sym))
        self.finish(sym, why)

    def finish(self, sym, why, px=None):
        tr = self.st["trades"].pop(sym, None)
        if tr is None:
            return
        self.cancel(tr.get("sl_id")); self.cancel_tp(sym, tr); self.save()
        px = px or self.exit_price(sym, tr)
        R = (px - tr["entry"]) * tr["side"] / tr["dist"] if tr["dist"] else 0.0
        log.info(f"VOLC CLOSED {sym[:-4]}: {why} | exit {self.P(sym, px)} | {R:+.2f}R before fees")
        self.tg(f"{'✅' if R > 0 else '❌'} <b>{sym[:-4]} VOLC closed · {notify.num(R, 2, sign=True)}R</b>\nExit {self.P(sym, px)} · {notify.esc(why)}")

    def exit_price(self, sym, tr):
        if not self.dry:
            try:
                q = v = 0.0
                xs = "SELL" if tr["side"] == 1 else "BUY"
                for t in self.x.user_trades(sym, limit=100, start_ms=tr["entry_ms"] - 60_000):
                    if t.get("side") == xs:
                        q += float(t["qty"]); v += float(t["qty"]) * float(t["price"])
                if q:
                    return v / q
            except Exception as e:
                log.info(f"trade history: {e}")
        return self.x.last_price(sym)

    def run(self):
        log.info(f"VOLC sleeve online{' (DRY RUN)' if self.dry else ''} · {' '.join(s[:-4] for s in self.coins)} · "
                 f"{self.cfg.get('share', 0.25):g} x the BTC risk per trade · {self.p}")
        while True:
            try:
                now = self.now()
                close_ms = (now // TF) * TF
                if not self.dry:
                    self.manage()                        # fills first (an order that filled just before a close)
                if self.st["last_candle"] < close_ms and now - close_ms >= 3000:
                    if not self.on_close(close_ms):
                        if now - close_ms > 15 * 60_000:
                            log.warning("4h data not served 15 min after the close: this close skipped")
                            self.st["last_candle"] = close_ms; self.save()
                if not self.dry:
                    self.manage()
            except BinanceError as e:
                log.error(f"Binance: {e}")
                if e.code in (-2014, -2015, -1022):
                    raise SystemExit("VOLC sleeve: API key / permission problem")
            except Exception as e:
                log.exception(f"error: {e}")
                time.sleep(10)
            time.sleep(float(self.cfg.get("poll_s", 5)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--testnet", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    notify.load_secrets_env(HERE)
    logdir = HERE / "logs"; logdir.mkdir(exist_ok=True)
    lg = logging.getLogger("volc"); lg.setLevel(logging.DEBUG); lg.propagate = False
    con = logging.StreamHandler(sys.stdout); con.setLevel(logging.INFO); con.setFormatter(logging.Formatter("%(message)s"))
    fh = logging.FileHandler(logdir / "VOLC.log", encoding="utf-8"); fh.setLevel(logging.DEBUG)
    ff = logging.Formatter("%(asctime)s UTC  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"); ff.converter = time.gmtime; fh.setFormatter(ff)
    for hd in (con, fh, notify.TelegramHandler("VOLC sleeve")):
        lg.addHandler(hd)
    while True:
        try:
            s = Sleeve(load_cfg(), testnet=a.testnet, dry=a.dry_run)
            break
        except BinanceError as e:
            if e.code in (-2014, -2015, -1022):
                raise SystemExit(f"VOLC sleeve: API key / permission problem: {e}")
            lg.warning(f"Binance error at start-up: {e}; retrying in 30 s")
        except Exception as e:
            lg.warning(f"cannot reach Binance ({type(e).__name__}); retrying in 30 s")
        time.sleep(30)
    s.run()


if __name__ == "__main__":
    main()
