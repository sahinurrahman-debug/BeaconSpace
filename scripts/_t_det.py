import sys, time, datetime as dt
sys.path.insert(0, ".")
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from floodsys.data import s1, dem
from floodsys.data.grid import Grid
from floodsys.flood import detect
SP="C:/Users/hp/AppData/Local/Temp/claude/C--Users-hp-Desktop-Trash-Multimodal-AI/559c01db-8be7-4a85-833e-04fecb4eace7/scratchpad/"
bbox=(85.10,27.90,85.48,28.30); g=Grid.from_lonlat_bbox(bbox,20)
event=dt.datetime(2026,8,25,22,0,tzinfo=dt.timezone.utc)
acqs=s1.search_acquisitions(bbox, dt.date(2026,6,15), dt.date(2026,9,25))
pairs=s1.plan_pairs(acqs,event)
t=time.time(); st=s1.load_pair(pairs[0],g); T=dem.terrain_layers(g); print("loaded",round(time.time()-t))
db=s1.prepare_db(st,g.res)
t=time.time(); r=detect.detect(db,T["slope"],T["hand"],g.res); print("detect",round(time.time()-t,1),"s")
cls=r["cls"]; ha=g.res**2/1e4
for k,n in detect.CLASS_NAMES.items(): print(n, round((cls==k).sum()*ha,1),"ha")
print(r["noise"])
np.save(SP+"cls_ro85.npy",cls)
fig,ax=plt.subplots(1,3,figsize=(21,8))
ax[0].imshow(db["post_vv"],cmap="gray",vmin=-25,vmax=0); ax[0].set_title("post VV dB")
ax[1].imshow(r["dvv"],cmap="RdBu",vmin=-8,vmax=8); ax[1].set_title("dVV (post-pre)")
rgb=np.zeros(cls.shape+(3,)); rgb[...]=np.clip((db["post_vv"]+25)/25,0,1)[...,None]*0.6
rgb[cls==1]=[0,0.4,1]; rgb[cls==2]=[1,0.5,0]; rgb[cls==3]=[0,0.9,0.9]
ax[2].imshow(rgb); ax[2].set_title("classes: blue=flood, orange=debris, cyan=perm water")
for a in ax: a.axis("off")
plt.tight_layout(); plt.savefig(SP+"det_ro85.png",dpi=70)
