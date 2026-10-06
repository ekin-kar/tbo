import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from engine import data as D
from engine.data import _unpack
import pandas as pd, numpy as np
from pathlib import Path
U=D.UPLOADS
def ld(n): return _unpack((U/n).read_bytes())
for sym,dig in [('XAUUSD',2),('USDJPY',3)]:
    b=ld(f'{sym}_DUKA_BID.m1pack'); a=ld(f'{sym}_DUKA_ASK.m1pack'); br=ld(f'{sym}_M1.m1pack')
    m=b.merge(a[['t','o','c','h','l']],on='t',how='left',suffixes=('','_a'))
    sp=((m.o_a-m.o)+(m.c_a-m.c))/2
    m['sp']=sp.clip(lower=0)
    print(sym,'ask missing frac',m.o_a.isna().mean())
    m['yr']=pd.to_datetime(m.t*60,unit='s').dt.year
    print((m.groupby('yr').apply(lambda g:(g.sp/g.c).median()*100)).round(4).to_dict())
    # overlap with broker
    o=m.merge(br[['t','o','c','h','l']],on='t',suffixes=('','_b'))
    o=o[o.t>=pd.Timestamp('2024-06-01').value//60_000_000_000]
    print('overlap rows',len(o),'bid offset median (broker-duka) close',(o.c_b-o.c).median(),'daily-ish std',(o.c_b-o.c).std())
    s=pd.read_csv(U/f'{sym}_SPREAD.csv'); s['t']=pd.to_datetime(s.Time).to_numpy().astype('datetime64[m]').astype('int64')
    s['sp_b']=s.AvgSpread*10**-dig
    q=m.merge(s[['t','sp_b']],on='t')
    q['mon']=pd.to_datetime(q.t*60,unit='s').dt.to_period('M')
    print('ratio broker/duka by month (median of ratio of medians):')
    print(q.groupby('mon').apply(lambda g: round(g.sp_b.median()/g.sp.median(),3)).to_dict())
    s['mon']=pd.to_datetime(s.t*60,unit='s').dt.to_period('Q')
    bb=br.merge(s[['t','sp_b','mon']],on='t')
    print('broker rel spread % by quarter',bb.groupby('mon').apply(lambda g:round((g.sp_b/g.c).median()*100,5)).to_dict())
    np.savez(D.CACHE/f'{sym}_duka.npz',t=m.t.values,o=m.o.values,h=m.h.values,l=m.l.values,c=m.c.values,v=m.v.values,sp=m.sp.fillna(np.nan).values)
