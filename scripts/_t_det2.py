import sys, datetime as dt
sys.path.insert(0, ".")
import numpy as np, matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import ndimage as ndi
from floodsys.data import s1, dem
from floodsys.data.grid import Grid
SP="C:/Users/hp/AppData/Local/Temp/claude/C--Users-hp-Desktop-Trash-Multimodal-AI/559c01db-8be7-4a85-833e-04fecb4eace7/scratchpad/"
bbox=(85.10,27.90,85.48,28.30); g=Grid.from_lonlat_bbox(bbox,20)
event=dt.datetime(2026,8,25,22,0,tzinfo=dt.timezone.utc)
pairs=s1.plan_pairs(s1.search_acquisitions(bbox, dt.date(2026,6,15), dt.date(2026,9,25)),event)
st=s1.load_pair(pairs[0],g); T=dem.terrain_layers(g)
def sm(x): return ndi.uniform_filter(np.nan_to_num(x,nan=1e-4),3)
pv,ph,qv,qh=[st[k] for k in ("post_vv","post_vh","pre_vv","pre_vh")]
dvv=10*np.log10(sm(pv)/sm(qv)); dvh=10*np.log10(sm(ph)/sm(qh))
hand=T["hand"]; slope=T["slope"]
for name,d in (("dVV",dvv),("dVH",dvh)):
    a=d[(hand<15)&(slope<15)]; b=d[(hand>150)]
    print(name,"valley p1/5/50/95/99:",np.percentile(a,[1,5,50,95,99]).round(2)," hills:",np.percentile(b,[1,5,50,95,99]).round(2), "frac valley |d|>3:",(np.abs(a)>3).mean().round(3))
print("global sigma smoothed", 1.4826*np.median(np.abs(dvv-np.median(dvv))))
r0,r1,c0,c1=1650,2150,100,600
fig,ax=plt.subplots(2,3,figsize=(21,14))
ax[0,0].imshow(10*np.log10(pv[r0:r1,c0:c1]),cmap="gray",vmin=-25,vmax=0); ax[0,0].set_title("post VV")
ax[0,1].imshow(10*np.log10(qv[r0:r1,c0:c1]),cmap="gray",vmin=-25,vmax=0); ax[0,1].set_title("pre VV")
ax[0,2].imshow(dvv[r0:r1,c0:c1],cmap="RdBu",vmin=-8,vmax=8); ax[0,2].set_title("dVV smoothed")
ax[1,0].imshow(dvh[r0:r1,c0:c1],cmap="RdBu",vmin=-8,vmax=8); ax[1,0].set_title("dVH")
ax[1,1].imshow(np.clip(hand[r0:r1,c0:c1],0,100),cmap="viridis"); ax[1,1].set_title("HAND")
ax[1,2].imshow(slope[r0:r1,c0:c1],cmap="magma",vmin=0,vmax=50); ax[1,2].set_title("slope")
plt.tight_layout(); plt.savefig(SP+"zoom_low.png",dpi=55)
