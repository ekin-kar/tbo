exec(open(__file__.rsplit('/',1)[0]+'/oct2026_lab.py').read())
g=R.get('XAUUSD'); j=R.get('USDJPY')
def rep(name,sym,od,**kw):
    for c in ('main','stress'):
        tr=R.run(sym,od,c,**kw); y=tr.entry_time.dt.year
        row={'name':name,'c':c,**st(tr)}
        for p,(a,b) in R.PERIODS.items(): row[p]=round(tr.R[(y>=a)&(y<=b)].sum(),1)
        print(row,flush=True)
print('== GOLD')
rep('base','XAUUSD',X.pday_trend(g))
for eod in (1020,1080,1140): rep(f'eod{eod}','XAUUSD',X.pday_trend(g,eod=eod))
for be in (1.0,1.5): rep(f'be{be}','XAUUSD',X.pday_trend(g),be_R=be)
for rr in (2.5,3.0): rep(f'rr{rr}','XAUUSD',X.pday_trend(g,rr=rr))
print('== USDJPY')
rep('base','USDJPY',X.volc_f(j))
for h in (12,16,20,24): rep(f'maxhold{h}h','USDJPY',X.volc_f(j),max_bars=h*60)
for be in (1.0,1.5): rep(f'be{be}+20h','USDJPY',X.volc_f(j),be_R=be,max_bars=1200)
