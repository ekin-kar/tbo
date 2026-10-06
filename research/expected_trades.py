"""Engine expected trade list for PDAYT on BROKER data from 12 Nov 2024 (Dukascopy+0.13 only fills history before
10 Apr 2024 and the broker's 4 Oct-12 Nov 2024 gap, so the EMA and 12 Nov levels match a gap-free cTrader history)."""
import R, ideas as X, numpy as np, pandas as pd
from engine.data import _unpack
from engine import engine as E, indicators as I
M=lambda s:int(pd.Timestamp(s).value//60_000_000_000)
br=_unpack(open(R.U/'XAUUSD_M1.m1pack','rb').read())
dk=np.load(R.C/'XAUUSD_duka.npz')
g0,g1=M('2024-10-04 20:59'),M('2024-11-12 15:18')
sel=(dk['t']<M('2024-04-10'))|((dk['t']>=g0)&(dk['t']<g1))
t=np.r_[dk['t'][sel],br.t.values]; o=np.argsort(t,kind='stable'); t=t[o]
m1={'t':t}
for k in 'ohlc': m1[k]=np.r_[dk[k][sel]+0.13,br[k].values][o]
m1['v']=np.r_[dk['v'][sel],br.v.values][o]
assert (np.diff(t)>0).all()
# spreads: measured file where present, else 0.65 x Dukascopy (broker late-2024 level)
s=pd.read_csv(R.U/'XAUUSD_SPREAD.csv'); st=pd.to_datetime(s.Time).to_numpy().astype('datetime64[m]').astype(np.int64)
idx=np.clip(np.searchsorted(st,t),0,len(st)-1); ok=st[idx]==t
dsp=pd.Series(dk['sp'],index=dk['t']); dfill=dsp.reindex(t).to_numpy()*0.65
sp=np.where(ok,s.AvgSpread.values[idx]*0.01,np.nan); sp=np.where(np.isnan(sp),dfill,sp)
sp=R._fill_hour_month(t,sp)
np.savez(R.C/'hybrid_gold.npz',**m1,sp=sp)
tr=E.run('XAUUSD',X.pday_trend(m1),spread=sp)
tr=tr[tr.entry_time>='2024-11-12'].reset_index(drop=True)
# day-level table
d,didx=X.daily(m1); e=I.ema(d['c'],40)
keys=pd.to_datetime(d['key']*86400,unit='s')
day=pd.DataFrame({'key':keys,'close':d['c'],'ema40':e})
day['side_next']=np.where(day.close>day.ema40,'LONG','SHORT')
rows=[]
mod=t%1440; k07=np.flatnonzero((mod==75)&(t>=M('2024-11-12')))
cal=t//1440; st_=np.flatnonzero(np.r_[True,cal[1:]!=cal[:-1]])
dh=np.maximum.reduceat(m1['h'],st_); dl=np.minimum.reduceat(m1['l'],st_)
cd=np.repeat(np.arange(len(st_)),np.diff(np.r_[st_,len(t)]))
b=X.D.resample(m1,15); a=I.atr(b['h'],b['l'],b['c'],14); A=np.interp(t,b['t']+15,np.nan_to_num(a))
for j in k07:
    kd=didx[j]; prev=kd-1
    c,em=d['c'][prev],e[prev]; side=1 if c>em else -1
    ph,pl=dh[cd[j]-1],dl[cd[j]-1]
    date=pd.to_datetime(t[j]*60,unit='s').normalize()
    tt=tr[tr.entry_time.dt.normalize()==date]
    rows.append(dict(date=date.date(),wd=date.day_name()[:3],trend_day=keys[prev].date(),last_close=round(c,2),ema40=round(em,2),
        dist_pct=round((c-em)/em*100,3),side='LONG' if side>0 else 'SHORT',
        order=('BUY STOP' if side>0 else 'SELL STOP')+(' (market: already beyond)' if (side>0 and m1['o'][j]+sp[j]>=ph) or (side<0 and m1['o'][j]<=pl) else ''),
        level=round(ph if side>0 else pl,2),sl_dist=round(2*A[j],2),
        filled='yes' if len(tt) else 'no',entry_time=tt.entry_time.iloc[0] if len(tt) else '',entry=round(tt.entry.iloc[0],2) if len(tt) else '',
        exit_time=tt.exit_time.iloc[0] if len(tt) else '',exit=round(tt.exit.iloc[0],2) if len(tt) else '',
        reason=tt.reason.iloc[0] if len(tt) else '',R=round(tt.R.iloc[0],2) if len(tt) else ''))
days=pd.DataFrame(rows)
days['near_ema']=np.where(days.dist_pct.abs()<0.1,'CHECK','')
days.to_csv(R.C.parent/'PDAYT_expected_days.csv',index=False)
out=tr[['entry_time','dir','entry','sl_dist','exit_time','exit','reason','R']].copy()
out['dir']=np.where(out.dir==1,'BUY','SELL'); out=out.round({'entry':2,'sl_dist':2,'exit':2,'R':3})
out.to_csv(R.C.parent/'PDAYT_expected_trades.csv',index=False)
print('trades',len(tr),'R',round(tr.R.sum(),1),'win%',round((tr.R>0).mean()*100,1),'days listed',len(days),'filled',(days.filled=="yes").sum(),'near-EMA days',(days.near_ema=="CHECK").sum())
print(tr.groupby(tr.entry_time.dt.to_period('Q')).R.agg(['size','sum']).round(1).T.to_string())
print('check: trades on days not in day table',set(tr.entry_time.dt.date)-set(days.date))
print(days.head(8).to_string())
