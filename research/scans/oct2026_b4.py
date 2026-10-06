exec(open(__file__.rsplit('/',1)[0]+'/oct2026_lab.py').read())
def pweek(m1,start=75,sl_atr=2.0,rr=2.0,eod=1200,trend=0,tf=15,expiry_days=1):
    """Previous WEEK high/low stop orders placed each day at `start`, valid until eod; optional daily-EMA side filter."""
    t=m1['t']; day=t//1440; wd=(day+3)%7; dk=np.where(wd==6,day+1,day); wk=(dk+3)//7   # Monday-based week id
    st=np.flatnonzero(np.r_[True,wk[1:]!=wk[:-1]])
    wh=np.maximum.reduceat(m1['h'],st); wl=np.minimum.reduceat(m1['l'],st)
    widx=np.repeat(np.arange(len(st)),np.diff(np.r_[st,len(t)]))
    ph=np.r_[np.nan,wh[:-1]][widx]; pl=np.r_[np.nan,wl[:-1]][widx]
    b=D.resample(m1,tf); a=I.atr(b['h'],b['l'],b['c'],14)
    A=np.full(len(t),np.nan); ok=b['act']<len(t); A[b['act'][ok]]=a[ok]; A=pd.Series(A).ffill().to_numpy()
    mod=t%1440; k=np.flatnonzero((mod==start)&np.isfinite(ph)&np.isfinite(A))
    # only if price is inside last week's range at placement
    c=m1['o'][k]; k=k[(c<ph[k])&(c>pl[k])]
    od,_=F._base(m1)
    if trend: s=X.daily_ema_side(m1,trend)
    up=k if not trend else k[s[k]==1]; dn=k if not trend else k[s[k]==-1]
    od.place(up,E.STOP,1,sl_atr*A[up],rr*sl_atr*A[up],price=ph[up],expiry_min=eod-start,slot=0)
    od.place(dn,E.STOP,-1,sl_atr*A[dn],rr*sl_atr*A[dn],price=pl[dn],expiry_min=eod-start,slot=1)
    od.force_exit[F.eod_mask(m1,eod)]=True
    return od
g=R.get('XAUUSD'); j=R.get('USDJPY')
for sym,m in (('XAUUSD',g),('USDJPY',j)):
    for start in (75,420):
        for trend in (0,40):
            r=report(f'{sym} pweek s{start} trend{trend}',sym,pweek(m,start=start,trend=trend),costs=('main',))
            print('   corr',corr(r['main'][1]))
