"""Stage 2: anchored walk-forward. For each test year pick the config with the best return/drawdown on all
earlier data, record its trades in the test year; compare the stitched out-of-sample result with TBO v1.0."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
import pickle, sys
import numpy as np, pandas as pd
import common as C

SYM = sys.argv[1] if len(sys.argv) > 1 else "BTCUSDT"
z = pickle.load(open(C.D.CACHE / f"wf_{SYM}.pkl", "rb"))
combos, trades = z["combos"], z["trades"]
BASE = dict(tf=240, n=20, sl_atr=1.5, hold_h=120, ema_n=50, sides="long", trail=(12, 2.0), slope_d=0,
            no_weekend=False, be_R=0.0)
base_id = combos.index(BASE)
TESTS = [2022, 2023, 2024, 2025, 2026]


def stream(tr, a, b):
    x = tr[(tr.entry_time >= a) & (tr.entry_time < b)].sort_values("exit_time")
    return x


def mar(x, years):
    if len(x) < 25 * years:
        return -np.inf, 0, 0
    r = x.R.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    yr = x.groupby(x.entry_time.dt.year).R.sum()
    if (yr < 0).sum() > 1:
        return -np.inf, r.sum(), dd
    return r.sum() / years / max(dd, 3.0), r.sum(), dd


def evaluate(pick_fn, label):
    oos, picks = [], []
    for y in TESTS:
        i = pick_fn(y)
        picks.append(i)
        oos.append(stream(trades[i], f"{y}-01-01", f"{y + 1}-01-01"))
    x = pd.concat(oos)
    return x, picks


def best_on_train(y):
    yrs = (pd.Timestamp(f"{y}-01-01") - pd.Timestamp("2020-03-01")).days / 365.25
    sc = [mar(stream(trades[i], "2020-03-01", f"{y}-01-01"), yrs)[0] for i in range(len(combos))]
    return int(np.argmax(sc))


def report(x, label):
    r = x.R.to_numpy(); eq = np.cumsum(r); dd = (np.maximum.accumulate(np.r_[0, eq])[1:] - eq).max()
    yrs = 4.75
    out = dict(label=label, trades=len(r), R=round(r.sum(), 1), R_yr=round(r.sum() / yrs, 1), DD_R=round(dd, 1),
               MAR=round(r.sum() / yrs / dd, 2), by_year=x.groupby(x.entry_time.dt.year).R.sum().round(1).to_dict())
    for risk in (0.02, 0.03):
        e = 1000 * np.cumprod(1 + risk * r); pk = np.maximum.accumulate(e)
        out[f"{int(risk*100)}%: $/mo%"] = f"{((e[-1] / 1000) ** (1 / (yrs * 12)) - 1) * 100:.1f}%/mo, DD {((pk - e) / pk).max() * 100:.0f}%"
    print(out)


if __name__ == "__main__":
    xb, _ = evaluate(lambda y: base_id, "TBO v1.0 fixed")
    report(xb, "TBO v1.0 fixed (2022-2026)")
    xw, picks = evaluate(best_on_train, "walk-forward")
    report(xw, "walk-forward best-on-past")
    for y, i in zip(TESTS, picks):
        print(y, combos[i])
    # how much does in-sample selection flatter? best config chosen on ALL data, measured on the same years
    yrs_all = 4.75
    sc = [mar(stream(trades[i], "2022-01-01", "2026-10-01"), yrs_all)[0] for i in range(len(combos))]
    ib = int(np.argmax(sc))
    report(stream(trades[ib], "2022-01-01", "2026-10-01"), "hindsight best (cheating, for scale)")
    print(combos[ib])
    pickle.dump(dict(xw=xw, xb=xb, picks=picks), open(C.D.CACHE / f"wf_eval_{SYM}.pkl", "wb"))
