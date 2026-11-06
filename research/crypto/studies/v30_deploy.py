"""v3.0 deployment check (Nov 2026): C1 (16 h same-coin cooldown after a loss < -0.5R) + C2 (all-coins exit curve) + C4
(panic v2.7 on the 5 core coins at 3 units/event + the 7 other DEV12 coins on a separate 0.75 x 3 = 2.25 units/event pool,
optionally at most `max_extra_open` extra-coin sleeve positions at a time, ranked C = |doi| x |pz| when more trigger).
Gates as v30_deep_campaign (fixed-unit x, 40 phase copies, drawdown-matched money vs bot v2.8 + panic v2.7).

    python v30_deploy.py            -> research/results/v30_deploy.csv (+ printed)"""
import os, sys
from pathlib import Path
os.environ.setdefault("BOT_TRADES", "v28nov")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
import v30lib as V, hourly51 as H
import v30_deep_campaign as D

RES = D.RES
EXTRA7 = [s for s in H.DEV12 if s not in V.COINS]
C1 = dict(ctrl="cool", p=dict(cool_h=16, mode=1, cool_R=-0.5))
C2S = {"C2a be1.75 lock5.5>2": dict(be_R=1.75, lock_R=5.5, lock_to=2.0),
       "C2b be1.75 lock5>2": dict(be_R=1.75, lock_R=5.0, lock_to=2.0),
       "C2c be1.5 lock5>2": dict(be_R=1.5, lock_R=5.0, lock_to=2.0)}
EXIT_COMMON = dict(stale_h=60, stale_to=0.0, lock2_R=8.0, lock2_to=3.5)


def select_hybrid(cands, extra_cap=None, units=3.0, share=0.75):
    """Hour by hour. Core coins (the 5 live ones): every free coin that triggers (one trade per coin at a time), units
    split over the core coins entered that hour. Extra coins: at most extra_cap open extra positions at once; if more
    trigger than free extra slots, the top ones by C = |doi| x |pz|; share x units split over the extra coins entered."""
    cands = cands.sort_values(["t", "sym"]).reset_index(drop=True)
    busy, open_x, out = {}, [], []
    for t, g in cands.groupby("t", sort=True):
        open_x = [x for x in open_x if x >= t]
        g = g[[busy.get(s, pd.Timestamp(0)) + pd.Timedelta(hours=1) < t for s in g.sym]]
        if g.empty:
            continue
        core, ext = g[g.sym.isin(V.COINS)], g[~g.sym.isin(V.COINS)]
        if extra_cap is not None and len(ext):
            free = extra_cap - len(open_x)
            ext = ext.iloc[0:0] if free <= 0 else ext.assign(_s=-(ext.doi.abs() * ext.pz.abs())).sort_values("_s").head(free).drop(columns="_s")
        for part, u in ((core, units), (ext, units * share)):
            if part.empty:
                continue
            for _, r in part.iterrows():
                busy[r.sym] = r.t_exit
                if r.sym not in V.COINS:
                    open_x.append(r.t_exit)
            out.append(part.assign(n=len(part), w=u / len(part)))
    return pd.concat(out, ignore_index=True)


def main():
    specs = {"BASE v2.8+v2.7": None}
    for nm, ex in C2S.items():
        specs[f"C1+{nm}"] = dict(id=f"C1+{nm}", ctrl="cool", p=C1["p"], exL=dict(ex, **EXIT_COMMON), exS=dict(ex, **EXIT_COMMON))
    eng = [s for s in specs.values() if s]
    runs = D.run_jobs(eng, shifts=[0] + D.SH)
    import panic_sleeve as PSL                                       # the research sleeve = what the bot's parity test checks
    sleeves = {"v2.7": PSL.events(extra_coins=())}
    for nm, cap in (("C4 uncapped", None), ("C4 extra cap 3", 3), ("C4 extra cap 2", 2)):
        sleeves[nm] = PSL.events(extra_coins=PSL.EXTRA_COINS, max_extra_open=cap)
    sb = D.ev_score(sleeves["v2.7"])
    rows, items = [], []
    bot0 = V.rows(D.base_at(0))
    for nm, sp in specs.items():
        X = runs[sp["id"]][0] if sp else D.base_at(0)
        xd, xo, s = D.xpair(X, 0, D.P20); x22 = D.xpair(X, 0, D.P22)[0]
        ph = np.array([[v > 1 for v in D.xpair(runs[sp["id"]][sh], sh, D.P20)[:2]] for sh in D.SH], float) if sp else np.full((1, 2), np.nan)
        for snm, E in sleeves.items():
            if sp is None and snm != "v2.7":
                continue
            ss = D.ev_score(E)
            lab = nm if sp is None else f"{nm} + {snm}"
            rows.append(dict(id=lab, tbo_x2020=xd, tbo_x2022=x22, tbo_x2024=xo, phase_dev=ph[:, 0].mean(), phase_oos=ph[:, 1].mean(), n_tbo=len(X),
                             sleeve_x22=ss[D.P22]["ratio"] / sb[D.P22]["ratio"], sleeve_x24=ss[D.P24]["ratio"] / sb[D.P24]["ratio"],
                             sleeve_n22=ss[D.P22]["n"], sleeve_n24=ss[D.P24]["n"],
                             max_open_extra=int(E[~E.sym.isin(V.COINS)].pipe(lambda z: max([((z.t <= t) & (z.t_exit >= t)).sum() for t in z.t] or [0])))))
            S_ = PSL.sleeve_rows(E); A = np.r_[V.rows(X), np.c_[S_, np.ones(len(S_))]]; A = A[np.lexsort((A[:, 5], A[:, 0]))]
            items.append((lab, A, V.base_policy()))
    R = pd.DataFrame(rows)
    M = D.g6_many(items)
    R = R.merge(M.add_prefix("M_"), left_on="id", right_index=True, how="left")
    R.to_csv(RES / "v30_deploy.csv", index=False)
    pd.set_option("display.width", 260); pd.set_option("display.max_columns", 40)
    print(R[["id", "tbo_x2020", "tbo_x2022", "tbo_x2024", "phase_dev", "phase_oos", "sleeve_x22", "sleeve_x24", "max_open_extra", "M_k",
             "M_m2020", "M_dd2020", "M_m2022", "M_dd2022", "M_m2024", "M_dd2024", "M_boot_med", "M_boot_p10", "M_boot_dd90", "M_G6"]].round(3).to_string(index=False))


if __name__ == "__main__":
    main()
