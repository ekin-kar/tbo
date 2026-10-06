"""Gold session-structure scan: breakouts, liquidity sweeps (take a level, m15 close back inside -> reverse) and session
direction (continuation / reversal), for Asia (00-07 UTC), London (07-12) and New York (12-20). Costs: 'main'."""
import sys, pathlib, itertools; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, numba as nb, R, ideas as X
from engine import engine as E, indicators as I, data as D
from engine.strategies import families as F
g=R.get('XAUUSD'); t=g['t']; mod=t%1440; N=len(t)
day=t//1440; wd=(day+3)%7; dk=np.where(wd==6,day+1,day)              # Sunday evening belongs to Monday
ds=np.flatnonzero(np.r_[True,dk[1:]!=dk[:-1]]); didx=np.repeat(np.arange(len(ds)),np.diff(np.r_[ds,N]))
WIN={'ASIA':(0,420),'LON':(420,720),'NY':(720,1200),'DAY':(-120,1440)}
def win_hl(s,e):
    m=(mod>=s)&(mod<e) if s>=0 else np.ones(N,bool)
    if s<0: m=np.ones(N,bool)
    H=np.maximum.reduceat(np.where(m,g['h'],-np.inf),ds); L=np.minimum.reduceat(np.where(m,g['l'],np.inf),ds)
    H[~np.isfinite(H)]=np.nan; L[~np.isfinite(L)]=np.nan; return H,L
LV={}
for w,(s,e) in WIN.items():
    H,L=win_hl(s,e)
    LV[w]=(H[didx],L[didx],e)                                            # today's, known from minute e (DAY: never today)
    LV['P'+w]=(np.r_[np.nan,H[:-1]][didx],np.r_[np.nan,L[:-1]][didx],-1) # previous day's, known all day
O0=g['o'][ds]; C0=g['c'][np.r_[ds[1:],N]-1]
b=D.resample(g,15); a15=I.atr(b['h'],b['l'],b['c'],14)
A=np.full(N,np.nan); ok=b['act']<N; A[b['act'][ok]]=a15[ok]; A=pd.Series(A).ffill().to_numpy()
dd,di2=X.daily(g); trr=np.r_[np.nan,np.maximum(dd['h'][1:],dd['c'][:-1])-np.minimum(dd['l'][1:],dd['c'][:-1])]
DATR=pd.Series(trr).rolling(14).mean().shift(1).to_numpy()[di2]
SIDE=X.daily_ema_side(g,40)
def eod_at(e): return F.eod_mask(g,min(e,1200))
# ---------- 1. breakout: stop orders at level H/L placed at trade-window start, valid to window end
def brk(lv,tw,sl=2.0,rr=2.0,trend=0,narrow=0.0,hold_to=None):
    H,L,known=LV[lv]; s,e=WIN[tw]; start=max(s,known if known>0 else s)
    k=np.flatnonzero((mod==start)&(wd<5)); k=k[np.isfinite(H[k])&np.isfinite(A[k])]
    px=g['o'][k]; k=k[(px<H[k])&(px>L[k])]                               # only if price is inside the range at placement
    if narrow>0: k=k[(H[k]-L[k])<narrow*DATR[k]]
    od,_=F._base(g); up=k; dn=k
    if trend: up=k[SIDE[k]==1]; dn=k[SIDE[k]==-1]
    od.place(up,E.STOP,1,sl*A[up],rr*sl*A[up],price=H[up],expiry_min=e-start,slot=0)
    od.place(dn,E.STOP,-1,sl*A[dn],rr*sl*A[dn],price=L[dn],expiry_min=e-start,slot=1)
    od.force_exit[eod_at(hold_to or e)]=True; return od
# ---------- 2. sweep & reverse on m15 closes
bmod=b['t']%1440; bact=np.minimum(b['act'],N-1); bend=np.clip(b['act']-1,0,N-1)
bday=didx[np.minimum(np.searchsorted(t,b['t']),N-1)]
@nb.njit
def _sweep(bday,bmod,h,l,c,a,H,L,s,e,sw,buf,tf):
    n=len(h); sig=np.zeros(n,np.int64); sl=np.full(n,np.nan); cur=-1; done=False; eh=-1e18; el=1e18
    for i in range(n):
        if bday[i]!=cur: cur=bday[i]; done=False; eh=-1e18; el=1e18
        if bmod[i]<s or bmod[i]+tf>e or done or not (a[i]>0) or not (H[i]==H[i]): continue
        eh=max(eh,h[i]); el=min(el,l[i])
        if eh>=H[i]+sw*a[i] and c[i]<H[i] and c[i]>L[i]: sig[i]=-1; sl[i]=eh+buf*a[i]-c[i]; done=True
        elif el<=L[i]-sw*a[i] and c[i]>L[i] and c[i]<H[i]: sig[i]=1; sl[i]=c[i]-(el-buf*a[i]); done=True
    return sig,sl
def swp(lv,tw,sw=0.2,rr=1.5,buf=0.3,trend=0,hold_to=None):
    H,L,known=LV[lv]; s,e=WIN[tw]; s=max(s,known if known>0 else s)
    sig,sl=_sweep(bday,bmod,b['h'],b['l'],b['c'],a15,H[bend],L[bend],s,e,sw,buf,15)
    k=np.flatnonzero(sig!=0)
    if trend: k=k[SIDE[bact[k]]==sig[k]]
    od,_=F._base(g); od.place(bact[k],E.MARKET,sig[k],sl[k],rr*sl[k])
    od.force_exit[eod_at(hold_to or e)]=True; return od
# ---------- 3. session direction: at trade-window start, direction of the signal window's move (open->close)
def sdir(sw_,tw,mode=1,kmin=0.0,sl=2.0,rr=2.0,trend=0):
    s1,e1=WIN[sw_]; s2,e2=WIN[tw]
    k=np.flatnonzero((mod==s2)&(wd<5)); j0=np.searchsorted(t,t[k]-(s2-s1)); okk=(t[k]-t[j0])<=(s2-s1)+10
    mv=g['o'][k]-g['o'][j0]; d_=(mode*np.sign(mv)).astype(int)
    sel=okk&(np.abs(mv)>kmin*DATR[k])&np.isfinite(A[k])&(d_!=0)
    if trend: sel&=SIDE[k]==d_
    k,d_=k[sel],d_[sel]
    od,_=F._base(g); od.place(k,E.MARKET,d_,sl*A[k],rr*sl*A[k] if rr>0 else 0.0); od.force_exit[eod_at(e2)]=True; return od
def evalt(tr):
    y=tr.entry_time.dt.year; x=tr.R.sort_values(ascending=False)
    pos,neg=tr.R[tr.R>0].sum(),-tr.R[tr.R<=0].sum(); s=tr.sort_values('exit_time'); c=np.r_[0,np.cumsum(s.R.values)]
    r=dict(n=len(tr),R=round(tr.R.sum(),1),PF=round(pos/max(neg,1e-9),2),DD=round((np.maximum.accumulate(c)-c).max(),1),
           no_top2=round(x.sum()-x.head(int(np.ceil(len(x)*0.02))).sum(),1))
    for p,(a_,b_) in R.PERIODS.items(): r[p]=round(tr.R[(y>=a_)&(y<=b_)].sum(),1)
    return r
if __name__=='__main__':
    rows=[]
    def go(fam,name,od,**p):
        tr=R.run('XAUUSD',od,'main'); r=dict(fam=fam,setup=name,**p,**evalt(tr)); rows.append(r)
    BRK=[('PASIA','ASIA'),('ASIA','LON'),('ASIA','NY'),('LON','NY'),('PDAY','LON'),('PDAY','NY'),('PLON','ASIA'),('PNY','ASIA')]
    for (lv,tw),sl,rr,tr_,nar,ht in itertools.product(BRK,(1.5,2.0),(1.5,2.0,3.0),(0,40),(0.0,0.5),(None,1200)):
        if ht==1200 and WIN[tw][1]>=1200: continue
        go('breakout',f'{lv}->{tw}',brk(lv,tw,sl,rr,tr_,nar,ht),sl=sl,rr=rr,trend=tr_,narrow=nar,exit_at=ht or WIN[tw][1])
    print('breakouts done',len(rows),flush=True)
    SWP=[('PDAY','ASIA'),('PASIA','ASIA'),('ASIA','LON'),('ASIA','NY'),('LON','NY'),('PDAY','LON'),('PDAY','NY')]
    for (lv,tw),sw,rr,buf,tr_,ht in itertools.product(SWP,(0.1,0.3,0.6),(1.0,1.5,2.0),(0.3,),(0,40),(None,1200)):
        if ht==1200 and WIN[tw][1]>=1200: continue
        go('sweep',f'{lv}@{tw}',swp(lv,tw,sw,rr,buf,tr_,ht),sweep=sw,rr=rr,trend=tr_,exit_at=ht or WIN[tw][1])
    print('sweeps done',len(rows),flush=True)
    for (s_,tw),mode,km,rr,tr_ in itertools.product((('ASIA','LON'),('ASIA','NY'),('LON','NY')),(1,-1),(0.0,0.3,0.6),(2.0,0.0),(0,40)):
        go('direction',f'{s_}->{tw} {"cont" if mode==1 else "rev"}',sdir(s_,tw,mode,km,2.0,rr,tr_),kmin=km,rr=rr,trend=tr_)
    df=pd.DataFrame(rows); df.to_pickle('/tmp/claude-0/-home-user-trade2/b9a9744d-83b2-50d8-8675-62baa49483d5/scratchpad/gold_sessions.pkl')
    df.to_csv(pathlib.Path(__file__).resolve().parent.parent/'results'/'gold_sessions_scan.csv',index=False)
    P=['old','dev','val','hold']; good=df[(df[P]>0).all(axis=1)&(df.no_top2>0)&(df.n>=150)].sort_values('R',ascending=False)
    print(f'\nconfigs: {len(df)} | positive in all 4 periods, >0 without top 2%, >=150 trades: {len(good)}')
    print(good.head(40).to_string(index=False))
    print('\nby setup: share of configs positive in all 4 periods')
    print(df.assign(ok=(df[P]>0).all(axis=1)).groupby(['fam','setup']).agg(configs=('ok','size'),share_ok=('ok','mean'),best_R=('R','max'),median_R=('R','median')).round(2).to_string())
