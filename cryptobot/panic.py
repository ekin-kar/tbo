"""
TBO panic sleeve: buys forced-liquidation crashes and sells the rebound. Runs on a Binance SUB-ACCOUNT (its own
positions, so it never interferes with the main bot's trades), keys PANIC_API_KEY / PANIC_API_SECRET in .env.
Started by run_all.py when those keys are set; settings in panic.json; signal maths in panic_signal.py (the same code
as the research, research/crypto/core/panic_sleeve.py).

    python panic.py              # live
    python panic.py --testnet    # Binance futures testnet / demo keys
    python panic.py --dry-run    # no orders: logs and alerts what it would do

Every hour, right after the hourly close, for each coin of panic.json:
  signal  the last 4 h: price fell >= 1.5x its normal 4-hour move, open interest fell >= 12%, futures premium z <= -1
  entry   market BUY at once (= the next hour's open in the backtest)
  exits   take-profit +3 x ATR(1h) and stop -4 x ATR(1h) (never more than 20% below) on Binance; the stop moves to the entry once the price has
          been +2 x ATR above it; otherwise closed at market 12 h after the entry
  size    `units` per panic event (1 unit = 1/6 of the ladder's BTC risk; a 5% move = 1 unit's risk), on the
          balance of the main account + this sub-account, split equally over the coins that trigger in the same hour
  v3.0    the same signal and exits on `extra_coins` (panic.json) with their own pool of extra_share x units per event
          (split over the extra coins entered that hour; the core `coins` keep their full units) and at most
          max_extra_open extra-coin trades at a time: if more extra coins trigger than free slots, the largest
          |OI drop| x |premium z| first (research/crypto/core/panic_sleeve.events, checked by dev/test_panic_sim.py)
State in state_panic.json; a restart picks up the open trades (the exchange is the source of truth for positions).
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
import panic_signal as PS                              # noqa: E402
from binance_futures import Futures, BinanceError      # noqa: E402

PREFIX = "pn"
HOUR = 3_600_000
log = logging.getLogger("panic")


def floor_step(x, step):
    return round(math.floor(x / step + 1e-9) * step, 12)


def ceil_step(x, step):
    return round(math.ceil(x / step - 1e-9) * step, 12)


def fmt(x, step):
    dec = max(0, -int(math.floor(math.log10(step)))) if step < 1 else 0
    return f"{x:.{dec}f}"


def load_cfg(path=HERE / "panic.json"):
    cfg = json.loads(Path(path).read_text())
    cfg["signal"] = dict(PS.DEFAULTS, **cfg.get("signal", {}))
    return cfg


def ladder_btc_pct(total):
    """BTC risk % of the risk ladder row for this balance (portfolio.json), else config_btc.json risk_pct."""
    try:
        pf = json.loads((HERE / "portfolio.json").read_text())
        row = None
        for r in sorted(pf.get("risk_ladder") or [], key=lambda r: float(r["from_usdt"])):
            if total >= float(r["from_usdt"]):
                row = r
        if row and "BTCUSDT" in row:
            return float(row["BTCUSDT"])
    except (OSError, ValueError):
        pass
    return float(json.loads((HERE / "config_btc.json").read_text())["risk_pct"])


class Sleeve:
    def __init__(self, cfg, testnet=False, dry=False):
        self.cfg, self.testnet, self.dry = cfg, testnet, dry
        self.p = cfg["signal"]; self.core = list(cfg["coins"]); self.extra = list(cfg.get("extra_coins", []))
        self.coins = self.core + [s for s in self.extra if s not in self.core]
        self.sub = Futures(os.environ.get("PANIC_API_KEY", ""), os.environ.get("PANIC_API_SECRET", ""), testnet=testnet)
        self.main = Futures(os.environ.get("BINANCE_API_KEY", ""), os.environ.get("BINANCE_API_SECRET", ""), testnet=testnet)
        self.f = {s: self.sub.exchange_info(s) for s in self.coins}
        self.state_path = HERE / f"state_panic{'_testnet' if testnet else ''}.json"
        self.st = json.loads(self.state_path.read_text()) if self.state_path.exists() else {"trades": {}, "last_hour": 0}

    def save(self):
        tmp = self.state_path.with_suffix(".tmp"); tmp.write_text(json.dumps(self.st, indent=1)); tmp.replace(self.state_path)

    def tg(self, text):
        if notify.enabled():
            mode = " <i>(dry run)</i>" if self.dry else " <i>(testnet)</i>" if self.testnet else ""
            first, _, rest = text.partition("\n")
            notify.send(first + mode + ("\n" + rest if rest else ""))

    def cid(self, kind, sym):
        return f"{PREFIX}_{kind}_{sym[:-4]}_{int(time.time() * 1000)}"

    def P(self, sym, x):
        return notify.px(x, self.f[sym]["tick"])

    # ── balances ──
    def sub_equity(self):
        if self.dry:
            return float(self.cfg.get("dry_run_equity", 100))
        return float(self.sub.account()["totalMarginBalance"])

    def total_equity(self):
        """Main account + sub-account (the research sizes on one pool). Main unreadable: the sub-account alone x 4."""
        sub = self.sub_equity()
        try:
            main = float(self.cfg.get("dry_run_equity_main", 300)) if self.dry else float(self.main.account()["totalMarginBalance"])
            if not self.dry:                             # the user's own isolated trades on non-bot coins: not in the pool
                bots = set()
                for f in HERE.glob("config_*.json"):
                    try:
                        bots.add(json.loads(f.read_text())["strategy"]["symbol"])
                    except (OSError, ValueError, KeyError):
                        pass
                try:
                    main -= sum(v for s, v in self.main.isolated_positions().items() if s not in bots)
                except Exception as e:
                    log.info(f"isolated positions unreadable ({e}): counted in the balance this time")
        except Exception as e:
            log.warning(f"main account balance unreadable ({e}): sizing on the sub-account balance x 4")
            main = 3 * sub
        return main + sub, sub

    # ── data ──
    def hourly(self, sym, last_open):
        """Closed hourly bars up to the one opened at last_open, with OI (sample at :55 of each hour) and premium."""
        k = [b for b in self.main.klines(sym, "1h", 1000) if b[0] <= last_open]
        if not k or k[-1][0] != last_open:
            return None
        pr = {b[0]: b[4] for b in self.main.premium_klines(sym, "1h", 1000)}
        oi = sorted(self.main.open_interest_hist(sym, period="5m", limit=500))
        ts = [t for t, _ in oi]

        def oi_of(t_open):                              # the hour's last 5-minute sample (research: the :55 row)
            j = bisect.bisect_left(ts, t_open + HOUR) - 1
            return oi[j][1] if j >= 0 and ts[j] >= t_open + 30 * 60_000 else float("nan")
        if math.isnan(oi_of(last_open)) or not ts or ts[-1] < last_open + 55 * 60_000:
            return None                                 # the hour's last OI sample is not published yet
        o = [b[1] for b in k]; h = [b[2] for b in k]; l = [b[3] for b in k]; c = [b[4] for b in k]
        oiv = [oi_of(b[0]) for b in k]
        prv = [pr.get(b[0], float("nan")) for b in k]
        return o, h, l, c, oiv, prv

    def check_hour(self, last_open):
        """After the close of the hour that opened at last_open: find the coins that trigger. None = data not ready."""
        hits = []
        for sym in self.coins:
            d = self.hourly(sym, last_open)
            if d is None:
                return None
            o, h, l, c, oi, pr = d
            f = PS.features(h, l, c, oi, pr, self.p["window_h"])
            sig = PS.signal(f, **self.p)
            info = dict(rz=float(f["rz"][-1]), doi=float(f["doi"][-1]), pz=float(f["pz"][-1]), atr=float(f["atr"][-1]),
                        move=c[-1] / c[-1 - int(self.p["window_h"])] - 1)
            log.debug(f"{sym} hour {notify.when(last_open + HOUR)}: move {info['move'] * 100:+.2f}% ({info['rz']:+.2f}x normal), "
                      f"OI {info['doi'] * 100:+.1f}%, premium z {info['pz']:+.2f}" + (" -> SIGNAL" if sig[-1] else ""))
            if sig[-1] and sym not in self.st["trades"] and last_open > self.st.get("exit_hour", {}).get(sym, -1):
                hits.append((sym, info))                # (as the research: not in the hour its last trade closed)
        return hits

    # ── trading ──
    def select(self, hits):
        """The trades to open this hour: [(sym, info, n, units)]. Core coins all enter (units split over them); extra coins
        only into the free extra slots, the largest |doi| x |pz| first, extra_share x units split over those entered."""
        U = float(self.cfg.get("units", 3))
        core = [(s, i) for s, i in hits if s in self.core]
        ext = [(s, i) for s, i in hits if s not in self.core]
        cap = self.cfg.get("max_extra_open")
        if ext and cap is not None:
            free = int(cap) - sum(1 for s in self.st["trades"] if s not in self.core)
            ext = sorted(ext, key=lambda z: (-abs(z[1]["doi"]) * abs(z[1]["pz"]), z[0]))[:max(0, free)]
        out = [(s, i, len(core), U) for s, i in core]
        out += [(s, i, len(ext), U * float(self.cfg.get("extra_share", 0.75))) for s, i in ext]
        return out

    def open_trade(self, sym, info, n, total, sub, units=None):
        f = self.f[sym]; units = float(self.cfg.get("units", 3)) if units is None else float(units)
        risk = total * ladder_btc_pct(total) / 100 * units / 6 / n          # $ lost on a 5% move
        price = self.main.last_price(sym)
        notional = risk / 0.05
        cap = sub * float(self.cfg.get("max_leverage", 4))
        if notional > cap:
            log.warning(f"{sym}: size {notional:.2f} capped at {cap:.2f} ({self.cfg.get('max_leverage', 4)}x the sub-account balance; move more to the sub-account)")
            notional = cap
        if notional < f["min_notional"]:
            if f["min_notional"] <= 1.5 * notional:
                notional = f["min_notional"] * 1.02
            else:
                log.warning(f"{sym}: panic signal, but the size ${notional:.2f} is below Binance's minimum ${f['min_notional']:g}: skipped")
                self.tg(f"⚡ <b>{sym[:-4]} panic signal</b> skipped\nSize ${notional:.2f} below Binance's minimum ${f['min_notional']:g}")
                return
        qty = floor_step(notional / price, max(f["step"], f["mkt_step"]))
        if qty < f["min_qty"]:
            log.warning(f"{sym}: quantity {qty} below the minimum: skipped"); return
        now = self.sub.now_ms() if not self.dry else int(time.time() * 1000)
        if self.dry:
            fill, got = price, qty
        else:
            r = self.sub.market(sym, "BUY", fmt(qty, f["step"]), client_id=self.cid("in", sym))
            got = float(r.get("executedQty") or qty); fill = float(r.get("avgPrice") or 0) or price
        a = info["atr"]
        stop = floor_step(max(fill - self.p["stop_atr"] * a, fill * (1 - self.p["stop_max"])), f["tick"])
        tp = ceil_step(fill + self.p["tp_atr"] * a, f["tick"]) if self.p["tp_atr"] > 0 else None
        tr = dict(entry_ms=now, entry=fill, qty=got, atr=a, stop=stop, tp=tp, be_at=fill + self.p["be_atr"] * a if self.p["be_atr"] > 0 else None,
                  be_done=False, sl_id=None, tp_id=None, risk=risk, n=n, **{k: info[k] for k in ("move", "doi", "pz", "rz")})
        self.st["trades"][sym] = tr; self.save()
        self.place_exits(sym)
        log.info(f"PANIC BUY {got:g} {sym[:-4]} @ {self.P(sym, fill)} (move {info['move'] * 100:+.1f}%, OI {info['doi'] * 100:+.1f}%, "
                 f"premium z {info['pz']:+.2f}) | TP {self.P(sym, tp) if tp else '-'} | stop {self.P(sym, stop)} | risk ${risk:.2f} per 5% move")
        rows = [f"⚡ <b>{sym[:-4]} panic buy</b>",
                f"Entry <b>{self.P(sym, fill)}</b>",
                f"Last {int(self.p['window_h'])}h: price {notify.pct(info['move'] * 100, sign=True, dec=1)}, open interest {notify.pct(info['doi'] * 100, sign=True, dec=1)}",
                f"Take profit {self.P(sym, tp)} ({notify.pct((tp / fill - 1) * 100, sign=True, dec=1)})" if tp else "Take profit: none",
                f"Stop {self.P(sym, stop)} ({notify.pct((stop / fill - 1) * 100, sign=True, dec=1)})",
                f"Stop to entry at {self.P(sym, tr['be_at'])}" if tr["be_at"] else "",
                f"Size {notify.usd(got * fill)} · {notify.usd(risk)} per 5% move",
                f"Closes by {notify.when(now + int(self.p['hold_h']) * HOUR, day=False)} at the latest"]
        self.tg("\n".join(r for r in rows if r))

    def place_exits(self, sym):
        tr = self.st["trades"][sym]; f = self.f[sym]
        if self.dry:
            return
        stop = tr["entry"] if tr["be_done"] else tr["stop"]
        stop = floor_step(stop, f["tick"])
        last = self.main.last_price(sym)
        if last <= stop:
            self.close(sym, "stop (price already below it)"); return
        if not tr.get("sl_id"):
            try:
                tr["sl_id"] = self.sub.stop_market(sym, "SELL", fmt(stop, f["tick"]), close_position=True, client_id=self.cid("sl", sym))["algoId"]
            except BinanceError as e:
                if e.code == -2021:
                    self.close(sym, "stop (price already below it)"); return
                raise
        if tr.get("tp") and not tr.get("tp_id"):
            if last >= tr["tp"]:
                self.close(sym, "take profit (price already above it)"); return
            try:
                tr["tp_id"] = self.sub.take_profit_market(sym, "SELL", fmt(tr["tp"], f["tick"]), client_id=self.cid("tp", sym))["algoId"]
            except BinanceError as e:
                if e.code == -2021:
                    self.close(sym, "take profit (price already above it)"); return
                raise
        self.save()

    def cancel(self, algo_id):
        if algo_id and not self.dry:
            try:
                self.sub.cancel_algo(algo_id=algo_id)
            except BinanceError:
                pass

    def triggered(self, algo_id):
        if not algo_id:
            return False
        try:
            return self.sub.algo_order(algo_id=algo_id).get("algoStatus") in ("TRIGGERED", "FINISHED")
        except BinanceError:
            return False

    def order_alive(self, algo_id):
        try:
            return self.sub.algo_order(algo_id=algo_id).get("algoStatus") in ("NEW", "TRIGGERING")
        except BinanceError:
            return False

    def close(self, sym, why):
        """Close at market (time exit, or a level already passed), cancel the exit orders, report."""
        tr = self.st["trades"].get(sym)
        if tr is None:
            return
        if not self.dry:
            amt, _ = self.sub.position(sym)
            if amt > 0:
                self.sub.market(sym, "SELL", fmt(amt, self.f[sym]["step"]), reduce_only=True, client_id=self.cid("x", sym))
        self.finish(sym, why)

    def trigger_ms(self, algo_id):
        """When a stop / take-profit order triggered (Binance triggerTime), 0 if unknown."""
        if not algo_id or self.dry:
            return 0
        try:
            return int(self.sub.algo_order(algo_id=algo_id).get("triggerTime") or 0)
        except BinanceError:
            return 0

    def finish(self, sym, why, exit_ms=None):
        tr = self.st["trades"].pop(sym, None)
        if tr is None:
            return
        now = self.sub.now_ms() if not self.dry else int(time.time() * 1000)
        ex = exit_ms or max(self.trigger_ms(tr.get("tp_id")), self.trigger_ms(tr.get("sl_id"))) or now
        self.st.setdefault("exit_hour", {})[sym] = (min(ex, now) // HOUR) * HOUR   # no new signal in the hour it closed
        self.cancel(tr.get("sl_id")); self.cancel(tr.get("tp_id")); self.save()
        exit_px, pnl, fees = self.result(sym, tr)
        ret = exit_px / tr["entry"] - 1
        net = pnl - fees
        log.info(f"PANIC CLOSED {sym[:-4]}: {why} | exit {self.P(sym, exit_px)} ({ret * 100:+.2f}%) | net ${net:+.2f}")
        icon = "✅" if net > 0 else "❌"
        try:
            sub = self.sub_equity()
        except Exception:
            sub = None
        self.tg("\n".join([f"{icon} <b>{sym[:-4]} panic closed · {notify.pct(ret * 100, sign=True)} · {notify.usd(net, sign=True)}</b>",
                           f"Exit {self.P(sym, exit_px)} · {notify.esc(why)}",
                           f"Entry {self.P(sym, tr['entry'])} · held {notify.held((self.sub.now_ms() if not self.dry else time.time() * 1000) - tr['entry_ms'])}",
                           f"Fees {notify.usd(fees)}" + (f" · sub-account {notify.usd(sub)}" if sub is not None else "")]))

    def result(self, sym, tr):
        """(exit price, realized PnL, fees) from the trade history; estimated from the last price if unreadable."""
        if not self.dry:
            try:
                q = v = pnl = fees = 0.0
                for t in self.sub.user_trades(sym, limit=100, start_ms=tr["entry_ms"] - 60_000):
                    c, asset = float(t.get("commission", 0)), t.get("commissionAsset", "USDT")
                    fees += c if asset in ("USDT", "USDC") else c * self.main.last_price(asset + "USDT")
                    if t.get("side") == "SELL":
                        q += float(t["qty"]); v += float(t["qty"]) * float(t["price"]); pnl += float(t.get("realizedPnl", 0))
                if q:
                    return v / q, pnl, fees
            except Exception as e:
                log.info(f"trade history: {e}")
        px = tr.get("dry_exit") or self.main.last_price(sym)
        return px, (px - tr["entry"]) * tr["qty"], 0.0005 * tr["qty"] * (tr["entry"] + px)

    def manage(self):
        now = self.sub.now_ms() if not self.dry else int(time.time() * 1000)
        for sym in list(self.st["trades"]):
            tr = self.st["trades"][sym]
            if self.dry:                                # dry run: the exits are simulated on the 1-minute prices
                k = self.main.klines(sym, "1m", 1000, start_ms=tr["entry_ms"])
                st = tr["entry"] if tr["be_done"] else tr["stop"]
                if k and min(b[3] for b in k) <= st:
                    tr["dry_exit"] = st; self.finish(sym, "breakeven stop" if tr["be_done"] else "stop"); continue
                if k and tr.get("tp") and max(b[2] for b in k) >= tr["tp"]:
                    tr["dry_exit"] = tr["tp"]; self.finish(sym, "take profit"); continue
                amt = tr["qty"]
            else:
                amt, _ = self.sub.position(sym)
            if amt <= 0:                                # the stop or the take-profit filled on Binance
                self.finish(sym, "take profit" if self.triggered(tr.get("tp_id")) else ("breakeven stop" if tr["be_done"] else "stop"))
                continue
            if now >= tr["entry_ms"] + int(self.p["hold_h"]) * HOUR:
                self.close(sym, f"time exit ({int(self.p['hold_h'])} h)"); continue
            if tr.get("be_at") and not tr["be_done"]:
                hi = max([b[2] for b in self.main.klines(sym, "1m", 1000, start_ms=tr["entry_ms"])] or [0])
                if hi >= tr["be_at"]:
                    tr["be_done"] = True; self.cancel(tr.get("sl_id")); tr["sl_id"] = None
                    log.info(f"PANIC {sym[:-4]}: +{self.p['be_atr']:g} ATR reached ({self.P(sym, hi)}): stop moved to the entry {self.P(sym, tr['entry'])}")
                    self.tg(f"🛡 <b>{sym[:-4]} panic</b> stop moved to the entry {self.P(sym, tr['entry'])}")
                    self.save()
            if not self.dry and (not tr.get("sl_id") or not self.order_alive(tr["sl_id"])):
                tr["sl_id"] = None
                if tr.get("tp_id") and not self.order_alive(tr["tp_id"]):
                    tr["tp_id"] = None
                self.place_exits(sym)

    def adopt(self):
        """Positions on the sub-account without state (e.g. after a lost state file): protect them."""
        if self.dry:
            return
        for sym, (amt, entry) in self.sub.positions().items():
            if sym in self.st["trades"] or amt <= 0 or sym not in self.coins:
                continue
            k = self.main.klines(sym, "1h", 300)
            a = float(PS.atr([b[2] for b in k], [b[3] for b in k], [b[4] for b in k])[-1])
            self.st["trades"][sym] = dict(entry_ms=self.sub.now_ms(), entry=entry, qty=amt, atr=a, stop=max(entry - self.p["stop_atr"] * a, entry * (1 - self.p["stop_max"])),
                                          tp=entry + self.p["tp_atr"] * a, be_at=entry + self.p["be_atr"] * a, be_done=False, sl_id=None, tp_id=None,
                                          risk=0.0, n=1, move=0.0, doi=0.0, pz=0.0, rz=0.0)
            log.warning(f"{sym}: position {amt} on the sub-account without a record: stop, take-profit and a 12 h exit set from now")
            self.place_exits(sym)

    def run(self):
        if not self.dry:
            if self.sub.hedge_mode():
                raise SystemExit("Sub-account is in Hedge mode; switch it to One-way.")
            for s in self.coins:
                try:
                    self.sub.set_leverage(s, min(5, int(self.cfg.get("exchange_leverage", 5))))     # Binance: sub-accounts max 5x
                except BinanceError as e:
                    log.warning(f"{s}: leverage not set ({e})")
        total, sub = self.total_equity()
        log.info(f"panic sleeve online{' (DRY RUN)' if self.dry else ''} · sub-account {sub:.2f} USDT, main + sub {total:.2f} · "
                 f"{' '.join(s[:-4] for s in self.core)} · {self.cfg.get('units', 3):g} units per event"
                 + (f" · extra {' '.join(s[:-4] for s in self.extra)} at {self.cfg.get('extra_share', 0.75):g}x, max {self.cfg.get('max_extra_open')} open" if self.extra else ""))
        self.adopt()
        while True:
            try:
                now = self.main.now_ms()
                last_open = (now // HOUR) * HOUR - HOUR             # the hour that closed most recently
                if self.st.get("last_hour", 0) < last_open and now - (last_open + HOUR) >= 30_000:
                    hits = self.check_hour(last_open)
                    late = now - (last_open + HOUR) > 15 * 60_000
                    if hits is not None or late:
                        if hits is None:
                            log.warning("hourly data incomplete 15 min after the close: hour skipped")
                            hits = []
                        self.st["last_hour"] = last_open; self.save()
                        if hits and not late:
                            total, sub = self.total_equity()
                            picked = self.select(hits)
                            for sym, _ in hits:
                                if sym not in [z[0] for z in picked]:
                                    log.info(f"{sym}: panic signal, but {self.cfg.get('max_extra_open')} extra-coin trades are already open / ranked higher: skipped")
                            for sym, info, n, u in picked:
                                self.open_trade(sym, info, n, total, sub, units=u)
                self.manage()
            except BinanceError as e:
                log.error(f"Binance: {e}")
                if e.code in (-2014, -2015, -1022):
                    raise SystemExit("panic sleeve: API key / permission problem")
            except Exception as e:
                log.exception(f"error: {e}")
                time.sleep(10)
            time.sleep(float(self.cfg.get("poll_s", 15)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--testnet", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    notify.load_secrets_env(HERE)
    logdir = HERE / "logs"; logdir.mkdir(exist_ok=True)
    lg = logging.getLogger("panic"); lg.setLevel(logging.DEBUG); lg.propagate = False
    con = logging.StreamHandler(sys.stdout); con.setLevel(logging.INFO); con.setFormatter(logging.Formatter("%(message)s"))
    fh = logging.FileHandler(logdir / "PANIC.log", encoding="utf-8"); fh.setLevel(logging.DEBUG)
    ff = logging.Formatter("%(asctime)s UTC  %(message)s", datefmt="%Y-%m-%d %H:%M:%S"); ff.converter = time.gmtime; fh.setFormatter(ff)
    for hd in (con, fh, notify.TelegramHandler("Panic sleeve")):
        lg.addHandler(hd)
    if not (os.environ.get("PANIC_API_KEY") and os.environ.get("PANIC_API_SECRET")) and not a.dry_run:
        raise SystemExit("PANIC_API_KEY / PANIC_API_SECRET not set in .env (the sub-account's key)")
    while True:
        try:
            s = Sleeve(load_cfg(), testnet=a.testnet, dry=a.dry_run)
            break
        except BinanceError as e:
            if e.code in (-2014, -2015, -1022):
                raise SystemExit(f"panic sleeve: API key / permission problem: {e}")
            lg.warning(f"Binance error at start-up: {e}; retrying in 30 s")
        except Exception as e:
            lg.warning(f"cannot reach Binance ({type(e).__name__}); retrying in 30 s")
        time.sleep(30)
    s.run()


if __name__ == "__main__":
    main()
