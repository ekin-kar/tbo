"""reports/market_regimes.html: the crypto market regime engine (research/crypto/core/crypto_regimes.py) - BTC / ETH daily
price coloured by regime (RB / TS / HM), how many days each state has in 2020-23 and 2024-26, the v3.1 trades by state
(research/results/v32_regime_census*.csv), the feature quintiles and v3.1 vs v3.2 as deployed (botsim: TBO + panic + VOLC, each
with its own ladder), balance / drop from $300 (2024 run).
    python research/crypto/pages/make_regimes_html.py"""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]
import json, os
os.environ.setdefault("BOT_TRADES", "v32")
import numpy as np, pandas as pd
import common as C
import crypto_regimes as R

RES = C.ROOT / "research" / "results"
DESC = {
    "RB": {"UpClean": "20-day move in the top third, efficient, little overlap", "UpChop": "up 20 days but choppy (overlap high or efficiency low)",
           "FlatCalm": "no 20-day trend, volatility below its median", "FlatWild": "no 20-day trend, volatility above its median",
           "DownChop": "down 20 days but choppy", "DownClean": "20-day move in the bottom third, efficient"},
}


def series(sym):
    r = R.regimes(sym)
    r = r[r.index >= "2020-03-01"]
    return dict(t=[str(d.date()) for d in r.index], c=[round(float(v), 6) for v in r.c], RB=r.RB.tolist(), TS=r.TS.tolist(), HM=r.HM.tolist())


def shares(sym):
    r = R.regimes(sym); out = {}
    for clf in ("RB", "TS", "HM"):
        dev = r[r.index < R.DEV_END][clf].value_counts(normalize=True); oos = r[r.index >= R.DEV_END][clf].value_counts(normalize=True)
        out[clf] = {k: [round(float(dev.get(k, 0)) * 100, 1), round(float(oos.get(k, 0)) * 100, 1)] for k in sorted(set(dev.index) | set(oos.index)) if k != "na"}
    return out


def centroids():
    F = R.frozen()
    return {f"H{k}": dict(zip(R.CORE7, [round(v, 2) for v in c])) for k, c in enumerate(F["centroids"])}


V31_LADDER = [(0, 5.7, 3.8, 0.7885, 6.27), (1000, 4.75, 3.135, 0.7885, 5.225), (10000, 2.375, 1.615, 0.399, 2.6125)]   # v3.1's portfolio.json


def deployed_curves(a="2024-01-01", b="2026-11-07", eq0=300.0):
    """Daily balance and drop of v3.1 (no size column, its ladder) and v3.2 (botsim's default: size column, portfolio.json)."""
    import botsim as B
    pf31 = dict(B.PF, risk_ladder=[{"from_usdt": f, "BTCUSDT": bt, "ETHUSDT": et, "BNBUSDT": al, "SOLUSDT": al, "ADAUSDT": al, "cap_pct": cp}
                                   for f, bt, et, al, cp in V31_LADDER])
    keep = B.TR[:, 6].copy()
    try:
        B.TR[:, 6] = 1.0
        h31 = B.history(B.bot_policy(pf31), a, b, eq0, full=True)
    finally:
        B.TR[:, 6] = keep
    h32 = B.history(B.bot_policy(), a, b, eq0, full=True)
    ser = lambda h: dict(bal=[round(float(v), 2) for v in h["bal"]], dd=[round(float(-v), 2) for v in h["dd"]])
    lab = B.label(B.bot_policy())
    return dict(t=[str(d.date()) for d in h32["bal"].index], series={"v3.1 (until 13 Nov 2026)": ser(h31), "v3.2 (deployed)": ser(h32)},
                note=(f"TBO v3.2 = v3.1 + the wild-pullback size (x0.25 when the coin's daily ATR14 / ATR100 >= 0.98 and the last 5 days "
                      f"moved >= 0.25 ATR against the order, at its 4h arming close), ladder {lab}. v3.1: ladder 5.7 / 3.8 / 0.79% -> "
                      f"4.75 / 3.135 / 0.79% from $1,000 -> 2.375 / 1.615 / 0.40% from $10,000. Whole system (TBO + panic + VOLC), "
                      f"from $300 on 1 Jan 2024 (botsim, as every page)."),
                notes=["Regime-conditional exits, vetoes, early cuts, short-side exits, BTC-chop risk, breadth risk, funding extremes, "
                       "smooth / 3-tier VolReg sizing and an engine-exact skip: none passed the gates (v32 / v32b / v32c reports).",
                       "The wild-pullback size-down passed all four gates on the bot's own cap rule (plateau 100%, 98-99% of nulls, "
                       "92.5-100% of 40 phase copies); on the 14 untouched coins it helps in 2020-23 and lowers the 2024-26 drop, net "
                       "there slightly negative (research/results/v32c_REPORT.md)."])


def main(v32=None):
    view = pd.read_csv(RES / "v32_regime_census_view.csv")
    data = dict(coins={s[:-4]: series(s) for s in ("BTCUSDT", "ETHUSDT")}, shares={s[:-4]: shares(s) for s in ("BTCUSDT", "ETHUSDT")},
                desc=DESC, centroids=centroids(), fit={k: v for k, v in R.frozen().items() if k != "centroids"},
                census=view.replace({np.nan: None}).to_dict("records"), quint=json.loads((RES / "v32_quintiles.json").read_text()),
                curves=deployed_curves())
    html = (pathlib.Path(__file__).resolve().parent / "regimes_template.html").read_text(encoding="utf-8").replace(
        "/*DATA*/null", json.dumps(data, separators=(",", ":")))
    (C.ROOT / "reports" / "market_regimes.html").write_text(html, encoding="utf-8")
    print("written market_regimes.html", len(html) // 1024, "KB")


if __name__ == "__main__":
    main()
