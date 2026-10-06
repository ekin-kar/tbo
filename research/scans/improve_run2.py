exec(open(__file__.rsplit('/',1)[0]+'/improve_lab.py').read())
import challenge_test as CT
g=R.get('XAUUSD'); SP='/tmp/claude-0/-home-user-trade2/b9a9744d-83b2-50d8-8675-62baa49483d5/scratchpad/'
def st2(tr,lab):
    r=st(tr,lab); mo=tr.groupby(tr.exit_time.dt.to_period('M')).R.sum(); print(f"{'':40s}   monthly Sharpe {mo.mean()/mo.std():.3f}  worst 6 months {mo.rolling(6).sum().min():+.1f}")
print('== gold: cancel unfilled orders at ... (UTC)')
OUT={}
for cut in (540,600,660,690,720,750,780,840,900,960,1200):
    od=X.pday_trend(g); od.expiry[:]=np.minimum(od.expiry,cut-75); tr=R.run('XAUUSD',od,'main'); st2(tr,f'  cancel at {cut//60:02d}:{cut%60:02d}'); OUT[cut]=tr
OUT[720].to_pickle(SP+'TG_c12.pkl'); OUT[840].to_pickle(SP+'TG_c14.pkl')
print('\n== when do fills happen and how good are they? (baseline, by fill hour UTC)')
b=OUT[1200]; h=b.entry_time.dt.hour; y=b.entry_time.dt.year
era=np.select([y<=2018,y<=2022,y<=2024],['16-18','19-22','23-24'],'25-26')
print(b.assign(h=pd.cut(h,[0,3,6,9,12,15,20],right=False),era=era).pivot_table(index='h',columns='era',values='R',aggfunc=['sum','count'],observed=True).round(1).to_string())
print('\n== USD concentration: gold long + USDJPY short (or gold short + USDJPY long) open at the same time')
TG=pd.read_pickle(SP+'TG.pkl'); TJ=pd.read_pickle(SP+'TJ.pkl')
G=CT.clean('XAUUSD',TG,0.02).assign(b='g',usd=lambda d:-d.dir); J=CT.clean('USDJPY',TJ,0.002).assign(b='j',usd=lambda d:d.dir)
A=pd.concat([G,J]).sort_values('entry_time').reset_index(drop=True)
same=np.zeros(len(A),bool)
for i,r in A.iterrows():
    o=A[(A.b!=r.b)&(A.entry_time<r.entry_time)&(A.exit_time>r.entry_time)]
    same[i]=(o.usd==r.usd).any()
A['same']=same
print(f"trades entering while the other bot holds the SAME dollar bet: {same.sum()} ({100*same.mean():.0f}%) | their avg R {A.R[same].mean():+.3f} vs others {A.R[~same].mean():+.3f}")
for lab,w in (('as now',1.0),('halve 2nd same-USD trade',0.5),('skip 2nd same-USD trade',0.0)):
    x=A.copy(); x['P']=np.where(x.b=='g',0.6,0.8)*x.R*np.where(x.same,w,1.0)
    s=x.sort_values('exit_time'); c=np.r_[0,np.cumsum(s.P.values)]; dd=(np.maximum.accumulate(c)-c).max(); mo=x.groupby(x.exit_time.dt.to_period('M')).P.sum()
    yy=x.entry_time.dt.year
    print(f"  {lab:28s} total {x.P.sum():+6.1f}%  maxDD {dd:5.1f}%  ret/DD {x.P.sum()/dd:5.2f}  monthly Sharpe {mo.mean()/mo.std():.3f} | "+' '.join(f"{p}={x.P[(yy>=a)&(yy<=b_)].sum():+5.1f}" for p,(a,b_) in R.PERIODS.items()))
