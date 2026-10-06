import R, numpy as np
from engine import engine as E
class Orders4(E.Orders): SLOTS=4
def merge(m1,*ods):
    """Combine strategies into ONE netting bot: each strategy gets its own OCO slot pair; one position at a time;
    orders of the other strategy that trade while a position is open are dropped (miss_if_crossed)."""
    o=Orders4(m1)
    for i,od in enumerate(ods):
        for a in ['kind','direction','price','sl','tp','expiry']:
            getattr(o,a)[:,2*i:2*i+2]=getattr(od,a)
        o.force_exit|=od.force_exit   # NOTE: forced flat of one strategy flattens the account position
    o.allow_entry=np.logical_and.reduce([od.allow_entry for od in ods])
    o.allow_fill=np.logical_and.reduce([od.allow_fill for od in ods])
    return o
def run_combo(sym,ods,cost):
    o=merge(R.get(sym),*ods)
    return R.run(sym,o,cost,group_size=2,miss_if_crossed=True)
