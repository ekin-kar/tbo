"""Ladder step-up: above the start the risk grows linearly with profit, from 1.0x at the start to `top`x at +`full`% (then flat).
Below the start: shrink as before. Live equity, Funding Pips 0.7/0.9 min 0.6x and FundedHive Low 0.4/0.5 min 0.3x."""
import sys, pathlib, itertools; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd
from multiprocessing import Pool
import scaling_grid as SG, fundingpips_sim as FS, fundedhive_sim as FH
MULT='(1.0 + (up_mult - 1.0) * min(1.0, (bal - E0) / (E0 * up_at)) if bal >= E0 else max(minm, (bal - FLR) / (E0 - FLR)))'
fp_sim=SG.patched(FS.sim,'want = (rg if sym[j] == 0 else rv) * bal','want = (rg if sym[j] == 0 else rv) * bal * '+MULT.replace('E0','1.0').replace('FLR','FLOOR'),'minm=1.0, up_at=9.0, up_mult=1.0')
fh_eval=SG.patched(FH.evaluate,'sz[no] = (rg if sym[j] == 0 else rv) * bal','sz[no] = (rg if sym[j] == 0 else rv) * bal * '+MULT.replace('E0','e0').replace('FLR','floor'),'minm=1.0, up_at=9.0, up_mult=1.0')
SG.fp_sim=fp_sim; SG.fh_eval=fh_eval
if __name__=='__main__':
    LAD=[(9.0,1.0)]+[(f,t) for f in (0.04,0.06,0.08) for t in (1.25,1.5)]
    jobs=[('FP',0.7,0.9,0.6,f,t) for f,t in LAD]+[('FH',0.4,0.5,0.3,f,t) for f,t in LAD]
    with Pool(4,initializer=SG.init) as p: rows=list(p.imap_unordered(SG.cell,jobs))
    pd.DataFrame(rows).round(2).to_csv(pathlib.Path(__file__).resolve().parent.parent/'results'/'ladder_grid.csv',index=False); print('DONE',len(rows))
