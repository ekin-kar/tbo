"""Research data layer: spliced Dukascopy(2016-2024) + broker(2025-) bid bars, two cost levels."""
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import numpy as np, pandas as pd
from pathlib import Path
from engine.data import _unpack
from engine import engine as E, indicators as I, data as D, metrics as M
U=D.UPLOADS; C=D.CACHE
SPLICE=int(pd.Timestamp('2025-01-01').value//60_000_000_000)
DIG={'XAUUSD':2,'USDJPY':3}
OFFSET={'XAUUSD':0.13,'USDJPY':0.0}          # broker bid - duka bid (measured 0.132 / 0.000)
CONS_MULT={'XAUUSD':0.65,'USDJPY':2.0}       # broker late-2024 spread / duka spread
CURR_REL={'XAUUSD':0.00003,'USDJPY':0.00001} # broker spread since Q2 2025 (gold) / Q4 2025 (jpy), fraction of price
def _fill_hour_month(t,sp):
    sp=sp.copy(); df=pd.DataFrame({'m':(pd.to_datetime(t*60,unit='s').to_period('M')).astype(str),'h':(t%1440)//60,'s':sp})
    med=df.groupby(['m','h']).s.transform('median'); sp=np.where(np.isnan(sp),med,sp)
    med2=df.assign(s=sp).groupby('h').s.transform('median'); sp=np.where(np.isnan(sp),med2,sp)
    return sp
def build(sym):
    f=C/f'{sym}_all.npz'
    if f.exists():
        z=np.load(f); return {k:z[k] for k in z.files}
    dk=np.load(C/f'{sym}_duka.npz'); br=_unpack((U/f'{sym}_M1.m1pack').read_bytes())
    m=dk['t']<SPLICE; bm=br.t.values>=SPLICE
    t=np.r_[dk['t'][m],br.t.values[bm]]
    out={'t':t}
    for k in 'ohlc': out[k]=np.r_[dk[k][m]+OFFSET[sym],br[k].values[bm]]
    out['v']=np.r_[dk['v'][m],br.v.values[bm]]
    dsp=_fill_hour_month(dk['t'][m],dk['sp'][m])
    s=pd.read_csv(U/f'{sym}_SPREAD.csv'); st=pd.to_datetime(s.Time).to_numpy().astype('datetime64[m]').astype(np.int64)
    ssp=s.AvgSpread.values*10.0**-DIG[sym]
    bt=br.t.values[bm]; idx=np.searchsorted(st,bt); idx=np.clip(idx,0,len(st)-1); ok=st[idx]==bt
    bsp=np.where(ok,ssp[idx],np.nan); print(sym,'broker spread coverage',ok.mean())
    bsp=_fill_hour_month(bt,bsp)
    out['sp_cons']=np.r_[CONS_MULT[sym]*dsp,bsp]
    out['sp_curr']=np.r_[CURR_REL[sym]*out['c'][:m.sum()],bsp]
    out['duka']=np.r_[np.ones(m.sum(),bool),np.zeros(bm.sum(),bool)]
    np.savez(f,**out); return out
_cache={}
def get(sym):
    if sym not in _cache: _cache[sym]=build(sym)
    return _cache[sym]
def run(sym,od,cost='cons',**kw):
    m1=get(sym); return E.run(sym,od,spread=m1['sp_'+cost],**kw)
minutes=lambda s: int(pd.Timestamp(s).value//60_000_000_000)
PERIODS={'old':(2016,2018),'dev':(2019,2022),'val':(2023,2024),'hold':(2025,2026)}
def yearly(tr):
    if len(tr)==0: return pd.DataFrame()
    y=tr.entry_time.dt.year
    g=tr.groupby(y)
    return pd.DataFrame({'n':g.size(),'R':g.R.sum().round(1),'avgR':g.R.mean().round(3),
        'PF':g.R.apply(lambda r: round(r[r>0].sum()/-r[r<=0].sum(),2) if (r<=0).any() else np.inf),
        'L_R':g.apply(lambda d:d.R[d.dir==1].sum()).round(1),'S_R':g.apply(lambda d:d.R[d.dir==-1].sum()).round(1)})
def per(tr,p):
    a,b=PERIODS[p]; y=tr.entry_time.dt.year; return tr[(y>=a)&(y<=b)]
def dev_only(tr): return per(tr,'dev')

# ── Round 2 cost model: CURRENT broker spread level for all years, Dukascopy/broker per-minute SHAPE kept ──
TARGET_REL={'XAUUSD':0.00003,'USDJPY':0.00001}   # current median spread as fraction of price
def _add_main(sym,m):
    if 'sp_main' in m: return m
    shape=m['sp_cons'].copy(); shape[m['duka']]/=CONS_MULT[sym]
    rel=shape/m['c']
    mon=(m['t']//1440)  # day index -> month key via pandas
    mk=pd.to_datetime(m['t']*60,unit='s').to_period('M').astype(str)
    med=pd.Series(rel).groupby(mk).transform('median').to_numpy()
    m['sp_main']=shape*(TARGET_REL[sym]/med)
    m['sp_stress']=2*m['sp_main']
    m['sp_real']=np.where(m['duka'],np.nan,m['sp_cons'])   # measured broker file (2025-26 only)
    return m
_get_old=get
def get(sym):
    return _add_main(sym,_get_old(sym))
