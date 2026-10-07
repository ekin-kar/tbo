"""User idea (Oct 2026): with every TBO trade open a half-size opposite 'hedge'. If the main trade is stopped out,
keep the hedge until its take-profit (stop moved to the entry price, so it cannot turn into a loss); if the main
trade runs h R in profit, close the hedge. Variants: hedge TP k x stop distance, kill level h, delayed hedge (opened only
once the main trade is -d R). Minute replay (tradesim), costs as the bot (taker + slippage, funding). v2.4 trades,
BTC ETH BNB SOL ADA, bot weights; first period 2020-23, then 2024-26."""
from multiprocessing import Pool
import numpy as np, pandas as pd
import common as C
import tradesim as T
import filter_test2 as F2, filter_test3 as F3
from ideas_v4 import acct

COINS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
WT = {"BTCUSDT": 1.0, "ETHUSDT": 0.5, "BNBUSDT": 1 / 6, "SOLUSDT": 1 / 6, "ADAUSDT": 1 / 6}
RULES = [(k, h, d, half) for k in (1.0, 1.5, 2.0, 3.0) for h in (0.5, 1.0, 1.5) for d in (0.0,) for half in (0.5,)]
RULES += [(k, h, d, 0.5) for k in (1.5, 2.0, 3.0) for h in (1.0,) for d in (0.5, 0.8)]       # delayed hedge
RULES += [(2.0, 1.0, 0.0, 1.0), (1.0, 1.0, 0.0, 1.0)]                                        # full-size hedge


def first(mask):
    i = np.flatnonzero(mask)
    return int(i[0]) if len(i) else -1


def hedge_R(sym, e, s, P, D, xi, k, h, d, size):
    """R (in units of the main trade's risk) of the hedge for one trade; 0 if never opened."""
    m = T.data(sym); n = len(m["t"]); j1 = min(e + T.HOLD, n - 1)
    H, L, O = m["h"], m["l"], m["o"]
    cost = T.C.TAKER + T.slip(sym)
    hs = -s
    # opening: at the main entry, or (delayed) when the main trade is d R against
    if d > 0:
        lvl = P - s * d * D
        seg = (L[e:xi + 1] <= lvl) if s > 0 else (H[e:xi + 1] >= lvl)
        o = first(seg)
        if o < 0:
            return 0.0
        e2 = e + o; P2 = lvl
    else:
        e2, P2 = e, P
    tp = P2 + hs * k * D                       # hedge take profit
    kill = P + s * h * D                       # main trade h R in profit -> hedge closed
    xi_main = xi
    j = e2
    # phase 1: while the main trade is open
    seg_end = min(xi_main, j1)
    Hs, Ls = H[j:seg_end + 1], L[j:seg_end + 1]
    t_tp = first((Ls <= tp) if hs < 0 else (Hs >= tp))
    t_kill = first((Hs >= kill) if s > 0 else (Ls <= kill))
    if t_kill >= 0 and (t_tp < 0 or t_kill <= t_tp):          # pessimistic on ties
        xj, xp = j + t_kill, kill
    elif t_tp >= 0:
        xj, xp = j + t_tp, tp
    else:
        # phase 2: main trade closed; hedge stop at its entry (cannot lose any more than costs), TP, or time
        j = seg_end + 1
        if j >= j1:
            xj, xp = j1, O[j1]
        else:
            Hs, Ls = H[j:j1], L[j:j1]
            t_tp = first((Ls <= tp) if hs < 0 else (Hs >= tp))
            t_be = first((Hs >= P2) if hs < 0 else (Ls <= P2))
            if t_be >= 0 and (t_tp < 0 or t_be <= t_tp):
                xj, xp = j + t_be, P2 if not ((O[j + t_be] > P2) if hs < 0 else (O[j + t_be] < P2)) else O[j + t_be]
            elif t_tp >= 0:
                xj, xp = j + t_tp, tp
            else:
                xj, xp = j1, O[j1]
    hours = (m["t"][xj] - m["t"][e2]) / 60
    gross = (xp - P2) * hs
    return size * (gross - cost * P2 - cost * xp - T.C.FUNDING_8H * hours / 8 * P2) / D


def run(sym):
    F2.CUR["sym"] = sym
    x = T.base_trades(sym, skip_fn=F3.make("sum_open_interest_value", 72, -0.03))
    rows = []
    for r in x.itertuples():
        xi, xp, why, b = T.path(sym, r.e, r.dir, r.entry, r.sl_dist)
        R0 = T.R_of(sym, r.dir, r.entry, r.sl_dist, xi, xp, r.e)[0]
        row = dict(sym=sym, entry_time=r.entry_time, exit_time=r.exit_time, dir=r.dir, R0=R0)
        for rule in RULES:
            row[rule] = hedge_R(sym, r.e, r.dir, r.entry, r.sl_dist, xi, *rule)
        rows.append(row)
    return pd.DataFrame(rows)


if __name__ == "__main__":
    with Pool(4) as p:
        X = pd.concat(p.map(run, COINS)).sort_values("exit_time").reset_index(drop=True)
    W = X.sym.map(WT).to_numpy() * np.where(X.dir < 0, 0.5, 1)
    EXT = X.exit_time.values.astype("datetime64[m]").astype(np.int64)
    DEV = (X.entry_time < "2024-01-01").to_numpy(); HO = ~DEV
    R0 = X.R0.to_numpy()
    b = {p: acct(R0, W, EXT, m) for p, m in (("dev", DEV), ("ho", HO))}
    print(f"{len(X)} trades. Base: 2020-23 net {b['dev'][0]:.0f}R, max drop {b['dev'][1]:.1f}R, net/drop {b['dev'][2]:.2f} | "
          f"2024-26 net {b['ho'][0]:.0f}R, drop {b['ho'][1]:.1f}R, net/drop {b['ho'][2]:.2f} | trades in profit {(R0 > 0.05).mean()*100:.0f}%")
    half = R0 * 0.5
    hd = {p: acct(half, W, EXT, m) for p, m in (("dev", DEV), ("ho", HO))}
    print(f"Reference, no hedge but HALF size: net/drop {hd['dev'][2]:.2f} | {hd['ho'][2]:.2f} (same edge, half the swings)\n")
    print(f"{'hedge rule':58s} | 2020-23 net / drop / net÷drop | 2024-26 net / drop / net÷drop | trades in profit | stopped-out trades rescued")
    for rule in RULES:
        k, h, d, size = rule
        Rt = R0 + X[rule].to_numpy()
        a = acct(Rt, W, EXT, DEV); c = acct(Rt, W, EXT, HO)
        lost = R0 < -0.5
        rescued = ((Rt > -0.5) & lost).sum() / max(lost.sum(), 1) * 100
        nm = f"{'half' if size == 0.5 else 'full'}-size hedge{' after -%.1fR' % d if d else ' at entry'}, TP {k}R, closed when main +{h}R"
        print(f"{nm:58s} | {a[0]:5.0f}R {a[1]:5.1f}R {a[2]:5.2f} | {c[0]:5.0f}R {c[1]:5.1f}R {c[2]:5.2f} | {(Rt > 0.05).mean()*100:5.0f}% | {rescued:5.0f}%")
