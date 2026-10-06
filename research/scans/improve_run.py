exec(open(__file__.rsplit('/',1)[0]+'/improve_lab.py').read())
g=R.get('XAUUSD'); j=R.get('USDJPY')
TG=R.run('XAUUSD',X.pday_trend(g),'main'); mg,eg,fg=prep('XAUUSD',TG,gold_fx)
TJ=R.run('USDJPY',X.volc_f(j),'main',max_bars=1200); mj,ej,fj=prep('USDJPY',TJ,jpy_fx)
print('################ GOLD (PDAYT) ################')
st(TG,'baseline (2R, flat 20:00)')
print('-- 1. scale out')
for tp1,frac,tp in ((1.0,0.5,2.0),(1.0,0.5,3.0),(1.0,0.5,4.0),(1.5,0.5,3.0),(1.0,0.33,3.0)):
    st(resim('XAUUSD',TG,mg,eg,fg,tp=tp,tp1=tp1,frac=frac),f'  {int(frac*100)}% at {tp1}R, rest at {tp}R')
st(resim('XAUUSD',TG,mg,eg,fg,tp=3.0,tp1=1.0,frac=0.5,be=1.0),'  50% at 1R + BE, rest at 3R')
print('-- 4. time-decay exit (not +x R after N hours -> exit)')
for N,dR in ((120,0.5),(240,0.5),(240,0.25),(360,0.5),(480,0.5),(240,1.0)):
    st(resim('XAUUSD',TG,mg,eg,fg,tp=2.0,dN=N,dR=dR),f'  after {N//60}h best < {dR}R -> exit')
print('-- 2. breakout buffer, 5. order life, 6. weekly trend, 3. close confirmation (engine)')
b15=D.resample(g,15); a15=I.atr(b15['h'],b15['l'],b15['c'],14); A=np.full(len(g['t']),np.nan); ok=b15['act']<len(g['t']); A[b15['act'][ok]]=a15[ok]; A=pd.Series(A).ffill().to_numpy()
for buf in (0.1,0.2,0.3):
    od=X.pday_trend(g); k=od.kind!=0
    od.price[:,0]=np.where(od.kind[:,0]!=0,od.price[:,0]+buf*A,od.price[:,0]); od.price[:,1]=np.where(od.kind[:,1]!=0,od.price[:,1]-buf*A,od.price[:,1])
    st(R.run('XAUUSD',od,'main'),f'  buffer {buf} ATR beyond the level')
for cut in (600,720,960):
    od=X.pday_trend(g); od.expiry[:]=np.minimum(od.expiry,cut-75); st(R.run('XAUUSD',od,'main'),f'  orders cancelled at {cut//60}:00')
# weekly trend: prior completed week's close vs EMA10 of weekly closes
t=g['t']; day=t//1440; wk=(day+3)//7; ws=np.flatnonzero(np.r_[True,wk[1:]!=wk[:-1]]); wc=g['c'][np.r_[ws[1:],len(t)]-1]
for n in (10,20):
    e=pd.Series(wc).ewm(span=n,adjust=False).mean().to_numpy(); s=np.where(wc>e,1,-1); s=np.r_[0,s[:-1]]
    widx=np.repeat(np.arange(len(ws)),np.diff(np.r_[ws,len(t)])); W=s[widx]
    od=X.pday_trend(g); od.kind[~(W==1),0]=0; od.kind[~(W==-1),1]=0; st(R.run('XAUUSD',od,'main'),f'  + weekly trend (EMA{n} of weekly closes)')
# close confirmation: first m15 close beyond the level on the trend side, 01:15-19:00 -> market
dd,didx=X.daily(g); 
st_=np.flatnonzero(np.r_[True,day[1:]!=day[:-1]]); dh=np.maximum.reduceat(g['h'],st_); dl=np.minimum.reduceat(g['l'],st_)
cd=np.repeat(np.arange(len(st_)),np.diff(np.r_[st_,len(t)])); ph=np.r_[np.nan,dh[:-1]][cd]; pl=np.r_[np.nan,dl[:-1]][cd]; side=X.daily_ema_side(g,40)
bend=np.clip(b15['act']-1,0,len(t)-1); bm=b15['t']%1440; bd=b15['t']//1440
up=(b15['c']>ph[bend])&(side[bend]==1); dn=(b15['c']<pl[bend])&(side[bend]==-1); win=(bm>=60)&(bm+15<=1140)
sig=np.where(up&win,1,np.where(dn&win,-1,0)); first=np.zeros(len(sig),bool); seen=set()
for i in np.flatnonzero(sig!=0):
    if bd[i] not in seen: seen.add(bd[i]); first[i]=True
k=np.flatnonzero(first); ka=np.minimum(b15['act'][k],len(t)-1)
od,_=F._base(g); od.place(ka,E.MARKET,sig[k],2.0*a15[k],4.0*a15[k]); od.force_exit[F.eod_mask(g,1200)]=True
st(R.run('XAUUSD',od,'main',max_trades_day=1),'  m15 close confirmation instead of stop order')
print('\n################ USDJPY (VOLC, 20h max hold) ################')
st(TJ,'baseline (2.5R, 20h)')
for tp1,frac,tp in ((1.0,0.5,2.5),(1.0,0.5,3.5),(1.5,0.5,3.0)):
    st(resim('USDJPY',TJ,mj,ej,fj,tp=tp,tp1=tp1,frac=frac,maxbars=1200),f'  {int(frac*100)}% at {tp1}R, rest at {tp}R')
for N,dR in ((240,0.5),(360,0.5),(480,0.5),(360,0.25),(600,0.5)):
    st(resim('USDJPY',TJ,mj,ej,fj,tp=2.5,maxbars=1200,dN=N,dR=dR),f'  after {N//60}h best < {dR}R -> exit')
bj=D.resample(j,60); aj=I.atr(bj['h'],bj['l'],bj['c'],14); AJ=np.full(len(j['t']),np.nan); ok=bj['act']<len(j['t']); AJ[bj['act'][ok]]=aj[ok]; AJ=pd.Series(AJ).ffill().to_numpy()
for buf in (0.1,0.2,0.3):
    od=X.volc_f(j); od.price[:,0]=np.where(od.kind[:,0]!=0,od.price[:,0]+buf*AJ,od.price[:,0]); od.price[:,1]=np.where(od.kind[:,1]!=0,od.price[:,1]-buf*AJ,od.price[:,1])
    st(R.run('USDJPY',od,'main',max_bars=1200),f'  buffer {buf} ATR(h1) beyond the range')
for life in (360,720):
    od=X.volc_f(j); od.expiry[:]=np.minimum(od.expiry,life); st(R.run('USDJPY',od,'main',max_bars=1200),f'  orders valid {life//60}h instead of 24h')
TG.to_pickle('/tmp/claude-0/-home-user-trade2/b9a9744d-83b2-50d8-8675-62baa49483d5/scratchpad/TG.pkl'); TJ.to_pickle('/tmp/claude-0/-home-user-trade2/b9a9744d-83b2-50d8-8675-62baa49483d5/scratchpad/TJ.pkl')
