import sys, time, datetime as dt
sys.path.insert(0, ".")
import numpy as np
from floodsys.data import s1
from floodsys.data.grid import Grid
bbox=(85.10,27.90,85.48,28.30)
event=dt.datetime(2026,8,25,22,0,tzinfo=dt.timezone.utc)
acqs=s1.search_acquisitions(bbox, dt.date(2026,6,15), dt.date(2026,9,25))
for a in acqs: print(a.label(), "cov=%.2f"%a.coverage, len(a.items),"slices")
pairs=s1.plan_pairs(acqs,event)
for p in pairs: print(round(p.score,1), p.describe())
g=Grid.from_lonlat_bbox(bbox,20)
t=time.time()
d=s1.load_pair(pairs[0], g)
print("loaded in", round(time.time()-t), "s", {k:(v.shape, float(np.isnan(v).mean())) for k,v in d.items()})
