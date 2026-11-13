"""
Runs one bot process per config (default: every config_*.json here) and restarts any that stops.
    python run_all.py                 # live
    python run_all.py --testnet       # Binance futures testnet / demo keys
    python run_all.py --dry-run       # no orders, prints decisions
    python run_all.py config_btc.json config_eth.json   # only these
Stop with Ctrl+C (stops all bots; open positions keep their stop-loss on Binance).
To stop NEW entries but keep managing open trades: create an empty file named PAUSE in this folder.
The panic sleeve (panic.py, on a Binance sub-account) runs too when PANIC_API_KEY / PANIC_API_SECRET are in .env.
The VOLC sleeve (volc.py, v3.1, on this main account next to the coin bots) runs when volc.json says "enabled": true.
Telegram (if set in .env): one message when the bots start; /status in the chat (or the bot's / menu) answers with the
current situation of every coin, live from Binance. The bots themselves send their trade events (opened, breakeven,
profit lock, closed, cap cuts) and warnings. No message after the 4h checks.
"""
import json, re, subprocess, sys, time, threading
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import notify                                    # noqa: E402

flags = [a for a in sys.argv[1:] if a.startswith("--")]
cfgs = [a for a in sys.argv[1:] if not a.startswith("--")] or sorted(str(p.name) for p in HERE.glob("config_*.json"))
procs, fails, lock = {}, {c: 0 for c in cfgs + ["panic", "volc"]}, threading.Lock()
notify.load_secrets_env(HERE)
TESTNET, DRY = "--testnet" in flags, "--dry-run" in flags
MODE = " <i>(dry run)</i>" if DRY else " <i>(testnet)</i>" if TESTNET else ""
TF_MS = 4 * 3600_000


def cfg_of(c):
    return json.loads((HERE / c).read_text())


ORDER = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
SYMS = sorted((cfg_of(c)["strategy"]["symbol"] for c in cfgs), key=lambda s: (ORDER.index(s) if s in ORDER else 99, s))
COIN = {s: s[:-4] for s in SYMS}
STRAT = {cfg_of(c)["strategy"]["symbol"]: cfg_of(c)["strategy"] for c in cfgs}


def stop_stage(st, sd):
    """The trend bot's current stop stage (the most favourable one reached, as strategy.stop_level), for /status."""
    if st.get("lock2_done"):
        return f" (+{sd.get('lock2_to', 3.5):g}R)"
    if st.get("lock_done"):
        return f" (+{sd.get('lock_to', 2.0):g}R)"
    if st.get("be_done"):
        return " (BE)"
    if st.get("stale_done"):
        to = float(sd.get("stale_to", 0.0))
        return " (BE, stale)" if to == 0 else f" ({to:+g}R, stale)"
    if st.get("casc_done"):
        return f" ({sd.get('casc_to', -0.25):g}R, cascade)"
    if st.get("fb_done"):
        return f" ({sd.get('fb_to', -0.5):g}R, failed breakout)"
    return ""


def volc_trade_syms():
    """Coins on which the VOLC sleeve holds a trade (state_volc.json)."""
    try:
        return set(json.loads((HERE / f"state_volc{'_testnet' if TESTNET else ''}.json").read_text()).get("trades", {}))
    except (OSError, ValueError):
        return set()


def pump(cfg, p):
    tag = "PNC" if cfg == PANIC else "VLC" if cfg == VOLC else cfg.replace("config_", "").replace(".json", "").upper()
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


PANIC = "panic"                                  # the panic sleeve's process name (panic.py, sub-account)
VOLC = "volc"                                    # the VOLC sleeve's process name (volc.py, main account; v3.1)


def volc_on():
    try:
        return bool(json.loads((HERE / "volc.json").read_text()).get("enabled"))
    except (OSError, ValueError):
        return False


def panic_on():
    import os
    return bool(os.environ.get("PANIC_API_KEY") and os.environ.get("PANIC_API_SECRET")) and (HERE / "panic.json").exists()


def start(cfg):
    cmd = [str(HERE / "panic.py")] if cfg == PANIC else [str(HERE / "volc.py")] if cfg == VOLC else [str(HERE / "bot.py"), str(HERE / cfg)]
    p = subprocess.Popen([sys.executable, "-u"] + cmd + flags, cwd=HERE,
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
        return float(x.account()["totalMarginBalance"]) + (panic_balance() or 0.0), x.now_ms()
    except Exception:
        return None, int(time.time() * 1000)


def panic_balance():
    """The sub-account's balance (None when the panic sleeve is off or unreadable)."""
    if not panic_on() or DRY:
        return None
    try:
        import os
        from binance_futures import Futures
        if "px" not in _X:
            _X["px"] = Futures(os.environ["PANIC_API_KEY"], os.environ["PANIC_API_SECRET"], testnet=TESTNET)
        return float(_X["px"].account()["totalMarginBalance"])
    except Exception:
        return None


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


def short_reason(line):
    """The 4h check's 'no order' reason, short enough for a phone line."""
    oi = re.search(r"open interest ([−+-]?[\d.]+)%", line)
    if oi:
        return f"OI {notify.num(float(oi.group(1).replace('−', '-')), 0, sign=True)}% (filter)"
    low = re.search(r"near its (\d+)-day low", line)
    if low:
        return f"OI at {low.group(1)}-day low (filter)"
    for key, short in (("no clear daily trend", "no trend"), ("stretched", "price stretched"), ("weekend", "weekend"),
                       ("PAUSE", "paused"), ("minimum", "size below minimum"), ("cap is full", "cap full")):
        if key in line:
            return short
    return notify.esc(line.replace("no order · ", "")) or "no order"


IND = "   "                                           # indent of a coin's detail lines


def status_message(title="📊 <b>Status</b>"):
    """Every coin as it is now, in lines short enough for a phone (about 30 characters): open trades and waiting orders
    first (live from Binance), then the coins without an order and why (from the last 4h check); then balance, open
    risk and the cap."""
    if DRY:
        return f"{title}{MODE}\nDry run: no account to read."
    x = exchange()
    eq, now = float(x.account()["totalMarginBalance"]), x.now_ms()
    pos, orders = x.positions(), x.open_algo_orders()
    last_close = now // TF_MS * TF_MS
    P = lambda s, v: notify.px(v, tick(s))
    blocks, idle, risk, upnl = [], [], 0.0, 0.0
    vt = volc_trade_syms()
    for s in SYMS:
        st, c = state(s), COIN[s]
        mine = [o for o in orders if o.get("symbol") == s]
        volc_only = s in pos and s in vt and not st.get("entry_ms") and not st.get("manual")   # listed under VOLC, not here
        if s in pos and not volc_only:
            price = x.last_price(s)
            amt, entry = pos[s]
            side = 1 if amt > 0 else -1
            pnl = amt * (price - entry)                 # (Binance's average entry; fees not included)
            entry = st.get("fill_px") or entry
            d = float(st.get("sl_dist") or 0)
            stops = [float(o.get("triggerPrice") or 0) for o in mine if not str(o.get("clientAlgoId", "")).startswith("vc_")
                     and (str(o.get("closePosition")).lower() == "true" or str(o.get("reduceOnly")).lower() == "true")]
            stop = (max(stops) if side > 0 else min(stops)) if stops else None
            upnl += pnl
            if stop:
                risk += max(0.0, side * (entry - stop)) * abs(amt)
            stage = stop_stage(st, STRAT.get(s, {}))
            held = notify.held(now - st["entry_ms"]) if st.get("entry_ms") else "?"
            blocks.append([f"<b>{c} ● {'long' if side > 0 else 'short'}</b> {notify.num(side * (price - entry) / d if d else 0, 2, sign=True)}R"
                           f" · {notify.usd(pnl, sign=True)}",
                           f"{IND}{P(s, entry)} → {P(s, price)}",
                           f"{IND}SL {P(s, stop)}{stage} · {held}" if stop else f"{IND}⚠️ <b>SL not found on Binance</b> · {held}"])
            continue
        entries = [o for o in mine if str(o.get("clientAlgoId", "")).startswith("tbo_in_")]   # (not the VOLC sleeve's vc_in_)
        held_back = not entries and st.get("entry_trig") and not st.get("entry_qty")
        if entries or held_back:
            price = x.last_price(s)
            o = entries[0] if entries else {}
            side = (1 if o.get("side") == "BUY" else -1) if o else (st.get("entry_side") or 1)
            trig = float(o.get("triggerPrice") or 0) if o else float(st["entry_trig"])
            d = float(st.get("sl_dist") or 0)
            qty = float(o.get("quantity") or st.get("entry_qty") or 0) if o else 0.0
            blk = [f"<b>{c} {'▲ buy' if side > 0 else '▼ sell'} stop</b> {P(s, trig)}",
                   f"{IND}price {P(s, price)} · {notify.num(side * (trig / price - 1) * 100, 2)}% away"]
            blk.append(f"{IND}SL {P(s, trig - side * d)} · risk {notify.usd(qty * d)}" if o else f"{IND}held back: cap full")
            blocks.append(blk)
            continue
        ck = st.get("check") or {}
        line = ck.get("line", "")
        if ck.get("t") != last_close:
            idle.append(f"{c} · waiting for its 4h check")
        elif line.startswith(("▲", "▼", "●")):
            idle.append(f"{c} · order used, next {notify.when(last_close + TF_MS, day=False)}")
        else:
            idle.append(f"{c} · {short_reason(line)}")
    sub = panic_balance()
    if sub is not None:
        eq += sub                                       # the bot sizes on main + sub-account (one pool)
    _, cap = risk_text(eq)
    out = [f"{title} · {notify.when(now)}{MODE}"]
    for blk in blocks:
        out += [""] + blk
    out += panic_lines(x, now)
    out += volc_lines(x, now)
    if idle:
        out += ["", "<b>No order</b>"] + idle
    out += ["", f"Balance <b>{notify.usd(eq)}</b>" + (f" ({notify.usd(upnl, sign=True)} open)" if pos else "")]
    if sub is not None:
        out.append(f"{IND}main {notify.usd(eq - sub)} · panic {notify.usd(sub)}")
    if eq:
        out.append(f"Risk {risk / eq * 100:.1f}%" + (f" of {cap:g}% cap" if cap else "") + f" · {notify.usd(risk)}")
    if (HERE / "PAUSE").exists():
        out.append("⏸ Paused (PAUSE file)")
    elif weekend(now):
        out.append(f"🌙 No new orders till {notify.when(orders_resume(now))}")
    return "\n".join(out)


def panic_lines(x, now):
    """The panic sleeve's open trades (state_panic.json), in the same short phone lines; nothing when none is open."""
    if not panic_on():
        return []
    try:
        st = json.loads((HERE / f"state_panic{'_testnet' if TESTNET else ''}.json").read_text())
    except (OSError, ValueError):
        st = {"trades": {}}
    cfg = json.loads((HERE / "panic.json").read_text()); hold = int(cfg.get("signal", {}).get("hold_h", 12))
    out = []
    for s_, tr in st.get("trades", {}).items():
        price = x.last_price(s_); P = lambda v: notify.px(v, tick(s_))
        r = price / tr["entry"] - 1; left = max(0, tr["entry_ms"] + hold * 3_600_000 - now)
        out += ["", f"<b>{s_[:-4]} ⚡ panic</b> {notify.pct(r * 100, sign=True)} · {notify.usd((price - tr['entry']) * tr['qty'], sign=True)}",
                f"{IND}{P(tr['entry'])} → {P(price)}",
                f"{IND}TP {P(tr['tp']) if tr.get('tp') else '-'} · SL {P(tr['entry'] if tr.get('be_done') else tr['stop'])}",
                f"{IND}closes in {notify.held(left)}"]
    return out


def volc_lines(x, now):
    """The VOLC sleeve's open trades (state_volc.json); nothing when none is open."""
    if not volc_on():
        return []
    try:
        st = json.loads((HERE / f"state_volc{'_testnet' if TESTNET else ''}.json").read_text())
        hold = int(json.loads((HERE / "volc.json").read_text()).get("signal", {}).get("hold_h", 36))
    except (OSError, ValueError):
        return []
    out = []
    for s_, tr in st.get("trades", {}).items():
        price = x.last_price(s_); P = lambda v: notify.px(v, tick(s_)); side = tr["side"]
        r = side * (price - tr["entry"]) / tr["dist"] if tr.get("dist") else 0.0
        left = max(0, tr["entry_ms"] + hold * 3_600_000 - now)
        out += ["", f"<b>{s_[:-4]} 🌀 VOLC {'long' if side > 0 else 'short'}</b> {notify.num(r, 2, sign=True)}R",
                f"{IND}{P(tr['entry'])} → {P(price)}",
                f"{IND}TP {P(tr['tp'])} · SL {P(tr['stop'])}",
                f"{IND}closes in {notify.held(left)}"]
    return out


def startup_message():
    eq, _ = account()
    rows = [f"🟢 <b>TBO v{bot_version()} online</b>{MODE}",
            f"Balance <b>{notify.usd(eq)}</b>" if eq is not None else "Balance not readable right now",
            "⚡ Panic sleeve on (sub-account)" if panic_on() else "",
            "🌀 VOLC sleeve on (main account)" if volc_on() else "",
            "/status for details"]
    rows = [r for r in rows if r]
    publish("\n".join(rows))


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
    if panic_on():
        start(PANIC)                                 # the panic sleeve on the sub-account
    if volc_on():
        start(VOLC)                                  # the VOLC sleeve on the main account (v3.1)
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
                    name = "Panic sleeve" if c == PANIC else "VOLC sleeve" if c == VOLC else COIN.get(cfg_of(c)['strategy']['symbol'], c)
                    notify.send(f"♻️ <b>{name}</b> {'' if c in (PANIC, VOLC) else 'bot '}stopped (exit code {p.returncode}) · restarting in {wait} s")
                    time.sleep(wait); start(c)
    except KeyboardInterrupt:
        print("stopping all bots (stop-losses stay on Binance)", flush=True)
        notify.send("🔴 <b>TBO stopped</b>\nOpen trades keep their stop loss on Binance; no new orders until it runs again.", wait=True)
        for p, _ in procs.values():
            p.terminate()


if __name__ == "__main__":
    main()
