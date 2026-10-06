import sys, pathlib; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, R, ideas as X, challenge_test as CT
SP='/tmp/claude-0/-home-user-trade2/b9a9744d-83b2-50d8-8675-62baa49483d5/scratchpad/'
V=CT.clean('USDJPY',R.run('USDJPY',X.volc_f(R.get('USDJPY')),'main',max_bars=1200),0.002)
src=open(pathlib.Path(__file__).resolve().parent/'acct_speed.py').read(); code=src[src.index('days=CT.days'):src.index('ACC=[')]
days=CT.days
st_=np.arange(np.searchsorted(days,pd.Timestamp('2016-01-04')),np.searchsorted(days,pd.Timestamp('2025-09-19')))
rec=np.arange(np.searchsorted(days,pd.Timestamp('2023-10-02')),np.searchsorted(days,pd.Timestamp('2025-09-19')))
GOLDS={'gold bot now':CT.G,'combined PDAYT+ASIAB(trend) rule1':pd.read_pickle(SP+'net_asiab_t_r1.pkl'),'combined PDAYT+ASIAB(no trend) rule1':pd.read_pickle(SP+'net_asiab_r1.pkl')}
for acc,tg,fl,dl,pt,gd,risks in (('FundedHive Low 10%/5%',(0.10,),0.95,0.02,0.01,0.015,[(0.4,0.5),(0.5,0.5)]),('Funding Pips 12%/12%',(0.12,),0.88,0.02,1.0,0.015,[(0.6,0.8),(0.8,0.8)])):
    print('\n'+acc)
    for gname,Gt in GOLDS.items():
        ns={**globals(),'S':[Gt[['exit_time','R']],V[['exit_time','R']]]}; exec(code,ns); sim=ns['sim']
        for rg,rv in risks:
            line=f'  {gname:38s} gold {rg} / UJ {rv}'
            for wl,ss in (('2016-25',st_),('since Oct 23',rec)):
                ok,fail,end=sim(ss,[rg,rv],tg,fl,dl,pt,gd); mt=end/21; p=ok.mean()
                line+=f' | {wl}: pass {100*p:5.1f}% fail {100*fail.mean():4.1f}% median {np.median(mt[ok]):4.1f}mo E={mt.mean()/p:4.1f}mo'
            print(line,flush=True)
