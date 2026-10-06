import sys; import pathlib; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import R, ideas as X, numpy as np, pandas as pd
from engine import engine as E, indicators as I, data as D
from engine.strategies import families as F
def st(tr):
    if len(tr)==0: return dict(n=0)
    s=tr.sort_values('exit_time'); c=np.r_[0,np.cumsum(s.R.values)]
    pos,neg=tr.R[tr.R>0].sum(),-tr.R[tr.R<=0].sum()
    return dict(n=len(tr),R=round(tr.R.sum(),1),PF=round(pos/max(neg,1e-9),2),DD=round((np.maximum.accumulate(c)-c).max(),1))
def report(name,sym,od,costs=('main','stress')):
    out={}
    for c in costs:
        tr=R.run(sym,od,c); y=tr.entry_time.dt.year
        row={'name':name,'cost':c,**st(tr)}
        for p,(a,b) in R.PERIODS.items(): row[p]=round(tr.R[(y>=a)&(y<=b)].sum(),1)
        row['yrs']=' '.join(f'{v:+.0f}' for v in tr.groupby(y).R.sum().values)
        out[c]=(row,tr); print(row,flush=True)
    return out
_base={}
def base():
    if not _base:
        _base['g']=R.run('XAUUSD',X.pday_trend(R.get('XAUUSD')),'main')
        _base['j']=R.run('USDJPY',X.volc_f(R.get('USDJPY')),'main')
    return _base
def corr(tr):
    b=base(); f=lambda t:t.groupby(t.exit_time.dt.floor('D')).R.sum()
    df=pd.DataFrame({'g':f(b['g']),'j':f(b['j']),'x':f(tr)}).fillna(0)
    w=df.resample('W').sum()
    return dict(cd_g=round(df.corr().loc['x','g'],2),cd_j=round(df.corr().loc['x','j'],2),cw_g=round(w.corr().loc['x','g'],2),cw_j=round(w.corr().loc['x','j'],2))
