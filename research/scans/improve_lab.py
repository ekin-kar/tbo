"""Exit/variant lab for the two live bots. Entries come from the engine; exits re-simulated on m1 bars (bid + main spread):
SL, optional TP, partial take-profit (frac at tp1), breakeven, max hold, time-decay (exit if best < dR after N min), forced exit."""
import sys, pathlib; sys.path[:0]=[str(pathlib.Path(__file__).resolve().parent.parent)]
import numpy as np, pandas as pd, numba as nb, R, ideas as X
from engine import engine as E, indicators as I, data as D
from engine.strategies import families as F
@nb.njit
def walk(o,h,l,sp,ent,ep,dirs,sld,fx,tp,tp1,frac,be,maxbars,dN,dR):
    n=len(ent); out=np.zeros(n); xi=np.zeros(n,np.int64)
    for q in range(n):
        j=ent[q]; d=dirs[q]; s=sld[q]; e=ep[q]; stop=e-d*s; best=-1e9; part=0.0; left=1.0; done=False
        end=fx[q]
        if maxbars>0 and j+maxbars<end: end=j+maxbars
        for i in range(j,end):
            # adverse first
            if d==1:
                if l[i]<=stop:
                    px=min(stop,o[i]) if i>j else stop; out[q]=part+left*(px-e)/s; xi[q]=i; done=True; break
                fav=(h[i]-e)/s
            else:
                if h[i]+sp[i]>=stop:
                    px=max(stop,o[i]+sp[i]) if i>j else stop; out[q]=part+left*(e-px)/s; xi[q]=i; done=True; break
                fav=(e-l[i]-sp[i])/s
            if i>j:
                if frac>0 and left==1.0 and fav>=tp1: part=frac*tp1; left=1.0-frac
                if tp>0 and fav>=tp: out[q]=part+left*tp; xi[q]=i; done=True; break
            if fav>best: best=fav
            if be>0 and best>=be: stop=max(stop,e) if d==1 else min(stop,e)
            if dN>0 and i-j==dN and best<dR:
                px=o[i+1] if d==1 else o[i+1]+sp[i+1]; out[q]=part+left*d*(px-e)/s; xi[q]=i+1; done=True; break
        if not done:
            i=end; px=o[i] if d==1 else o[i]+sp[i]; out[q]=part+left*d*(px-e)/s; xi[q]=i
    return out,xi
def prep(sym,tr,fx_fn):
    m=R.get(sym); t=m['t']
    ent=np.searchsorted(t,tr.entry_time.values.astype('datetime64[m]').astype(np.int64)); fx=fx_fn(m,ent)
    return m,ent,fx
def resim(sym,tr,m,ent,fx,tp=0.0,tp1=0.0,frac=0.0,be=0.0,maxbars=0,dN=0,dR=0.0,adj=0.0):
    r,xi=walk(m['o'],m['h'],m['l'],m['sp_main'],ent,tr.entry.values,tr.dir.values.astype(np.int64),tr.sl_dist.values,fx,tp,tp1,frac,be,maxbars,dN,dR)
    out=tr.copy(); comm=D.COMMISSION_PER_SIDE*2*tr.entry.values/tr.sl_dist.values
    out['R']=r-comm-adj; out['exit_time']=pd.to_datetime(m['t'][xi]*60,unit='s'); return out
def gold_fx(m,ent):
    """forced exit = first bar at/after 20:00 UTC of the entry day"""
    em=F.eod_mask(m,1200); f=np.flatnonzero(em); j=np.searchsorted(f,ent); return f[np.minimum(j,len(f)-1)]
def jpy_fx(m,ent):
    """forced exit = Friday 20:00 UTC (first bar at/after) - max hold handled by maxbars"""
    t=m['t']; wd=D.weekday(t); em=F.eod_mask(m,1200)&(wd==4); f=np.flatnonzero(em); j=np.searchsorted(f,ent); return f[np.minimum(j,len(f)-1)]
def st(tr,lab):
    s=tr.sort_values('exit_time'); c=np.r_[0,np.cumsum(s.R.values)]; dd=(np.maximum.accumulate(c)-c).max(); y=tr.entry_time.dt.year
    x=tr.R.sort_values(ascending=False); pos,neg=tr.R[tr.R>0].sum(),-tr.R[tr.R<=0].sum()
    print(f"{lab:40s} n={len(tr):5d} R={tr.R.sum():+6.1f} PF={pos/max(neg,1e-9):.2f} DD={dd:5.1f} R/DD={tr.R.sum()/dd:5.2f} no_top2={x.sum()-x.head(int(np.ceil(len(x)*.02))).sum():+6.1f} | "
          +' '.join(f"{p}={tr.R[(y>=a)&(y<=b)].sum():+5.1f}" for p,(a,b) in R.PERIODS.items()),flush=True)
    return dict(lab=lab,R=tr.R.sum(),DD=dd)
