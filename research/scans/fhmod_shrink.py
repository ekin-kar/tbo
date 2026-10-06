"""FundedHive Moderate (6% static, 3% daily, 1.5%/trade, bot stop 2.0%): base risk x shrink minimum, live equity."""
import sys, pathlib, itertools; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd
from multiprocessing import Pool
import scaling_grid as SG, fundingpips_sim as FS, fundedhive_sim as FH
def cell(args):
    rg,rv,minm=args; ent,ext,sym,Rr,off,fc,fw=SG.D; R_=FH.RULES['moderate']; tail=(R_['daily'],R_['target'],R_['floor'],FH.RESET)
    run=lambda e,x,s,r,of,h: SG.fh_eval(e,x,s,r,of,fc,fw,rg/100,rv/100,1.0,R_['guard'],FH.SLIP,h,*tail,minm,9.0,1.0)
    out=dict(firm='FHmod',gold=rg,jpy=rv,minm=minm)
    for w,(a,b) in SG.WIN.items():
        res=[run(ent[i]+s,ext[i]+s,sym[i],Rr[i],off[i],24*30*1440) for i,s in SG.boot_paths(a,b)]
        out.update({f'{w}_{k}':v for k,v in zip(('pass','fail','med','E'),SG.summ(res))})
    res=[]
    for s in range(FS.sat(SG.REAL[0]),FS.sat(SG.REAL[1]),FS.WEEK):
        k=np.searchsorted(ent,s); res.append(run(ent[k:],ext[k:],sym[k:],Rr[k:],off[k:],24*30*1440))
    out.update({f'real_{k}':v for k,v in zip(('pass','fail','med','E'),SG.summ(res))})
    return out
if __name__=='__main__':
    jobs=list(itertools.product(((0.4,0.5),(0.5,0.6),(0.6,0.75)),(1.0,0.6,0.5,0.3)))
    jobs=[(a,b,m) for (a,b),m in jobs]
    with Pool(4,initializer=SG.init) as p: rows=list(p.imap_unordered(cell,jobs))
    pd.DataFrame(rows).round(2).to_csv(pathlib.Path(__file__).resolve().parent.parent/'results'/'fhmod_shrink.csv',index=False); print('DONE')
