"""BTC losing-streak brake (Oct 2026): the bot exactly as now (ladder + open-risk cap, botsim.py), but after N
consecutive BTC stop-outs (a BTC trade closing at -0.5R or worse; breakeven / small exits do not count either way) new
BTC trades are sized x CUT until a BTC trade reaches +1.5R (its breakeven point), or until one closes as a winner.
Runs from $200: Mar 2020 and Jan 2024 to Sep 2026 (the two runs on the pages), plus 2022."""
from multiprocessing import Pool
import numpy as np, pandas as pd
import botsim as BS

MIN = BS.MIN


def run(x, pol, g, eq0=200.0):
    ev = []
    for i, (e, xx, be, d, R, c) in enumerate(x):
        ev += [(e, 1, i), (max(be, e + 1e-3), 0, i), (max(xx, e + 2e-3), 2, i)]
    rank = {2: 0, 0: 1, 1: 2}
    ev.sort(key=lambda z: (z[0], rank[z[1]]))
    eq = eq0; opn = {}; pk = eq0; dd = 0.0; pk1 = 0.0; dd1 = 0.0
    streak = 0; reduced = False; n_red = 0
    for t, kind, i in ev:
        e, xx, be, d, R, c = x[i]; c = int(c)
        if kind == 1:
            fr, rk, cap = BS.row_at(pol, eq)
            amt = eq * rk[c] / 100 * (pol["smult"] if d < 0 else 1.0)
            if reduced and (c == 0 or g.get("scope") == "all"):
                amt *= g["cut"]; n_red += c == 0
            if cap > 0 and c not in pol["exempt"]:
                room = cap / 100 * eq - sum(v[0] for v in opn.values() if not v[1])
                if amt > room:
                    amt = room if room > pol["minf"] * amt else 0.0
            if amt > 0:
                opn[i] = [amt, False, c]
        elif kind == 0 and i in opn:
            opn[i][1] = True
            if c == 0 and g.get("reset", "be") == "be":
                streak = 0; reduced = False
        elif kind == 2 and i in opn:
            a = opn.pop(i)[0]; eq += a * R
            if c == 0 and g:
                if R <= -0.5:
                    streak += 1
                    if streak >= g["n"]:
                        reduced = True
                elif R >= 0.5:
                    streak = 0
                    if g.get("reset") == "win":
                        reduced = False
        w = eq - sum(v[0] for v in opn.values() if not v[1])
        pk = max(pk, w); dd = max(dd, (pk - w) / pk)
        if pk >= 1000:
            pk1 = max(pk1, w); dd1 = max(dd1, (pk1 - w) / pk1)
    return eq, dd * 100, dd1 * 100, n_red


VARS = {"bot now": {}}
for n in (2, 3):
    for cut in (0.5, 0.33):
        V = dict(n=n, cut=cut)
        VARS[f"after {n} BTC stops: BTC x{cut} until a BTC trade hits +1.5R"] = V
        VARS[f"after {n} BTC stops: BTC x{cut} until a BTC winner closes"] = dict(V, reset="win")
        VARS[f"after {n} BTC stops: ALL coins x{cut} until BTC +1.5R"] = dict(V, scope="all")


def job(name):
    g = VARS[name]; out = []
    for a in ("2020-03-01", "2022-01-01", "2024-01-01"):
        x, _, _ = BS.window(a, "2026-10-01")
        out.append(run(x, BS.bot_policy(), g))
        out.append(run(x, BS.flat_policy(5, 2.5, 0.83), g, 100.0))
    return name, out


if __name__ == "__main__":
    x, _, _ = BS.window("2024-01-01", "2026-10-01")
    assert abs(run(x, BS.bot_policy(), {})[0] - 25154.34) < 1, "baseline mismatch"
    with Pool(3) as p:
        res = p.map(job, list(VARS))
    b = res[0][1]
    print(f"{'':58s} |        ladder from $200, to Sep 2026: final / worst drop / drop after $1k        | flat 5%+cap: drop 2020 / 2024 | BTC trades cut (2024 run)")
    print(f"{'':58s} | {'Mar 2020':^27s} | {'Jan 2022':^27s} | {'Jan 2024':^27s} |")
    for n, o in res:
        L = [o[0], o[2], o[4]]; Fl = [o[1], o[5]]
        cells = " | ".join(f"${r[0]:>11,.0f} {r[1]:4.1f}% {r[2]:4.1f}%" for r in L)
        print(f"{n[:58]:58s} | {cells} | {Fl[0][1]:5.1f}% {Fl[1][1]:5.1f}% (${Fl[1][0]:,.0f}) | {o[4][3]}", flush=True)
