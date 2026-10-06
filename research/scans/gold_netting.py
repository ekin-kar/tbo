"""PDAYT + ASIAB on a NETTING account (one gold position at a time). Trades from the standalone runs, merged:
 rule1 'first come': only the first entry of the day is kept;
 rule2 'one at a time': a trade is dropped if it would enter while the other one is still open (its level was reached
        during the open position -> suspended order missed); otherwise kept."""
import sys, pathlib; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, R, challenge_test as CT
SP='/tmp/claude-0/-home-user-trade2/b9a9744d-83b2-50d8-8675-62baa49483d5/scratchpad/'
P=CT.clean('XAUUSD',R.run('XAUUSD',__import__('ideas').pday_trend(R.get('XAUUSD')),'main'),0.02).assign(bot='PDAYT')
def load(n): a=pd.read_pickle(SP+n+'.pkl'); return CT.clean('XAUUSD',a.assign(R=a.R+0.02),0.02)   # pickles already had -0.02
def merge(A,rule):
    x=pd.concat([P,A]).sort_values(['entry_time','bot']).reset_index(drop=True); keep=[]; busy=pd.Timestamp(0); seen=set()
    for i,r in x.iterrows():
        d=r.entry_time.date()
        if rule==1:
            if d in seen: continue
            seen.add(d); keep.append(i)
        else:
            if r.entry_time<busy: continue
            keep.append(i); busy=r.exit_time
    return x.loc[keep]
def st(tr,lab):
    s=tr.sort_values('exit_time'); c=np.r_[0,np.cumsum(s.R.values)]; dd=(np.maximum.accumulate(c)-c).max(); y=tr.entry_time.dt.year
    mo=tr.groupby(tr.exit_time.dt.to_period('M')).R.sum(); x=tr.R.sort_values(ascending=False)
    print(f"{lab:38s} n={len(tr):5d} R={tr.R.sum():+6.1f} DD={dd:5.1f} R/DD={tr.R.sum()/dd:5.2f} Sharpe(m)={mo.mean()/mo.std():.2f} no_top2={x.sum()-x.head(int(np.ceil(len(x)*.02))).sum():+6.1f} | "
          +' '.join(f"{p}={tr.R[(y>=a)&(y<=b)].sum():+5.1f}" for p,(a,b) in R.PERIODS.items())+f" | 2025={tr.R[y==2025].sum():+.0f} 2026={tr.R[y==2026].sum():+.0f}")
st(P,'PDAYT alone (now)')
for n,lab in (('asiab','ASIAB'),('asiab_t','ASIAB +trend')):
    A=load(n).assign(bot='ASIAB'); st(A,f'{lab} alone')
    for rule in (1,2):
        m=merge(A,rule); st(m,f'netting rule{rule}: PDAYT+{lab}')
        print(f"{'':38s}   kept: PDAYT {(m.bot=='PDAYT').sum()} of {len(P)}, ASIAB {(m.bot=='ASIAB').sum()} of {len(A)}")
        m.to_pickle(SP+f'net_{n}_r{rule}.pkl')
