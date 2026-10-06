"""Funding Pips with the 3% daily-loss option (bot daily stop 2.0% / 2.5%), same scaling rules as scaling_grid.py."""
import sys, pathlib, itertools; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd
from multiprocessing import Pool
import scaling_grid as SG, fundingpips_sim as FS
def cell(args):
    rg,rv,minm,ua,um,guard=args; ent,ext,sym,Rr,off,fc,fw=SG.D; out=dict(firm='FP3',gold=rg,jpy=rv,minm=minm,up_at=ua,up_mult=um,guard=guard)
    run=lambda e,x,s,r,of,h: SG.fp_sim(e,x,s,r,of,fc,fw,rg/100,rv/100,guard/100,0.0005,h,0.03,0.0,minm,ua,um)
    for w,(a,b) in SG.WIN.items():
        res=[run(ent[i]+s,ext[i]+s,sym[i],Rr[i],off[i],24*30*1440) for i,s in SG.boot_paths(a,b)]
        out.update({f'{w}_{k}':v for k,v in zip(('pass','fail','med','E'),SG.summ(res))})
    res=[]
    for s in range(FS.sat(SG.REAL[0]),FS.sat(SG.REAL[1]),FS.WEEK):
        k=np.searchsorted(ent,s); res.append(run(ent[k:],ext[k:],sym[k:],Rr[k:],off[k:],24*30*1440))
    out.update({f'real_{k}':v for k,v in zip(('pass','fail','med','E'),SG.summ(res))})
    return out
if __name__=='__main__':
    jobs=[(rg,rv,mm,ua,um,gd) for (rg,rv),mm,(ua,um),gd in itertools.product(((0.8,1.0),(1.0,1.25),(1.2,1.5)),(1.0,0.5),((9.0,1.0),(0.02,1.25)),(2.0,2.5))]
    with Pool(4,initializer=SG.init) as p: rows=list(p.imap_unordered(cell,jobs))
    pd.DataFrame(rows).round(2).to_csv(pathlib.Path(__file__).resolve().parent.parent/'results'/'fp3_grid.csv',index=False); print('DONE',len(rows))
