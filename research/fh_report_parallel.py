"""Runs fundedhive_report.py's journeys for every (account type, data period) in parallel and writes the same JSON."""
import sys, pathlib, json; sys.path[:0] = [str(pathlib.Path(__file__).resolve().parent), str(pathlib.Path(__file__).resolve().parent.parent)]
from multiprocessing import Pool
import fundedhive_report as HR, fundingpips_sim as F
D = None
def init():
    global D; D = F.load()
def job(a):
    rule, w = a; s0, s1 = HR.WINDOWS[w]
    return rule, w, HR.summarise(*HR.journeys(D, rule, s0, s1, N=3000, seed=21))
if __name__ == "__main__":
    out = {"fund_delay": HR.FUND_DELAY, "pay_every": HR.PAY_EVERY, "keeps": [k * 100 for k in HR.KEEPS], "trigs": [t * 100 for t in HR.TRIGS],
           "weeks": HR.WEEKS.tolist(), "plans": {r: {} for r in HR.PLAN}}
    jobs = [(r, w) for r in HR.PLAN for w in HR.WINDOWS]
    with Pool(int(sys.argv[1]) if len(sys.argv) > 1 else 4, initializer=init) as p:
        for rule, w, s in p.imap_unordered(job, jobs):
            out["plans"][rule][w] = s; f = s["funded"]["3/1"]
            print(rule, w, "pass", s["pass_pct"], "fail", s["fail_pct"], "median days", s["pass_days"]["50"], "lost", f["lost_pct"], flush=True)
    out["plans"] = {r: {w: out["plans"][r][w] for w in HR.WINDOWS} for r in HR.PLAN}     # keep the period order
    json.dump(out, open(pathlib.Path(__file__).resolve().parent / "results" / "fundedhive_plan_data.json", "w"))
    print("written")
