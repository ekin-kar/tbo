exec(open(__file__.rsplit('/',1)[0]+'/gold_sessions.py').read().split("if __name__=='__main__':")[0])
import challenge_test as CT
V=CT.clean('USDJPY',R.run('USDJPY',X.volc_f(R.get('USDJPY')),'main',max_bars=1200),0.002)
Gb=CT.G
for name,kw in (('ASIAB (no trend)',dict(lv='PASIA',tw='ASIA',sl=2.0,rr=3.0,hold_to=1200)),('ASIAB +trend',dict(lv='PASIA',tw='ASIA',sl=2.0,rr=3.0,trend=40,hold_to=1200))):
    od=brk(**kw)
    for c in ('main','stress'):
        tr=R.run('XAUUSD',od,c); tr['R']-=0.02; y=tr.entry_time.dt.year
        print(f"{name} [{c}] {evalt(tr)}")
    print('   per year:',' '.join(f"{a}:{b:+.0f}" for a,b in tr.groupby(y).R.sum().items()))
    print('   long',round(tr.R[tr.dir==1].sum(),1),'short',round(tr.R[tr.dir==-1].sum(),1),'| reasons',tr.reason.value_counts().to_dict())
    tr.to_pickle(f"/tmp/claude-0/-home-user-trade2/b9a9744d-83b2-50d8-8675-62baa49483d5/scratchpad/{'asiab_t' if '+trend' in name else 'asiab'}.pkl")
# pass effect, closed trades: same simulator as acct_speed.py with a third stream
src=open(__file__.rsplit('/',1)[0]+'/acct_speed.py').read()
for nm in ('asiab','asiab_t'):
    A3=pd.read_pickle(f"/tmp/claude-0/-home-user-trade2/b9a9744d-83b2-50d8-8675-62baa49483d5/scratchpad/{nm}.pkl")
    A3=CT.clean('XAUUSD',A3.assign(R=A3.R+0.02),0.02)
    S=[Gb[['exit_time','R']],V[['exit_time','R']],A3[['exit_time','R']]]
    ns={**globals(),'S':S}; exec(src[src.index('days=CT.days'):src.index('ACC=[')],ns)
    M,SS,K,sim=ns['M'],ns['SS'],ns['K'],ns['sim']; days=CT.days
    st_=np.arange(np.searchsorted(days,pd.Timestamp('2016-01-04')),np.searchsorted(days,pd.Timestamp('2025-09-19')))
    rec=np.arange(np.searchsorted(days,pd.Timestamp('2023-10-02')),np.searchsorted(days,pd.Timestamp('2025-09-19')))
    print(f'\n== pass effect with {nm} (closed trades; FundedHive Low 10%/5%, 2% daily, 1%/trade, bot stop 1.5%)')
    for lab,rk in (('now gold .4 / UJ .5',[0.4,0.5,0]),('+ new .2',[0.4,0.5,0.2]),('+ new .3',[0.4,0.5,0.3]),('+ new .4',[0.4,0.5,0.4]),('gold .3 / UJ .5 + new .3',[0.3,0.5,0.3])):
        line=f'  {lab:26s}'
        for wl,ss in (('2016-25',st_),('since Oct 23',rec)):
            ok,fail,end=sim(ss,rk,(0.10,),0.95,0.02,0.01,0.015); mt=end/21; p=ok.mean()
            line+=f' | {wl}: pass {100*p:5.1f}% fail {100*fail.mean():4.1f}% median {np.median(mt[ok]):4.1f}mo E={mt.mean()/p:4.1f}mo'
        print(line,flush=True)
    print(f'== Funding Pips 12%/12%, 2% daily')
    for lab,rk in (('now gold .6 / UJ .8',[0.6,0.8,0]),('+ new .3',[0.6,0.8,0.3]),('+ new .5',[0.6,0.8,0.5])):
        line=f'  {lab:26s}'
        for wl,ss in (('2016-25',st_),('since Oct 23',rec)):
            ok,fail,end=sim(ss,rk,(0.12,),0.88,0.02,1.0,0.015); mt=end/21; p=ok.mean()
            line+=f' | {wl}: pass {100*p:5.1f}% fail {100*fail.mean():4.1f}% median {np.median(mt[ok]):4.1f}mo'
        print(line,flush=True)
