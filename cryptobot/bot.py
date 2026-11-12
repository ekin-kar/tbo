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
  * v3.0: second profit lock (+8R -> stop +3.5R), stale stop (60 h after the fill, never at +1.5R and above -0.3R: stop
    to the entry) and a 16 h cooldown after a loss (no entry fills; the 4h order waits and is placed when it ends)
  * v3.1: failed-breakout stop tighten (from 8 h after the fill, at each hourly close: been +0.9R but never +1.5R and
    now below -0.2R -> stop to -0.5R; the cooldown follows whatever the result), BTC stop-out cascade (BTC's trade closed
    below -0.5R -> the other coins' open same-direction trades get their stop raised to -0.25R; read from BTC's state
    file) and the VOLC sleeve (volc.py) on the same account: while it holds this coin the bot places no order on it and
    leaves its position alone (state_volc.json)
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
from oi_history import OIHistory                       # noqa: E402
import notify                                          # noqa: E402

VERSION = "3.1"
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
        self.cfg, self.dry, self.testnet = cfg, dry, testnet
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
        self.oi_hist = OIHistory(self.x, self.sym, self.p.oi_low_days, self.dir, self.suffix) if self.p.oi_low_days > 0 else None

    # ── state ──
    def load_state(self):
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return dict(last_candle=0, entry_id=None, entry_side=0, sl_dist=0.0, sl_id=None, entry_ms=0,
                    best=0.0, be_done=False, lock_done=False, lock2_done=False, stale_done=False, cool_until=0)

    def reset_trade(self):
        """Forget the closed trade (the cooldown and the last_close record stay)."""
        self.st.update(sl_id=None, entry_side=0, entry_ms=0, best=0.0, be_done=False, lock_done=False, lock2_done=False,
                       stale_done=False, stale_checked=False, sl_trig=0.0, fb_done=False, fb_be=False, fb_from=0, fb_best=0.0,
                       fb_close=None, casc_done=False, casc_seen=0)

    def save(self):
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.st, indent=1))
        tmp.replace(self.state_path)

    # ── Telegram (trade events; warnings go through notify.TelegramHandler) ──
    @property
    def coin(self):
        return self.sym[:-4] if self.sym.endswith("USDT") else self.sym

    def tg(self, text):
        if notify.enabled():
            mode = " <i>(dry run)</i>" if self.dry else " <i>(testnet)</i>" if getattr(self, "testnet", False) else ""
            first, _, rest = text.partition("\n")
            notify.send(first + mode + ("\n" + rest if rest else ""))

    def cid(self, kind):
        """Order id, unique on the whole account: all coins' bots act in the same second at a 4h close, so the coin and
        the millisecond are part of it (Binance rejects a repeated id with -4116)."""
        return f"{PREFIX}_{kind}_{self.coin}_{int(time.time() * 1000)}"

    def P(self, x):
        return notify.px(x, self.f["tick"])

    def announce_open(self, amt, entry_px, stop):
        """The trade is open and its stop loss is on Binance."""
        self.st["announce"] = False
        if not notify.enabled():
            return
        try:
            side, q, d = (1 if amt > 0 else -1), abs(amt), self.st.get("sl_dist") or 0.0
            eq = self.equity()
            risk = q * abs(entry_px - stop)
            want = eq * self.risk_now(eq) * (self.short_mult if side < 0 else 1.0)
            lvl, e_ms = self.st.get("fill_lvl") or 0.0, self.st.get("entry_ms") or self.x.now_ms()
            rows = [f"{'📈' if side > 0 else '📉'} <b>{self.coin} {'long' if side > 0 else 'short'} opened</b>",
                    f"Entry <b>{self.P(entry_px)}</b>" + (f" · level {self.P(lvl)}, slippage {side * (entry_px / lvl - 1) * 100:+.3f}%" if lvl else ""),
                    f"Stop loss <b>{self.P(stop)}</b> ({notify.pct(-abs(entry_px - stop) / entry_px * 100)})"]
            rows.append("Take profit: none fixed, winners run up to the time exit")
            if self.p.be_R > 0:
                rows.append(f"At {self.P(entry_px + side * self.p.be_R * d)} (+{self.p.be_R:g}R) the stop moves to the entry")
            if self.p.lock_R > 0:
                rows.append(f"At {self.P(entry_px + side * self.p.lock_R * d)} (+{self.p.lock_R:g}R) the stop locks +{self.p.lock_to:g}R")
            if self.p.lock2_R > 0:
                rows.append(f"At {self.P(entry_px + side * self.p.lock2_R * d)} (+{self.p.lock2_R:g}R) the stop locks +{self.p.lock2_to:g}R")
            if self.p.stale_h > 0:
                rows.append(f"Not at +{self.p.be_R:g}R after {self.p.stale_h:g} h (and above {self.p.stale_thr:g}R): stop to the entry")
            if self.p.fb_h > 0:
                rows.append(f"From {self.p.fb_h:g} h: if it was +{self.p.fb_mfe:g}R but falls below {self.p.fb_thr:g}R (hourly close), stop to {self.p.fb_to:g}R")
            if self.p.casc_src:
                rows.append(f"If a {self.p.casc_src[:-4]} trade in the same direction is stopped out, stop to {self.p.casc_to:g}R")
            rows.append(f"Size {notify.esc(fmt(q, self.f['step']))} {self.coin} = {notify.usd(q * entry_px)} ({q * entry_px / eq:.1f}× the balance)")
            rows.append(f"Risk <b>{notify.usd(risk)}</b> = {risk / eq * 100:.2f}% of {notify.usd(eq)}")
            rows.append(f"Opened {notify.when(e_ms)} · time exit {notify.when(e_ms + self.p.max_hold_h * 3600_000)} ({notify.tz_label()})")
            pf = self.portfolio()
            if self.sym in pf.get("cap_exempt", []):
                rows.append("Open-risk cap: BTC is exempt (always full size)")
            elif self.cap_frac(eq) > 0:
                used, _ = self.open_risk()
                cap = self.cap_frac(eq) * eq
                rows.append(f"Open-risk cap: {notify.usd(used + risk)} of {notify.usd(cap)} in use ({self.cap_frac(eq) * 100:.2f}% of the balance)"
                            + (f" · trade shrunk to {risk / want * 100:.0f}% of its normal size" if risk < 0.95 * want and used + want > cap else ""))
            self.tg("\n".join(rows))
        except Exception as e:
            log.info(f"telegram (open): {e}")

    def report_close(self, why):
        """Result of the trade that just closed (before the state is reset)."""
        if not notify.enabled() or not self.st.get("entry_ms"):
            return
        try:
            e_ms, side, now = self.st["entry_ms"], self.st.get("entry_side") or 0, self.x.now_ms()
            entry, risk = self.st.get("fill_px") or 0.0, self.st.get("risk_usdt") or 0.0
            pnl = fees = funding = 0.0; xq = xv = 0.0
            try:
                for t in self.x.user_trades(self.sym, limit=200, start_ms=e_ms - 60_000):
                    if int(t["time"]) < e_ms - 60_000:
                        continue
                    pnl += float(t.get("realizedPnl", 0))
                    c = float(t.get("commission", 0))
                    fees += c if t.get("commissionAsset", "USDT") in ("USDT", "USDC") else c * self.x.last_price(t["commissionAsset"] + "USDT")
                    if float(t.get("realizedPnl", 0)) != 0 or (t.get("side") == ("SELL" if side > 0 else "BUY")):
                        xq += float(t["qty"]); xv += float(t["qty"]) * float(t["price"])
                    if not side:
                        side = 1 if t.get("side") == "BUY" else -1
                    if not entry and float(t.get("realizedPnl", 0)) == 0:
                        entry = float(t["price"])
                for r in self.x.income(e_ms, now):
                    if r.get("symbol") == self.sym and r.get("incomeType") == "FUNDING_FEE":
                        funding += float(r["income"])
            except Exception as e:
                log.info(f"telegram (trade history): {e}")
            est = not xq                                # no trade history: estimate from the price now
            exit_px = xv / xq if xq else self.x.last_price(self.sym)
            if est:
                q = self.st.get("fill_qty") or 0.0
                pnl = side * (exit_px - entry) * q
                fees = 0.0005 * q * (entry + exit_px)
            net = pnl - fees + funding
            R = net / risk if risk > 0 else 0.0
            icon = "✅" if R >= 0.2 else "❌" if R <= -0.2 else "⚪"
            rows = [f"{icon} <b>{self.coin} {'long' if side > 0 else 'short'} closed · {notify.num(R, 2, sign=True)}R · {notify.usd(net, sign=True)}</b>",
                    f"Exit {self.P(exit_px)} · {notify.esc(why)}",
                    f"Entry {self.P(entry)} · held {notify.held(now - e_ms)}",
                    f"Fees {notify.usd(fees)} · funding {notify.usd(funding, sign=True)}" + (" <i>(estimated: trade history not readable)</i>" if est else ""),
                    f"Balance {notify.usd(self.equity())}"]
            self.tg("\n".join(rows))
        except Exception as e:
            log.info(f"telegram (close): {e}")

    # ── helpers ──
    def equity(self):
        """The balance the risk is sized on: this account + the panic sleeve's sub-account when its key is in .env
        (one pool, as in the research; portfolio.json "pool_panic_balance": false sizes on this account alone)."""
        if self.dry:
            return float(self.cfg.get("dry_run_equity", 1000))
        return float(self.x.account()["totalMarginBalance"]) - sum(self.manual_positions().values()) + self.panic_balance()

    def bot_symbols(self):
        """The coins the bots on this account trade (config_*.json next to this one)."""
        if getattr(self, "_bot_syms", None) is None:
            syms = {self.sym}
            for f in self.dir.glob("config_*.json"):
                try:
                    syms.add(json.loads(f.read_text())["strategy"]["symbol"])
                except (OSError, ValueError, KeyError):
                    pass
            self._bot_syms = syms
        return self._bot_syms

    def manual_positions(self):
        """The user's own trades: ISOLATED-margin positions on coins no bot trades, {symbol: isolated margin + PnL}. They
        are left out of the balance the bot sizes on and out of the open-risk cap (the bots trade cross margin)."""
        fn = getattr(self.x, "isolated_positions", None)
        if fn is None:
            return {}
        now = time.time()
        if now - getattr(self, "_man_t", 0) < 10:
            return self._man
        try:
            iso = fn()
            self._man = {s: v for s, v in iso.items() if s not in self.bot_symbols()}
        except Exception as e:
            log.info(f"isolated positions unreadable ({e}): manual trades counted this time")
            self._man = {}
        self._man_t = now
        return self._man

    def panic_balance(self):
        if not (os.environ.get("PANIC_API_KEY") and os.environ.get("PANIC_API_SECRET")) or not self.portfolio().get("pool_panic_balance", True):
            return 0.0
        now = time.time()
        if now - getattr(self, "_pb_t", 0) < 60:
            return self._pb
        try:
            if not hasattr(self, "_px"):
                self._px = Futures(os.environ["PANIC_API_KEY"], os.environ["PANIC_API_SECRET"], testnet=self.testnet)
            self._pb = float(self._px.account()["totalMarginBalance"]); self._pb_t = now
        except Exception as e:
            log.warning(f"panic sub-account balance unreadable ({e}): sizing on the last known value")
            self._pb = getattr(self, "_pb", 0.0); self._pb_t = now
        return self._pb

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
            log.debug(f"cancel {algo_id}: {e.msg} (already gone)")

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
                log.debug(f"size {qty} below the exchange minimum (equity {eq:.2f}): no order")
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

    # ── v3.1: the VOLC sleeve on the same account (volc.py, state_volc.json) ──
    def volc_state(self):
        try:
            return json.loads((self.dir / f"state_volc{self.suffix}.json").read_text())
        except (OSError, ValueError):
            return {}

    def volc_fill(self, sym=None):
        """True if the position on this coin is the VOLC sleeve's: its trade is recorded, or one of its entry orders on
        this coin has just triggered (volc.py records the trade within seconds)."""
        sym = sym or self.sym
        vs = self.volc_state()
        if sym in vs.get("trades", {}):
            return True
        if self.st.get("entry_id") and not self.dry:      # both orders triggered in the same moment: the trend bot keeps the
            try:                                          # coin and the sleeve closes its own part (volc.py)
                if self.x.algo_order(algo_id=self.st["entry_id"]).get("algoStatus") in ("TRIGGERED", "FINISHED"):
                    return False
            except BinanceError:
                pass
        for aid in (vs.get("orders", {}).get(sym) or {}).values():
            if not aid or self.dry:
                continue
            try:
                if self.x.algo_order(algo_id=aid).get("algoStatus") in ("TRIGGERED", "FINISHED"):
                    return True
            except BinanceError:
                pass
        return False

    def drop_entry_order(self):
        """Cancel this bot's waiting entry order (the coin is the VOLC sleeve's for now)."""
        if self.st.get("entry_id"):
            self.cancel(self.st["entry_id"])
        self.st.update(entry_id=None, entry_trig=0.0, entry_qty=0.0)
        self.st.pop("cool_order", None)

    def record_close(self, exit_px, exit_ms):
        """v3.1: the closed trade's R (net of costs, as the research) for the cascade of the other coins' bots."""
        side, entry, dist = self.st.get("entry_side") or 0, self.st.get("fill_px") or 0.0, self.st.get("sl_dist") or 0.0
        if not (side and entry and dist and exit_px):
            return
        fee = float(self.cfg.get("fee_side", 0.0006 if self.sym in ("BTCUSDT", "ETHUSDT") else 0.0008))
        hours = max(0.0, (exit_ms - (self.st.get("entry_ms") or exit_ms)) / 3_600_000)
        R = S.net_R(side, entry, exit_px, dist, hours, fee)
        self.st["last_close"] = dict(ms=int(exit_ms), side=side, R=round(R, 4))

    def open_risk(self, filled_before=None):
        """USDT lost if every OTHER open position not yet at breakeven hit its stop now (every symbol on the account).
        filled_before (ms): count only positions that filled before it (the first to fill keeps its size); an exempt
        coin (BTC) also counts when it filled in the same minute (BTC goes first, as in the research simulation)."""
        pos = self.x.positions()
        exempt = set(self.portfolio().get("cap_exempt", []))
        volc = set(self.volc_state().get("trades", {}))
        pos.pop(self.sym, None)
        for s in self.manual_positions():              # the user's own isolated trades: not in the cap
            pos.pop(s, None)
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
            if st is not None and st.get("manual"):     # the user's own trade on a bot coin: not in the cap
                continue
            if (st is not None and st.get("volc_hold")) or sym in volc:   # the VOLC sleeve's trade: outside the cap
                continue
            if filled_before and st is not None:
                e_ms = st.get("entry_ms") or 0
                if e_ms == 0 and st.get("entry_side"):
                    continue                            # its bot has not seen the fill yet (seconds ago): checked again next poll
                if sym in exempt:                       # BTC: counts if it filled in the same minute as ours or before
                    if e_ms // 60_000 > filled_before // 60_000:
                        continue
                elif e_ms > filled_before:              # others: only if they filled before ours
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
    def start_cooldown(self, exit_px, exit_ms):
        """v3.0: a trade that closed below cool_R (price R) starts cool_h hours without entry fills on this coin."""
        side, entry, dist = self.st.get("entry_side") or 0, self.st.get("fill_px") or 0.0, self.st.get("sl_dist") or 0.0
        if not (side and entry and S.cooldown_after(self.p, side, entry, exit_px, dist, fb_done=self.st.get("fb_done"))):
            return
        until = exit_ms - exit_ms % 60_000 + int(round(self.p.cool_h * 60)) * 60_000
        self.st["cool_until"] = max(int(self.st.get("cool_until") or 0), until)
        why = "after the failed-breakout stop" if self.st.get("fb_done") and side * (exit_px - entry) / dist >= self.p.cool_R else f"(< {self.p.cool_R:g}R)"
        log.info(f"COOLDOWN: closed at {side * (exit_px - entry) / dist:+.2f}R {why}: no new {self.coin} entry until {utc(until)} UTC")
        self.tg(f"⏸ <b>{self.coin} cooldown</b>\nAfter the loss no new {self.coin} trade until {notify.when(until)}"
                f" ({self.p.cool_h:g} h, {notify.tz_label()})")

    def cooling(self, now=None):
        return (now or self.x.now_ms()) < int(self.st.get("cool_until") or 0)

    def close_position(self, amt, why, tg_why=None):
        side = "SELL" if amt > 0 else "BUY"
        try:
            exit_px, exit_ms = self.x.last_price(self.sym), self.x.now_ms()
        except Exception:
            exit_px, exit_ms = 0.0, self.x.now_ms()
        log.info(f"EXIT ({tg_why or why}): closing {abs(amt):g} {self.coin} at market")
        if not self.dry:
            self.x.market(self.sym, side, fmt(abs(amt), self.f["step"]), reduce_only=True,
                          client_id=self.cid("x"))
            if notify.enabled():
                time.sleep(1.5)                         # let the fill reach the trade history
        self.report_close(tg_why or why)
        self.cancel(self.st.get("sl_id"))
        if exit_px:
            self.record_close(exit_px, exit_ms)
            self.start_cooldown(exit_px, exit_ms)
        self.reset_trade()
        self.save()

    def place_sl(self, amt, entry_px):
        side = 1 if amt > 0 else -1
        dist = self.st.get("sl_dist") or 0.0
        if dist <= 0:                                   # unknown (manual / lost state): use the current ATR
            k4, _ = self.candles()
            dist = self.p.sl_atr * S.atr([k[2] for k in k4], [k[3] for k in k4], [k[4] for k in k4], self.p.atr_n)[-1]
            self.st["sl_dist"] = dist
        trig = S.stop_level(self.p, side, entry_px, dist, be_done=self.st.get("be_done"), lock_done=self.st.get("lock_done"),
                            lock2_done=self.st.get("lock2_done"), stale_done=self.st.get("stale_done"),
                            fb_done=self.st.get("fb_done"), casc_done=self.st.get("casc_done"))   # most favourable stage
        trig = floor_step(trig, self.f["tick"]) if side == 1 else ceil_step(trig, self.f["tick"])
        self.st["sl_trig"] = trig
        log.info(f"STOP LOSS now at {self.P(trig)} (entry {self.P(entry_px)}, size {abs(amt):g} {self.coin})")
        if self.dry:
            return trig
        last = self.x.last_price(self.sym)
        if (side == 1 and last <= trig) or (side == -1 and last >= trig):
            log.warning(f"price {last} already beyond the stop {fmt(trig, self.f['tick'])}: closing at market")
            self.close_position(amt, "SL (price already past the stop)", "stop loss (price was already past it)")
            return None
        try:
            r = self.x.stop_market(self.sym, "SELL" if side == 1 else "BUY", fmt(trig, self.f["tick"]),
                                   close_position=True, client_id=self.cid("sl"))
            self.st["sl_id"] = r["algoId"]
        except BinanceError as e:
            if e.code == -2021:                         # would trigger at once: price is already past the stop
                log.warning("price already beyond the stop: closing at market")
                self.close_position(amt, "SL (gap)", "stop loss (price gapped past it)")
                return None
            raise
        self.save()
        return trig

    def place_entry(self, side, trig, qty):
        """Stop-market entry at trig; at market if the price is already beyond it (the backtest fills at the open)."""
        q, bs = fmt(qty, self.f["step"]), ("BUY" if side == 1 else "SELL")
        self.st.update(entry_trig=trig, entry_qty=qty)
        last = self.x.last_price(self.sym)
        if (side == 1 and last >= trig) or (side == -1 and last <= trig):
            log.info(f"price {last} already beyond the level: market entry (as the backtest fills at the open)")
            self.x.market(self.sym, bs, q, client_id=self.cid("mk"))
            return True
        try:
            r = self.x.stop_market(self.sym, bs, fmt(trig, self.f["tick"]), qty=q, client_id=self.cid("in"))
            self.st["entry_id"] = r["algoId"]
        except BinanceError as e:
            if e.code != -2021:
                raise
            log.info("price already beyond the level: market entry (as the backtest fills at the open)")
            self.x.market(self.sym, bs, q, client_id=self.cid("mk"))
            return True
        return False

    def on_candle_close(self, open_ms):
        k4, k1 = self.candles()
        if not k4 or k4[-1][0] != open_ms:
            log.debug("latest closed 4h candle not served yet; retrying")
            return False
        h, l, c = [k[2] for k in k4], [k[3] for k in k4], [k[4] for k in k4]
        weekday = datetime.fromtimestamp((open_ms + self.p.tf_min * 60_000) / 1000, timezone.utc).weekday()
        dec = S.decide(self.p, h, l, c, [k[4] for k in k1], weekday, [k[2] for k in k1], [k[3] for k in k1])
        amt, entry_px = self.x.position(self.sym)
        if amt != 0 and not self.st.get("entry_ms") and not self.st.get("manual") and not self.st.get("volc_hold") and not self.dry:
            # a fill in the last seconds before this close (or found after a restart): adopt it (stop loss!) while the entry
            # order is still on record; clearing the order first made the bot take its own trade for a manual one
            self.check_position()
            amt, entry_px = self.x.position(self.sym)
        log.debug(f"4h close {utc(open_ms + 4 * 3600_000)}: close {self.P(c[-1])}  ATR {self.P(dec.atr)}  trend "
                 f"{'up' if dec.trend > 0 else 'down' if dec.trend < 0 else 'none'}"
                 f"{'  (weekend: no new orders)' if self.p.no_weekend and weekday >= 5 else ''}  position {amt}")
        close_ms = open_ms + self.p.tf_min * 60_000
        status = None                                   # the line for the 4h-check message
        # 1. trail exit
        if not self.st.get("manual") and not self.st.get("volc_hold") and ((amt > 0 and dec.exit_long) or (amt < 0 and dec.exit_short)):
            self.close_position(amt, "trail", "trail exit")
            amt = 0.0
        # 2. the previous entry order expires at this close
        if self.st.get("entry_id"):
            self.cancel(self.st["entry_id"])
            self.st["entry_id"] = None
        self.st.update(entry_trig=0.0, entry_qty=0.0)    # (also ends an entry waiting for room under the cap)
        self.st.pop("cool_order", None)                 # (and an order waiting for the cooldown to end)
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
                log.debug(f"open interest {chg * 100:+.1f}% over {self.p.oi_lookback_h} h"
                         + (f" (<= {self.p.oi_min_chg * 100:.0f}%: no new entry order)" if blocked else ""))
        # open interest near its low of the last oi_low_days days (v2.8): no new order
        low_blocked = False
        if self.oi_hist is not None:
            try:
                self.oi_hist.update(budget_s=20)        # (the archive part is fetched at start-up)
                rank = S.oi_rank(self.oi_hist.series(), close_ms, self.p.oi_low_days * 24, self.p.oi_low_days * 12)
            except Exception as e:                     # never let missing data stop the bot: no filter then
                rank = None
                log.warning(f"open interest history unavailable ({e}): OI-low filter not applied this candle")
            if rank is None:
                log.debug(f"OI-low filter: not enough history yet ({self.oi_hist.hours()} of {self.p.oi_low_days * 12} hours): not applied")
            else:
                low_blocked = S.oi_low_blocks(self.p, rank)
                log.debug(f"open interest ranks {rank * 100:.0f}% of its last {self.p.oi_low_days} days"
                          + (f" (< {self.p.oi_low_rank * 100:.0f}%: no new entry order)" if low_blocked else ""))
        # 3. new entry order while flat (re-read: the old entry order may have filled in the meantime)
        if amt == 0 and not self.dry:
            amt, _ = self.x.position(self.sym)
            if amt != 0:
                log.info(f"the previous entry order filled just now ({amt}): no new order")
        risk_open = 0.0
        if amt != 0 and self.st.get("volc_hold"):
            status = "no order · the VOLC sleeve holds this coin"
        elif amt != 0 and self.st.get("manual"):
            status = "no order · your own position on this coin (left alone)"
        elif amt != 0:
            side_ = 1 if amt > 0 else -1
            ep = self.st.get("fill_px") or entry_px
            d_ = self.st.get("sl_dist") or 0.0
            r_now = side_ * (c[-1] - ep) / d_ if d_ else 0.0
            stage = ("profit locked at +%gR" % self.p.lock2_to if self.st.get("lock2_done") else "profit locked at +%gR" % self.p.lock_to if self.st.get("lock_done")
                     else "stop at breakeven" if self.st.get("be_done") or self.st.get("stale_done") else "stop " + self.P(ep - side_ * d_))
            risk_open = 0.0 if self.st.get("be_done") or self.st.get("stale_done") else abs(amt) * d_
            status = f"● in a {'long' if side_ > 0 else 'short'} since {notify.when(self.st.get('entry_ms') or self.x.now_ms())} · {notify.num(r_now, 1, sign=True)}R now · {stage}"
        elif self.paused():
            status = "paused (PAUSE file): no new orders"
        elif self.p.no_weekend and weekday >= 5:
            status = "weekend: no new orders"
        elif blocked:
            status = f"no order · open interest {notify.pct(chg * 100, sign=True, dec=1)} in {self.p.oi_lookback_h} h (filter)"
        elif low_blocked:
            status = f"no order · open interest near its {self.p.oi_low_days}-day low (filter)"
        elif dec.trend == 0:
            status = "no order · no clear daily trend"
        elif dec.long_trigger is None and dec.short_trigger is None:
            status = "no order · price stretched far from the daily trend line"
        if self.paused():
            log.info("PAUSE file present: no new entry orders (open positions are still managed)")
        cross_ok = True
        if amt == 0 and not self.paused() and not self.dry:
            cross_ok = self.ensure_cross()
            if not cross_ok:
                status = f"no order · {self.coin} is on isolated margin and could not be switched back to cross"
        if amt == 0 and not self.paused() and cross_ok:
            self.reset_trade()
            for side, trig in ((1, dec.long_trigger), (-1, dec.short_trigger)):
                if trig is None or blocked or low_blocked:
                    continue
                trig = ceil_step(trig, self.f["tick"]) if side == 1 else floor_step(trig, self.f["tick"])
                if not (trig > 0 and dec.sl_dist > 0 and math.isfinite(trig)):
                    log.warning(f"invalid level {trig} / stop distance {dec.sl_dist}: no order")
                    continue
                if self.cooling():                      # v3.0 cooldown after a loss: the order waits until it ends
                    cu = int(self.st["cool_until"])
                    self.st["cool_order"] = dict(side=side, trig=trig, sl_dist=dec.sl_dist, expire=close_ms + self.p.tf_min * 60_000)
                    log.info(f"cooldown until {utc(cu)} UTC: {'BUY' if side == 1 else 'SELL'} stop {fmt(trig, self.f['tick'])} "
                             f"placed then if this candle's order is still valid")
                    status = (f"{'▲ buy' if side == 1 else '▼ sell'} stop {self.P(trig)} waits: cooldown after a loss until "
                              f"{notify.when(cu)}" + (" (after this candle: no order)" if cu >= self.st["cool_order"]["expire"] else ""))
                    break
                try:
                    qty, note, no_room = self.size(dec.sl_dist, trig, side)
                except Exception as e:                  # cap on but the account cannot be read: add no risk blind
                    log.warning(f"open risk unavailable ({e}): no new entry order this candle")
                    break
                if note:
                    log.debug(note)
                if no_room:                             # the cap is full: wait, re-checked every minute until the next close
                    log.info(f"no entry order for now ({'BUY' if side == 1 else 'SELL'} stop {fmt(trig, self.f['tick'])}): "
                             f"placed if room opens before the price gets there, until the next 4h close")
                    self.st.update(sl_dist=dec.sl_dist, entry_side=side, entry_trig=trig, entry_qty=0.0,
                                   entry_from=open_ms + self.p.tf_min * 60_000)
                    status = (f"{'▲ buy' if side == 1 else '▼ sell'} stop {self.P(trig)} held back: the open-risk cap is full "
                              f"(placed if room opens before the next check)")
                    break
                if qty <= 0:
                    status = "no order · size below Binance's minimum"
                    continue
                log.debug(f"ENTRY ORDER {'BUY' if side == 1 else 'SELL'} {fmt(qty, self.f['step'])} stop "
                         f"{fmt(trig, self.f['tick'])}  (SL dist {dec.sl_dist:.2f} = {dec.sl_dist / trig * 100:.2f}%, "
                         f"risk {qty * dec.sl_dist:.2f} USDT, valid until the next 4h close)")
                self.st.update(sl_dist=dec.sl_dist, entry_side=side, entry_from=open_ms + self.p.tf_min * 60_000)
                eq_ = self.equity()
                want_ = eq_ * self.risk_now(eq_) * (self.short_mult if side < 0 else 1.0)
                status = (f"{'▲ buy' if side == 1 else '▼ sell'} stop {self.P(trig)} · stop loss {self.P(trig - side * dec.sl_dist)} "
                          f"({dec.sl_dist / trig * 100:.2f}%) · risk {notify.usd(qty * dec.sl_dist)}"
                          + (f" (shrunk to {qty * dec.sl_dist / want_ * 100:.0f}% by the open-risk cap)" if "shrunk" in (note or "") else ""))
                if self.dry:
                    break
                if self.place_entry(side, trig, qty):
                    status = f"{'▲ bought' if side == 1 else '▼ sold'} at market: price was already past {self.P(trig)}"
                break                                   # one entry order at a time (sides="both": trend picks one)
        self.st["last_candle"] = open_ms
        self.st["check"] = dict(t=close_ms, line=status or "no order", risk=round(risk_open, 2))
        log.debug(f"4h check: {status or 'no order'}")
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

    def ensure_cross(self):
        """Before a new entry order: the bots trade cross margin at their own leverage. After a manual isolated trade the
        coin stays isolated on Binance: switch it back (only possible with no position and no open orders on it)."""
        try:
            sc = self.x.symbol_config(self.sym)
        except Exception:
            return True                                 # unreadable: carry on as before
        if str(sc.get("marginType", "")).upper() not in ("ISOLATED",):
            return True
        try:
            self.x.set_margin_type(self.sym, "CROSSED")
            self.x.set_leverage(self.sym, int(self.cfg.get("exchange_leverage", max(1, math.ceil(self.max_lev)))))
            log.info(f"{self.coin} switched back from isolated to cross margin at {self.cfg.get('exchange_leverage')}x")
            return True
        except BinanceError as e:
            log.warning(f"{self.coin} is on isolated margin and could not be switched back to cross ({e}): no entry order")
            return False

    def manual_trade(self, amt):
        """True while the position on this coin is the user's own: one that appeared with no entry order of the bot's
        pending (e.g. a manual trade during the weekend pause). The bot leaves it alone (no stop, no cap trim, no exits)
        and places no new orders on this coin until it is closed. A position adopted that way by an older version
        (no entry level recorded) is released: the bot's stop on it is cancelled."""
        if self.st.get("manual"):
            return True
        if self.st.get("entry_ms"):
            if self.st.get("fill_lvl"):
                return False                            # the bot's own trade
            self.cancel(self.st.get("sl_id"))
            self.reset_trade()
            why = "adopted earlier without an entry order of the bot's: released, the bot's stop on it cancelled"
        elif self.st.get("entry_id") or self.st.get("entry_trig"):
            return False                                # the bot's entry order filled
        else:
            why = "no entry order of the bot's was pending"
        self.st["manual"] = True; self.save()
        log.info(f"{self.coin} position {amt:g} is not the bot's ({why}): left alone, no new orders on {self.coin} until it is closed")
        self.tg(f"🖐 <b>{self.coin}: your own position, left alone</b>\n{notify.esc(why)}. The bot places no orders on "
                f"{self.coin} until it is closed.")
        return True

    def check_position(self):
        """Every poll: protect a new fill, time exit, clean up after a stop-out."""
        amt, entry_px = self.x.position(self.sym)
        now = self.x.now_ms()
        if amt == 0 and self.st.get("volc_hold"):
            self.st["volc_hold"] = False; self.save()   # the VOLC trade is over: orders again from the next 4h close
            return
        if amt != 0 and (self.st.get("volc_hold") or (not self.st.get("entry_ms") and not self.st.get("manual") and self.volc_fill())):
            if not self.st.get("volc_hold"):
                log.info(f"{self.coin}: the VOLC sleeve's trade ({amt:g}): no orders on {self.coin} until it is closed")
                self.st["volc_hold"] = True
            if self.st.get("entry_id") or self.st.get("entry_trig") or self.st.get("cool_order"):
                self.drop_entry_order()
            self.save()
            return
        if amt != 0 and self.manual_trade(amt):
            return
        if amt == 0 and self.st.get("manual"):
            self.st["manual"] = False; self.save()     # the user's own trade is closed: the bot trades this coin again
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
                slip = f", level {self.P(lvl)}, slippage {side * (entry_px / lvl - 1) * 100:+.3f}%" if lvl else ""
                risk = abs(amt) * (self.st.get("sl_dist") or 0)
                self.st.update(entry_id=None, entry_trig=0.0, entry_qty=0.0)   # the entry order has triggered
                self.st["cap_check"] = self.cap_frac() > 0
                self.st.update(fill_px=entry_px, fill_lvl=lvl, fill_qty=abs(amt), risk_usdt=risk, entry_side=side, announce=True,
                               fb_from=fill_ms - fill_ms % 60_000 + 60_000, casc_seen=fill_ms - fill_ms % 60_000 - 1)
                log.info(f"FILLED {'long' if side > 0 else 'short'} {abs(amt):g} {self.coin} @ {self.P(entry_px)}{slip}, risk {risk:.2f} USDT")
                self.save()
            if not self.sl_alive():
                stop = self.place_sl(amt, entry_px)
                if stop and self.st.get("announce"):
                    self.announce_open(amt, entry_px, stop)
                    self.save()
            if self.st.get("cap_check") and self.st.get("entry_ms"):
                self.trim_to_cap(amt)
                amt, entry_px = self.x.position(self.sym)
            if self.st.get("entry_ms"):                 # (place_sl may have closed it: price already past the stop)
                self.check_breakeven(amt, entry_px)
            if self.st.get("entry_ms"):
                self.check_fb(amt, entry_px)
            if self.st.get("entry_ms"):
                self.check_cascade(amt)
            if self.st.get("entry_ms") and self.p.stale_h > 0 and not self.st.get("stale_checked"):
                at = self.st["entry_ms"] - self.st["entry_ms"] % 60_000 + int(round(self.p.stale_h * 60)) * 60_000
                if now >= at:
                    self.check_stale(amt, entry_px)
            if self.st.get("entry_ms") and now - self.st["entry_ms"] >= self.p.max_hold_h * 3600_000:
                self.close_position(amt, f"time ({self.p.max_hold_h:.0f}h)", f"time exit after {self.p.max_hold_h / 24:g} days")
        elif self.st.get("entry_ms"):
            why = "closed outside the bot (by hand?)"
            try:
                if self.st.get("sl_id") and self.x.algo_order(algo_id=self.st["sl_id"]).get("algoStatus") in ("TRIGGERED", "FINISHED"):
                    why = ("profit-lock stop (+%gR)" % self.p.lock2_to if self.st.get("lock2_done") else
                           "profit-lock stop (+%gR)" % self.p.lock_to if self.st.get("lock_done") else
                           "breakeven stop" if self.st.get("be_done") else "stale stop (at the entry)" if self.st.get("stale_done") else
                           "cascade stop (%gR)" % self.p.casc_to if self.st.get("casc_done") else
                           "failed-breakout stop (%gR)" % self.p.fb_to if self.st.get("fb_done") else "stop loss")
            except Exception:
                why = "stop loss or closed by hand"
            log.info(f"position closed: {why}")
            self.report_close(why)
            self.cancel(self.st.get("sl_id"))
            exit_ms = now - 60_000                      # the stop filled since the last poll (exact time if Binance says)
            try:
                tt = int(self.x.algo_order(algo_id=self.st["sl_id"]).get("triggerTime") or 0) if self.st.get("sl_id") else 0
                if 0 < tt <= now:
                    exit_ms = tt
            except Exception:
                pass
            exit_px = self.st.get("sl_trig") or self.x.last_price(self.sym)
            self.record_close(exit_px, exit_ms)
            self.start_cooldown(exit_px, exit_ms)
            self.reset_trade()
            self.save()
        elif self.st.get("cool_order"):
            self.release_cooldown(now)
        elif self.st.get("entry_trig") and now - self.st.get("cap_seen_ms", 0) >= 60_000:
            self.st["cap_seen_ms"] = now
            self.resize_entry()

    def release_cooldown(self, now):
        """v3.0: the cooldown has ended inside the candle whose order was held back: place it now (at market if the price
        is already past the level, as the backtest fills a waiting stop order at that minute's open)."""
        co = self.st["cool_order"]
        if now >= co["expire"]:
            self.st.pop("cool_order", None); self.save()
            return
        if self.cooling(now) or self.paused():
            return
        self.st.pop("cool_order", None)
        side, trig, dist = co["side"], co["trig"], co["sl_dist"]
        try:
            qty, note, no_room = self.size(dist, trig, side)
        except Exception as e:
            log.warning(f"open risk unavailable ({e}): no entry order after the cooldown this candle")
            self.save()
            return
        self.st.update(sl_dist=dist, entry_side=side, entry_from=now)
        if no_room:
            log.info(f"cooldown over, but the open-risk cap is full: {'BUY' if side == 1 else 'SELL'} stop {fmt(trig, self.f['tick'])} waits for room")
            self.st.update(entry_trig=trig, entry_qty=0.0); self.save()
            return
        if qty <= 0:
            self.save()
            return
        log.info(f"COOLDOWN over: entry order {'BUY' if side == 1 else 'SELL'} {fmt(qty, self.f['step'])} stop {fmt(trig, self.f['tick'])}"
                 + (f" ({note})" if note else ""))
        if not self.dry:
            self.place_entry(side, trig, qty)
        self.save()

    def check_stale(self, amt, entry_px):
        """v3.0, once at stale_h after the fill: a trade that never reached +be_R and is above stale_thr R gets its stop at
        entry + stale_to x dist (closed at market if the price is already below it)."""
        self.st["stale_checked"] = True                  # (checked once, at that minute, as the backtest)
        side, dist = (1 if amt > 0 else -1), self.st.get("sl_dist") or 0.0
        px = self.x.last_price(self.sym)
        if not S.stale_moves(self.p, side, entry_px, dist, px, self.st.get("be_done")):
            self.save()
            return
        self.st["stale_done"] = True
        log.info(f"STALE STOP: {self.p.stale_h:g} h without +{self.p.be_R:g}R ({side * (px - entry_px) / dist:+.2f}R now): stop moves to the entry")
        self.cancel(self.st.get("sl_id")); self.st["sl_id"] = None
        stop = self.place_sl(amt, entry_px)
        if stop:
            self.tg(f"⏳ <b>{self.coin} stale trade</b>\n{self.p.stale_h:g} h without reaching +{self.p.be_R:g}R: stop moved to the entry {self.P(stop)}")
        self.save()

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
        """For 2 minutes after a fill: if coins that filled earlier (or BTC in the same minute) left less room than this
        order was sized for, cut the position to fit, or close it if less than cap_min_fraction would remain."""
        try:
            eq = self.equity()
            want = abs(amt) * self.st["sl_dist"]
            allowed, note = self.capped(eq, want, filled_before=self.st["entry_ms"])
        except Exception as e:
            log.warning(f"open risk unavailable ({e}): cap check after the fill retried next poll")
            return
        if self.x.now_ms() - self.st["entry_ms"] > 120_000:
            self.st["cap_check"] = False
            self.save()
        if allowed >= want * 0.95:                      # (5% slack: equity moves a little between order and fill)
            return
        step = max(self.f["step"], self.f["mkt_step"])
        keep = floor_step(allowed / self.st["sl_dist"], step)
        px = self.x.last_price(self.sym)
        if allowed <= 0 or keep < self.f["min_qty"] or keep * px < self.f["min_notional"]:
            log.info(f"CAP after the fill: {note}")
            self.close_position(amt, "open-risk cap (other coins filled first)", "closed by the open-risk cap: other coins filled first")
            return
        cut = floor_step(abs(amt) - keep, step)
        if cut <= 0:
            return
        log.info(f"CAP after the fill: {note}: position cut by {fmt(cut, self.f['step'])} to {fmt(keep, self.f['step'])}")
        self.st["risk_usdt"] = keep * self.st["sl_dist"]
        self.tg(f"✂️ <b>{self.coin} trade cut by the open-risk cap</b>\nOther coins filled first: "
                f"{fmt(abs(amt), self.f['step'])} → {fmt(keep, self.f['step'])} {self.coin}, "
                f"risk {notify.usd(want)} → {notify.usd(keep * self.st['sl_dist'])}")
        self.x.market(self.sym, "SELL" if amt > 0 else "BUY", fmt(cut, self.f["step"]), reduce_only=True,
                      client_id=self.cid("cap"))

    def check_fb(self, amt, entry_px):
        """v3.1 failed-breakout stop tighten, replayed on CLOSED 1m candles exactly as the research engine: at the open of
        each minute on the hour, from fb_h hours after the fill minute, the best excursion so far (1m highs / lows from the
        minute after the fill) and the previous 1m close decide; disabled once the trade has been +be_R."""
        if self.p.fb_h <= 0 or self.st.get("fb_done") or self.st.get("fb_be") or not self.st.get("sl_dist"):
            return
        side, dist = (1 if amt > 0 else -1), self.st["sl_dist"]
        entry = self.st.get("fill_px") or entry_px
        e_min = self.st["entry_ms"] - self.st["entry_ms"] % 60_000
        first = e_min + int(round(self.p.fb_h * 60)) * 60_000
        now = self.x.now_ms()
        if now < first - 6 * 3600_000:                  # nothing to decide for hours: read the candles later
            return
        start = self.st.get("fb_from") or e_min + 60_000
        best = self.st.get("fb_best") or entry
        last = self.st.get("fb_close")
        fired = False
        bars = [k for k in self.x.klines(self.sym, "1m", 1000, start_ms=start) if k[0] >= start and k[0] + 60_000 <= now]
        nxt = start
        for k in bars:
            t = k[0]
            if t % 3600_000 == 0 and t >= first and last is not None and S.fb_fires(self.p, side, entry, dist, best, last):
                fired = True; break
            best = max(best, k[2]) if side == 1 else min(best, k[3])
            last = k[4]; nxt = t + 60_000
            if side * (best - entry) >= self.p.be_R * dist:
                self.st["fb_be"] = True; break
        if not fired and not self.st.get("fb_be") and nxt % 3600_000 == 0 and first <= nxt <= now and last is not None:
            fired = S.fb_fires(self.p, side, entry, dist, best, last)       # the hour that has just begun
        self.st.update(fb_from=nxt, fb_best=best, fb_close=last)
        if not fired:
            self.save()
            return
        self.st["fb_done"] = True
        log.info(f"FAILED BREAKOUT: was +{side * (best - entry) / dist:.2f}R, hourly close {side * (last - entry) / dist:+.2f}R: "
                 f"stop moves to {self.p.fb_to:g}R")
        self.cancel(self.st.get("sl_id")); self.st["sl_id"] = None
        stop = self.place_sl(amt, entry_px)
        if stop:
            self.tg(f"✂️ <b>{self.coin} failed breakout</b>\nIt was +{side * (best - entry) / dist:.2f}R and is back at "
                    f"{side * (last - entry) / dist:+.2f}R: stop moved to {self.P(stop)} ({self.p.fb_to:g}R)")
        self.save()

    def check_cascade(self, amt):
        """v3.1 cascade: BTC's bot records each closed trade (last_close in its state file); a stop-out below casc_R in this
        trade's direction, at or after this trade's fill minute, raises this trade's stop to entry + casc_to x dist."""
        src = self.p.casc_src
        if not src or src == self.sym or self.st.get("casc_done"):
            return
        lc = (self.coin_state(src) or {}).get("last_close")
        if not lc or int(lc.get("ms", 0)) <= int(self.st.get("casc_seen") or 0):
            return
        self.st["casc_seen"] = int(lc["ms"])
        side = 1 if amt > 0 else -1
        e_min = self.st["entry_ms"] - self.st["entry_ms"] % 60_000
        if float(lc.get("R", 0)) >= self.p.casc_R or int(lc.get("side", 0)) != side or e_min > int(lc["ms"]):
            self.save()
            return
        self.st["casc_done"] = True
        log.info(f"CASCADE: {src[:-4]} {'long' if side > 0 else 'short'} stopped out ({float(lc['R']):+.2f}R): stop moves to {self.p.casc_to:g}R")
        if S.stop_level(self.p, side, self.st.get("fill_px") or 0.0, self.st["sl_dist"], **{k: self.st.get(k) for k in (
                "be_done", "lock_done", "lock2_done", "stale_done", "fb_done")}) == S.stop_level(
                self.p, side, self.st.get("fill_px") or 0.0, self.st["sl_dist"], casc_done=True, **{k: self.st.get(k) for k in (
                "be_done", "lock_done", "lock2_done", "stale_done", "fb_done")}):
            self.save()                                 # an earlier stage already holds the stop higher
            return
        _, entry_px = self.x.position(self.sym)
        self.cancel(self.st.get("sl_id")); self.st["sl_id"] = None
        stop = self.place_sl(amt, entry_px)
        if stop:
            self.tg(f"🔗 <b>{self.coin} cascade</b>\n{src[:-4]}'s {'long' if side > 0 else 'short'} was stopped out: stop moved to "
                    f"{self.P(stop)} ({self.p.casc_to:g}R)")
        self.save()

    def check_breakeven(self, amt, entry_px):
        """Move the stop to entry (+ be_off) once a 1m candle after the fill went be_R x dist in favour, and to
        entry + lock_to x dist once it went lock_R x dist (profit lock, v2.6)."""
        be_left = self.p.be_R > 0 and not self.st.get("be_done")
        lock_left = self.p.lock_R > 0 and not self.st.get("lock_done")
        lock2_left = self.p.lock2_R > 0 and not self.st.get("lock2_done")
        if not (be_left or lock_left or lock2_left) or not self.st.get("sl_dist"):
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
        moved = False
        if be_left and side * (best - entry_px) >= self.p.be_R * self.st["sl_dist"]:
            log.info(f"BREAKEVEN: price reached {self.P(best)} (+{self.p.be_R:g}R): stop moves to the entry")
            self.st["be_done"] = True; moved = True
        if lock_left and side * (best - entry_px) >= self.p.lock_R * self.st["sl_dist"]:
            log.info(f"PROFIT LOCK: price reached {self.P(best)} (+{self.p.lock_R:g}R): stop moves to +{self.p.lock_to:g}R")
            self.st["lock_done"] = True; moved = True
        if lock2_left and side * (best - entry_px) >= self.p.lock2_R * self.st["sl_dist"]:
            log.info(f"PROFIT LOCK 2: price reached {self.P(best)} (+{self.p.lock2_R:g}R): stop moves to +{self.p.lock2_to:g}R")
            self.st["lock2_done"] = True; moved = True
        if moved:
            old = self.st.get("sl_id")
            self.cancel(old)
            self.st["sl_id"] = None
            stop = self.place_sl(amt, entry_px)
            if stop:
                risk = self.st.get("risk_usdt") or abs(amt) * self.st["sl_dist"]
                if self.st.get("lock2_done") and lock2_left:
                    self.tg(f"🔒 <b>{self.coin} profit locked higher</b>\nPrice reached {self.P(best)} (+{self.p.lock2_R:g}R) · "
                            f"stop moved to {self.P(stop)} = +{self.p.lock2_to:g}R ({notify.usd(self.p.lock2_to * risk, sign=True)} at worst)")
                elif self.st.get("lock_done") and lock_left:
                    self.tg(f"🔒 <b>{self.coin} profit locked</b>\nPrice reached {self.P(best)} (+{self.p.lock_R:g}R) · "
                            f"stop moved to {self.P(stop)} = +{self.p.lock_to:g}R ({notify.usd(self.p.lock_to * risk, sign=True)} at worst)")
                else:
                    self.tg(f"🛡 <b>{self.coin} stop moved to breakeven</b>\nPrice reached {self.P(best)} (+{self.p.be_R:g}R) · "
                            f"stop now at the entry {self.P(stop)}: this trade can no longer lose (apart from fees)")
        self.save()

    def run(self):
        if not self.dry:
            if self.x.hedge_mode():
                raise SystemExit("Account is in Hedge mode; switch Binance Futures to One-way mode first.")
            # exchange leverage only sets the margin locked per position (cross margin); position size is still
            # capped at max_leverage x equity by size(). Higher here = less margin locked when all coins are open.
            try:
                self.x.set_leverage(self.sym, int(self.cfg.get("exchange_leverage", max(1, math.ceil(self.max_lev)))))
            except BinanceError as e:                   # e.g. an open isolated position (the user's own trade) blocks a change
                log.warning(f"leverage not set ({e}); the bot keeps running with the current leverage")
        if self.oi_hist is not None:                   # first start: up to ~90 archive files (a few seconds per coin)
            try:
                n = self.oi_hist.update(budget_s=300)
                log.debug(f"open interest history: {self.oi_hist.hours()} hours ({n} archive days fetched)")
            except Exception as e:
                log.warning(f"open interest history not loaded yet ({e}); retried at the next 4h close")
        eq = self.equity()
        exempt = self.sym in self.portfolio().get("cap_exempt", [])
        log.info(f"TBO v{VERSION} online{' (DRY RUN)' if self.dry else ''} · balance {eq:.2f} USDT · risk {self.risk_now(eq) * 100:g}% "
                 f"(shorts x{self.short_mult:g}) · cap {'exempt' if exempt else f'{self.cap_frac(eq) * 100:g}%'} · "
                 f"size up to {self.max_lev:g}x the balance")
        log.debug(f"{self.sym} on {self.x.base} | risk from {'the ladder in portfolio.json' if self.ladder_row(eq) else 'risk_pct'} | "
                  f"profit lock +{self.p.lock_R}R -> +{self.p.lock_to}R, +{self.p.lock2_R}R -> +{self.p.lock2_to}R | stale {self.p.stale_h} h | "
                  f"cooldown {self.p.cool_h} h after < {self.p.cool_R}R | {self.p.to_dict()}")
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
                        log.debug("catching up on the last 4h close (the bot was not running at that moment)")
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
    notify.load_secrets_env(path.parent)
    logdir = path.parent / "logs"; logdir.mkdir(exist_ok=True)
    sym = cfg["strategy"]["symbol"]
    lg = logging.getLogger("tbo"); lg.setLevel(logging.DEBUG); lg.propagate = False
    con = logging.StreamHandler(sys.stdout); con.setLevel(logging.INFO)          # run_all.py adds the time and the coin
    con.setFormatter(logging.Formatter("%(message)s"))
    fh = logging.FileHandler(logdir / f"{sym}.log", encoding="utf-8"); fh.setLevel(logging.DEBUG)   # everything, UTC times
    ff = logging.Formatter("%(asctime)s UTC  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"); ff.converter = time.gmtime
    fh.setFormatter(ff)
    for h in (con, fh, notify.TelegramHandler(sym[:-4] + (" testnet" if a.testnet else "") + (" dry run" if a.dry_run else ""))):
        lg.addHandler(h)
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
