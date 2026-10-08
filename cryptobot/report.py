"""
Results report from Binance (read-only: places no orders). Run it after the trial and send the files in
cryptobot/reports/ (plus the cryptobot/logs/ folder) for the comparison with the backtest.

    python report.py                  # the last 90 days
    python report.py --days 31        # the last 31 days (run it at the end of every month: Binance keeps only
                                      # a few months of history, and the monthly files then cover the whole trial)
    python report.py --testnet

Writes reports/report_<date>.md (summary), reports/trades_<date>.csv (one row per trade: open -> flat) and
reports/income_<date>.csv (every PnL / fee / funding / transfer line).
"""
import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import notify                                            # noqa: E402
from binance_futures import Futures, BinanceError        # noqa: E402

DAY = 86_400_000
WEEK = 7 * DAY


def utc(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M")


def fetch_income(x, start, end):
    rows, t = [], start
    while t < end:
        try:
            page = x.income(t, min(t + WEEK, end) - 1)
        except BinanceError as e:
            print(f"income {utc(t)[:10]}: {e} (skipped: older than Binance keeps?)")
            page = []
        rows += page
        if len(page) >= 1000:                            # full page: continue right after its last row
            t = int(page[-1]["time"]) + 1
        else:
            t = min(t + WEEK, end)
        time.sleep(0.2)
    seen, out = set(), []
    for r in rows:                                       # pages can overlap by a row: drop duplicates
        k = (r.get("tranId"), r.get("incomeType"), r.get("symbol"), r.get("time"), r.get("income"))
        if k not in seen:
            seen.add(k); out.append(r)
    return sorted(out, key=lambda r: int(r["time"]))


def fetch_fills(x, sym, start, end):
    rows, t = {}, start
    while t < end:
        try:
            page = x.user_trades(sym, limit=1000, start_ms=t, end_ms=min(t + WEEK, end) - 1)
        except BinanceError as e:
            print(f"{sym} fills {utc(t)[:10]}: {e} (skipped: older than Binance keeps?)")
            page = []
        for r in page:
            rows[r["id"]] = r
        t = int(page[-1]["time"]) + 1 if len(page) >= 1000 else min(t + WEEK, end)
        time.sleep(0.2)
    return sorted(rows.values(), key=lambda r: (int(r["time"]), r["id"]))


def round_trips(sym, fills):
    """Fills -> trades (position from flat back to flat)."""
    out, pos, cur = [], 0.0, None
    for f in fills:
        q = float(f["qty"]) * (1 if f["side"] == "BUY" else -1)
        px, t = float(f["price"]), int(f["time"])
        if cur is None:
            cur = dict(symbol=sym, side="long" if q > 0 else "short", open=t, qty=0.0, cost=0.0, exit_qty=0.0, exit_cost=0.0,
                       pnl=0.0, fees=0.0, fills=0)
        opening = (q > 0) == (cur["side"] == "long")
        if opening:
            cur["qty"] += abs(q); cur["cost"] += abs(q) * px
        else:
            cur["exit_qty"] += abs(q); cur["exit_cost"] += abs(q) * px
        cur["pnl"] += float(f["realizedPnl"]); cur["fees"] += float(f["commission"]); cur["fills"] += 1
        pos = round(pos + q, 9)
        if pos == 0:
            cur["close"] = t; out.append(cur); cur = None
    if cur is not None:
        cur["close"] = None; out.append(cur)
    for tr in out:
        tr["entry"] = tr["cost"] / tr["qty"] if tr["qty"] else 0.0
        tr["exit"] = tr["exit_cost"] / tr["exit_qty"] if tr["exit_qty"] else None
        tr["hours"] = (tr["close"] - tr["open"]) / 3_600_000 if tr["close"] else None
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--testnet", action="store_true")
    a = ap.parse_args()
    notify.load_env(HERE / ".env")
    x = Futures(os.environ.get("BINANCE_API_KEY", ""), os.environ.get("BINANCE_API_SECRET", ""), testnet=a.testnet)
    syms = [json.loads(p.read_text())["strategy"]["symbol"] for p in sorted(HERE.glob("config_*.json"))]
    end = x.now_ms(); start = end - a.days * DAY
    print(f"reading {a.days} days of account history for {', '.join(syms)} ...")
    inc = fetch_income(x, start, end)
    trades = []
    for s in syms:
        try:
            trades += round_trips(s, fetch_fills(x, s, start, end))
        except BinanceError as e:
            print(f"{s}: {e}")
    trades.sort(key=lambda t: t["open"])
    acct = x.account()
    bal_now = float(acct["totalWalletBalance"]); eq_now = float(acct["totalMarginBalance"])

    by_type = defaultdict(float)
    for r in inc:
        by_type[r["incomeType"]] += float(r["income"])
    transfers = sum(float(r["income"]) for r in inc if r["incomeType"] in ("TRANSFER", "INTERNAL_TRANSFER", "COIN_SWAP_DEPOSIT", "COIN_SWAP_WITHDRAW"))
    trading = sum(v for k, v in by_type.items() if k not in ("TRANSFER", "INTERNAL_TRANSFER", "COIN_SWAP_DEPOSIT", "COIN_SWAP_WITHDRAW"))
    bal_start = bal_now - trading - transfers
    # daily wallet balance (closed trades, fees, funding, transfers) and the deepest fall from a peak
    daily, run, peak, dd = {}, bal_start, max(bal_start, 1e-9), 0.0
    for r in inc:
        run += float(r["income"]); daily[utc(int(r["time"]))[:10]] = run
        if r["incomeType"] not in ("TRANSFER", "INTERNAL_TRANSFER"):
            peak = max(peak, run); dd = max(dd, (peak - run) / peak if peak > 0 else 0)
        else:
            peak = max(peak, run)
    months = defaultdict(float)
    for r in inc:
        if r["incomeType"] not in ("TRANSFER", "INTERNAL_TRANSFER"):
            months[utc(int(r["time"]))[:7]] += float(r["income"])

    out = HERE / "reports"; out.mkdir(exist_ok=True)
    tag = datetime.now(timezone.utc).strftime("%Y%m%d")
    with open(out / f"trades_{tag}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "side", "open_utc", "close_utc", "hours", "qty", "entry", "exit", "pnl_usdt", "fees_usdt", "fills"])
        for t in trades:
            w.writerow([t["symbol"], t["side"], utc(t["open"]), utc(t["close"]) if t["close"] else "open", f"{t['hours']:.1f}" if t["hours"] else "",
                        f"{t['qty']:g}", f"{t['entry']:.6g}", f"{t['exit']:.6g}" if t["exit"] else "", f"{t['pnl']:.4f}", f"{t['fees']:.4f}", t["fills"]])
    with open(out / f"income_{tag}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["time_utc", "type", "symbol", "income", "asset", "info"])
        for r in inc:
            w.writerow([utc(int(r["time"])), r["incomeType"], r.get("symbol", ""), r["income"], r.get("asset", ""), r.get("info", "")])

    closed = [t for t in trades if t["close"]]
    net = [t["pnl"] - t["fees"] for t in closed]
    L = [f"# TBO results {utc(start)[:10]} .. {utc(end)[:10]} (UTC)", "",
         f"- Wallet balance at the start: {bal_start:.2f} USDT; now {bal_now:.2f} (equity with open trades {eq_now:.2f})",
         f"- Deposits / withdrawals in the period: {transfers:+.2f}",
         f"- Trading result: {trading:+.2f} USDT = realized PnL {by_type.get('REALIZED_PNL', 0):+.2f}, fees {by_type.get('COMMISSION', 0):+.2f}, "
         f"funding {by_type.get('FUNDING_FEE', 0):+.2f}" + "".join(f", {k} {v:+.2f}" for k, v in by_type.items()
                                                                   if k not in ("REALIZED_PNL", "COMMISSION", "FUNDING_FEE", "TRANSFER", "INTERNAL_TRANSFER")),
         f"- Deepest fall of the wallet balance from a peak (closed trades): {dd * 100:.1f}%",
         f"- Trades closed: {len(closed)} (open now: {len(trades) - len(closed)}); winners {sum(n > 0 for n in net)}, "
         f"losers {sum(n <= 0 for n in net)}; best {max(net, default=0):+.2f}, worst {min(net, default=0):+.2f}", "",
         "| Month | Result USDT |", "|---|---|"] + [f"| {m} | {v:+.2f} |" for m, v in sorted(months.items())] + [
         "", "| Coin | Trades | Net USDT | Fees |", "|---|---|---|---|"]
    for s in syms:
        ts = [t for t in closed if t["symbol"] == s]
        L.append(f"| {s} | {len(ts)} | {sum(t['pnl'] - t['fees'] for t in ts):+.2f} | {sum(t['fees'] for t in ts):.2f} |")
    L += ["", "Send this folder (`reports/`) and `logs/` for the comparison with the backtest of the same days."]
    (out / f"report_{tag}.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))
    print(f"\nwritten: {out / f'report_{tag}.md'}, trades_{tag}.csv, income_{tag}.csv")


if __name__ == "__main__":
    main()
