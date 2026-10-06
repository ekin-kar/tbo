"""FundedHive Low (5% static, 2% daily, 1%/trade), fresh account: base risk x shrink minimum (below start only), live equity."""
import sys, pathlib, itertools; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import pandas as pd
from multiprocessing import Pool
import scaling_grid as SG
if __name__=='__main__':
    jobs=[('FH',rg,rv,mm,9.0,1.0) for (rg,rv),mm in itertools.product(((0.3,0.4),(0.4,0.5),(0.5,0.6),(0.6,0.75),(0.7,0.85)),(1.0,0.75,0.6,0.5,0.3))]
    with Pool(4,initializer=SG.init) as p: rows=list(p.imap_unordered(SG.cell,jobs))
    pd.DataFrame(rows).round(2).to_csv(pathlib.Path(__file__).resolve().parent.parent/'results'/'fh_shrink.csv',index=False); print('DONE')
