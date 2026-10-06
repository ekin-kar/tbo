import sys, pathlib; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, R, challenge_test as CT
SP='/tmp/claude-0/-home-user-trade2/b9a9744d-83b2-50d8-8675-62baa49483d5/scratchpad/'
src=open(pathlib.Path(__file__).resolve().parent/'acct_speed.py').read(); code=src[src.index('days=CT.days'):src.index('ACC=[')]
days=CT.days
st_=np.arange(np.searchsorted(days,pd.Timestamp('2016-01-04')),np.searchsorted(days,pd.Timestamp('2025-09-19')))
rec=np.arange(np.searchsorted(days,pd.Timestamp('2023-10-02')),np.searchsorted(days,pd.Timestamp('2025-09-19')))
TJ=CT.clean('USDJPY',pd.read_pickle(SP+'TJ.pkl'),0.002)
def halve(G,J):
    G=G.assign(b='g',usd=-G.dir); J=J.assign(b='j',usd=J.dir); A=pd.concat([G,J]).sort_values('entry_time').reset_index(drop=True)
    ent=A.entry_time.values; ex=A.exit_time.values; b=A.b.values; u=A.usd.values; w=np.ones(len(A))
    for i in range(len(A)):
        o=(b!=b[i])&(ent<ent[i])&(ex>ent[i])&(u==u[i])
        if o.any(): w[i]=0.5
    A['R']=A.R*w; return A[A.b=='g'],A[A.b=='j']
V={'now':(CT.clean('XAUUSD',pd.read_pickle(SP+'TG.pkl'),0.02),TJ)}
V['gold cancel 12:00']=(CT.clean('XAUUSD',pd.read_pickle(SP+'TG_c12.pkl'),0.02),TJ)
V['halve same-USD']=halve(*V['now'])
V['cancel 12:00 + halve']=halve(*V['gold cancel 12:00'])
for acc,tg,fl,dl,pt,gd,risks in (('FundedHive Low 10%/5% (1%/trade)',(0.10,),0.95,0.02,0.01,0.015,[(0.4,0.5),(0.5,0.6),(0.6,0.75)]),
                                 ('Funding Pips 12%/12%',(0.12,),0.88,0.02,1.0,0.015,[(0.6,0.8),(0.8,1.0)])):
    print('\n'+acc)
    for vname,(Gt,Jt) in V.items():
        ns={**globals(),'S':[Gt[['exit_time','R']],Jt[['exit_time','R']]]}; exec(code,ns); sim=ns['sim']
        for rg,rv in risks:
            line=f'  {vname:22s} {rg}/{rv}'
            for wl,ss in (('2016-25',st_),('since Oct 23',rec)):
                ok,fail,end=sim(ss,[rg,rv],tg,fl,dl,pt,gd); mt=end/21; p=ok.mean()
                line+=f' | {wl}: pass {100*p:5.1f}% fail {100*fail.mean():4.1f}% med {np.median(mt[ok]):4.1f}mo E={mt.mean()/p:4.1f}mo'
            print(line,flush=True)
