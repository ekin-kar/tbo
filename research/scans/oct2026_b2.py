exec(open(__file__.rsplit('/',1)[0]+'/oct2026_lab.py').read())
def dtrend(m1,N=20,M=10,sl_atr=3.0,at=60,longonly=False,rr=0):
    """Daily channel breakout: prior daily close beyond N-day high/low -> market entry at `at` min after the
    day's first bar; exit when prior daily close crosses the M-day opposite channel; SL sl_atr*ATR20(daily)."""
    d,didx=X.daily(m1); h,l,c=d['h'],d['l'],d['c']
    tr=np.r_[np.nan,np.maximum(h[1:],c[:-1])-np.minimum(l[1:],c[:-1])]; atr=pd.Series(tr).rolling(20).mean().to_numpy()
    hiN=pd.Series(h).rolling(N).max().shift(1).to_numpy(); loN=pd.Series(l).rolling(N).min().shift(1).to_numpy()
    hiM=pd.Series(h).rolling(M).max().shift(1).to_numpy(); loM=pd.Series(l).rolling(M).min().shift(1).to_numpy()
    up=c>hiN; dn=c<loN; xl=c<loM; xs=c>hiM          # known at the close of day i -> act on day i+1
    t=m1['t']; first=d['starts']; nd=len(first)
    act=np.searchsorted(t,t[first]+at)               # bar ~`at` min into each day
    od,_=F._base(m1)
    for i in range(nd-1):
        k=act[i+1]
        if k>=len(t) or not np.isfinite(atr[i]): continue
        if up[i]: od.place(np.array([k]),E.MARKET,1,sl_atr*atr[i],rr*sl_atr*atr[i])
        elif dn[i] and not longonly: od.place(np.array([k]),E.MARKET,-1,sl_atr*atr[i],rr*sl_atr*atr[i])
        if xl[i]: od.exit_long[k]=True
        if xs[i]: od.exit_short[k]=True
    return od
g=R.get('XAUUSD'); j=R.get('USDJPY')
for sym,m in (('XAUUSD',g),('USDJPY',j)):
    for N,M in ((20,10),(55,20),(20,20)):
        for sl in (2.0,3.0):
            r=report(f'{sym} dtrend N{N} M{M} sl{sl}',sym,dtrend(m,N,M,sl),costs=('main',))
            print('   corr',corr(r['main'][1]))
