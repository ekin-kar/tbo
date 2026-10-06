"""Walk-forward ensembles (top-K configs on past data, equal risk split) and a drawdown risk throttle."""
import pickle, sys
import numpy as np, pandas as pd
import common as C
from wf_eval import combos, trades, stream, mar, TESTS, report, base_id, SYM


def topk(y, k):
    yrs = (pd.Timestamp(f"{y}-01-01") - pd.Timestamp("2020-03-01")).days / 365.25
    sc = np.array([mar(stream(trades[i], "2020-03-01", f"{y}-01-01"), yrs)[0] for i in range(len(combos))])
    return list(np.argsort(-sc)[:k])


def ensemble(k):
    parts = []
    for y in TESTS:
        ids = topk(y, k)
        for i in ids:
            x = stream(trades[i], f"{y}-01-01", f"{y + 1}-01-01").copy(); x["R"] /= k
            parts.append(x)
    return pd.concat(parts).sort_values("exit_time")


def throttle(x, dd_R=4.0, mult=0.5):
    """Risk x mult while the closed-trade equity is more than dd_R below its peak (in full-risk R)."""
    r = x.R.to_numpy(); out = np.empty(len(r)); eq = pk = 0.0
    for i, v in enumerate(r):
        m = mult if pk - eq > dd_R else 1.0
        out[i] = v * m; eq += out[i]; pk = max(pk, eq)
    y = x.copy(); y["R"] = out
    return y


if __name__ == "__main__":
    res = {}
    for k in (1, 5, 10, 25, 50):
        x = ensemble(k); res[k] = x
        report(x, f"walk-forward top-{k} ensemble")
    pickle.dump(res, open(C.D.CACHE / f"wf_ens_{SYM}.pkl", "wb"))
    for k in (1, 10):
        for dd, mult in ((3, 0.5), (5, 0.5), (8, 0.5)):
            report(throttle(res[k], dd, mult), f"top-{k} + throttle {mult}x beyond -{dd}R")
