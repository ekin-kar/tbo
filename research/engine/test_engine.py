"""Hand-built scenarios with known correct answers. Run: python -m engine.test_engine"""
import numpy as np
from . import engine as E

T0 = 29_000_000  # arbitrary minute (a weekday, mid-day)


def bars(rows):
    a = np.array(rows, float)
    return {"t": T0 + np.arange(len(a), dtype=np.int64), "o": a[:, 0], "h": a[:, 1], "l": a[:, 2], "c": a[:, 3]}


def sim(rows, setup, spread=0.0, **kw):
    m1 = bars(rows)
    od = E.Orders(m1)
    setup(od)
    return E.run("XAUUSD", od, spread=spread, **kw)


def check(name, got, exp):
    ok = all(abs(g - e) < 1e-9 if isinstance(e, float) else g == e for g, e in zip(got, exp))
    print(("PASS " if ok else "FAIL ") + name, "" if ok else f"got {got} expected {exp}")
    return ok


flat = [100, 100.5, 99.5, 100]
res = []

# 1. long market, TP hit
t = sim([flat, [100, 101, 99.9, 100.8], [100.8, 102.5, 100.7, 102]],
        lambda od: od.place([1], E.MARKET, 1, 2.0, 2.0))
res.append(check("long TP", [t.entry[0], t.exit[0], t.reason[0], t.R_gross[0]], [100.0, 102.0, "TP", 1.0]))

# 2. long market, SL and TP touched in the same bar -> SL
t = sim([flat, [100, 100.2, 99.8, 100], [100, 102.5, 97.5, 100]],
        lambda od: od.place([1], E.MARKET, 1, 2.0, 2.0))
res.append(check("both touched -> SL", [t.exit[0], t.reason[0]], [98.0, "SL"]))

# 3. long, gap below SL -> exit at the worse open
t = sim([flat, [100, 100.2, 99.8, 100], [96.0, 96.5, 95.5, 96]],
        lambda od: od.place([1], E.MARKET, 1, 2.0, 2.0))
res.append(check("gap through SL -> open", [t.exit[0], t.reason[0], t.R_gross[0]], [96.0, "SL", -2.0]))

# 4. short with spread 0.1: entry at bid, SL checked on ask
t = sim([flat, [100, 100.2, 99.8, 100], [100, 101.95, 99.9, 101]],
        lambda od: od.place([1], E.MARKET, -1, 2.0, 2.0), spread=0.1)
res.append(check("short SL on ask", [t.entry[0], t.exit[0], t.reason[0]], [100.0, 102.0, "SL"]))

# 5. long with spread: entry at ask, TP needs bid to reach it
t = sim([flat, [100, 100.2, 99.8, 100], [100, 102.05, 99.9, 102], [102, 102.2, 101.9, 102]],
        lambda od: od.place([1], E.MARKET, 1, 2.0, 2.0), spread=0.1)
res.append(check("long entry at ask", [t.entry[0], t.exit[0], t.reason[0]], [100.1, 102.1, "TP"]))

# 6. buy stop fills intrabar; TP ignored on the fill bar; SL counts on it
t = sim([flat, [100, 104, 99.9, 102.5], [102.5, 102.8, 102.2, 102.5]],
        lambda od: od.place([1], E.STOP, 1, 5.0, 2.0, price=101.0, expiry_min=60))
res.append(check("stop fill, no TP on fill bar", [t.entry[0], t.reason[0]], [101.0, "END"]))
t = sim([flat, [100, 101.5, 95.0, 96]],
        lambda od: od.place([1], E.STOP, 1, 5.0, 2.0, price=101.0, expiry_min=60))
res.append(check("stop fill then SL same bar", [t.entry[0], t.exit[0], t.reason[0]], [101.0, 96.0, "SL"]))

# 7. buy stop, market gaps above it -> fill at open
t = sim([flat, [102, 102.5, 101.8, 102.2]],
        lambda od: od.place([1], E.STOP, 1, 5.0, 0.0, price=101.0, expiry_min=60))
res.append(check("stop gap fill at open", [t.entry[0]], [102.0]))

# 8. buy limit needs trade-through by pad
t = sim([flat, [100, 100.2, 99.0, 99.5], [99.5, 99.6, 98.95, 99.2]],
        lambda od: od.place([1], E.LIMIT, 1, 5.0, 0.0, price=99.0, expiry_min=60), limit_pad=0.02)
res.append(check("limit needs trade-through", [t.entry_time[0].minute == ((T0 + 2) % 60)], [True]))

# 9. pending expires
t = sim([flat, [100, 100.2, 99.8, 100], [100, 100.2, 99.8, 100], [100, 103, 99.8, 100]],
        lambda od: od.place([1], E.STOP, 1, 5.0, 0.0, price=101.0, expiry_min=2))
res.append(check("pending expiry", [len(t)], [0]))

# 10. forced exit at open
def fe(od):
    od.place([1], E.MARKET, 1, 5.0, 5.0)
    od.force_exit[3] = True
t = sim([flat, [100, 100.2, 99.8, 100], [100, 100.9, 99.8, 100.7], [100.6, 100.7, 100.5, 100.6]], fe)
res.append(check("forced exit at open", [t.exit[0], t.reason[0]], [100.6, "FORCED"]))

# 11. orders while in a position are ignored; max trades per day
def two(od):
    od.place([1, 2], E.MARKET, 1, 5.0, 1.0)
    od.place([4], E.MARKET, -1, 5.0, 1.0)
t = sim([flat, [100, 100.2, 99.8, 100], [100, 100.2, 99.8, 100], [100, 101.5, 99.9, 101], [101, 101.2, 100.8, 101], [101, 101.1, 99.5, 99.8]], two)
res.append(check("ignore orders in position", [len(t), t.dir[0], t.dir[1]], [2, 1, -1]))
t = sim([flat, [100, 100.2, 99.8, 100], [100, 100.2, 99.8, 100], [100, 101.5, 99.9, 101], [101, 101.2, 100.8, 101], [101, 101.1, 99.5, 99.8]], two, max_trades_day=1)
res.append(check("max trades per day", [len(t)], [1]))

# 12. commission in R
t = sim([flat, [100, 101, 99.9, 100.8], [100.8, 102.5, 100.7, 102]], lambda od: od.place([1], E.MARKET, 1, 2.0, 2.0))
res.append(check("commission", [t.R[0]], [(2.0 - 15e-6 * (100 + 102)) / 2.0]))

print(f"\n{sum(res)}/{len(res)} passed")
