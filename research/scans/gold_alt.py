exec(open(__file__.rsplit('/',1)[0]+'/gold_far.py').read().split("tr=R.run")[0])
import itertools
def on_days(mask_days):
    """per-minute bool: the calendar day is in mask_days (array of day ids)"""
    return np.isin(day,mask_days)
def stats(tr):
    y=tr.entry_time.dt.year; s=tr.sort_values('exit_time'); c=np.r_[0,np.cumsum(s.R.values)]
    x=tr.R.sort_values(ascending=False); no2=x.sum()-x.head(int(np.ceil(len(x)*0.02))).sum()
    pos,neg=tr.R[tr.R>0].sum(),-tr.R[tr.R<=0].sum()
    return f"n={len(tr):4d} R={tr.R.sum():+6.1f} PF={pos/max(neg,1e-9):.2f} DD={(np.maximum.accumulate(c)-c).max():5.1f} no_top2={no2:+6.1f} | "+' '.join(f"{p}={tr.R[(y>=a_)&(y<=b_)].sum():+5.1f}" for p,(a_,b_) in R.PERIODS.items())
def far_days(lo,hi): return DAYS.day[(DAYS.dist>lo)&(DAYS.dist<=hi)].values
def alt_pullback(days_,sl=2.0,rr=2.0,at=75,tp_level=False):
    od=F._base(g)[0]; kk=np.flatnonzero((mod==at)&on_days(days_)&np.isfinite(side)&np.isfinite(A))
    s=side[kk].astype(int)
    if tp_level:
        lv=np.where(s==1,ph[kk],pl[kk]); tp=np.abs(lv-g['o'][kk])
        od.place(kk,E.MARKET,s,sl*A[kk],tp)
    else: od.place(kk,E.MARKET,s,sl*A[kk],rr*sl*A[kk])
    od.force_exit[F.eod_mask(g,1200)]=True; return od
def alt_box(days_,box_end=420,dl=960,sl=2.0,rr=2.0,trend=True):
    od=F.session_breakout(g,box_end=box_end,sl_atr=sl,rr=rr,entry_deadline=dl,eod=1200)
    m_=on_days(days_); od.kind[~m_,:]=0
    if trend: od.kind[~(side==1),0]=0; od.kind[~(side==-1),1]=0
    return od
def alt_other(days_,sl=2.0,rr=2.0,start=75):
    od=F.prev_day_level(g,sl_atr=sl,rr=rr,tf=15,start=start,eod=1200)
    m_=on_days(days_); od.kind[~m_,:]=0
    od.kind[~(side==-1),0]=0; od.kind[~(side==1),1]=0       # the COUNTER-trend level only
    return od
for lab,(lo,hi) in (('far >0.5 ATR',(0.5,9)),('mid 0.25-0.5',(0.25,0.5))):
    dd_=far_days(lo,hi); print(f'\n######## {lab}: {len(dd_)} days')
    for sl,rr in ((2.0,2.0),(1.5,2.0)):
        print(f'pullback mkt 01:15 sl{sl} rr{rr}   ',stats(R.run('XAUUSD',alt_pullback(dd_,sl,rr),'main')))
    print('pullback mkt 01:15 TP=level       ',stats(R.run('XAUUSD',alt_pullback(dd_,tp_level=True),'main')))
    for at in (420,780): print(f'pullback mkt {at//60:02d}:00 sl2 rr2        ',stats(R.run('XAUUSD',alt_pullback(dd_,at=at),'main')))
    for be,trd in itertools.product((420,600),(True,False)):
        print(f'box 00:00-{be//60:02d}:00 breakout trend={trd!s:5}',stats(R.run('XAUUSD',alt_box(dd_,box_end=be,trend=trd),'main')))
    print('counter-trend prev-day level 01:15',stats(R.run('XAUUSD',alt_other(dd_),'main')))
