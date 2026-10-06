import sys, pathlib; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, R, ideas as X, challenge_test as CT
SP='/tmp/claude-0/-home-user-trade2/b9a9744d-83b2-50d8-8675-62baa49483d5/scratchpad/'
V=CT.clean('USDJPY',R.run('USDJPY',X.volc_f(R.get('USDJPY')),'main',max_bars=1200),0.002)
src=open(pathlib.Path(__file__).resolve().parent/'acct_speed.py').read(); code=src[src.index('days=CT.days'):src.index('ACC=[')]
days=CT.days
st_=np.arange(np.searchsorted(days,pd.Timestamp('2016-01-04')),np.searchsorted(days,pd.Timestamp('2025-09-19')))
rec=np.arange(np.searchsorted(days,pd.Timestamp('2023-10-02')),np.searchsorted(days,pd.Timestamp('2025-09-19')))
def ld(n): a=pd.read_pickle(SP+n+'.pkl'); return CT.clean('XAUUSD',a.assign(R=a.R+0.02),0.02)
GOLDS={'PDAYT (now)':(CT.G,[0.4,0.6]),'ASIAB no trend':(ld('asiab'),[0.4,0.6]),'ASIAB +trend':(ld('asiab_t'),[0.4,0.6,0.8,1.0])}
for gname,(Gt,_) in GOLDS.items():
    s=Gt.sort_values('exit_time'); c=np.r_[0,np.cumsum(s.R.values)]; yrs=(s.exit_time.max()-s.exit_time.min()).days/365
    print(f"{gname:16s} trades/yr={len(Gt)/yrs:5.0f} R/yr={Gt.R.sum()/yrs:5.1f} DD={(np.maximum.accumulate(c)-c).max():5.1f}R R/DD={Gt.R.sum()/(np.maximum.accumulate(c)-c).max():.2f}")
for acc,tg,fl,dl,pt,gd,uj,risks in (('FundedHive Low 10%/5% (max 1%/trade)',(0.10,),0.95,0.02,0.01,0.015,0.5,None),('Funding Pips 12%/12%',(0.12,),0.88,0.02,1.0,0.015,0.8,None)):
    print('\n'+acc+f'  (USDJPY {uj}%)')
    for gname,(Gt,rs) in GOLDS.items():
        ns={**globals(),'S':[Gt[['exit_time','R']],V[['exit_time','R']]]}; exec(code,ns); sim=ns['sim']
        for rg in rs:
            if acc.startswith('Funding') and rg<0.6: continue
            line=f'  {gname:16s} gold {rg}'
            for wl,ss in (('2016-25',st_),('since Oct 23',rec)):
                ok,fail,end=sim(ss,[rg,uj],tg,fl,dl,pt,gd); mt=end/21; p=ok.mean()
                line+=f' | {wl}: pass {100*p:5.1f}% fail {100*fail.mean():4.1f}% median {np.median(mt[ok]):4.1f}mo E={mt.mean()/p:4.1f}mo'
            print(line,flush=True)
