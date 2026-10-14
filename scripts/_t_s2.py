import sys, time, datetime as dt, pickle
sys.path.insert(0, ".")
import numpy as np
from floodsys.data import s2
from floodsys.data.grid import Grid
from floodsys.config import DetectParams
bbox=(85.10,27.90,85.48,28.30); g=Grid.from_lonlat_bbox(bbox,20)
event=dt.datetime(2026,8,25,22,0,tzinfo=dt.timezone.utc)
t=time.time(); ev=s2.optical_evidence(bbox,event,g,DetectParams()); print("s2 time",round(time.time()-t))
if ev:
    print({k:(v if not isinstance(v,np.ndarray) else (v.shape, float(v.mean()) if v.dtype==bool else None)) for k,v in ev.items() if k not in("ndvi_post","mndwi_post")})
    np.savez_compressed("cache/s2_test.npz", **{k:v for k,v in ev.items() if isinstance(v,np.ndarray)})
