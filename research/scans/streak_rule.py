"""USDJPY losing-streak rule on the live-equity simulators, on top of the chosen risk scaling.
USDJPY counts its losses in a row as its trades close (a close by the bots' daily stop counts as a loss); while the count is >= sk its
new trades get sw x risk; a winning USDJPY trade resets the count. Funding Pips 0.7/0.9 (shrink from 4%, min 0.3x) and
FundedHive Low 0.4/0.5 (shrink from 0, min 0.3x)."""
import sys, pathlib, inspect, textwrap; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, numba as nb, pandas as pd
from multiprocessing import Pool
import fundingpips_sim as FS, fundedhive_sim as FH
def patch(fn, pairs, extra):
    src=textwrap.dedent(inspect.getsource(fn.py_func)).replace('@nb.njit(cache=True)\n','')
    for a,b in pairs:
        assert src.count(a)==1,(fn.__name__,a); src=src.replace(a,b)
    hdr=src.split('\n',1)[0]; src=src.replace(hdr,hdr.replace('):',', '+extra+'):'),1)
    ns=dict(fn.py_func.__globals__); exec(src,ns); return nb.njit(ns[fn.__name__])
LOSS_ON_GUARD='\n'.join(['for q in range(no):','    if sym[op[q]] == 1: streak += 1'])
fp=patch(FS.sim,[
  ('t0 = ent[0]; bal = 1.0; base = 1.0; halted = False','t0 = ent[0]; bal = 1.0; base = 1.0; halted = False; streak = 0'),
  ('                if minm < 1.0 and bal < 1.0 - dz: want *= max(minm, (bal - FLOOR) / ((1.0 - dz) - FLOOR))\n',
   '                if minm < 1.0 and bal < 1.0 - dz: want *= max(minm, (bal - FLOOR) / ((1.0 - dz) - FLOOR))\n                if sym[j] == 1 and streak >= sk: want *= sw\n'),
  ('            bal = lvl; no = 0; halted = True','            for q in range(no):\n                if sym[op[q]] == 1: streak += 1\n            bal = lvl; no = 0; halted = True'),
  ('                bal += sz[q] * Rr[i]; op[q] = op[no - 1]; sz[q] = sz[no - 1]; no -= 1',
   '                bal += sz[q] * Rr[i]\n                if sym[i] == 1: streak = 0 if Rr[i] > 0 else streak + 1\n                op[q] = op[no - 1]; sz[q] = sz[no - 1]; no -= 1'),
],'sk=99, sw=1.0')
fh=patch(FH.evaluate,[
  ('t0 = ent[0]; bal = e0; base = e0; halted = False','t0 = ent[0]; bal = e0; base = e0; halted = False; streak = 0'),
  ('                if minm < 1.0 and bal < 1.0 - dz: sz[no] *= max(minm, (bal - floor) / ((1.0 - dz) - floor))\n',
   '                if minm < 1.0 and bal < 1.0 - dz: sz[no] *= max(minm, (bal - floor) / ((1.0 - dz) - floor))\n                if sym[j] == 1 and streak >= sk: sz[no] *= sw\n'),
  ('            bal = lvl; no = 0; halted = True','            for q in range(no):\n                if sym[op[q]] == 1: streak += 1\n            bal = lvl; no = 0; halted = True'),
  ('                bal += sz[q] * Rr[i]; op[q] = op[no - 1]; sz[q] = sz[no - 1]; no -= 1',
   '                bal += sz[q] * Rr[i]\n                if sym[i] == 1: streak = 0 if Rr[i] > 0 else streak + 1\n                op[q] = op[no - 1]; sz[q] = sz[no - 1]; no -= 1'),
],'sk=99, sw=1.0')
D=None; N=3000; REAL=("2016-01-09","2024-09-21")
WIN={"2y":("2024-09-21","2026-09-19"),"3y":("2023-09-23","2026-09-19"),"10y":("2016-01-09","2026-09-19")}
def init():
    global D; D=FS.load()
def paths(a,b,seed=7):
    ent=D[0]; rng=np.random.default_rng(seed); W=FS.WEEK; st=np.arange(FS.sat(a),FS.sat(b)-4*W,W); lo=np.searchsorted(ent,st); hi=np.searchsorted(ent,st+4*W)
    for p in range(N):
        pick=rng.integers(0,len(st),26); idx=np.concatenate([np.arange(lo[q],hi[q]) for q in pick])
        yield idx,np.repeat(np.arange(26)*4*W-st[pick]+st[0],hi[pick]-lo[pick])
def summ(o):
    o=np.array(o,float); ok=o[:,0]==1; mo=o[:,1]/1440/30.4; p=ok.mean()
    return 100*p,100*(o[:,0]==-1).mean(),float(np.median(mo[ok])),mo.mean()/p
def cell(a):
    firm,sk,sw=a; ent,ext,sym,Rr,off,fc,fw=D; out=dict(firm=firm,sk=sk,sw=sw)
    if firm=='FP': run=lambda e,x,s,r,of,h: fp(e,x,s,r,of,fc,fw,0.007,0.009,0.015,0.0005,h,0.02,0.0,0.3,0.04,sk,sw)
    else:
        R_=FH.RULES['low']; run=lambda e,x,s,r,of,h: fh(e,x,s,r,of,fc,fw,0.004,0.005,1.0,R_['guard'],FH.SLIP,h,R_['daily'],R_['target'],R_['floor'],FH.RESET,0.3,0.0,sk,sw)
    for w,(a_,b_) in WIN.items():
        out.update({f'{w}_{k}':v for k,v in zip(('pass','fail','med','E'),summ([run(ent[i]+s,ext[i]+s,sym[i],Rr[i],off[i],24*30*1440) for i,s in paths(a_,b_)]))})
    res=[]
    for s in range(FS.sat(REAL[0]),FS.sat(REAL[1]),FS.WEEK):
        k=np.searchsorted(ent,s); res.append(run(ent[k:],ext[k:],sym[k:],Rr[k:],off[k:],24*30*1440))
    out.update({f'real_{k}':v for k,v in zip(('pass','fail','med','E'),summ(res))})
    return out
if __name__=='__main__':
    rules=[(99,1.0),(3,0.5),(4,0.5),(5,0.5),(3,0.75),(4,0.75)]
    jobs=[(f,sk,sw) for f in ('FP','FH') for sk,sw in rules]
    with Pool(int(sys.argv[1]) if len(sys.argv)>1 else 4,initializer=init) as p: rows=list(p.imap_unordered(cell,jobs))
    pd.DataFrame(rows).round(2).to_csv(pathlib.Path(__file__).resolve().parent.parent/'results'/'streak_rule.csv',index=False); print('DONE')
