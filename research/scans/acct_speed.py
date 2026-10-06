"""Which account type + risk gets funded fastest? Real trade sequence of the live bots (gold PDAYT, USDJPY VOLC + 20h max hold),
a fresh account started every trading day 2016 - Sep 2025, closed-trade basis, bots' daily stop modelled.
Expected time to a funded account counts retries: E[T] = (mean days of one attempt) / pass rate."""
import sys, pathlib; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, R, ideas as X, challenge_test as CT
V=CT.clean('USDJPY',R.run('USDJPY',X.volc_f(R.get('USDJPY')),'main',max_bars=1200),0.002)[['exit_time','R']]
S=[CT.G[['exit_time','R']],V]
days=CT.days; pos={d:i for i,d in enumerate(days)}
tr=pd.concat([s.assign(s=i) for i,s in enumerate(S)]).sort_values('exit_time'); tr['day']=tr.exit_time.dt.normalize()
tr['i']=tr.day.map(lambda d:pos.get(d,pos.get(d-pd.offsets.BDay(1)))); tr=tr.dropna(subset=['i']); tr['i']=tr.i.astype(int)
tr['k']=tr.groupby('i').cumcount(); K=tr.k.max()+1
M=np.zeros((len(days),K)); SS=np.zeros((len(days),K),int); M[tr.i,tr.k]=tr.R.values; SS[tr.i,tr.k]=tr.s.values
def sim(starts,risk,targets,floor,daily,pt,guard,H=520,slip=0.0005):
    risk=np.asarray(risk)/100; n=len(starts); bal=np.ones(n); ph=np.zeros(n,int); fail=np.zeros(n,bool); end=np.full(n,H)
    for t in range(H):
        di=starts+t; act=~fail&(ph<len(targets))&(di<len(days))
        if not act.any(): break
        dic=np.minimum(di,len(days)-1); Rr=M[dic]; Ss=SS[dic]; day0=bal.copy(); halted=np.zeros(n,bool)
        for k in range(K):
            x=Rr[:,k]; rr=risk[Ss[:,k]]; live=act&~halted&(x!=0); pnl=np.where(live,rr*x*bal,0.0)
            fl=day0*(1-guard)-slip*day0; cap=live&(bal+pnl<fl); pnl=np.where(cap,fl-bal,pnl)
            f=live&(-pnl>pt*bal*1.05); bal=bal+pnl
            nf=f|(live&(bal<=day0*(1-daily)))|(live&(bal<=floor)); end[nf&~fail]=t; fail|=nf
            halted|=cap|(live&(bal<=day0*(1-guard)))
        for p,tg in enumerate(targets):
            hit=act&~fail&(ph==p)&(bal>=1+tg); ph[hit]+=1; bal[hit]=1.0
        done=act&~fail&(ph==len(targets)); end[done&(end==H)]=t
    ok=ph==len(targets); return ok,fail,end
ACC=[  # name, targets, static floor, daily, per-trade limit, bots' daily stop
 ('Funding Pips 1-step Flex 12%/12%',(0.12,),0.88,0.02,1.0,0.015),
 ('FundedHive Low 10%/5%',(0.10,),0.95,0.02,0.01,0.015),
 ('FundedHive Moderate 10%/6%',(0.10,),0.94,0.03,0.015,0.02),
 ('Generic 1-step 10%/8% (4% daily)',(0.10,),0.92,0.04,1.0,0.02),
 ('Generic 1-step 10%/10% (5% daily)',(0.10,),0.90,0.05,1.0,0.02),
 ('Generic 2-step 8%+5% / 10% (5% daily)',(0.08,0.05),0.90,0.05,1.0,0.02)]
GOLD=[0.3,0.4,0.5,0.6,0.8,1.0,1.2]; JR=1.25         # USDJPY risk = 1.25 x gold risk (live ratio ~1.2-1.33)
st_=np.arange(np.searchsorted(days,pd.Timestamp('2016-01-04')),np.searchsorted(days,pd.Timestamp('2025-09-19')))
rec=np.arange(np.searchsorted(days,pd.Timestamp('2023-10-02')),np.searchsorted(days,pd.Timestamp('2025-09-19')))
out=[]
for name,tg,fl,dl,pt,gd in ACC:
    print(f'\n{name}   (risk gold / USDJPY: pass% | fail% | median months to pass | months per failed try | EXPECTED months to funded incl. retries | tries per funded)')
    for g in GOLD:
        r=[g,round(g*JR,2)]
        if pt<1 and max(r)>pt*100: continue
        line=f'  {g:.1f}/{g*JR:.2f}:'
        for lab,ss in (('2016-25',st_),('since Oct 23',rec)):
            ok,fail,end=sim(ss,r,tg,fl,dl,pt,gd); res=~ok&~fail
            p=ok.mean(); mt=end/21
            exp=(mt.mean())/p if p>0 else np.inf      # each attempt lasts until pass/fail/timeout; retries until pass
            line+=f' | {lab}: {100*p:5.1f}% {100*fail.mean():4.1f}% {np.median(mt[ok]):4.1f}mo fail@{np.median(mt[fail]) if fail.any() else 0:4.1f}mo  E={exp:4.1f}mo tries={1/p:4.2f}'
            out.append(dict(acct=name,gold=g,jpy=round(g*JR,2),win=lab,passp=100*p,fail=100*fail.mean(),med=np.median(mt[ok]),E=exp,tries=1/p))
        print(line,flush=True)
pd.DataFrame(out).to_csv(pathlib.Path(__file__).resolve().parent.parent/'results'/'account_speed.csv',index=False)
