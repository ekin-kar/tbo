"""Funding Pips 2% daily: shrink minimum 0.3 / 0.5 / 0.6 / 0.75 / fixed at several base risks (live equity)."""
import sys, pathlib, itertools; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import pandas as pd
from multiprocessing import Pool
import scaling_grid as SG
if __name__=='__main__':
    jobs=[('FP',rg,rv,mm,9.0,1.0) for (rg,rv),mm in itertools.product(((0.6,0.8),(0.7,0.9),(0.8,1.0)),(1.0,0.75,0.6,0.5,0.3))]
    with Pool(4,initializer=SG.init) as p: rows=list(p.imap_unordered(SG.cell,jobs))
    pd.DataFrame(rows).round(2).to_csv(pathlib.Path(__file__).resolve().parent.parent/'results'/'fp2_shrink.csv',index=False); print('DONE')
