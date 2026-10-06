"""Step-up after a profit on top of the chosen shrink settings (live equity).
Funding Pips 2%: 0.7/0.9 min 0.6x. FundedHive Low: 0.4/0.5 and 0.5/0.6, min 0.3x (max risk kept <= 0.9% for the 1%/trade rule)."""
import sys, pathlib, itertools; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import pandas as pd
from multiprocessing import Pool
import scaling_grid as SG
if __name__=='__main__':
    STEPS=[(9.0,1.0)]+[(a,m) for a in (0.01,0.02,0.04,0.06) for m in (1.25,1.5)]
    jobs=[('FP',0.7,0.9,0.6,a,m) for a,m in STEPS]
    jobs+=[('FH',rg,rv,0.3,a,m) for (rg,rv) in ((0.4,0.5),(0.5,0.6)) for a,m in STEPS if max(rg,rv)*m<=0.9]
    with Pool(4,initializer=SG.init) as p: rows=list(p.imap_unordered(SG.cell,jobs))
    pd.DataFrame(rows).round(2).to_csv(pathlib.Path(__file__).resolve().parent.parent/'results'/'stepup_grid.csv',index=False); print('DONE',len(rows))
