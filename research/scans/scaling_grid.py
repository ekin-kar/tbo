"""Grid: base risk x shrink-near-floor minimum x step-up after profit, on the live-equity simulators.
Risk multiplier at each new trade (balance relative to start = 1.0):
  balance >= 1 + up_at  -> up_mult           (step-up after a profit of up_at)
  1 <= balance < 1+up_at -> 1.0
  balance < 1            -> max(minm, (balance - floor) / (1 - floor))   (minm = 1.0 -> no shrinking)
Score: expected months to a funded account incl. retries = mean months per attempt / pass rate."""
import sys, pathlib, inspect, textwrap, itertools; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, numba as nb, pandas as pd
from multiprocessing import Pool
import fundingpips_sim as FS, fundedhive_sim as FH
MULT='(up_mult if bal >= E0 * (1.0 + up_at) else (1.0 if bal >= E0 else max(minm, (bal - FLR) / (E0 - FLR))))'
def patched(fn,old,new,extra):
    src=textwrap.dedent(inspect.getsource(fn.py_func)).replace('@nb.njit(cache=True)\n','')
    assert old in src; src=src.replace(old,new); hdr=src.split('\n',1)[0]; src=src.replace(hdr,hdr.replace('):',', '+extra+'):'),1)
    ns=dict(fn.py_func.__globals__); exec(src,ns); return nb.njit(ns[fn.__name__])
fp_sim=patched(FS.sim,'want = (rg if sym[j] == 0 else rv) * bal','want = (rg if sym[j] == 0 else rv) * bal * '+MULT.replace('E0','1.0').replace('FLR','FLOOR'),'minm=1.0, up_at=9.0, up_mult=1.0')
fh_eval=patched(FH.evaluate,'sz[no] = (rg if sym[j] == 0 else rv) * bal','sz[no] = (rg if sym[j] == 0 else rv) * bal * '+MULT.replace('E0','e0').replace('FLR','floor'),'minm=1.0, up_at=9.0, up_mult=1.0')
D=None
def init():
    global D; D=FS.load()
WIN={"2y":("2024-09-21","2026-09-19"),"3y":("2023-09-23","2026-09-19"),"10y":("2016-01-09","2026-09-19")}
REAL=("2016-01-09","2024-09-21"); N=1200
def boot_paths(a,b,seed=7):
    ent=D[0]; rng=np.random.default_rng(seed); W=FS.WEEK; starts=np.arange(FS.sat(a),FS.sat(b)-4*W,W); lo=np.searchsorted(ent,starts); hi=np.searchsorted(ent,starts+4*W)
    for p in range(N):
        pick=rng.integers(0,len(starts),26); idx=np.concatenate([np.arange(lo[q],hi[q]) for q in pick])
        yield idx,np.repeat(np.arange(26)*4*W-starts[pick]+starts[0],hi[pick]-lo[pick])
def summ(o):
    o=np.array(o,float); ok=o[:,0]==1; mo=o[:,1]/1440/30.4; p=ok.mean()
    return 100*p,100*(o[:,0]==-1).mean(),float(np.median(mo[ok])) if ok.any() else np.nan,(mo.mean()/p if p>0 else np.inf)
def cell(args):
    firm,rg,rv,minm,up_at,up_mult=args; ent,ext,sym,Rr,off,fc,fw=D; out=dict(firm=firm,gold=rg,jpy=rv,minm=minm,up_at=up_at,up_mult=up_mult)
    if firm=='FH':
        R_=FH.RULES['low']; tail=(R_['daily'],R_['target'],R_['floor'],FH.RESET)
        run=lambda e,x,s,r,of,h: fh_eval(e,x,s,r,of,fc,fw,rg/100,rv/100,1.0,R_['guard'],FH.SLIP,h,*tail,minm,up_at,up_mult)
    else:
        run=lambda e,x,s,r,of,h: fp_sim(e,x,s,r,of,fc,fw,rg/100,rv/100,0.015,0.0005,h,0.02,0.0,minm,up_at,up_mult)
    for w,(a,b) in WIN.items():
        res=[run(ent[i]+s,ext[i]+s,sym[i],Rr[i],off[i],24*30*1440) for i,s in boot_paths(a,b)]
        out.update({f'{w}_{k}':v for k,v in zip(('pass','fail','med','E'),summ(res))})
    res=[]
    for s in range(FS.sat(REAL[0]),FS.sat(REAL[1]),FS.WEEK):
        k=np.searchsorted(ent,s); res.append(run(ent[k:],ext[k:],sym[k:],Rr[k:],off[k:],24*30*1440))
    out.update({f'real_{k}':v for k,v in zip(('pass','fail','med','E'),summ(res))})
    return out
if __name__=='__main__':
    STEPS=[(9.0,1.0),(0.01,1.25),(0.02,1.25),(0.02,1.5),(0.05,1.25),(0.05,1.5)]
    jobs=[]
    for (rg,rv),mm,(ua,um) in itertools.product(((0.4,0.5),(0.5,0.6),(0.6,0.75)),(1.0,0.5,0.3,0.2),STEPS):
        if max(rg,rv)*um>0.9: continue                           # FundedHive 1% per-trade rule (keep a margin for slippage)
        jobs.append(('FH',rg,rv,mm,ua,um))
    for (rg,rv),mm,(ua,um) in itertools.product(((0.6,0.8),(0.8,1.0),(1.0,1.25)),(1.0,0.5,0.3),[(9.0,1.0),(0.02,1.25),(0.04,1.25),(0.06,1.25),(0.04,1.5)]):
        jobs.append(('FP',rg,rv,mm,ua,um))
    print('cells:',len(jobs),flush=True)
    with Pool(4,initializer=init) as p:
        rows=[]
        for r in p.imap_unordered(cell,jobs):
            rows.append(r); print(len(rows),{k:(round(v,1) if isinstance(v,float) else v) for k,v in r.items() if k in('firm','gold','jpy','minm','up_at','up_mult','3y_E','10y_E','real_E','10y_fail')},flush=True)
    pd.DataFrame(rows).round(2).to_csv(pathlib.Path(__file__).resolve().parent.parent/'results'/'scaling_grid.csv',index=False)
    print('DONE')
