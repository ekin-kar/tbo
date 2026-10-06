"""Funding Pips live-equity simulator (fundingpips_sim.py) at higher risk than the current 0.6 / 0.8."""
import sys, pathlib; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import fundingpips_sim as FS, pandas as pd
D=FS.load()
WIN={"2y":("2024-09-21","2026-09-19"),"3y":("2023-09-23","2026-09-19"),"10y":("2016-01-09","2026-09-19")}
rows=[]
for rg,rv,g in ((0.6,0.8,1.5),(0.8,1.0,1.5),(1.0,1.25,1.5),(1.2,1.5,1.5),(1.0,1.25,1.25)):
    r=dict(gold=rg,jpy=rv,guard=g)
    for w,(a,b) in WIN.items():
        s=FS.summ(FS.boot(D,rg/100,rv/100,g/100,0.0005,a,b,N=3000)); r.update({f"{w}_{k}":round(v,1) for k,v in s.items() if k in ('passp','fail','med','in6')})
    s=FS.summ(FS.rolling(D,rg/100,rv/100,g/100,0.0005,"2016-01-09","2024-09-21")); r.update({f"roll_{k}":round(v,1) for k,v in s.items() if k in ('passp','fail','med')})
    rows.append(r); print(r,flush=True)
pd.DataFrame(rows).to_csv(pathlib.Path(__file__).resolve().parent.parent/'results'/'fundingpips_highrisk.csv',index=False)
