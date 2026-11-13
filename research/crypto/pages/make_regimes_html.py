"""reports/market_regimes.html: the crypto market regime engine (research/crypto/core/crypto_regimes.py) - BTC / ETH daily
price coloured by regime (RB / TS / HM), how many days each state has in 2020-23 and 2024-26, the v3.1 trades by state
(research/results/v32_regime_census*.csv), the feature quintiles and the v3.1 vs v3.2 balance / drop from $300 (2024 run).
    python research/crypto/pages/make_regimes_html.py"""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]
import json, os
os.environ.setdefault("BOT_TRADES", "v31")
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


def main(v32=None):
    view = pd.read_csv(RES / "v32_regime_census_view.csv")
    data = dict(coins={s[:-4]: series(s) for s in ("BTCUSDT", "ETHUSDT")}, shares={s[:-4]: shares(s) for s in ("BTCUSDT", "ETHUSDT")},
                desc=DESC, centroids=centroids(), fit={k: v for k, v in R.frozen().items() if k != "centroids"},
                census=view.replace({np.nan: None}).to_dict("records"), quint=json.loads((RES / "v32_quintiles.json").read_text()),
                curves=json.loads((RES / "v32_curves.json").read_text()) if (RES / "v32_curves.json").exists() else None)
    html = (pathlib.Path(__file__).resolve().parent / "regimes_template.html").read_text(encoding="utf-8").replace(
        "/*DATA*/null", json.dumps(data, separators=(",", ":")))
    (C.ROOT / "reports" / "market_regimes.html").write_text(html, encoding="utf-8")
    print("written market_regimes.html", len(html) // 1024, "KB")


if __name__ == "__main__":
    main()
