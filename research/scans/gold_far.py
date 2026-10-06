import sys, pathlib; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, R, ideas as X
from engine import engine as E, indicators as I, data as D
from engine.strategies import families as F
g=R.get('XAUUSD'); t=g['t']; mod=t%1440; day=t//1440
# per calendar day: previous calendar day's high/low (as PDAY), trend side, price at 01:15, ATR(m15) at 01:15
st=np.flatnonzero(np.r_[True,day[1:]!=day[:-1]]); dh=np.maximum.reduceat(g['h'],st); dl=np.minimum.reduceat(g['l'],st)
cd=np.repeat(np.arange(len(st)),np.diff(np.r_[st,len(t)])); ph=np.r_[np.nan,dh[:-1]][cd]; pl=np.r_[np.nan,dl[:-1]][cd]
side=X.daily_ema_side(g,40)
b=D.resample(g,15); a=I.atr(b['h'],b['l'],b['c'],14); A=np.full(len(t),np.nan); ok=b['act']<len(t); A[b['act'][ok]]=a[ok]; A=pd.Series(A).ffill().to_numpy()
dd,didx=X.daily(g); trd=np.r_[np.nan,np.maximum(dd['h'][1:],dd['c'][:-1])-np.minimum(dd['l'][1:],dd['c'][:-1])]; datr=pd.Series(trd).rolling(14).mean().shift(1).to_numpy()[didx]
k=np.flatnonzero((mod==75)&((day+3)%7<5)&np.isfinite(side)&np.isfinite(ph))
lvl=np.where(side[k]==1,ph[k],pl[k]); px=g['o'][k]; dist=np.where(side[k]==1,lvl-px,px-lvl)/datr[k]   # distance in DAILY ATRs
DAYS=pd.DataFrame({'day':day[k],'dist':dist,'side':side[k],'date':pd.to_datetime(day[k]*86400,unit='s')})
tr=R.run('XAUUSD',X.pday_trend(g),'main'); tr['day']=tr.entry_time.values.astype('datetime64[D]').astype(np.int64)
DAYS=DAYS.merge(tr[['day','R']],on='day',how='left'); DAYS['filled']=DAYS.R.notna(); DAYS['y']=DAYS.date.dt.year
DAYS['bucket']=pd.cut(DAYS.dist,[-9,0,0.25,0.5,0.75,1.0,1.5,9],labels=['already past','0-0.25','0.25-0.5','0.5-0.75','0.75-1.0','1.0-1.5','>1.5'])
g_=DAYS.groupby('bucket',observed=True).agg(days=('day','size'),fill_rate=('filled','mean'),trades=('filled','sum'),R=('R','sum'),avgR=('R','mean'))
print('distance from 01:15 price to the bot\'s order level, in DAILY ATRs (10 years):'); print(g_.round(2).to_string())
print('\nshare of trading days with NO gold trade:',round(1-DAYS.filled.mean(),3))
DAYS.to_pickle('/tmp/claude-0/-home-user-trade2/b9a9744d-83b2-50d8-8675-62baa49483d5/scratchpad/gold_days.pkl')
