"""Losing streaks: are they predictable (clustering)? Equity-curve filters per bot."""
import sys, pathlib; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, R, challenge_test as CT
SP='/tmp/claude-0/-home-user-trade2/b9a9744d-83b2-50d8-8675-62baa49483d5/scratchpad/'
G=CT.clean('XAUUSD',pd.read_pickle(SP+'TG.pkl'),0.02).sort_values('entry_time'); J=CT.clean('USDJPY',pd.read_pickle(SP+'TJ.pkl'),0.002).sort_values('entry_time')
rng=np.random.default_rng(1)
for name,T in (('GOLD',G),('USDJPY',J)):
    r=T.R.values; n=len(r)
    print(f'\n######## {name}: {n} trades, avg {r.mean():+.3f}R, win rate {100*(r>0).mean():.1f}%')
    # 1. longest losing streak vs shuffled
    def longest(x):
        best=cur=0
        for v in x:
            cur=cur+1 if v<=0 else 0; best=max(best,cur)
        return best
    sh=[longest(rng.permutation(r)) for _ in range(500)]
    print(f'longest losing streak: {longest(r)} trades | random order: median {np.median(sh):.0f}, 95% range {np.percentile(sh,2.5):.0f}-{np.percentile(sh,97.5):.0f}')
    # 2. do bad stretches predict bad next trades?
    for N in (10,20,40):
        past=pd.Series(r).rolling(N).sum().shift(1).to_numpy(); nxt=pd.Series(r[::-1]).rolling(N).sum().to_numpy()[::-1]   # sum of this + next N-1 trades
        ok=np.isfinite(past)&np.isfinite(nxt)
        q=np.nanpercentile(past[ok],[25,75])
        bad=ok&(past<=q[0]); good=ok&(past>=q[1])
        print(f'  after the worst 25% of {N}-trade stretches, next {N} trades avg {nxt[bad].mean()/N:+.3f}R | after the best 25%: {nxt[good].mean()/N:+.3f}R | overall {nxt[ok].mean()/N:+.3f}R')
    # 3. equity-curve filter: half (or zero) risk while the last N trades sum below 0 / below -k
    print('  equity-curve filters (risk multiplier applied to the NEXT trade):')
    def show(lab,w):
        x=r*w; c=np.r_[0,np.cumsum(x)]; dd=(np.maximum.accumulate(c)-c).max(); y=T.entry_time.dt.year.values
        mo=pd.Series(x,index=T.exit_time.dt.to_period('M').values).groupby(level=0).sum()
        print(f'    {lab:34s} avg risk x{w.mean():.2f} | R {x.sum():+6.1f} DD {dd:5.1f} R/DD {x.sum()/dd:5.2f} Sharpe(m) {mo.mean()/mo.std():.3f} | '+' '.join(f"{p}={x[(y>=a)&(y<=b)].sum():+5.1f}" for p,(a,b) in R.PERIODS.items()))
    show('none',np.ones(n))
    for N in (10,20,30):
        past=pd.Series(r).rolling(N,min_periods=N).sum().shift(1).fillna(1).to_numpy()
        show(f'half risk if last {N} trades < 0',np.where(past<0,0.5,1.0))
        show(f'skip if last {N} trades < 0',np.where(past<0,0.0,1.0))
    eq=np.cumsum(r); peak=np.maximum.accumulate(eq); dd_=np.r_[0,(peak-eq)[:-1]]
    for k in (5,10):
        show(f'half risk while {k}R+ below the peak',np.where(dd_>=k,0.5,1.0))
