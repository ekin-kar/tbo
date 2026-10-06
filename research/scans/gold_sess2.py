exec(open(__file__.rsplit('/',1)[0]+'/gold_sessions.py').read().split("if __name__=='__main__':")[0])
import challenge_test as CT
base=R.run('XAUUSD',X.pday_trend(g),'main'); base['R']-=0.02
def placed_at(lv,tw,start,**kw):
    s0=WIN[tw]; WIN[tw]=(start,s0[1])
    try: return brk(lv,tw,**kw)
    finally: WIN[tw]=s0
def combo(tr,w=1.0):
    a=pd.concat([base[['entry_time','exit_time','R','dir']],tr.assign(R=tr.R*w)[['entry_time','exit_time','R','dir']]]).sort_values('exit_time')
    c=np.r_[0,np.cumsum(a.R.values)]; dd=(np.maximum.accumulate(c)-c).max(); mo=a.groupby(a.exit_time.dt.to_period('M')).R.sum()
    return a.R.sum(),dd,mo.mean()/mo.std()
def overlap(tr):
    bd=set(base.entry_time.dt.date); td=tr.entry_time.dt.date
    same=td.isin(bd); m=tr[same].assign(d=lambda x:x.entry_time.dt.date).merge(base.assign(d=base.entry_time.dt.date)[['d','dir','R']],on='d',suffixes=('','_b'))
    f=lambda x:x.groupby(x.entry_time.dt.date).R.sum()
    c=pd.concat([f(base),f(tr)],axis=1).fillna(0).corr().iloc[0,1]
    return f"same-day as gold bot {100*same.mean():.0f}% (same direction {100*(m.dir==m.dir_b).mean():.0f}%) | daily corr {c:.2f} | R on days gold bot has no trade: {tr.R[~same].sum():+.1f} ({(~same).sum()} trades)"
r0=combo(base.iloc[:0]); print(f"gold bot alone: R={r0[0]:.1f} DD={r0[1]:.1f} R/DD={r0[0]/r0[1]:.2f} monthly Sharpe={r0[2]:.2f}")
C={'PASIA->ASIA sl2 rr3':dict(lv='PASIA',tw='ASIA',sl=2.0,rr=3.0,hold_to=1200),
   'PASIA->ASIA sl2 rr3 +trend':dict(lv='PASIA',tw='ASIA',sl=2.0,rr=3.0,trend=40,hold_to=1200),
   'PLON->ASIA sl2 rr3 narrow':dict(lv='PLON',tw='ASIA',sl=2.0,rr=3.0,narrow=0.5,hold_to=1200)}
for name,kw in C.items():
    tr=R.run('XAUUSD',brk(**kw),'main'); tr['R']-=0.02
    print(f"\n== {name}: {evalt(tr)}"); print('   ',overlap(tr))
    for w in (0.5,1.0):
        r=combo(tr,w); print(f"    gold bot + this at {w}x risk: R={r[0]:.1f} DD={r[1]:.1f} R/DD={r[0]/r[1]:.2f} monthly Sharpe={r[2]:.2f}")
print('\n== neighbours of PASIA->ASIA (placement time x stop x target), hold to 20:00, no trend: R | all-4-periods-positive')
rows=[]
for st_,sl,rr in itertools.product((0,75,120),(1.5,2.0,2.5),(2.0,2.5,3.0,4.0)):
    tr=R.run('XAUUSD',placed_at('PASIA','ASIA',st_,sl=sl,rr=rr,hold_to=1200),'main'); e=evalt(tr)
    rows.append(dict(place=f'{st_//60:02d}:{st_%60:02d}',sl=sl,rr=rr,R=e['R'],ok=all(e[p]>0 for p in ('old','dev','val','hold')),PF=e['PF'],DD=e['DD']))
nb_=pd.DataFrame(rows); print(nb_.pivot_table(index=['place','sl'],columns='rr',values='R').round(0).to_string())
print('all 4 periods positive:'); print(nb_.pivot_table(index=['place','sl'],columns='rr',values='ok').to_string())
