import R, pandas as pd, sys
def split(tr,sym,years=None):
    L=pd.read_pickle(R.C/f'reg_{sym}.pkl')
    tr=tr.copy(); tr['m']=tr.entry_time.dt.to_period('M')
    if years: tr=tr[tr.entry_time.dt.year.between(*years)]
    tr=tr.join(L[['direction','vol_reg']],on='m')
    out=[]
    for col in ['direction','vol_reg']:
        g=tr.groupby(col); nm=tr.groupby(col).m.nunique()
        out.append(pd.DataFrame({'months':nm,'n':g.size(),'R':g.R.sum().round(1),'R/month':(g.R.sum()/nm).round(2),'avgR':g.R.mean().round(3)}))
    return pd.concat(out)
if __name__=='__main__':
    per=sys.argv[1]; yrs=R.PERIODS[per]
    for name,sym in [('PDAY','XAUUSD'),('VOLC','USDJPY')]:
        for c in ['cons','curr']:
            tr=pd.read_pickle(R.C/f'tr_{name}_{c}.pkl')
            print(name,c,per); print(split(tr,sym,yrs).to_string())
