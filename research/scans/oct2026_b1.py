exec(open(__file__.rsplit('/',1)[0]+'/oct2026_lab.py').read())
g=R.get('XAUUSD'); j=R.get('USDJPY')
print('== USDJPY PDAYT (prev-day break + daily EMA40)')
for start in (0,75,180,420):
    for sl in (1.5,2.0):
        report(f'UJ pdayt s{start} sl{sl}','USDJPY',X.pday_trend(j,sl_atr=sl,start=start),costs=('main',))
print('== Gold VOLC 24h (Fri close)')
for ratio in (0.7,0.8):
    for rr in (2.0,2.5):
        report(f'G volc r{ratio} rr{rr}','XAUUSD',X.volc_f(g,ratio=ratio,rr=rr),costs=('main',))
print('== VOLC h4 / m30 on both')
for sym,m in (('USDJPY',j),('XAUUSD',g)):
    for tf in (30,240):
        od=F.vol_contraction(m,tf=tf,ratio=0.8,lookback=10,sl_atr=1.5,rr=2.5,hold_min=24*60 if tf<240 else 5*1440)
        report(f'{sym} volc tf{tf}',sym,od,costs=('main',))
