import R, numpy as np, pandas as pd
from engine import engine as E, indicators as I, data as D
from engine.strategies import families as F
def random_like(sym,tr,sl_mult,rr,eod=None,tf=15,atr_n=14,seeds=40,cost='cons',max_bars=0,years=None,extra_exit=None):
    """Random market entries: same count per year, same minute-of-day as the real trades, same long share,
    same SL (x ATR tf) / TP rules and same forced flat time. Returns list of total R per seed."""
    m1=R.get(sym); t=m1['t']
    b=D.resample(m1,tf); a=I.atr(b['h'],b['l'],b['c'],atr_n); A=np.interp(t,b['t']+tf,np.nan_to_num(a))
    pl=(tr.dir==1).mean()
    et=tr.entry_time.values.astype('datetime64[m]').astype(np.int64)
    days=np.unique(t//1440); dyear=pd.to_datetime(days*86400,unit='s').year.values
    tset=set(t.tolist()); pools={y:days[dyear==y] for y in np.unique(dyear)}
    out=[]
    for s in range(seeds):
        rng=np.random.default_rng(s)
        idxs=[]
        for e in et:
            y=pd.Timestamp(e*60e9).year; mod=e%1440
            pool=pools[y]
            for _ in range(20):
                d=rng.choice(pool)
                if d*1440+mod in tset: idxs.append(np.searchsorted(t,d*1440+mod)); break
        idxs=np.unique(np.array(idxs))
        od=E.Orders(m1)
        dirs=np.where(rng.random(len(idxs))<pl,1,-1)
        od.place(idxs,E.MARKET,dirs,sl_mult*A[idxs],sl_mult*rr*A[idxs] if rr>0 else 0.0)
        if eod is not None: od.force_exit[F.eod_mask(m1,eod)]=True
        if extra_exit is not None: od.force_exit|=extra_exit
        r=R.run(sym,od,cost,max_bars=max_bars)
        out.append(r.R.sum())
    return np.array(out)
