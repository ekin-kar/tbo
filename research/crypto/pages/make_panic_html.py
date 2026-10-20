"""reports/panic.html: the panic sleeve (cryptobot/panic.py) - rules, the bot alone vs bot + sleeve (bot's real sizing
from $300), every sleeve trade, one-setting-at-a-time plateaus, the exit study. research/crypto/core/panic_sleeve.py."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import json
import numpy as np, pandas as pd
import common as C
import botsim as B
import panic_sleeve as PSL

END = "2026-10-01"; EQ0 = 300.0
STARTS = {"2022": "2022-01-01", "2024": "2024-01-01"}


def series(a, ev=None):
    r = PSL.run(a, END, ev=ev, keep="events")
    e = pd.DataFrame(r["events"], columns=["t", "bal", "worst"])
    e["t"] = pd.Timestamp(a) + pd.to_timedelta(e.t, unit="m"); e = e.set_index("t")
    idx = pd.date_range(pd.Timestamp(a), pd.Timestamp(END) - pd.Timedelta(days=1), freq="D")
    bal = e.bal.resample("D").last().reindex(idx).ffill().fillna(EQ0)
    w = e.worst.resample("D").min().reindex(idx).ffill().fillna(EQ0)
    dd = (w / np.maximum.accumulate(np.maximum(w.values, 1e-9)) - 1) * 100
    return r, bal, dd


def stats(ev):
    w, lo = ev.ret[ev.ret > 0], ev.ret[ev.ret <= 0]
    return dict(n=int(len(ev)), events=int(ev.t.nunique()), win=float((ev.ret > 0).mean() * 100) if len(ev) else 0.0,
                avg=float(ev.ret.mean() * 100) if len(ev) else 0.0, avg_win=float(w.mean() * 100) if len(w) else 0.0,
                avg_loss=float(lo.mean() * 100) if len(lo) else 0.0, pf=float(w.sum() / -lo.sum()) if len(lo) and lo.sum() < 0 else None,
                worst=float(ev.ret.min() * 100) if len(ev) else 0.0)


def variant(units=PSL.UNITS, **kw):
    ev = PSL.events(**kw)
    out = dict(stats(ev))
    for k, a in STARTS.items():
        r = PSL.run(a, END, ev=ev, units=units); out[f"usd{k}"] = r["final"]; out[f"dd{k}"] = r["dd"]
    return out


SWEEPS = [
    ("window_h", "Window (hours the drop and the OI fall are measured over)", (2, 3, 4, 6, 8), lambda v: f"{v} h"),
    ("move_k", "Price fall (x the normal move for that window)", (0.5, 1.0, 1.5, 2.0, 2.5, 3.0), lambda v: f"{v:g}x"),
    ("oi_drop", "Open-interest fall", (0.08, 0.10, 0.12, 0.15, 0.20), lambda v: f"-{v * 100:g}%"),
    ("premium_z", "Futures discount (premium z-score)", (None, -0.5, -1.0, -1.5, -2.0), lambda v: "off" if v is None else f"<= {v:g}"),
    ("hold_h", "Maximum hold", (6, 8, 12, 18, 24), lambda v: f"{v} h"),
    ("tp_atr", "Take-profit", (0.0, 2.0, 2.5, 3.0, 3.5, 4.0), lambda v: "none" if not v else f"+{v:g} ATR"),
    ("be_atr", "Stop to the entry after", (0.0, 1.0, 1.5, 2.0, 3.0), lambda v: "never" if not v else f"+{v:g} ATR"),
    ("stop_atr", "Stop", (2.0, 3.0, 4.0, 6.0), lambda v: f"-{v:g} ATR"),
    ("stop_max", "Stop never more than ... below the entry", (1.0, 0.25, 0.20, 0.15, 0.10), lambda v: "no limit" if v >= 1 else f"-{v * 100:g}%"),
    ("units", "Size (units per panic event)", (1.0, 2.0, 3.0, 4.0, 6.0), lambda v: f"{v:g}"),
]

if __name__ == "__main__":
    ev = PSL.events()
    data = dict(params=PSL.P0, units=PSL.UNITS, coins=[c[:-4] for c in PSL.COINS], runs={}, years=[], sweeps=[], trades=[])
    for k, a in STARTS.items():
        r0, b0, d0 = series(a); r1, b1, d1 = series(a, ev)
        data["runs"][k] = dict(t0=a, bot=dict(final=r0["final"], dd=r0["dd"], bal=[float(f"{v:.4g}") for v in b0.values], ddser=[round(float(v), 2) for v in d0]),
                               both=dict(final=r1["final"], dd=r1["dd"], bal=[float(f"{v:.4g}") for v in b1.values], ddser=[round(float(v), 2) for v in d1]))
    for y in range(2022, 2027):
        a, b = f"{y}-01-01", (f"{y + 1}-01-01" if y < 2026 else END)
        r0, r1 = PSL.run(a, b), PSL.run(a, b, ev=ev); e = ev[(ev.t >= a) & (ev.t < b)]
        data["years"].append(dict(y=y, bot=r0["final"] / EQ0 * 100 - 100, both=r1["final"] / EQ0 * 100 - 100, bot_dd=r0["dd"], both_dd=r1["dd"],
                                  n=int(len(e)), avg=float(e.ret.mean() * 100) if len(e) else None))
    data["sleeve"] = stats(ev)
    data["exits"] = {k: int(v) for k, v in ev.why.value_counts().items()}
    data["held_h"] = float(((ev.t_exit - ev.t).dt.total_seconds() / 3600).mean())
    for _, r in ev.iterrows():
        data["trades"].append(dict(t=r.t.strftime("%Y-%m-%d %H:%M"), coin=r.sym[:-4], move=round(float(r.move) * 100, 1), rz=round(float(r.rz), 2),
                                   oi=round(float(r.doi) * 100, 1), pz=round(float(r.pz), 2), entry=float(f"{r.entry:.6g}"), exit=float(f"{r.exit:.6g}"),
                                   ret=round(float(r.ret) * 100, 2), why=r.why, n=int(r.n), held=round((r.t_exit - r.t).total_seconds() / 3600, 1)))
    base = {k: PSL.run(a, END)["final"] for k, a in STARTS.items()}
    base_dd = {k: PSL.run(a, END)["dd"] for k, a in STARTS.items()}
    data["base"] = dict(usd2022=base["2022"], usd2024=base["2024"], dd2022=base_dd["2022"], dd2024=base_dd["2024"])
    for key, title, vals, lab in SWEEPS:
        rows = []
        for v in vals:
            kw = {} if key == "units" else {key: v}
            st = variant(units=v if key == "units" else PSL.UNITS, **kw)
            chosen = (v == PSL.UNITS) if key == "units" else (v == PSL.P0[key])
            rows.append(dict(label=lab(v), chosen=bool(chosen), **st))
            print(key, lab(v), round(st["usd2022"]), round(st["dd2022"], 1), round(st["usd2024"]), round(st["dd2024"], 1), st["n"], flush=True)
        data["sweeps"].append(dict(key=key, title=title, rows=rows))
    html = (pathlib.Path(__file__).resolve().parent / "panic_template.html").read_text().replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
    (C.ROOT / "reports" / "panic.html").write_text(html)
    for k in STARTS:
        print(k, "bot", round(data["runs"][k]["bot"]["final"]), round(data["runs"][k]["bot"]["dd"], 1), "| bot + sleeve", round(data["runs"][k]["both"]["final"]), round(data["runs"][k]["both"]["dd"], 1))
    print("written", len(html) // 1024, "KB")
