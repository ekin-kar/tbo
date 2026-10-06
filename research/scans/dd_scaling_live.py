"""Live-equity check of account-level risk scaling (risk x max(minm, room) below the start balance; room = distance to floor
as a share of the full allowance). Patches the sizing line of fundingpips_sim.sim and fundedhive_sim.evaluate."""
import sys, pathlib, inspect, textwrap; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, numba as nb, pandas as pd
import fundingpips_sim as FS, fundedhive_sim as FH
def patched(fn,old,new,extra_args):
    src=textwrap.dedent(inspect.getsource(fn.py_func)).replace('@nb.njit(cache=True)\n','')
    assert old in src, old; src=src.replace(old,new)
    hdr=src.split('\n',1)[0]; src=src.replace(hdr,hdr.replace('):',', '+extra_args+'):'),1)
    ns=dict(fn.py_func.__globals__); exec(src,ns); return nb.njit(ns[fn.__name__])
fp_sim=patched(FS.sim,'want = (rg if sym[j] == 0 else rv) * bal',
               'want = (rg if sym[j] == 0 else rv) * bal * (1.0 if bal >= 1.0 else max(minm, (bal - FLOOR) / (1.0 - FLOOR)))','minm=1.0')
fh_eval=patched(FH.evaluate,'sz[no] = (rg if sym[j] == 0 else rv) * bal',
               'sz[no] = (rg if sym[j] == 0 else rv) * bal * (1.0 if bal >= e0 else max(minm, (bal - floor) / (e0 - floor)))','minm=1.0')
D=FS.load(); ent,ext,sym,Rr,off,fc,fw=D
def fp_cell(rg,rv,minm,N=2000):
    out={}
    for w,(a,b) in {"2y":("2024-09-21","2026-09-19"),"3y":("2023-09-23","2026-09-19"),"10y":("2016-01-09","2026-09-19")}.items():
        rng=np.random.default_rng(7); starts=np.arange(FS.sat(a),FS.sat(b)-4*FS.WEEK,FS.WEEK); lo=np.searchsorted(ent,starts); hi=np.searchsorted(ent,starts+4*FS.WEEK); o=[]
        for p in range(N):
            pick=rng.integers(0,len(starts),26); idx=np.concatenate([np.arange(lo[q],hi[q]) for q in pick])
            sh=np.repeat(np.arange(26)*4*FS.WEEK-starts[pick]+starts[0],hi[pick]-lo[pick])
            o.append(fp_sim(ent[idx]+sh,ext[idx]+sh,sym[idx],Rr[idx],off[idx],fc,fw,rg/100,rv/100,0.015,0.0005,24*30*1440,0.02,0.0,minm))
        o=np.array(o,float); ok=o[:,0]==1; out[w]=(100*ok.mean(),100*(o[:,0]==-1).mean(),np.median(o[ok,1]/1440/30.4))
    o=[]
    for s in range(FS.sat("2016-01-09"),FS.sat("2024-09-21"),FS.WEEK):
        k=np.searchsorted(ent,s); o.append(fp_sim(ent[k:],ext[k:],sym[k:],Rr[k:],off[k:],fc,fw,rg/100,rv/100,0.015,0.0005,24*30*1440,0.02,0.0,minm))
    o=np.array(o,float); ok=o[:,0]==1; out['real']=(100*ok.mean(),100*(o[:,0]==-1).mean(),np.median(o[ok,1]/1440/30.4)); return out
def fh_cell(rg,rv,minm,N=2000):
    R_=FH.RULES['low']; out={}
    tail=(R_['daily'],R_['target'],R_['floor'],FH.RESET)
    for w,(a,b) in FH.WINDOWS.items():
        o=np.array([fh_eval(ent[i]+s,ext[i]+s,sym[i],Rr[i],off[i],fc,fw,rg/100,rv/100,1.0,R_['guard'],FH.SLIP,26*28*1440,*tail,minm) for i,s in FH.paths(D,a,b,N,26,7)],float)
        ok=o[:,0]==1; out[w]=(100*ok.mean(),100*(o[:,0]==-1).mean(),np.median(o[ok,1]/1440/30.4))
    o=[]
    for s in range(FS.sat(FH.REAL[0]),FS.sat(FH.REAL[1]),FS.WEEK):
        k=np.searchsorted(ent,s); o.append(fh_eval(ent[k:],ext[k:],sym[k:],Rr[k:],off[k:],fc,fw,rg/100,rv/100,1.0,R_['guard'],FH.SLIP,24*30*1440,*tail,minm))
    o=np.array(o,float); ok=o[:,0]==1; out['real']=(100*ok.mean(),100*(o[:,0]==-1).mean(),np.median(o[ok,1]/1440/30.4)); return out
fmt=lambda o:' | '.join(f"{w}: pass {p:5.1f}% fail {f:4.1f}% med {m:3.1f}mo" for w,(p,f,m) in o.items())
rows=[]
print('FundedHive Low (live equity, 5% static, 2% daily from max(bal,eq) at 00:00 UTC, bot stop 1.5%)')
for rg,rv,mm in ((0.4,0.5,1.0),(0.4,0.5,0.5),(0.5,0.6,1.0),(0.5,0.6,0.5),(0.5,0.6,0.3),(0.6,0.75,1.0),(0.6,0.75,0.5),(0.6,0.75,0.3)):
    o=fh_cell(rg,rv,mm); print(f"  {rg}/{rv} {'fixed' if mm==1 else f'scaled, min {mm}x':16s} {fmt(o)}",flush=True); rows.append(dict(firm='FH Low',gold=rg,jpy=rv,minm=mm,**{f'{w}_{k}':v for w,t in o.items() for k,v in zip(('pass','fail','med'),t)}))
print('\nFunding Pips (live equity, 12% static, 2% daily from max(bal,eq) at 21:00 UTC, bot stop 1.5%)')
for rg,rv,mm in ((0.6,0.8,1.0),(0.6,0.8,0.5),(0.8,1.0,1.0),(0.8,1.0,0.5),(1.0,1.25,0.5)):
    o=fp_cell(rg,rv,mm); print(f"  {rg}/{rv} {'fixed' if mm==1 else f'scaled, min {mm}x':16s} {fmt(o)}",flush=True); rows.append(dict(firm='FP',gold=rg,jpy=rv,minm=mm,**{f'{w}_{k}':v for w,t in o.items() for k,v in zip(('pass','fail','med'),t)}))
pd.DataFrame(rows).round(2).to_csv(pathlib.Path(__file__).resolve().parent.parent/'results'/'dd_scaling_live.csv',index=False)
