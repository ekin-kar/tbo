"""Does any condition known at entry rank trades consistently in all four periods? (candidate for position sizing)"""
import sys, pathlib; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, R, ideas as X, challenge_test as CT
from engine import data as D, indicators as I
def feats(sym, tr):
    m=R.get(sym); t=m['t']; ei=np.searchsorted(t, tr.entry_time.values.astype('datetime64[m]').astype(np.int64))
    b=D.resample(m,60); a=I.atr(b['h'],b['l'],b['c'],14); a100=I.atr(b['h'],b['l'],b['c'],100)
    j=np.searchsorted(b['act'],ei,side='right')-1
    dd,didx=X.daily(m); trd=np.r_[np.nan,np.maximum(dd['h'][1:],dd['c'][:-1])-np.minimum(dd['l'][1:],dd['c'][:-1])]
    datr=pd.Series(trd).rolling(14).mean().shift(1).to_numpy()
    dpct=pd.Series(datr/dd['c']).rolling(250,min_periods=120).rank(pct=True).shift(0).to_numpy()   # vol regime percentile (known at day start)
    e40=pd.Series(dd['c']).ewm(span=40,adjust=False).mean().to_numpy(); ext=np.r_[np.nan,((dd['c']-e40)/datr)[:-1]]   # yesterday's close vs EMA40, in daily ATRs
    di=didx[ei]
    vol=pd.Series(m['v']).rolling(240,min_periods=60).sum().to_numpy()                       # tick volume of the 4 hours before entry
    vrel=vol[np.maximum(ei-1,0)]/pd.Series(vol).rolling(240*20,min_periods=240*5).median().to_numpy()[np.maximum(ei-1,0)]
    f=pd.DataFrame(index=tr.index)
    f['hour']=tr.entry_time.dt.hour.values
    f['weekday']=tr.entry_time.dt.dayofweek.values
    f['quiet']=(a/a100)[j]                                                                    # ATR14/ATR100 (h1) at entry
    f['vol_regime']=dpct[di]
    f['ema_dist']=np.abs(ext[di])*np.sign(ext[di])*tr.dir.values                              # distance from EMA40 in the trade's direction
    f['vol_before']=vrel
    return f
P=R.PERIODS
def table(name, tr, f, col, bins, labels):
    x=tr.assign(b=pd.cut(f[col],bins,labels=labels), y=tr.entry_time.dt.year)
    rows=[]
    for p,(a,b) in P.items():
        s=x[(x.y>=a)&(x.y<=b)]; rows.append(s.groupby('b',observed=False).R.mean().rename(p))
    T=pd.concat(rows,axis=1); T['n']=x.groupby('b',observed=False).R.size()
    rk=T[list(P)].rank(ascending=False); consistent=(rk.max(axis=1)-rk.min(axis=1)).max()==0 if len(T)>1 else False
    best=T[list(P)].idxmax(); worst=T[list(P)].idxmin()
    same_best=best.nunique()==1; same_worst=worst.nunique()==1
    print(f'\n-- {name}: {col}  (avg R per trade; best bucket same in all periods: {same_best}, worst same: {same_worst})')
    print(T.round(3).to_string())
G=CT.clean('XAUUSD',R.run('XAUUSD',X.pday_trend(R.get('XAUUSD')),'main'),0.02).reset_index(drop=True)
J=CT.clean('USDJPY',R.run('USDJPY',X.volc_f(R.get('USDJPY')),'main',max_bars=1200),0.002).reset_index(drop=True)
fg=feats('XAUUSD',G); fj=feats('USDJPY',J)
print('############ USDJPY')
table('USDJPY',J,fj,'hour',[-1,6,11,15,19,24],['Asia 00-07','London 07-12','LDN/NY 12-16','NY 16-20','late 20-24'])
table('USDJPY',J,fj,'weekday',[-1,0,1,2,3,4],['Mon','Tue','Wed','Thu','Fri'])
table('USDJPY',J,fj,'quiet',[0,0.6,0.7,0.75,0.8],['<0.6','0.6-0.7','0.7-0.75','0.75-0.8'])
table('USDJPY',J,fj,'vol_regime',[0,0.25,0.5,0.75,1.01],['low vol','mid-low','mid-high','high vol'])
table('USDJPY',J,fj,'ema_dist',[-99,-1,0,1,99],['against, far','against','with','with, far'])
table('USDJPY',J,fj,'vol_before',[0,0.7,1.0,1.4,99],['very low','low','high','very high'])
print('\n############ GOLD')
table('GOLD',G,fg,'vol_regime',[0,0.25,0.5,0.75,1.01],['low vol','mid-low','mid-high','high vol'])
table('GOLD',G,fg,'ema_dist',[0,0.5,1.5,3,99],['0-0.5 ATR','0.5-1.5','1.5-3','>3 ATR'])
table('GOLD',G,fg,'vol_before',[0,0.7,1.0,1.4,99],['very low','low','high','very high'])
table('GOLD',G,fg,'weekday',[-1,0,1,2,3,4],['Mon','Tue','Wed','Thu','Fri'])
table('GOLD',G,fg,'hour',[-1,2,6,11,15,20],['01-03 (Asia)','03-07','07-12 London','12-16 NY','16-20'])
