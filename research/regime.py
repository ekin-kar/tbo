"""Monthly regime labels. RULES FIXED BEFORE LOOKING AT STRATEGY RESULTS:
 direction: efficiency ratio ER = |sum daily log-returns| / sum |daily log-returns| over the month's trading days.
            ER >= 0.30 -> 'up' or 'down' by sign of the monthly return, else 'range'.
 volatility: realised vol = std of daily log-returns in the month; relvol = vol / median(vol of previous 12 months).
            relvol >= 1.30 -> 'high', <= 0.77 -> 'low', else 'normal'.  (first 12 months: median of available prior months, min 3)
 Daily close = last 1m bar of each UTC weekday (Sunday stubs merged into Monday)."""
import R, numpy as np, pandas as pd
def labels(sym):
    m=R.get(sym); t=pd.to_datetime(m['t']*60,unit='s')
    s=pd.Series(m['c'],index=t)
    d=s.groupby(t.normalize()).last()
    d=d[d.index.dayofweek<5]            # Sunday stub rolls into Monday's return
    r=np.log(d).diff().dropna()
    g=r.groupby(r.index.to_period('M'))
    df=pd.DataFrame({'ret':g.sum(),'abs':g.apply(lambda x:x.abs().sum()),'vol':g.std(),'n':g.size()})
    df['ER']=df.ret.abs()/df['abs']
    df['direction']=np.where(df.ER>=0.30,np.where(df.ret>0,'up','down'),'range')
    prior=df.vol.shift(1).rolling(12,min_periods=3).median()
    df['relvol']=df.vol/prior
    df['vol_reg']=np.where(df.relvol>=1.30,'high',np.where(df.relvol<=0.77,'low','normal'))
    df.loc[df.relvol.isna(),'vol_reg']='normal'
    return df
if __name__=='__main__':
    for s in ['XAUUSD','USDJPY']:
        L=labels(s); L.to_pickle(R.C/f'reg_{s}.pkl')
        print(s); print(pd.crosstab(L.index.year,[L.direction]).T.to_string()); print(pd.crosstab(L.index.year,[L.vol_reg]).T.to_string())
