"""Ideas 8 (size by trend strength) and 9 (several channel lengths), scored like ideas_v3.py."""
import sys, pathlib; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parents[1] / d) for d in ("core", "studies")]  # research/crypto layout
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import tradesim as T
from ideas_v3 import score

COINS = T.COINS


def lengths(args):
    sym, n = args
    x = T.base_trades(sym, n=n)
    return sym, n, pd.DataFrame(dict(sym=sym, entry_time=x.entry_time, exit_time=x.exit_time, dir=x.dir, R=x.R, size=1.0))


if __name__ == "__main__":
    X = pd.read_pickle(C.D.CACHE / "loser_features.pkl")
    base = pd.DataFrame(dict(sym=X.sym + "USDT", entry_time=X.entry_time, exit_time=X.exit_time, dir=X.side, R=X.R, size=1.0))
    b = score(base)
    dev = (X.entry_time < "2024-01-01").to_numpy()
    print("=== 8: size by trend strength: top third of the measure x1.5, bottom third x0.5 (cutoffs from 2020-23) ===")
    print(f"{'measure':34s} {'dev ratio':>10s} {'ho ratio':>10s}   (base {b['dev']['ratio']:.2f} / {b['ho']['ratio']:.2f})")
    rng = np.random.default_rng(0)
    rnd = []
    for _ in range(300):
        sz = rng.permutation(np.r_[np.full(len(X) // 3, 1.5), np.full(len(X) // 3, 0.5), np.ones(len(X) - 2 * (len(X) // 3))])
        s = score(base.assign(size=sz)); rnd.append((s["dev"]["ratio"] / b["dev"]["ratio"], s["ho"]["ratio"] / b["ho"]["ratio"]))
    rnd = np.array(rnd)
    print(f"{'random sizes (300 runs) 90th pct':34s} {np.percentile(rnd[:,0],90):9.2f}x {np.percentile(rnd[:,1],90):9.2f}x  median {np.median(rnd[:,0]):.2f}x / {np.median(rnd[:,1]):.2f}x")
    for f, lab in (("d_adx", "daily ADX"), ("d_ema50_slope5", "daily EMA50 slope"), ("d_di_spread", "daily +DI - -DI"),
                   ("er20", "4h efficiency ratio 20"), ("adx_4h", "4h ADX"), ("ret_30d_atr", "30-day move"),
                   ("d_ema20_50", "daily EMA20 vs EMA50"), ("di_spread_4h", "4h +DI - -DI"), ("btc_ema_dist", "BTC distance from EMA50"),
                   ("d_ema50_dist", "distance from daily EMA50")):
        v = X[f].to_numpy(float); lo, hi = np.nanquantile(v[dev], [1 / 3, 2 / 3])
        for sign, nm in ((1, "strong=big"), (-1, "strong=small")):
            sz = np.where(v >= hi, 1.5 if sign > 0 else 0.5, np.where(v <= lo, 0.5 if sign > 0 else 1.5, 1.0))
            s = score(base.assign(size=sz))
            print(f"{lab + ' ' + nm:34s} {s['dev']['ratio']/b['dev']['ratio']:9.2f}x {s['ho']['ratio']/b['ho']['ratio']:9.2f}x")
    print("\n=== 9: several channel lengths, risk split equally ===")
    with Pool(4) as p:
        res = p.map(lengths, [(s, n) for s in COINS for n in (10, 15, 20, 30, 40)])
    L = {}
    for s, n, d in res:
        L.setdefault(n, []).append(d)
    L = {n: pd.concat(v) for n, v in L.items()}
    for combo in ((20,), (10,), (15,), (30,), (40,), (10, 20, 40), (15, 20, 30), (20, 40), (10, 20), (15, 20, 30, 40)):
        d = pd.concat([L[n].assign(size=1 / len(combo)) for n in combo])
        s = score(d)
        print(f"  n={'+'.join(map(str, combo)):14s} trades/yr {len(d)/6.6:5.0f}  dev ratio {s['dev']['ratio']:5.2f} (x{s['dev']['ratio']/b['dev']['ratio']:.2f})  "
              f"ho ratio {s['ho']['ratio']:5.2f} (x{s['ho']['ratio']/b['ho']['ratio']:.2f})  profit% {s['ho']['profit']:3.0f}  longest full-loss streak {s['dev']['streak']}/{s['ho']['streak']}")
