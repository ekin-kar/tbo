"""Evaluation and funded-phase simulations for the live bots (gold PDAYT 01:15 / EMA40 + USDJPY VOLC).
Trades come from the engine at current costs, minus the measured live-execution gap (gold 0.02R, USDJPY 0.002R per trade),
trades crossing whole missing data days removed. Rules modelled: targets, per-trade / daily / total limits, the bots'
equity-based daily stop, B book with a flat 1% debt, the fee as starting debt, and the risk ladder."""
import numpy as np, pandas as pd, pickle
import R, ideas as X
def clean(sym, tr, adj):
    t=R.get(sym)['t']; gap=np.r_[0,np.diff(t)]; big=pd.to_datetime(t[np.flatnonzero(gap>120)]*60,unit='s').values.astype('datetime64[m]')
    a=tr.entry_time.values.astype('datetime64[m]'); b=tr.exit_time.values.astype('datetime64[m]'); hole=np.zeros(len(tr),bool)
    for x in big: hole|=(a<x)&(b>=x)
    tr=tr[~hole].copy(); tr['R']=tr.R-adj; return tr
G=clean('XAUUSD',R.run('XAUUSD',X.pday_trend(R.get('XAUUSD')),'main'),0.02)[['exit_time','R']]; G['s']=0
V=clean('USDJPY',R.run('USDJPY',X.volc_f(R.get('USDJPY')),'main'),0.002)[['exit_time','R']]; V['s']=1
days=pd.bdate_range('2016-01-04','2026-09-18'); pos={x:i for i,x in enumerate(days)}
tr=pd.concat([G,V]).sort_values('exit_time'); tr['day']=tr.exit_time.dt.normalize()
tr['i']=tr.day.map(lambda x: pos.get(x,pos.get(x-pd.offsets.BDay(1)))); tr=tr.dropna(subset=['i']); tr['i']=tr.i.astype(int)
tr['k']=tr.groupby('i').cumcount(); K=tr.k.max()+1
M=np.zeros((len(days),K)); S=np.zeros((len(days),K),int); M[tr.i,tr.k]=tr.R.values; S[tr.i,tr.k]=tr.s.values
def ev(idx,rg,rv,e0=1.0,target=1.10,floor=0.95,daily=0.02,pt=0.01,guard=0.015,slip=0.0005,H=600):
    n,_=idx.shape; bal=np.full(n,e0); done=np.zeros(n,bool); fail=np.zeros(n,bool); dn=np.full(n,-1)
    for t in range(H):
        act=(~fail)&(~done)
        if not act.any(): break
        Rr=M[idx[:,t]]; Ss=S[idx[:,t]]; day0=bal.copy(); halted=np.zeros(n,bool)
        for k in range(K):
            x=Rr[:,k]; rr=np.where(Ss[:,k]==0,rg,rv)/100; live=act&~halted&(x!=0); pnl=np.where(live,rr*x*bal,0.0)
            fl=day0*(1-guard)-slip*day0; cap=live&(bal+pnl<fl); pnl=np.where(cap,fl-bal,pnl)
            f=live&(-pnl>pt*bal); bal=bal+pnl
            fail|=f|(live&(bal<=day0-daily*day0))|(live&(bal<=floor)); halted|=cap|(live&(bal<=day0*(1-guard)))
        h=act&~fail&(bal>=target); done|=h; dn[h]=t
    return done,fail,dn
LAD=[(-99,0.15,0.20),(1,0.25,0.35),(2,0.40,0.50),(4,0.55,0.70),(7,None,None)]
def fund(idx,top,floor,daily,pt,guard,fee,H=252,slip=0.0005):
    thr=np.array([l[0] for l in LAD]); RG=np.array([l[1] if l[1] else top[0] for l in LAD]); RV=np.array([l[2] if l[2] else top[1] for l in LAD])
    n,_=idx.shape; eq=np.ones(n); debt=np.full(n,fee); inb=np.zeros(n,bool); ep=np.zeros(n,int); fail=np.zeros(n,bool); calm=np.zeros(n,int)
    for t in range(H):
        buf=(eq-1-debt)*100; ti=np.clip(np.searchsorted(thr,buf,side='right')-1,0,len(thr)-1); ti=np.where(calm>0,0,ti)
        g=np.where(inb,np.where(eq>=0.995,0.25,0.15),RG[ti])/100; v=np.where(inb,np.where(eq>=0.995,0.35,0.20),RV[ti])/100
        Rr=M[idx[:,t]]; Ss=S[idx[:,t]]; day0=eq.copy(); halted=np.zeros(n,bool); act=~fail
        for k in range(K):
            x=Rr[:,k]; rr=np.where(Ss[:,k]==0,g,v); live=act&~halted&(x!=0); pnl=np.where(live,rr*x*eq,0.0)
            fl=day0*(1-guard)-slip*day0; cap=live&(eq+pnl<fl); pnl=np.where(cap,fl-eq,pnl)
            f=live&(-pnl>pt*eq); eq=eq+pnl
            fail|=f|(live&(eq<=day0*(1-daily)))|(live&(eq<=floor)); halted|=cap|(live&(eq<=day0*(1-guard)))
        new=(~inb)&(eq<0.99)&(~fail); inb|=new; debt=np.where(new,debt+0.01,debt); ep+=new
        back=inb&(eq>=1.0)&(~fail); inb&=~back; calm=np.where(back,10,np.maximum(calm-1,0))
    return np.where(fail,-0.1,np.maximum(eq-1-debt,0)),fail,ep
N=15000; out={}
for lab,w0 in [('2y','2024-09-19'),('3y','2023-09-19'),('10y','2016-01-04')]:
    rng=np.random.default_rng(99); s0=np.searchsorted(days,pd.Timestamp(w0)); idx=np.empty((N,600),int)
    for s in range(0,600,21):
        st=rng.integers(s0,len(days)-21,N); w=min(21,600-s); idx[:,s:s+w]=st[:,None]+np.arange(w)
    for nm,args in [('Low 0.4/0.6',dict(rg=0.4,rv=0.6)),('Low 0.5/0.6',dict(rg=0.5,rv=0.6)),
                    ('Mod10k@10000 0.5/0.6',dict(rg=0.5,rv=0.6,floor=0.94,daily=0.03,pt=0.015,guard=0.02)),
                    ('Mod10k@9650 0.3/0.4',dict(rg=0.3,rv=0.4,e0=0.965,floor=0.94,daily=0.03,pt=0.015,guard=0.02))]:
        ok,f,dn=ev(idx,**args); out[(nm,lab)]=(round(100*ok.mean()),round(np.median(dn[ok])/21,1))
        print(lab,nm,out[(nm,lab)],flush=True)
    if lab!='10y':
        for nm,args in [('Funded LOW',dict(top=(0.65,0.85),floor=0.95,daily=0.02,pt=0.01,guard=0.015,fee=0.01)),
                        ('Funded MODERATE',dict(top=(0.70,0.90),floor=0.94,daily=0.03,pt=0.015,guard=0.02,fee=0.02))]:
            pay,f,ep=fund(idx[:,:252],**args)
            out[(nm,lab)]=dict(bbook=round(100*(ep>0).mean()),lost=round(100*f.mean(),1),p25=round(100*np.percentile(pay,25),1),med=round(100*np.median(pay),1),p75=round(100*np.percentile(pay,75),1))
            print(lab,nm,out[(nm,lab)],flush=True)
pickle.dump(out,open('risk_sims_results.pkl','wb'))
