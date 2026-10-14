import sys, time, datetime as dt
sys.path.insert(0, ".")
from floodsys.data import osm
snap = osm.latest_snapshot(dt.date(2026,8,26)); print("snapshot", snap)
bbox=(85.04,27.84,85.54,28.36)
t=time.time()
o = osm.load_osm(bbox, snap)
print(round(time.time()-t),"s")
for k,v in o.items():
    print(k, len(v), list(v.columns)[:14])
r=o["roads"]; print(r["highway"].value_counts().to_dict()); print("bridges tagged:", r["bridge"].notna().sum() if "bridge" in r else 0)
p=o["places"]; print(p[["name","place"]].head(40).to_string() if len(p) else "no places"); print(p["place"].value_counts().to_dict())
h=o["health"]; print(h[[c for c in ("name","amenity","healthcare") if c in h]].to_string() if len(h) else "no health")
