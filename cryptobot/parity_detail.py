"""Lists every difference between the bot on the simulated exchange (test_bot_sim.run) and the live-logic replay:
missing / extra trades and different exits, with whether the replay trade reached breakeven / the profit lock and
whether it was stopped inside its fill minute (the backtest's pessimistic case).
    python cryptobot/parity_detail.py ADAUSDT 2021-01-01 2026-09-30"""
import logging, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import test_bot_sim as T, replay as RP
from replay import C

if __name__ == "__main__":
    logging.basicConfig(level=logging.ERROR)
    sym, a, b = sys.argv[1], sys.argv[2], sys.argv[3]
    bt = T.run(sym, a, b)
    ref = RP.replay(C.load(sym), T.params(sym), a, b); ref = ref[ref.exit_time < b]
    bot = {C.D.to_datetime([x["entry_time"]])[0]: x for x in bt}
    first_ref = ref.entry_time.min()
    for r in ref.itertuples():
        x = bot.get(r.entry_time)
        tag = ("fill-minute stop " if r.exit_time == r.entry_time else "") + ("BE " if r.be_time < r.exit_time else "") + \
              ("LOCK " if r.lock_time < r.exit_time else "")
        if x is None:
            print(f"{sym} only in replay: {r.entry_time} -> {r.exit_time} {r.reason} R {r.R:+.2f} [{tag}]")
            continue
        xt = C.D.to_datetime([x["exit_time"]])[0]
        if xt != r.exit_time:
            Rb = (x["exit"] - x["entry"]) * x["dir"] / r.sl_dist
            print(f"{sym} exit differs: {r.entry_time} replay {r.exit_time} {r.reason} gross {(r.exit - r.entry) * r.dir / r.sl_dist:+.2f}R | "
                  f"bot {xt} {x['how']} gross {Rb:+.2f}R [{tag}]")
    for t, x in sorted(bot.items()):
        if t not in set(ref.entry_time):
            print(f"{sym} only in bot: {t} -> {C.D.to_datetime([x['exit_time']])[0]} gross {(x['exit'] - x['entry']) * x['dir']:+.4f} "
                  f"{'(before the replay has 1000 4h candles: ' + str(first_ref) + ')' if t < first_ref else ''}")
    print(f"{sym} done: bot {len(bt)}, replay {len(ref)}")
