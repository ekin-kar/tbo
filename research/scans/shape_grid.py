"""Shape of the risk scaling below the start (live equity). scale = max(minm, room**pw), room = (bal - floor) / ((1 - dz) - floor),
full risk while bal >= 1 - dz. dz = 0, pw = 1 is the current linear rule. Funding Pips 0.7/0.9 and FundedHive Low 0.4/0.5."""
import sys, pathlib, itertools, inspect, textwrap; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, numba as nb, pandas as pd
from multiprocessing import Pool
import fundingpips_sim as FS, fundedhive_sim as FH
class SG:   # helpers (formerly from scaling_grid.py, which patches the v6 simulator source)
    D=None; N=2000; REAL=("2016-01-09","2024-09-21")
    WIN={"2y":("2024-09-21","2026-09-19"),"3y":("2023-09-23","2026-09-19"),"10y":("2016-01-09","2026-09-19")}
    @staticmethod
    def init(): SG.D=FS.load()
    @staticmethod
    def boot_paths(a,b,seed=7):
        ent=SG.D[0]; rng=np.random.default_rng(seed); W=FS.WEEK; st=np.arange(FS.sat(a),FS.sat(b)-4*W,W); lo=np.searchsorted(ent,st); hi=np.searchsorted(ent,st+4*W)
        for p in range(SG.N):
            pick=rng.integers(0,len(st),26); idx=np.concatenate([np.arange(lo[q],hi[q]) for q in pick])
            yield idx,np.repeat(np.arange(26)*4*W-st[pick]+st[0],hi[pick]-lo[pick])
    @staticmethod
    def summ(o):
        o=np.array(o,float); ok=o[:,0]==1; mo=o[:,1]/1440/30.4; p=ok.mean()
        return 100*p,100*(o[:,0]==-1).mean(),float(np.median(mo[ok])) if ok.any() else np.nan,(mo.mean()/p if p>0 else np.inf)
def patch(fn, old, new, extra):
    src=textwrap.dedent(inspect.getsource(fn.py_func)).replace('@nb.njit(cache=True)\n','')
    assert old in src, old; src=src.replace(old,new); hdr=src.split('\n',1)[0]; src=src.replace(hdr,hdr.replace('):',', '+extra+'):'),1)
    ns=dict(fn.py_func.__globals__); exec(src,ns); return nb.njit(ns[fn.__name__])
SH='max(minm, max(0.0, (bal - FLR) / ((1.0 - dz) - FLR)) ** pw)'
fp=patch(FS.sim,'if minm < 1.0 and bal < 1.0: want *= max(minm, (bal - FLOOR) / (1.0 - FLOOR))',
         'if minm < 1.0 and bal < 1.0 - dz: want *= '+SH.replace('FLR','FLOOR'),'dz=0.0, pw=1.0')
fh=patch(FH.evaluate,'if minm < 1.0 and bal < 1.0: sz[no] *= max(minm, (bal - floor) / (1.0 - floor))',
         'if minm < 1.0 and bal < 1.0 - dz: sz[no] *= '+SH.replace('FLR','floor'),'dz=0.0, pw=1.0')
def cell(a):
    firm,rg,rv,mm,dz,pw=a; ent,ext,sym,Rr,off,fc,fw=SG.D; out=dict(firm=firm,gold=rg,jpy=rv,minm=mm,dz=dz,pw=pw)
    if firm=='FH':
        R_=FH.RULES['low']; run=lambda e,x,s,r,of,h: fh(e,x,s,r,of,fc,fw,rg/100,rv/100,1.0,R_['guard'],FH.SLIP,h,R_['daily'],R_['target'],R_['floor'],FH.RESET,mm,dz,pw)
    else:
        run=lambda e,x,s,r,of,h: fp(e,x,s,r,of,fc,fw,rg/100,rv/100,0.015,0.0005,h,0.02,0.0,mm,dz,pw)
    for w,(a_,b_) in SG.WIN.items():
        res=[run(ent[i]+s,ext[i]+s,sym[i],Rr[i],off[i],24*30*1440) for i,s in SG.boot_paths(a_,b_)]
        out.update({f'{w}_{k}':v for k,v in zip(('pass','fail','med','E'),SG.summ(res))})
    res=[]
    for s in range(FS.sat(SG.REAL[0]),FS.sat(SG.REAL[1]),FS.WEEK):
        k=np.searchsorted(ent,s); res.append(run(ent[k:],ext[k:],sym[k:],Rr[k:],off[k:],24*30*1440))
    out.update({f'real_{k}':v for k,v in zip(('pass','fail','med','E'),SG.summ(res))})
    return out
if __name__=='__main__':
    import sys as _s
    if len(_s.argv)>1 and _s.argv[1]=='gentle':
        shapes=[(0.6,0.0,0.5),(0.5,0.0,0.5),(0.4,0.0,0.5),(0.3,0.04,1.0),(0.4,0.05,1.0),(0.3,0.05,1.0)]
        fhs=[(0.3,0.0,0.5),(0.2,0.0,0.5),(0.1,0.0,0.5),(0.2,0.01,1.0)]
        out='shape_grid2.csv'
    else:
        shapes=[(1.0,0.0,1.0),(0.6,0.0,1.0),(0.6,0.02,1.0),(0.6,0.03,1.0),(0.6,0.04,1.0),(0.5,0.03,1.0),(0.5,0.04,1.0),(0.4,0.04,1.0),(0.5,0.0,2.0),(0.4,0.0,2.0)]
        fhs=[(1.0,0.0,1.0),(0.3,0.0,1.0),(0.3,0.01,1.0),(0.3,0.02,1.0),(0.2,0.02,1.0),(0.3,0.0,2.0),(0.2,0.0,2.0)]
        out='shape_grid.csv'
    jobs=[('FP',0.7,0.9,*sh) for sh in shapes]+[('FH',0.4,0.5,*sh) for sh in fhs]
    with Pool(4,initializer=SG.init) as p: rows=list(p.imap_unordered(cell,jobs))
    pd.DataFrame(rows).round(2).to_csv(pathlib.Path(__file__).resolve().parent.parent/'results'/out,index=False); print('DONE')
