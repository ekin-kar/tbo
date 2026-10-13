"""
Runs one bot process per config (default: every config_*.json here) and restarts any that stops.
    python run_all.py                 # live
    python run_all.py --testnet       # Binance futures testnet / demo keys
    python run_all.py --dry-run       # no orders, prints decisions
    python run_all.py config_btc.json config_eth.json   # only these
Stop with Ctrl+C (stops all bots; open positions keep their stop-loss on Binance).
To stop NEW entries but keep managing open trades: create an empty file named PAUSE in this folder.
Telegram (if set in .env): one message when the bots start; /status in the chat (or the bot's / menu) answers with the
current situation of every coin, live from Binance. The bots themselves send their trade events (opened, breakeven,
profit lock, closed, cap cuts) and warnings. No message after the 4h checks.
"""
import json, subprocess, sys, time, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import notify                                    # noqa: E402

flags = [a for a in sys.argv[1:] if a.startswith("--")]
cfgs = [a for a in sys.argv[1:] if not a.startswith("--")] or sorted(str(p.name) for p in HERE.glob("config_*.json"))
procs, fails, lock = {}, {c: 0 for c in cfgs}, threading.Lock()
notify.load_env(HERE / ".env")
TESTNET, DRY = "--testnet" in flags, "--dry-run" in flags
MODE = " <i>(dry run)</i>" if DRY else " <i>(testnet)</i>" if TESTNET else ""
TF_MS = 4 * 3600_000


def cfg_of(c):
    return json.loads((HERE / c).read_text())


ORDER = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
SYMS = sorted((cfg_of(c)["strategy"]["symbol"] for c in cfgs), key=lambda s: (ORDER.index(s) if s in ORDER else 99, s))
COIN = {s: s[:-4] for s in SYMS}


def pump(cfg, p):
    tag = cfg.replace("config_", "").replace(".json", "").upper()
    for line in p.stdout:
        with lock:
            print(f"{time.strftime('%H:%M:%S')}  {tag:<4s} {line.rstrip()}", flush=True)


def publish(msg):
    """A status message: the console (plain text) and Telegram (formatted)."""
    with lock:
        print("\n" + notify._plain(msg).replace("\n", "\n   ") + "\n", flush=True)
    notify.send(msg)


def publish_console(msg):
    with lock:
        print(f"{time.strftime('%H:%M:%S')}  {msg}", flush=True)


def start(cfg):
    p = subprocess.Popen([sys.executable, "-u", str(HERE / "bot.py"), str(HERE / cfg)] + flags, cwd=HERE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
    threading.Thread(target=pump, args=(cfg, p), daemon=True).start()
    procs[cfg] = (p, time.time())


# ── Telegram ──
def account():
    """(balance, exchange clock ms) or (None, local ms)."""
    try:
        import os
        from binance_futures import Futures
        if DRY:
            return float(cfg_of(cfgs[0]).get("dry_run_equity", 1000)), int(time.time() * 1000)
        x = Futures(os.environ.get("BINANCE_API_KEY", ""), os.environ.get("BINANCE_API_SECRET", ""), testnet=TESTNET)
        return float(x.account()["totalMarginBalance"]), x.now_ms()
    except Exception:
        return None, int(time.time() * 1000)


def portfolio():
    try:
        return json.loads((HERE / "portfolio.json").read_text())
    except (OSError, ValueError):
        return {}


def ladder_row(eq):
    row = None
    for r in sorted(portfolio().get("risk_ladder") or [], key=lambda r: float(r["from_usdt"])):
        if eq is not None and eq >= float(r["from_usdt"]):
            row = r
    return row


def risk_text(eq):
    row = ladder_row(eq)
    if row:
        alts = [s for s in SYMS if s not in ("BTCUSDT", "ETHUSDT")]
        parts = [f"{COIN[s]} {row[s]:g}%" for s in SYMS if s in ("BTCUSDT", "ETHUSDT") and s in row]
        if alts:
            parts.append(f"{'/'.join(COIN[s] for s in alts)} {row.get(alts[0], 0):g}% each")
        return " · ".join(parts), float(row.get("cap_pct", 0))
    parts = [f"{COIN[s]} {cfg_of(c)['risk_pct']:g}%" for c, s in zip(cfgs, SYMS)]
    return " · ".join(parts), float(portfolio().get("open_risk_cap_pct", 0) or 0)


def state(sym):
    try:
        return json.loads((HERE / f"state_{sym}{'_testnet' if TESTNET else ''}.json").read_text())
    except (OSError, ValueError):
        return {}


def weekend(t_ms):
    """No new orders are placed at a 4h close on Saturday or Sunday (UTC), as in the backtest."""
    return time.gmtime(t_ms / 1000).tm_wday >= 5


def orders_resume(t_ms):
    """The first 4h close after t_ms where new orders are placed again (Monday 00:00 UTC)."""
    t = t_ms // TF_MS * TF_MS + TF_MS
    while weekend(t):
        t += TF_MS
    return t


_X = {}


def exchange():
    """One Binance client for the status messages (made on first use)."""
    if "x" not in _X:
        import os
        from binance_futures import Futures
        _X["x"] = Futures(os.environ.get("BINANCE_API_KEY", ""), os.environ.get("BINANCE_API_SECRET", ""), testnet=TESTNET)
    return _X["x"]


def tick(sym):
    if sym not in _X:
        try:
            _X[sym] = exchange().exchange_info(sym)["tick"]
        except Exception:
            return None
    return _X[sym]


def status_message(title="📊 <b>Status</b>"):
    """Every coin as it is now: open trade (live price, R, P&L, stop), waiting order (distance to it), or why there is
    no order; then balance, open risk and the cap. Positions and orders are read from Binance, the rest from the bots'
    state files."""
    if DRY:
        return f"{title}{MODE}\nDry run: no account to read."
    x = exchange()
    acc = x.account()
    eq, now = float(acc["totalMarginBalance"]), x.now_ms()
    pos = x.positions()
    orders = x.open_algo_orders()
    last_close = now // TF_MS * TF_MS
    P = lambda s, v: notify.px(v, tick(s))
    rows, risk, upnl = [], 0.0, 0.0
    for s in SYMS:
        st, c = state(s), f"<b>{COIN[s]}</b>"
        mine = [o for o in orders if o.get("symbol") == s]
        price = x.last_price(s)
        if s in pos:
            amt, entry = pos[s]
            side = 1 if amt > 0 else -1
            pnl = amt * (price - entry)                 # (Binance's average entry; fees not included)
            entry = st.get("fill_px") or entry
            d = float(st.get("sl_dist") or 0)
            stops = [float(o.get("triggerPrice") or 0) for o in mine
                     if str(o.get("closePosition")).lower() == "true" or str(o.get("reduceOnly")).lower() == "true"]
            stop = (max(stops) if side > 0 else min(stops)) if stops else None
            r_now = side * (price - entry) / d if d else 0.0
            upnl += pnl
            if stop:
                risk += max(0.0, side * (entry - stop)) * abs(amt)
            stage = (f"profit locked at +{st.get('lock_to', 1.5):g}R" if st.get("lock_done") else
                     "stop at breakeven" if st.get("be_done") else "stop")
            held = notify.held(now - st["entry_ms"]) if st.get("entry_ms") else "?"
            rows.append(f"{c} ● <b>{'long' if side > 0 else 'short'}</b> {notify.num(r_now, 2, sign=True)}R "
                        f"({notify.usd(pnl, sign=True)}) · entry {P(s, entry)} · now {P(s, price)}\n"
                        f"      {stage} {P(s, stop) if stop else '<b>not found on Binance!</b>'} · held {held}")
            continue
        entries = [o for o in mine if "_in_" in str(o.get("clientAlgoId", ""))]
        if entries:
            o = entries[0]
            side = 1 if o.get("side") == "BUY" else -1
            trig = float(o.get("triggerPrice") or 0)
            d = float(st.get("sl_dist") or 0)
            qty = float(o.get("quantity") or st.get("entry_qty") or 0)
            away = side * (trig / price - 1) * 100
            rows.append(f"{c} {'▲ buy' if side > 0 else '▼ sell'} stop {P(s, trig)} · price {P(s, price)} "
                        f"({notify.pct(away, dec=2)} away)\n"
                        f"      stop loss {P(s, trig - side * d)} · risk {notify.usd(qty * d)}")
            continue
        ck = st.get("check") or {}
        line = ck.get("line", "")
        if st.get("entry_trig") and not st.get("entry_qty"):
            side = st.get("entry_side") or 1
            rows.append(f"{c} {'▲ buy' if side > 0 else '▼ sell'} stop {P(s, st['entry_trig'])} held back: open-risk cap full "
                        f"· price {P(s, price)}")
        elif ck.get("t") != last_close:
            rows.append(f"{c} <i>no report from the last 4h close yet</i> · price {P(s, price)}")
        elif line.startswith(("▲", "▼", "●")):
            rows.append(f"{c} no order: this candle's order was used · next decision at {notify.when(last_close + TF_MS, day=False)}")
        else:
            rows.append(f"{c} {notify.esc(line)}")
    _, cap = risk_text(eq)
    out = [f"{title} · {notify.when(now)} ({notify.tz_label()}){MODE}", ""] + rows + [""]
    out.append(f"Balance <b>{notify.usd(eq)}</b>" + (f" · open P&amp;L {notify.usd(upnl, sign=True)}" if pos else ""))
    out.append(f"Open risk {notify.usd(risk)} ({risk / eq * 100:.1f}%)" + (f" · cap {cap:g}%" if cap else "") if eq else "")
    if (HERE / "PAUSE").exists():
        out.append("⏸ PAUSE file: no new orders (open trades are still managed)")
    elif weekend(now):
        out.append(f"🌙 Weekend: no new orders until {notify.when(orders_resume(now))}; open trades are still managed")
    return "\n".join(out)


def startup_message():
    eq, now = account()
    wait_reports(now // TF_MS * TF_MS, 120)        # the bots act on the last 4h close right after starting
    rtext, cap = risk_text(eq)
    st0 = json.loads((HERE / cfgs[0]).read_text())["strategy"]
    rows = [f"🟢 <b>TBO v{bot_version()} online</b>{MODE}",
            f"Coins {' · '.join(COIN[s] for s in SYMS)}",
            f"Risk per trade {rtext} (shorts half)",
            f"Open-risk cap {cap:g}% of the balance (BTC exempt)" if cap else "Open-risk cap off",
            f"Exits: stop 1 ATR · breakeven at +{st0.get('be_R', 1.5):g}R · +{st0.get('lock_R', 5):g}R locks "
            f"+{st0.get('lock_to', 1.5):g}R · time exit after {st0.get('max_hold_h', 120) / 24:g} days",
            "Send /status any time for the current situation."]
    try:
        rows += ["", status_message("<b>Now</b>")]
    except Exception as e:
        rows += ["", f"Balance {notify.usd(eq)}" if eq is not None else "Balance: not readable right now",
                 f"(status not readable right now: {notify.esc(e)})"]
    publish("\n".join(rows))


def wait_reports(t_close, max_s):
    t0 = time.time()
    while time.time() - t0 < max_s:
        if all((state(s).get("check") or {}).get("t") == t_close for s in SYMS):
            return
        time.sleep(5)


def bot_version():
    for line in (HERE / "bot.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("VERSION"):
            return line.split("=")[1].strip().strip('"')
    return "?"


def main():
    mode = "dry run" if DRY else "testnet" if TESTNET else "live"
    print(f"TBO launcher · {mode} · {' '.join(COIN[s] for s in SYMS)}"
          f" · Telegram {'on' if notify.enabled() else 'off'}", flush=True)
    by_sym = {cfg_of(c)["strategy"]["symbol"]: c for c in cfgs}
    for s_ in SYMS:                                  # BTC first, then ETH, BNB, SOL, ADA
        start(by_sym[s_]); time.sleep(2)             # stagger start-up requests
    threading.Thread(target=startup_message, daemon=True).start()
    threading.Thread(target=notify.listen, daemon=True,
                     args=({"status": ("Current status of every coin", status_message)}, publish_console)).start()
    try:
        while True:
            time.sleep(5)
            for c, (p, t0) in list(procs.items()):
                if p.poll() is not None:
                    fails[c] = fails[c] + 1 if time.time() - t0 < 300 else 1
                    wait = 5 if fails[c] == 1 else 60
                    print(f"{time.strftime('%H:%M:%S')}  {c}: bot stopped (exit code {p.returncode}); restarting in {wait} s", flush=True)
                    notify.send(f"♻️ <b>{COIN.get(cfg_of(c)['strategy']['symbol'], c)}</b> bot stopped (exit code {p.returncode}) · "
                                f"restarting in {wait} s")
                    time.sleep(wait); start(c)
    except KeyboardInterrupt:
        print("stopping all bots (stop-losses stay on Binance)", flush=True)
        notify.send("🔴 <b>TBO stopped</b>\nOpen trades keep their stop loss on Binance; no new orders until it runs again.", wait=True)
        for p, _ in procs.values():
            p.terminate()


if __name__ == "__main__":
    main()
