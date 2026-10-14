import sys, datetime as dt
sys.path.insert(0, ".")
import numpy as np
from floodsys.data import s1, dem
from floodsys.data.grid import Grid
from floodsys.flood import detect
bbox=(85.10,27.90,85.48,28.30); g=Grid.from_lonlat_bbox(bbox,20)
event=dt.datetime(2026,8,25,22,0,tzinfo=dt.timezone.utc)
pairs=s1.plan_pairs(s1.search_acquisitions(bbox, dt.date(2026,6,15), dt.date(2026,9,25)),event,top=2)
T=dem.terrain_layers(g)
z=np.load("cache/s2_test.npz"); s2={k:z[k] for k in ("water","debris","clear")}
print("S2 clear",s2["clear"].mean().round(3),"water px",s2["water"].sum(),"debris px",s2["debris"].sum())
ha=g.res**2/1e4
res=[]
for pr in pairs:
    st=s1.load_pair(pr,g); db=s1.prepare_db(st,g.res)
    for lab,s in (("S1 only",None),("S1+S2",s2)):
        r=detect.detect(db,T["slope"],T["hand"],g.res,s2=s)
        print(pr.post.rel_orbit,lab,{n:round(float((r["cls"]==k).sum()*ha),1) for k,n in detect.CLASS_NAMES.items()})
        if s is None: res.append(r)
m=detect.merge_tracks(res); print("merged", {n:round(float((m["cls"]==k).sum()*ha),1) for k,n in detect.CLASS_NAMES.items()}, "2-track agreement ha", round(float((m["support"]>=2).sum()*ha),1))
a=np.isin(res[0]["cls"],(1,2)); b=np.isin(res[1]["cls"],(1,2))
print("RO85 vs RO19 overlap: IoU", round(float((a&b).sum()/max((a|b).sum(),1)),3), "| RO19 area ha", round(float(b.sum()*ha),1), "RO85 ha", round(float(a.sum()*ha),1))
