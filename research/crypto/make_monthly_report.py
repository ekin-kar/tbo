"""cryptobot/monthly_report.html: TBO, BTC+ETH+BNB+SOL+ADA at the bot's config risks (read from the configs), shorts at
short_risk_mult, no open-risk cap (like the bot), starting balance START.
Two runs: from Mar 2020 and a fresh start in Jan 2024 (the period no choice was based on)."""
import json, pickle
import numpy as np, pandas as pd
import common as C
from portfolio import simulate

ALL = pickle.load(open(C.D.CACHE / "portfolio_trades_v24.pkl", "rb"))
COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
T4 = pd.concat([ALL[(s, 0.0003)] for s in COINS])
CFG = {s: json.load(open(C.ROOT / "cryptobot" / f"config_{s[:-4].lower()}.json")) for s in COINS}
BASE = CFG["BTCUSDT"]["risk_pct"] / 100
W = {s: CFG[s]["risk_pct"] / 100 / BASE for s in COINS}
SM = CFG["BTCUSDT"]["short_risk_mult"]
START = 200.0


def build(start):
    cv, tk = simulate(T4, risk=BASE, cap=99, short_mult=SM, start=start, eq0=START, weights=W)
    tk = tk.sort_values("exit_time").copy()
    tk["kind"] = np.where(tk.R > 0.2, "win", np.where(tk.R < -0.2, "loss", "be"))
    daily = cv.equity.resample("1D").last().ffill()
    worst = cv.worst.resample("1D").min().ffill()
    first = pd.Timestamp(start)
    months = pd.period_range(first.to_period("M"), "2026-09", freq="M")
    bal_end = cv.equity.resample("ME").last().reindex([m.to_timestamp("M") for m in months]).ffill().fillna(START).to_numpy()
    rows = []; prev = START; peak = START
    for m, end in zip(months, bal_end):
        t = tk[tk.exit_time.dt.to_period("M") == m]
        peak = max(peak, end)
        best = t.loc[t.pnl.idxmax()] if len(t) else None
        rows.append(dict(month=str(m), start=round(prev, 2), end=round(float(end), 2), chg=round(float(end - prev), 2),
                         pct=round(float(end / prev - 1) * 100, 2), trades=int(len(t)), wins=int((t.kind == "win").sum()),
                         be=int((t.kind == "be").sum()), losses=int((t.kind == "loss").sum()),
                         best=f"{best.sym[:-4]} {'long' if best.dir > 0 else 'short'} +${best.pnl:,.0f}" if best is not None and best.pnl > 0 else "-",
                         dd=round(float(end / peak - 1) * 100, 1)))
        prev = float(end)
    mo = pd.Series([r["pct"] for r in rows])
    years = []
    for y in sorted({r["month"][:4] for r in rows}):
        ry = [r for r in rows if r["month"].startswith(y)]
        t = tk[tk.exit_time.dt.year == int(y)]
        wy = worst[worst.index.year == int(y)].to_numpy()       # same method as the overall figure: worst-case curve vs its own peak
        pk = np.maximum.accumulate(np.r_[ry[0]["start"], wy])[1:] if len(wy) else np.array([1.0])
        ddy = float(((wy / pk) - 1).min() * 100) if len(wy) else 0.0
        years.append(dict(year=y + (" (to Sep)" if y == "2026" else ""), start=ry[0]["start"], end=ry[-1]["end"],
                          pct=round((ry[-1]["end"] / ry[0]["start"] - 1) * 100, 1), trades=int(len(t)),
                          best=max(r["pct"] for r in ry), worst=min(r["pct"] for r in ry), pos=sum(r["pct"] > 0 for r in ry), n=len(ry),
                          dd=round(ddy, 1)))
    # drawdowns
    pkc = cv.equity.cummax(); ddc = float(((cv.equity / pkc) - 1).min() * 100)
    pkw = cv.worst.cummax(); ddw = float(((cv.worst / pkw) - 1).min() * 100)
    hw = daily.cummax(); nh = daily.index[daily >= hw]; gaps = np.diff(nh.values).astype("timedelta64[D]").astype(int)
    streak = best_streak = 0
    for k in tk.kind:
        streak = streak + 1 if k == "loss" else (streak if k == "be" else 0); best_streak = max(best_streak, streak)
    wins, losses = tk[tk.pnl > 0], tk[tk.pnl < 0]
    nmon = len(rows)
    summary = dict(final=round(float(bal_end[-1]), 2), total=round((bal_end[-1] / START - 1) * 100, 1), start=START,
                   cagr=round(((bal_end[-1] / START) ** (12 / nmon) - 1) * 100, 1), mavg=round(((bal_end[-1] / START) ** (1 / nmon) - 1) * 100, 2),
                   mmed=round(float(mo.median()), 2), mpos=int((mo > 0).sum()), mn=nmon, mbest=round(float(mo.max()), 1), mworst=round(float(mo.min()), 1),
                   ddc=round(ddc, 1), ddw=round(ddw, 1), flat=int(gaps.max()) if len(gaps) else 0,
                   trades=int(len(tk)), tpm=round(len(tk) / nmon, 1), winp=round((tk.kind == "win").mean() * 100, 1),
                   bep=round((tk.kind == "be").mean() * 100, 1), lossp=round((tk.kind == "loss").mean() * 100, 1),
                   avgwin=round(float(wins.pnl.mean()), 2), avgloss=round(float(losses.pnl.mean()), 2),
                   pf=round(float(wins.pnl.sum() / -losses.pnl.sum()), 2), bigwin=round(float(tk.pnl.max()), 2), bigloss=round(float(tk.pnl.min()), 2),
                   streak=int(best_streak), hold=round(float(tk.hours.mean()), 1),
                   longpnl=round(float(tk[tk.dir > 0].pnl.sum()), 2), shortpnl=round(float(tk[tk.dir < 0].pnl.sum()), 2),
                   longn=int((tk.dir > 0).sum()), shortn=int((tk.dir < 0).sum()))
    coins = [dict(coin=s[:-4], trades=int((tk.sym == s).sum()), winp=round(float((tk[tk.sym == s].kind == "win").mean() * 100), 1),
                  pnl=round(float(tk[tk.sym == s].pnl.sum()), 2), R=round(float(tk[tk.sym == s].R.sum()), 1),
                  best=round(float(tk[tk.sym == s].pnl.max()), 2)) for s in COINS]
    top = tk.nlargest(10, "pnl")
    tops = [dict(date=str(r.entry_time.date()), coin=r.sym[:-4], side="long" if r.dir > 0 else "short", R=round(float(r.R), 1),
                 pnl=round(float(r.pnl), 2), days=round(float(r.hours) / 24, 1)) for r in top.itertuples()]
    curve = [[int(t.value // 10**6), round(float(v), 2)] for t, v in daily.items()]
    return dict(rows=rows, years=years, summary=summary, coins=coins, tops=tops, curve=curve)


data = {"2020": build("2020-03-01"), "2024": build("2024-01-01"),
        "cfg": dict(risks={s[:-4]: CFG[s]["risk_pct"] for s in COINS}, smult=SM, start=START)}
html = open("monthly_report_template.html").read().replace("/*DATA*/null", json.dumps(data))
(C.ROOT / "cryptobot" / "monthly_report.html").write_text(html)
for k in ("2020", "2024"):
    print(k, data[k]["summary"])
