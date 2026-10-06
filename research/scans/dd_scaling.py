"""Account-level risk scaling in a challenge: risk x f(room), room = (balance - floor) / (1 - floor) (1 = at start, 0 = at floor).
Below the start balance risk shrinks linearly with the room left (never below `minm` x); at/above start: full risk."""
import sys, pathlib; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, R, challenge_test as CT
SP='/tmp/claude-0/-home-user-trade2/b9a9744d-83b2-50d8-8675-62baa49483d5/scratchpad/'
G=CT.clean('XAUUSD',pd.read_pickle(SP+'TG.pkl'),0.02); J=CT.clean('USDJPY',pd.read_pickle(SP+'TJ.pkl'),0.002)
days=CT.days; pos={d:i for i,d in enumerate(days)}
tr=pd.concat([G[['exit_time','R']].assign(s=0),J[['exit_time','R']].assign(s=1)]).sort_values('exit_time'); tr['day']=tr.exit_time.dt.normalize()
tr['i']=tr.day.map(lambda d:pos.get(d,pos.get(d-pd.offsets.BDay(1)))); tr=tr.dropna(subset=['i']); tr['i']=tr.i.astype(int)
tr['k']=tr.groupby('i').cumcount(); K=tr.k.max()+1
M=np.zeros((len(days),K)); SS=np.zeros((len(days),K),int); M[tr.i,tr.k]=tr.R.values; SS[tr.i,tr.k]=tr.s.values
def sim(starts,risk,target,floor,daily,pt,guard,mode='none',minm=0.5,boost=1.0,H=520,slip=0.0005):
    risk=np.asarray(risk)/100; n=len(starts); bal=np.ones(n); done=np.zeros(n,bool); fail=np.zeros(n,bool); end=np.full(n,H)
    for t in range(H):
        di=starts+t; act=~fail&~done&(di<len(days))
        if not act.any(): break
        dic=np.minimum(di,len(days)-1); Rr=M[dic]; Ss=SS[dic]; day0=bal.copy(); halted=np.zeros(n,bool)
        room=np.clip((bal-floor)/(1-floor),0,None)
        if mode=='linear': mult=np.where(bal<1,np.maximum(minm,room),1.0)
        elif mode=='step':  mult=np.where(room<0.5,minm,1.0)
        elif mode=='boost': mult=np.where(bal<1,np.maximum(minm,room),np.where(bal>1+0.5*target,boost,1.0))
        else: mult=np.ones(n)
        for k in range(K):
            x=Rr[:,k]; rr=risk[Ss[:,k]]*mult; live=act&~halted&(x!=0); pnl=np.where(live,rr*x*bal,0.0)
            fl=day0*(1-guard)-slip*day0; cap=live&(bal+pnl<fl); pnl=np.where(cap,fl-bal,pnl)
            f=live&(-pnl>pt*bal*1.05); bal=bal+pnl
            nf=f|(live&(bal<=day0*(1-daily)))|(live&(bal<=floor)); end[nf&~fail]=t; fail|=nf; halted|=cap|(live&(bal<=day0*(1-guard)))
        hit=act&~fail&(bal>=1+target); done|=hit; end[hit]=t
    return done,fail,end
st_=np.arange(np.searchsorted(days,pd.Timestamp('2016-01-04')),np.searchsorted(days,pd.Timestamp('2025-09-19')))
rec=np.arange(np.searchsorted(days,pd.Timestamp('2023-10-02')),np.searchsorted(days,pd.Timestamp('2025-09-19')))
MODES=[('none',{}),('linear, min 0.5x',dict(mode='linear',minm=0.5)),('linear, min 0.3x',dict(mode='linear',minm=0.3)),
       ('half risk in the bottom half',dict(mode='step',minm=0.5)),('linear 0.5x + 1.25x when >half way',dict(mode='boost',minm=0.5,boost=1.25))]
for acc,tg,fl,dl,pt,gd,risks in (('FundedHive Low 10%/5% (1%/trade)',0.10,0.95,0.02,0.01,0.015,[(0.4,0.5),(0.5,0.6),(0.6,0.75)]),
                                 ('Funding Pips 12%/12%',0.12,0.88,0.02,1.0,0.015,[(0.6,0.8),(0.8,1.0)])):
    print('\n'+acc)
    for rg,rv in risks:
        for lab,kw in MODES:
            if kw.get('mode')=='boost' and max(rg,rv)*1.25>pt*100: continue
            line=f'  {rg}/{rv} {lab:36s}'
            for wl,ss in (('2016-25',st_),('since Oct 23',rec)):
                ok,fail,end=sim(ss,[rg,rv],tg,fl,dl,pt,gd,**kw); mt=end/21; p=ok.mean()
                line+=f' | {wl}: pass {100*p:5.1f}% fail {100*fail.mean():4.1f}% med {np.median(mt[ok]):4.1f}mo E={mt.mean()/p:4.1f}mo'
            print(line,flush=True)
