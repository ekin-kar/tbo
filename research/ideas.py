import R, numpy as np, pandas as pd, itertools
from engine import engine as E, indicators as I, data as D
from engine.strategies import families as F
LOG=[]   # (idea, combos)
def daily(m1):
    """daily bars (UTC weekdays, Sunday stub merged into Monday) and, per minute, index of the CURRENT day."""
    t=m1['t']; day=t//1440; wd=(day+3)%7
    dkey=np.where(wd==6,day+1,day)            # Sunday -> Monday
    starts=np.flatnonzero(np.r_[True,dkey[1:]!=dkey[:-1]])
    dh=np.maximum.reduceat(m1['h'],starts); dl=np.minimum.reduceat(m1['l'],starts)
    dc=m1['c'][np.r_[starts[1:],len(t)]-1]; do=m1['o'][starts]
    didx=np.repeat(np.arange(len(starts)),np.diff(np.r_[starts,len(t)]))
    return dict(starts=starts,h=dh,l=dl,c=dc,o=do,key=dkey[starts]),didx
def volratio_prior(m1,n=20,base=250):
    """per minute: ATRn(daily) / median(ATRn over prior base days), using only COMPLETED prior days."""
    d,didx=daily(m1)
    tr=np.r_[np.nan,np.maximum(d['h'][1:],d['c'][:-1])-np.minimum(d['l'][1:],d['c'][:-1])]
    a=pd.Series(tr).rolling(n).mean()
    ratio=(a/a.rolling(base,min_periods=120).median()).to_numpy()
    prior=np.r_[np.nan,ratio[:-1]]            # value known at the start of each day
    return prior[didx]
def sweep(sym,build,grid,costs=('cons','curr'),years=R.PERIODS['dev'],tag=None):
    m1=R.get(sym); rows=[]; keys=list(grid)
    for vals in itertools.product(*[grid[k] for k in keys]):
        p=dict(zip(keys,vals)); od=build(m1,**p)
        t=m1['t']; y=pd.to_datetime(t*60,unit='s').year if False else None
        od.allow_entry[(t<R.minutes(f'{years[0]}-01-01'))|(t>=R.minutes(f'{years[1]+1}-01-01'))]=False
        row=dict(p)
        for c in costs:
            tr=R.run(sym,od,c); yr=tr.groupby(tr.entry_time.dt.year).R.sum()
            row[c+'_n']=len(tr); row[c+'_R']=round(tr.R.sum(),1)
            row[c+'_yrs']=' '.join(f'{v:+.0f}' for v in yr.values)
            row[c+'_L']=round(tr.R[tr.dir==1].sum(),1); row[c+'_S']=round(tr.R[tr.dir==-1].sum(),1)
        rows.append(row)
    LOG.append((tag,len(rows)))
    return pd.DataFrame(rows)

_vr={}
def vr(m1,n):
    k=(id(m1),n)
    if k not in _vr: _vr[k]=volratio_prior(m1,n)
    return _vr[k]
def pday_vol(m1,thr=0.0,n=20,sl_atr=2.0,rr=2.0,mode='break',side='high'):
    od=F.prev_day_level(m1,sl_atr=sl_atr,rr=rr,tf=15,start=420,eod=1200,mode=mode)
    v=vr(m1,n)
    bad=(v<thr) if side=='high' else ~(v<thr)
    bad=bad|np.isnan(v) if thr>0 else np.zeros(len(v),bool)
    od.kind[bad,:]=0
    return od

def daily_ema_side(m1,n):
    """per minute: +1 if prior completed day's close > EMA(n) of daily closes (prior days only), else -1."""
    d,didx=daily(m1); e=I.ema(d['c'],n)
    s=np.where(d['c']>e,1,-1).astype(float); s[:n]=np.nan
    prior=np.r_[np.nan,s[:-1]]; return prior[didx]
def pday_trend(m1,n=40,sl_atr=2.0,rr=2.0,start=75,eod=1200):
    """LIVE GOLD STRATEGY (PDAYT): at `start` (UTC minute, live 75 = 01:15) stop orders at the previous day's high/low,
    only on the side of the daily EMA(n) trend (live n=40); SL sl_atr x ATR14(m15), TP rr x SL, flat/expiry at `eod` (20:00)."""
    od=F.prev_day_level(m1,sl_atr=sl_atr,rr=rr,tf=15,start=start,eod=eod)
    s=daily_ema_side(m1,n)
    od.kind[~(s==1),0]=0      # slot0 = buy stop
    od.kind[~(s==-1),1]=0     # slot1 = sell stop
    return od

def asia_mr(m1,k_atr=2.0,sl_atr=2.0,rr=1.0,tf=15,ref=50,start=0,end=360,flat=405):
    """G2: fade m15 closes k ATR away from EMA(ref) during 00:00-06:00 UTC; flat 06:45."""
    b=D.resample(m1,tf); c=b['c']; e=I.ema(c,ref); a=I.atr(b['h'],b['l'],c,14)
    mb=D.minute_of_day(b['t']+tf)   # close time
    ok=(mb>=start+tf)&(mb<=end)&np.isfinite(a)
    lo=(c<e-k_atr*a)&ok; sh=(c>e+k_atr*a)&ok
    lo&=~np.r_[False,lo[:-1]]; sh&=~np.r_[False,sh[:-1]]
    k=np.flatnonzero(lo|sh)
    od,_=F._base(m1)
    od.place(b['act'][k],E.MARKET,np.where(lo[k],1,-1),sl_atr*a[k],sl_atr*rr*a[k])
    od.force_exit[F.eod_mask(m1,flat)]=True
    return od

def box_levels(m1,box_start,box_end):
    """per-minute running box high/low for the current UTC day over [box_start,box_end)."""
    t=m1['t']; mod=t%1440; day=t//1440
    inb=(mod>=box_start)&(mod<box_end)
    hi=np.where(inb,m1['h'],-np.inf); lo=np.where(inb,m1['l'],np.inf)
    starts=np.flatnonzero(np.r_[True,day[1:]!=day[:-1]])
    H=np.maximum.reduceat(hi,starts); L=np.minimum.reduceat(lo,starts)
    didx=np.repeat(np.arange(len(starts)),np.diff(np.r_[starts,len(t)]))
    return H[didx],L[didx]

def false_break(m1,sweep_atr=0.25,sl_buf=0.5,rr=1.5,tf=15,box_end=420,win_end=660,eod=1200):
    """G3: Asian box 00:00-box_end. Between box_end and win_end, if price has traded beyond the box by
    >= sweep_atr*ATR and an m15 candle then CLOSES back inside, fade it: SL beyond the sweep extreme + sl_buf ATR,
    TP = rr * risk. One signal per day (first)."""
    b=D.resample(m1,tf); a=I.atr(b['h'],b['l'],b['c'],14)
    H,L=box_levels(m1,0,box_end)
    ends=np.clip(b['act']-1,0,len(m1['t'])-1)
    bh,bl=H[ends],L[ends]
    mb=D.minute_of_day(b['t']); close_t=mb+tf
    day=D.day_index(b['t'])
    n=len(b['t']); sig=np.zeros(n,int); sl=np.full(n,np.nan)
    cur=-1; ext_h=-np.inf; ext_l=np.inf; done=False
    for i in range(n):
        if day[i]!=cur: cur=day[i]; ext_h=-np.inf; ext_l=np.inf; done=False
        if mb[i]<box_end or close_t[i]>win_end or done or not np.isfinite(a[i]) or not np.isfinite(bh[i]): continue
        ext_h=max(ext_h,b['h'][i]); ext_l=min(ext_l,b['l'][i])
        c=b['c'][i]
        if ext_h>=bh[i]+sweep_atr*a[i] and c<bh[i] and c>bl[i]:
            sig[i]=-1; sl[i]=ext_h+sl_buf*a[i]-c; done=True
        elif ext_l<=bl[i]-sweep_atr*a[i] and c>bl[i] and c<bh[i]:
            sig[i]=1; sl[i]=c-(ext_l-sl_buf*a[i]); done=True
    k=np.flatnonzero(sig!=0)
    od,_=F._base(m1)
    od.place(b['act'][k],E.MARKET,sig[k],sl[k],rr*sl[k])
    od.force_exit[F.eod_mask(m1,eod)]=True
    return od

def intraday_mom(m1,k_atr=1.0,sl_atr=1.5,rr=0,t_sig=13*60,t0=7*60,eod=1200,tf=15):
    """G7: if gold moved >= k*ATR(m15) x sqrt(bars) ... simpler: move from t0 open to t_sig >= k * daily-ATR-proxy,
    enter in the same direction at t_sig, SL sl_atr*ATR(m15)*4 (h1 scale), hold to eod (rr=0 -> no TP)."""
    t=m1['t']; mod=t%1440; day=t//1440
    b=D.resample(m1,60); a=I.atr(b['h'],b['l'],b['c'],14)
    atr_at=np.interp(t,b['t']+60,np.nan_to_num(a))
    starts=np.flatnonzero(np.r_[True,day[1:]!=day[:-1]])
    didx=np.repeat(np.arange(len(starts)),np.diff(np.r_[starts,len(t)]))
    o0=np.full(len(starts),np.nan)
    i0=np.flatnonzero(mod==t0); o0[didx[i0]]=m1['o'][i0]
    k=np.flatnonzero(mod==t_sig)
    mv=m1['o'][k]-o0[didx[k]]; A=atr_at[k]
    dirn=np.where(mv>=k_atr*A,1,np.where(mv<=-k_atr*A,-1,0))
    ok=(dirn!=0)&(A>0)&np.isfinite(mv); k,dirn,A=k[ok],dirn[ok],A[ok]
    od,_=F._base(m1)
    od.place(k,E.MARKET,dirn,sl_atr*A,(sl_atr*rr*A) if rr>0 else 0.0)
    od.force_exit[F.eod_mask(m1,eod)]=True
    return od

def volc_intraday(m1,tf=60,ratio=0.8,lookback=10,sl_atr=1.5,rr=2.5,eod=1200,start=360):
    """G8: VOLC mechanics on gold, entries only start..eod-120, flat at eod."""
    od=F.vol_contraction(m1,tf=tf,ratio=ratio,lookback=lookback,sl_atr=sl_atr,rr=rr,hold_min=24*60)
    mod=m1['t']%1440
    od.kind[(mod<start)|(mod>=eod-120),:]=0
    od.expiry[:]=np.minimum(od.expiry,np.maximum(eod-mod,1)[:,None])
    od.force_exit[F.eod_mask(m1,eod)]=True
    return od

def pday_nr(m1,nr=4,sl_atr=2.0,rr=2.0):
    """G9: PDAY only when the previous day's range was the narrowest of the last nr days."""
    od=F.prev_day_level(m1,sl_atr=sl_atr,rr=rr,tf=15,start=420,eod=1200)
    # use calendar-day ranges exactly like prev_day_level (prior calendar day with data)
    t=m1['t']; day=t//1440
    starts=np.flatnonzero(np.r_[True,day[1:]!=day[:-1]])
    rng=np.maximum.reduceat(m1['h'],starts)-np.minimum.reduceat(m1['l'],starts)
    wd=(day[starts]+3)%7
    ok=np.zeros(len(starts),bool)
    full=np.flatnonzero(wd!=6)                 # ignore Sunday stubs in the comparison window
    for j in range(len(starts)):
        p=j-1
        if p<0: continue
        prev=full[full<=p][-nr:]
        if len(prev)==nr and prev[-1]==p: ok[j]=rng[p]<=rng[prev].min()
    didx=np.repeat(np.arange(len(starts)),np.diff(np.r_[starts,len(t)]))
    od.kind[~ok[didx],:]=0
    return od

def ny_box(m1,box_start=420,box_end=810,sl_atr=1.5,rr=2.0,eod=1200,tf=15):
    """G10: box = London session (07:00-13:30), stop orders both sides from 13:30 to 18:00, flat 20:00."""
    return F.session_breakout(m1,box_end=box_end,sl_atr=sl_atr,rr=rr,tf=tf,entry_deadline=18*60,eod=eod,box_start=box_start)

def gotobi(m1,entry=23*60+5,exit_=55,sl_atr=1.5,only_gotobi=True,side=1):
    """J1: Tokyo fix. Long USDJPY after rollover (23:05 UTC) on the evening before a gotobi day
    (Tokyo date 5,10,15,20,25, last business day; weekend -> previous Friday), exit at 00:55 UTC (Tokyo 09:55 fix)."""
    t=m1['t']; mod=t%1440
    b=D.resample(m1,60); a=I.atr(b['h'],b['l'],b['c'],14); atr_at=np.interp(t,b['t']+60,np.nan_to_num(a))
    k=np.flatnonzero(mod==entry)
    # Tokyo date of the fix = UTC date of entry + 1 day
    fixday=pd.to_datetime((t[k]//1440+1)*86400,unit='s')
    bd=pd.bdate_range('2015-12-01','2026-12-31')
    targets=set()
    for y in range(2015,2027):
        for mth in range(1,13):
            ms=pd.Timestamp(y,mth,1); me=ms+pd.offsets.MonthEnd(0)
            days=[pd.Timestamp(y,mth,d) for d in (5,10,15,20,25)]+[me]
            for d in days:
                while d.dayofweek>=5: d-=pd.Timedelta(days=1)
                targets.add(d)
    isg=np.array([d in targets for d in fixday])
    wd=fixday.dayofweek.values
    sel=(isg if only_gotobi else ~isg)&(wd<5)&(atr_at[k]>0)
    k=k[sel]
    od,_=F._base(m1)
    od.allow_entry[:]=True; od.allow_fill[:]=True
    A=atr_at[k]
    od.place(k,E.MARKET,side,sl_atr*A,0.0)
    od.force_exit[F.eod_mask(m1,exit_)]=True
    return od

def volc_f(m1,ratio=0.8,lookback=10,sl_atr=1.5,rr=2.5):
    """VOLC with Friday close ON: no orders/fills from Fri 20:00 UTC, flat at Fri 20:00."""
    od=F.vol_contraction(m1,tf=60,ratio=ratio,lookback=lookback,sl_atr=sl_atr,rr=rr)
    t=m1['t']; wd=D.weekday(t); mod=t%1440
    blk=((wd==4)&(mod>=1200))|(wd>=5)
    od.allow_entry[blk]=False; od.allow_fill[blk]=False
    od.force_exit[F.eod_mask(m1,1200)&(wd==4)]=True
    return od
def pday(m1): return F.prev_day_level(m1,sl_atr=2.0,rr=2.0,tf=15,start=420,eod=1200)

def intraday_side(m1,tf,n):
    """per minute: sign(close - EMA_n) of the last CLOSED tf-candle."""
    b=D.resample(m1,tf); e=I.ema(b['c'],n); s=np.where(b['c']>e,1.0,-1.0); s[:n]=np.nan
    j=np.searchsorted(b['act'],np.arange(len(m1['t'])),side='right')-1   # last candle whose act <= minute
    out=np.full(len(m1['t']),np.nan); ok=j>=0; out[ok]=s[j[ok]]; return out
def pday_itrend(m1,tf=15,n=200):
    od=pday(m1); s=intraday_side(m1,tf,n)
    od.kind[~(s==1),0]=0; od.kind[~(s==-1),1]=0
    return od

def quiet_mr(m1,k_atr=2.5,thr=0.9,sl_atr=2.5,rr=1.0,tf=15,ref=50,start=420,end=1140,eod=1200):
    """Q1: fade m15 closes k ATR from EMA50 during 07:00-19:00, ONLY on days whose trailing 20d ATR
    is below thr x its 1-year median (quiet gold). Flat 20:00."""
    b=D.resample(m1,tf); c=b['c']; e=I.ema(c,ref); a=I.atr(b['h'],b['l'],c,14)
    v=vr(m1,20); ends=np.clip(b['act']-1,0,len(m1['t'])-1); vq=v[ends]<thr
    mb=D.minute_of_day(b['t']+tf)
    ok=(mb>=start)&(mb<=end)&np.isfinite(a)&vq
    lo=(c<e-k_atr*a)&ok; sh=(c>e+k_atr*a)&ok
    lo&=~np.r_[False,lo[:-1]]; sh&=~np.r_[False,sh[:-1]]
    k=np.flatnonzero(lo|sh); od,_=F._base(m1)
    od.place(b['act'][k],E.MARKET,np.where(lo[k],1,-1),sl_atr*a[k],sl_atr*rr*a[k])
    od.force_exit[F.eod_mask(m1,eod)]=True
    return od

def _london_fix_utc(t):
    """per-minute: UTC minute-of-day of the 15:00 London PM fix for that date (840 in BST, 900 in GMT)."""
    days=np.unique(t//1440)
    dt=pd.to_datetime(days*86400,unit='s')
    loc=(dt+pd.Timedelta(hours=12)).tz_localize('UTC').tz_convert('Europe/London')
    off=np.array([x.utcoffset().total_seconds()/60 for x in loc])
    fix=900-off
    return fix[np.searchsorted(days,t//1440)]
def fix_fade(m1,k_atr=1.0,look=90,exit_min=1080,sl_atr=1.5):
    """Q2: at London PM fix +5 min, if price moved >= k x ATR(h1) over the previous `look` minutes, fade it;
    SL sl_atr x ATR(h1), no TP, exit at exit_min UTC."""
    t=m1['t']; mod=t%1440; fx=_london_fix_utc(t)
    b=D.resample(m1,60); a=I.atr(b['h'],b['l'],b['c'],14); A=np.interp(t,b['t']+60,np.nan_to_num(a))
    k=np.flatnonzero(mod==fx+5)
    j0=np.searchsorted(t,t[k]-look-5); ok=(t[k]-t[j0])>=look   # bar at/after fix-look
    mv=m1['o'][k]-m1['o'][j0]
    d=np.where(mv>=k_atr*A[k],-1,np.where(mv<=-k_atr*A[k],1,0))
    sel=(d!=0)&ok&(A[k]>0); k,d=k[sel],d[sel]
    od,_=F._base(m1); od.place(k,E.MARKET,d,sl_atr*A[k],0.0)
    od.force_exit[F.eod_mask(m1,exit_min)]=True
    return od

def pdh_fail(m1,sweep_atr=0.2,rr=1.5,thr=99.0,sl_buf=0.3,tf=15,start=420,win_end=1080,eod=1200):
    """Q4: after 07:00, price trades beyond the previous day's high(low) by >= sweep_atr*ATR, then an m15 closes back
    inside -> fade; SL beyond the extreme + sl_buf ATR; TP rr x risk; optional quiet filter (vr20 < thr). 1/day."""
    b=D.resample(m1,tf); a=I.atr(b['h'],b['l'],b['c'],14)
    d_,didx=daily(m1)
    # previous calendar day with data, as in PDAY
    t=m1['t']; day=t//1440; st=np.flatnonzero(np.r_[True,day[1:]!=day[:-1]])
    dh=np.maximum.reduceat(m1['h'],st); dl=np.minimum.reduceat(m1['l'],st)
    cd=np.repeat(np.arange(len(st)),np.diff(np.r_[st,len(t)]))
    ph=np.r_[np.nan,dh[:-1]][cd]; pl=np.r_[np.nan,dl[:-1]][cd]
    ends=np.clip(b['act']-1,0,len(t)-1); PH,PL=ph[ends],pl[ends]; V=vr(m1,20)[ends]
    mb=D.minute_of_day(b['t']); bday=D.day_index(b['t'])
    n=len(b['t']); sig=np.zeros(n,int); sl=np.full(n,np.nan); cur=-1
    for i in range(n):
        if bday[i]!=cur: cur=bday[i]; eh=-np.inf; el=np.inf; done=False
        if mb[i]<start or mb[i]+tf>win_end or done or not np.isfinite(a[i]) or not np.isfinite(PH[i]): continue
        eh=max(eh,b['h'][i]); el=min(el,b['l'][i]); c=b['c'][i]
        if not (V[i]<thr): continue
        if eh>=PH[i]+sweep_atr*a[i] and c<PH[i]:
            sig[i]=-1; sl[i]=eh+sl_buf*a[i]-c; done=True
        elif el<=PL[i]-sweep_atr*a[i] and c>PL[i]:
            sig[i]=1; sl[i]=c-(el-sl_buf*a[i]); done=True
    k=np.flatnonzero(sig!=0); od,_=F._base(m1)
    od.place(b['act'][k],E.MARKET,sig[k],sl[k],rr*sl[k]); od.force_exit[F.eod_mask(m1,eod)]=True
    return od

def volc_x(m1,ratio=0.8,lookback=10,sl_atr=1.5,rr=2.5,block_start=0,block_end=0,min_width=0.0,trend=False):
    """VOLC + Friday close, plus optional: no entries/fills in [block_start, block_end) UTC minutes (news window),
    minimum 10-bar range width in ATRs, daily EMA50 trend filter."""
    od=volc_f(m1,ratio=ratio,lookback=lookback,sl_atr=sl_atr,rr=rr)
    t=m1['t']; mod=t%1440
    if block_end>block_start:
        blk=(mod>=block_start)&(mod<block_end); od.allow_entry[blk]=False; od.allow_fill[blk]=False
    if min_width>0 or trend:
        b=D.resample(m1,60); a=I.atr(b['h'],b['l'],b['c'],14)
        hh=I.rolling_max(b['h'],lookback); ll=I.rolling_min(b['l'],lookback)
        w=np.full(len(t),np.nan); act=b['act']; ok=act<len(t); w[act[ok]]=((hh-ll)/a)[ok]
        placed=od.kind[:,0]!=0
        if min_width>0:
            bad=placed&~(w>=min_width); od.kind[bad,:]=0
        if trend:
            s=daily_ema_side(m1,50); od.kind[~(s==1),0]=0; od.kind[~(s==-1),1]=0
    return od
def vsweep(grid,costs=('main','stress'),years=(2019,2022),be_list=(0.0,)):
    import itertools
    m1=R.get('USDJPY'); t=m1['t']; rows=[]; keys=list(grid)
    for vals in itertools.product(*[grid[k] for k in keys]):
        p=dict(zip(keys,vals))
        for be in be_list:
            od=volc_x(m1,**p); od.allow_entry[(t<R.minutes(f'{years[0]}-01-01'))|(t>=R.minutes(f'{years[1]+1}-01-01'))]=False
            row=dict(p); row['be']=be
            for c in costs:
                tr=R.run('USDJPY',od,c,be_R=be); y=tr.groupby(tr.entry_time.dt.year).R.sum()
                row[c+'_n']=len(tr); row[c+'_R']=round(tr.R.sum(),1); row[c+'_yrs']=' '.join(f'{v:+.0f}' for v in y.values)
                s=tr.sort_values('exit_time'); eq=np.r_[0,np.cumsum(s.R.values)]; row[c+'_DD']=round((np.maximum.accumulate(eq)-eq).max(),1)
            rows.append(row)
    return pd.DataFrame(rows)

def pday_trend_multi(m1,n=50,level='prev',cutoff=1080,sl_atr=2.0,rr=2.0,tf=15):
    """PDAYT that re-arms its stop order after a stopped-out trade: the allowed-side stop order is re-placed on every
    m1 bar from 07:00 until `cutoff`, so a second (third...) attempt happens if price crosses the level again.
    level='prev' = previous day's high/low (same level); level='day' = the day's own extreme so far (continuation)."""
    t=m1['t']; mod=t%1440; day=t//1440
    b=D.resample(m1,tf); a=I.atr(b['h'],b['l'],b['c'],14)
    A=np.full(len(t),np.nan); act=b['act']; ok=act<len(t); A[act[ok]]=a[ok]; A=pd.Series(A).ffill().to_numpy()
    st=np.flatnonzero(np.r_[True,day[1:]!=day[:-1]])
    dh=np.maximum.reduceat(m1['h'],st); dl=np.minimum.reduceat(m1['l'],st)
    cd=np.repeat(np.arange(len(st)),np.diff(np.r_[st,len(t)]))
    ph=np.r_[np.nan,dh[:-1]][cd]; pl=np.r_[np.nan,dl[:-1]][cd]
    if level=='day':
        rh=np.concatenate([np.maximum.accumulate(m1['h'][s:e]) for s,e in zip(st,np.r_[st[1:],len(t)])])
        rl=np.concatenate([np.minimum.accumulate(m1['l'][s:e]) for s,e in zip(st,np.r_[st[1:],len(t)])])
        ph=np.maximum(ph,rh); pl=np.minimum(pl,rl)
    side=daily_ema_side(m1,n)
    live=(mod>=420)&(mod<cutoff)&np.isfinite(ph)&np.isfinite(A)&np.isfinite(side)
    od=E.Orders(m1)
    up=live&(side==1); dn=live&(side==-1)
    k=np.flatnonzero(up); od.place(k,E.STOP,1,sl_atr*A[k],sl_atr*rr*A[k],price=ph[k],expiry_min=2,slot=0)
    k=np.flatnonzero(dn); od.place(k,E.STOP,-1,sl_atr*A[k],sl_atr*rr*A[k],price=pl[k],expiry_min=2,slot=1)
    od.force_exit[F.eod_mask(m1,1200)]=True
    return od
