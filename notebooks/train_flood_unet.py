# %% [markdown]
# # Flood segmentation model — U-Net trained on Kuro Siwo (Sentinel-1 pre/post change detection)
#
# **Hackathon Track B – AI component (flood segmentation model).** Runs on a free Google Colab **T4 GPU** (Runtime → Change runtime type → *T4 GPU*).
#
# What it does
# 1. Streams Kuro Siwo GRD shards from Hugging Face and caches a compact subset on the Colab disk (no 120 GB download).
# 2. Trains a 7-channel U-Net (ResNet-34 encoder) for 3 classes: *no water / permanent water / new flood water*.
# 3. Evaluates on the **held-out Kuro Siwo test events** (different geographies, never seen in training) at 10 m and 20 m,
#    on a **mountainous subset**, and against a physics-based threshold baseline.
# 4. Exports `flood_unet.onnx` + `flood_unet.json` (model card) to Google Drive. You put those into the repo's `models/` folder.
#
# **Data citation (required):** Bountos, N.I., Sdraka, M., Zavras, A., et al. *Kuro Siwo: 33 billion m² under the water. A global
# multi-temporal satellite dataset for rapid flood mapping.* NeurIPS 2024 Datasets & Benchmarks. (CC BY)
#
# Tip: every step caches to disk, so if Colab disconnects just re-run all cells from the top.

# %%
import subprocess, sys, os
def pip(*pkgs):
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", *pkgs], check=False)

SYNTH = os.environ.get("FLOODSYS_SYNTH") == "1"      # local smoke-test mode (no network, tiny)
if not SYNTH:
    pip("segmentation-models-pytorch", "onnx", "onnxruntime", "onnxscript")

import json, io, tarfile, time, math, random, hashlib, warnings
from pathlib import Path
import numpy as np, requests
import torch, torch.nn as nn, torch.nn.functional as F
from scipy import ndimage as ndi
warnings.filterwarnings("ignore")
print("torch", torch.__version__, "| CUDA:", torch.cuda.is_available(),
      "|", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU only")
if not SYNTH and not torch.cuda.is_available():
    print("⚠️  No GPU! Runtime → Change runtime type → T4 GPU, then re-run.")

# %%
# ---- Configuration (edit here) ----------------------------------------------------------------
if SYNTH:
    WORK = Path(os.environ.get("FLOODSYS_WORK", "./_synth_work")); OUT = WORK / "out"
else:
    try:
        from google.colab import drive
        drive.mount("/content/drive")
        OUT = Path("/content/drive/MyDrive/floodsys_out")      # results survive Colab resets
    except Exception:
        OUT = Path("/content/floodsys_out")
    WORK = Path("/content/work")                                # big cache lives on the fast local disk
WORK.mkdir(parents=True, exist_ok=True); OUT.mkdir(parents=True, exist_ok=True)

BASE = "https://huggingface.co/datasets/orion-ai-lab/Kuro-Siwo-Webdataset/resolve/main"
N_TRAIN_SHARDS, N_TEST_SHARDS = 5, 12            # shards that exist on HF (≈11 GB each)
TRAIN_SHARDS = list(range(N_TRAIN_SHARDS))
TEST_SHARDS  = list(range(N_TEST_SHARDS))
POS_KEEP, NEG_KEEP = 0.5, 0.15                   # fraction of flood-containing / flood-free train patches kept
TEST_MAX_PER_SHARD = 1200                        # first N patches of every test shard (stops the download early)
EPOCHS, BATCH, LR, CROP = 14, 32, 3e-4, 128
NW = 0 if (SYNTH or os.name == "nt") else 2     # DataLoader workers (Colab = Linux -> 2)
SEED = 0
random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
DEV = "cuda" if torch.cuda.is_available() else "cpu"
print("work:", WORK, "| out:", OUT, "| device:", DEV)

# %% [markdown]
# ## 1. Stream & cache Kuro Siwo
# Each sample: post-flood VV/VH, two pre-flood VV/VH (linear σ⁰, Lee-filtered, 10 m), DEM, mask (0 no water, 1 permanent water, 2 flood), valid mask.
# We store a **compact** version: dB images (float16), the *mean of the two pre-flood images* (matches the live system, which averages same-track pre images) and terrain slope.

# %%
def slope_deg(dem, res=10.0):
    d = np.where(np.isfinite(dem), dem, np.nanmedian(dem) if np.isfinite(dem).any() else 0.0)
    gy, gx = np.gradient(d, res)
    return np.degrees(np.arctan(np.hypot(gx, gy))).astype("float32")

def to_db(x):
    return 10.0 * np.log10(np.clip(x, 1e-4, None))

def iter_samples(url, max_samples=None, retries=4):
    """Yield dicts {field: ndarray / json} from a remote webdataset .tar, streaming (no full download)."""
    for attempt in range(retries):
        try:
            with requests.get(url, stream=True, timeout=120) as r:
                r.raise_for_status()
                tf = tarfile.open(fileobj=r.raw, mode="r|")
                key, cur, n = None, {}, 0
                for m in tf:
                    if not m.isfile():
                        continue
                    k, _, field = m.name.partition(".")
                    data = tf.extractfile(m).read()
                    if k != key:
                        if cur:
                            yield cur
                            n += 1
                            if max_samples and n >= max_samples:
                                return
                        key, cur = k, {}
                    cur[field] = json.loads(data) if field.endswith(".json") else np.load(io.BytesIO(data))
                if cur:
                    yield cur
            return
        except Exception as e:
            print(f"   stream error ({e}); retry {attempt+1}/{retries}")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("download failed: " + url)

def event_id(info):
    for k in ("act", "actid", "activation", "activation_id", "act_id", "event", "emsr"):
        if k in info: return str(info[k])
    try: return "ms1_" + str(info["sources"]["MS1"]["source_date"])
    except Exception: return "unknown"

def compact(s):
    g = lambda k: np.squeeze(s[k]).astype("float32")
    pv, ph = g("flood_vv.npy"), g("flood_vh.npy")
    pre_v = np.nanmean([g("sec1_vv.npy"), g("sec2_vv.npy")], axis=0)      # linear-domain mean of the 2 pre images
    pre_h = np.nanmean([g("sec1_vh.npy"), g("sec2_vh.npy")], axis=0)
    dem = g("dem.npy"); mask = np.squeeze(s["mask.npy"]).astype("int16")
    valid = np.squeeze(s["valid_mask.npy"]) > 0.5
    ok = valid & np.isfinite(pv) & np.isfinite(ph) & np.isfinite(pre_v) & np.isfinite(pre_h) & (pv > 0) & (pre_v > 0)
    label = np.where(np.isin(mask, (0, 1, 2)), mask, 255).astype("uint8"); label[~ok] = 255
    x = np.stack([to_db(np.nan_to_num(pv, nan=1e-4)), to_db(np.nan_to_num(ph, nan=1e-4)),
                  to_db(np.nan_to_num(pre_v, nan=1e-4)), to_db(np.nan_to_num(pre_h, nan=1e-4)),
                  np.clip(slope_deg(dem), 0, 89)]).astype("float16")
    meta = {"event": event_id(s.get("info.json", {})), "flood_frac": float((label == 2).mean()),
            "perm_frac": float((label == 1).mean()), "slope_mean": float(x[4].astype("float32").mean()),
            "dem_med": float(np.nanmedian(dem)) if np.isfinite(dem).any() else float("nan")}
    return x, label, meta

def synth_samples(n, seed):
    rng = np.random.default_rng(seed)
    for i in range(n):
        H = 224; yy, xx = np.mgrid[:H, :H]
        blob = ((yy - rng.integers(40, 180)) ** 2 + (xx - rng.integers(40, 180)) ** 2) < rng.integers(300, 1500)
        base = rng.normal(0.08, 0.02, (H, H)).clip(0.01); baseh = base * 0.25
        post, posth = base.copy(), baseh.copy(); post[blob] *= 0.05; posth[blob] *= 0.05
        mask = np.where(blob, 2, 0).astype("float32")
        yield {"flood_vv.npy": post[None].astype("float32"), "flood_vh.npy": posth[None].astype("float32"),
               "sec1_vv.npy": base[None].astype("float32"), "sec1_vh.npy": baseh[None].astype("float32"),
               "sec2_vv.npy": base[None].astype("float32"), "sec2_vh.npy": baseh[None].astype("float32"),
               "dem.npy": rng.normal(500, 5, (1, H, H)).astype("float32"), "mask.npy": mask[None],
               "valid_mask.npy": np.ones((1, H, H), "float32"), "info.json": {"act": f"synth{seed % 3}"}}

def build_shard(split, i):
    f = WORK / f"{split}_{i:02d}"
    if (f.with_suffix(".x.npy")).exists():
        return f
    print(f"[{split} shard {i}] streaming ...", flush=True)
    t0 = time.time(); rng = random.Random(SEED + i)
    xs, ys, metas, seen = [], [], [], 0
    src = (synth_samples(60 if split == "train" else 40, i) if SYNTH else
           iter_samples(f"{BASE}/{split}_GRD/shard-{i:05d}.tar", None if split == "train" else TEST_MAX_PER_SHARD))
    for s in src:
        seen += 1
        try:
            x, y, m = compact(s)
        except Exception as e:
            continue
        if split == "train":
            pos = m["flood_frac"] >= 0.002 or m["perm_frac"] >= 0.01
            if rng.random() > (POS_KEEP if pos else NEG_KEEP): continue
        xs.append(x); ys.append(y); metas.append(m)
        if seen % 500 == 0: print(f"   scanned {seen}, kept {len(xs)}", flush=True)
    np.save(f.with_suffix(".x.npy"), np.stack(xs)); np.save(f.with_suffix(".y.npy"), np.stack(ys))
    json.dump(metas, open(f.with_suffix(".meta.json"), "w"))
    print(f"[{split} shard {i}] kept {len(xs)}/{seen} in {time.time()-t0:.0f}s", flush=True)
    return f

if SYNTH:
    TRAIN_SHARDS, TEST_SHARDS, EPOCHS = [0, 1], [0], 2
train_files = [build_shard("train", i) for i in TRAIN_SHARDS]
test_files = [build_shard("test", i) for i in TEST_SHARDS]
# show what an info.json looks like, so you can see which fields exist
print("events (train):", sorted({m["event"] for f in train_files for m in json.load(open(f.with_suffix(".meta.json")))})[:30])
print("events (test) :", sorted({m["event"] for f in test_files for m in json.load(open(f.with_suffix(".meta.json")))})[:30])

# %% [markdown]
# ## 2. Features, dataset, augmentation
# The 7-channel **feature contract is identical to `floodsys/flood/model.py`** in the repo (so training and the live system agree):
# post VV/VH, pre VV/VH, speckle-robust log-ratio change VV/VH, slope. Augmentations: flips/rotations, global dB offset (Kuro Siwo is σ⁰ but the live system uses γ⁰ RTC),
# and a random **2× down-scale** (10 m → 20 m) because the live system often runs at 20 m.

# %%
def smoothed_change_db(post_db, pre_db, res):
    size = max(3, int(round(50.0 / res)) | 1)
    a, b = 10 ** (post_db / 10), 10 ** (pre_db / 10)
    return (10 * np.log10((ndi.uniform_filter(a, size) + 1e-6) / (ndi.uniform_filter(b, size) + 1e-6))).astype("float32")

def make_features(x5, res):
    """x5: (5,H,W) = post VV dB, post VH dB, pre VV dB, pre VH dB, slope deg  ->  (7,H,W) float32"""
    x5 = x5.astype("float32")
    svv = smoothed_change_db(x5[0], x5[2], res); svh = smoothed_change_db(x5[1], x5[3], res)
    f = np.stack([(x5[0] + 12) / 6, (x5[1] + 19) / 6, (x5[2] + 12) / 6, (x5[3] + 19) / 6,
                  np.clip(svv, -15, 15) / 5, np.clip(svh, -15, 15) / 5, np.clip(x5[4], 0, 60) / 30]).astype("float32")
    return np.nan_to_num(f)

def downscale2(x5, y):
    """10 m -> 20 m: average in the linear domain; labels by majority/ignore."""
    C, H, W = x5.shape
    lin = 10 ** (x5[:4].astype("float32") / 10)
    lin = lin.reshape(4, H // 2, 2, W // 2, 2).mean((2, 4))
    out = np.concatenate([to_db(lin), x5[4:5].astype("float32").reshape(1, H // 2, 2, W // 2, 2).mean((2, 4))])
    yb = y.reshape(H // 2, 2, W // 2, 2).transpose(0, 2, 1, 3).reshape(H // 2, W // 2, 4)
    yy = np.zeros((H // 2, W // 2), "uint8")
    for c in (0, 1, 2):
        yy[(yb == c).sum(-1) >= 2] = c
    yy[(yb == 255).sum(-1) >= 3] = 255
    return out, yy

class KS(torch.utils.data.Dataset):
    def __init__(self, files, train, mode="mixed"):          # mode: "mixed" (train), "10m", "20m"
        self.x = [np.load(f.with_suffix(".x.npy"), mmap_mode="r") for f in files]
        self.y = [np.load(f.with_suffix(".y.npy"), mmap_mode="r") for f in files]
        self.meta = [m for f in files for m in json.load(open(f.with_suffix(".meta.json")))]
        self.idx = [(a, b) for a, x in enumerate(self.x) for b in range(len(x))]
        self.train, self.mode = train, mode
    def __len__(self): return len(self.idx)
    def __getitem__(self, i):
        a, b = self.idx[i]
        x5, y = np.array(self.x[a][b]), np.array(self.y[a][b])
        res = 10.0
        coarse = (self.mode == "20m") or (self.train and random.random() < 0.5)
        if coarse:
            x5, y = downscale2(x5, y); res = 20.0
        if self.train:
            off = random.uniform(-1.5, 1.5); x5 = x5.astype("float32"); x5[:4] += off        # global gain change
            H = x5.shape[1]; c = CROP
            if H < c:
                p = c - H; x5 = np.pad(x5, ((0, 0), (0, p), (0, p)), mode="reflect"); y = np.pad(y, ((0, p), (0, p)), constant_values=255); H = c
            r0, c0 = random.randint(0, H - c), random.randint(0, H - c)
            x5, y = x5[:, r0:r0 + c, c0:c0 + c], y[r0:r0 + c, c0:c0 + c]
            k = random.randint(0, 3); x5, y = np.rot90(x5, k, (1, 2)), np.rot90(y, k)
            if random.random() < 0.5: x5, y = x5[:, :, ::-1], y[:, ::-1]
        f = make_features(np.ascontiguousarray(x5), res)
        return torch.from_numpy(f), torch.from_numpy(np.ascontiguousarray(y).astype("int64")), i

train_ds = KS(train_files, True)
val_n = max(1, int(0.08 * len(train_ds)))
# validation = held-out *chunks* of training shards (use test events only for the final report)
g = torch.Generator().manual_seed(SEED)
tr_sub, va_sub = torch.utils.data.random_split(train_ds, [len(train_ds) - val_n, val_n], generator=g)
dl_tr = torch.utils.data.DataLoader(tr_sub, batch_size=BATCH, shuffle=True, num_workers=NW, drop_last=True, persistent_workers=NW > 0)
va_ds = KS(train_files, False, "10m")
dl_va = torch.utils.data.DataLoader(torch.utils.data.Subset(va_ds, va_sub.indices), batch_size=BATCH, num_workers=NW)
print("train patches:", len(tr_sub), "| val patches:", len(va_sub))
cnt = np.zeros(3)
for fx in train_files:
    y = np.load(fx.with_suffix(".y.npy"), mmap_mode="r")[:300]
    for c in range(3): cnt[c] += (y == c).sum()
print("class pixel share (sample):", (cnt / cnt.sum()).round(4))

# %% [markdown]
# ## 3. Model & training

# %%
import segmentation_models_pytorch as smp
model = smp.Unet(encoder_name="resnet34", encoder_weights=None if SYNTH else "imagenet", in_channels=7, classes=3).to(DEV)
w = torch.tensor(1.0 / np.sqrt(np.maximum(cnt / cnt.sum(), 1e-4)), dtype=torch.float32); w = (w / w.min()).clamp(max=12).to(DEV)
print("class weights (no water / permanent water / flood):", w.cpu().numpy().round(2))
ce = nn.CrossEntropyLoss(weight=w, ignore_index=255)
dice = smp.losses.DiceLoss("multiclass", classes=[1, 2], ignore_index=255, from_logits=True)
def loss_fn(lo, y): return ce(lo, y) + 0.5 * dice(lo, y)
opt = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=1e-4)
sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=LR, total_steps=EPOCHS * max(1, len(dl_tr)), pct_start=0.15)
scaler = torch.amp.GradScaler("cuda", enabled=DEV == "cuda")

def confusion(pred, y, n=3):
    m = y != 255
    return np.bincount((y[m] * n + pred[m]).astype(int), minlength=n * n).reshape(n, n)

def scores(cm):
    out = {}
    for c, name in ((1, "permanent_water"), (2, "flood")):
        tp, fp, fn = cm[c, c], cm[:, c].sum() - cm[c, c], cm[c, :].sum() - cm[c, c]
        out[name] = {"iou": float(tp / max(tp + fp + fn, 1)), "f1": float(2 * tp / max(2 * tp + fp + fn, 1)),
                     "precision": float(tp / max(tp + fp, 1)), "recall": float(tp / max(tp + fn, 1))}
    out["mIoU3"] = float(np.mean([cm[c, c] / max(cm[c].sum() + cm[:, c].sum() - cm[c, c], 1) for c in range(3)]))
    return out

@torch.no_grad()
def evaluate(dl):
    model.eval(); cm = np.zeros((3, 3), dtype=np.int64)
    for xb, yb, ib in dl:
        with torch.autocast(DEV, enabled=DEV == "cuda"):
            pr = model(xb.to(DEV)).argmax(1).cpu().numpy()
        cm += confusion(pr, yb.numpy())
    return cm

hist = []
best = -1; t0 = time.time()
for ep in range(EPOCHS):
    model.train(); run = 0
    for it, (xb, yb, _) in enumerate(dl_tr):
        xb, yb = xb.to(DEV, non_blocking=True), yb.to(DEV, non_blocking=True)
        opt.zero_grad(set_to_none=True)
        with torch.autocast(DEV, enabled=DEV == "cuda"):
            loss = loss_fn(model(xb), yb)
        scaler.scale(loss).backward(); scaler.step(opt); scaler.update(); sched.step(); run += loss.item()
    sc = scores(evaluate(dl_va)); f_iou = sc["flood"]["iou"]
    hist.append({"epoch": ep + 1, "train_loss": run / max(1, len(dl_tr)), "val_flood_iou": f_iou, "val_flood_f1": sc["flood"]["f1"]})
    print(f"epoch {ep+1:02d}/{EPOCHS} loss {hist[-1]['train_loss']:.4f} | val flood IoU {f_iou:.3f} F1 {sc['flood']['f1']:.3f} "
          f"P {sc['flood']['precision']:.3f} R {sc['flood']['recall']:.3f} | {time.time()-t0:.0f}s", flush=True)
    if f_iou >= best:
        best = f_iou; torch.save(model.state_dict(), OUT / "flood_unet.pt")
model.load_state_dict(torch.load(OUT / "flood_unet.pt", map_location=DEV))

# %% [markdown]
# ## 4. Evaluation on **held-out events** (never seen in training)
# * ⚠️ The Hugging Face `test_GRD` shards are **not** an event-level hold-out: many of their events also occur in `train_GRD`.
#   The cell below therefore lists the events and reports a separate **"unseen events"** result (events absent from the training patches) — quote *that* as the honest generalisation number.
# * Reported at 10 m (native) and 20 m (what the live pipeline runs at by default), overall and for a **mountainous subset**
#   (mean slope ≥ 10°, the closest proxy to Himalayan terrain available inside the benchmark).
# * Compared with a **physics-based threshold baseline** (dark & dropped & flat) so we know the network really adds value.
# * The *true* Himalayan test is the EMSR927 case study in the repo (`scripts/evaluate_emsr927.py`); those maps are used for checking only.

# %%
def baseline_cm(ds):
    cm = np.zeros((3, 3), dtype=np.int64)
    for i in range(len(ds)):
        x, y, _ = ds[i]
        f = x.numpy(); post_vv, post_vh = f[0] * 6 - 12, f[1] * 6 - 19; pre_vv, pre_vh = f[2] * 6 - 12, f[3] * 6 - 19
        slope = f[6] * 30
        dark = (post_vv < -17) | (post_vh < -24); drop = ((post_vv - pre_vv) <= -3) | ((post_vh - pre_vh) <= -3)
        was_land = (pre_vv >= -17) & (pre_vh >= -23); pred = (dark & drop & was_land & (slope <= 12)).astype(int) * 2
        pred[(pre_vv < -17) & (post_vv < -17) & (slope <= 6)] = 1
        cm += confusion(pred, y.numpy())
    return cm

def loader(ds, ids=None):
    return torch.utils.data.DataLoader(ds if ids is None else torch.utils.data.Subset(ds, ids), batch_size=BATCH, num_workers=NW)

train_events = {m["event"] for f in train_files for m in json.load(open(f.with_suffix(".meta.json")))}
results = {}
for mode in ("10m", "20m"):
    ds = KS(test_files, False, mode)
    cm = evaluate(loader(ds))
    unseen_idx = [i for i, m in enumerate(ds.meta) if m["event"] not in train_events]
    overlap = sorted({m["event"] for m in ds.meta} & train_events)
    unseen = sorted({ds.meta[i]["event"] for i in unseen_idx})
    print(f"[{mode}] test-shard events also in training: {len(overlap)} | UNSEEN events: {unseen} ({len(unseen_idx)} patches)")
    mount_idx = [i for i, m in enumerate(ds.meta) if m["slope_mean"] >= 10]
    res = {"all": scores(cm), "n_patches": len(ds), "unseen_events": unseen, "events_overlapping_training": overlap}
    if len(unseen_idx) > 10:
        res["unseen_events_pooled"] = scores(evaluate(loader(ds, unseen_idx)))
        print(f"       UNSEEN-event flood IoU {res['unseen_events_pooled']['flood']['iou']:.3f}  F1 {res['unseen_events_pooled']['flood']['f1']:.3f}  "
              f"P {res['unseen_events_pooled']['flood']['precision']:.3f}  R {res['unseen_events_pooled']['flood']['recall']:.3f}   <-- quote this one")
    if len(mount_idx) > 10:
        res["mountain_slope_ge_10deg"] = scores(evaluate(loader(ds, mount_idx))); res["n_mountain_patches"] = len(mount_idx)
    sub_ids = list(range(0, len(ds), max(1, len(ds) // 600)))
    res["baseline_physics_threshold"] = scores(baseline_cm(torch.utils.data.Subset(ds, sub_ids)))
    res["model_on_same_subset"] = scores(evaluate(loader(ds, sub_ids)))
    per = {}
    for ev in sorted({m["event"] for m in ds.meta}):
        ids = [i for i, m in enumerate(ds.meta) if m["event"] == ev]
        if len(ids) >= 20:
            per[ev] = {"patches": len(ids), **scores(evaluate(loader(ds, ids)))["flood"]}
    res["per_event_flood"] = per
    results[mode] = res
    fl = res["all"]["flood"]
    print(f"[{mode}] held-out events: flood IoU {fl['iou']:.3f}  F1 {fl['f1']:.3f}  precision {fl['precision']:.3f}  recall {fl['recall']:.3f}")
    print(f"       physics baseline (same subset): IoU {res['baseline_physics_threshold']['flood']['iou']:.3f}  vs model {res['model_on_same_subset']['flood']['iou']:.3f}")
    if "mountain_slope_ge_10deg" in res:
        print(f"       mountainous patches ({res['n_mountain_patches']}): flood IoU {res['mountain_slope_ge_10deg']['flood']['iou']:.3f}")
json.dump(results, open(OUT / "metrics.json", "w"), indent=2, default=float)

# %%
# False-alarm check: held-out patches with NO flood at all -> how much land does the model wrongly call flood?
ds = KS(test_files, False, "20m")
neg = [i for i, m in enumerate(ds.meta) if m["flood_frac"] == 0.0 and m["perm_frac"] < 0.02]
fp_px = tot = 0
model.eval()
with torch.no_grad():
    for k in range(0, min(len(neg), 800), BATCH):
        ids = neg[k:k + BATCH]
        xb = torch.stack([ds[i][0] for i in ids]).to(DEV); yb = torch.stack([ds[i][1] for i in ids])
        pr = model(xb).argmax(1).cpu(); m = yb != 255
        fp_px += int(((pr == 2) & m).sum()); tot += int(m.sum())
fpr = fp_px / max(tot, 1)
print(f"flood-free held-out patches: {len(neg)} | false 'flood' pixels: {fpr*100:.4f}% of land")
results["false_alarm_rate_flood_free_patches"] = fpr
json.dump(results, open(OUT / "metrics.json", "w"), indent=2, default=float)

# %%
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(11, 3.6))
ax[0].plot([h["epoch"] for h in hist], [h["train_loss"] for h in hist]); ax[0].set_title("train loss"); ax[0].set_xlabel("epoch")
ax[1].plot([h["epoch"] for h in hist], [h["val_flood_iou"] for h in hist], label="IoU"); ax[1].plot([h["epoch"] for h in hist], [h["val_flood_f1"] for h in hist], label="F1")
ax[1].set_title("validation (flood class)"); ax[1].legend(); plt.tight_layout(); plt.savefig(OUT / "training_curves.png", dpi=120)
ds = KS(test_files, False, "10m"); pos = [i for i, m in enumerate(ds.meta) if m["flood_frac"] > 0.03][:6]
if pos:   # qualitative examples from held-out events
    fig, ax = plt.subplots(3, len(pos), figsize=(3 * len(pos), 9), squeeze=False)
    model.eval()
    with torch.no_grad():
        for j, i in enumerate(pos):
            x, y, _ = ds[i]; pr = model(x[None].to(DEV)).argmax(1)[0].cpu().numpy()
            ax[0, j].imshow(x[4].numpy(), cmap="RdBu", vmin=-3, vmax=3); ax[0, j].set_title("change VV")
            ax[1, j].imshow(np.where(y.numpy() == 255, 0, y.numpy()), vmin=0, vmax=2); ax[1, j].set_title("reference")
            ax[2, j].imshow(pr, vmin=0, vmax=2); ax[2, j].set_title("model")
            for a in ax[:, j]: a.axis("off")
    plt.tight_layout(); plt.savefig(OUT / "examples_heldout.png", dpi=100)

# %% [markdown]
# ## 5. Export to ONNX (CPU inference in the live system) and write the model card

# %%
model.eval().cpu()
dummy = torch.randn(1, 7, 256, 256)
onnx_path = OUT / "flood_unet.onnx"
kw = dict(input_names=["input"], output_names=["logits"], opset_version=17,
          dynamic_axes={"input": {0: "b", 2: "h", 3: "w"}, "logits": {0: "b", 2: "h", 3: "w"}})
try:
    torch.onnx.export(model, dummy, str(onnx_path), dynamo=False, **kw)
except TypeError:
    torch.onnx.export(model, dummy, str(onnx_path), **kw)
import onnxruntime as ort
sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
xt = torch.randn(2, 7, 192, 160)
with torch.no_grad(): ref = model(xt).numpy()
got = sess.run(None, {"input": xt.numpy()})[0]
diff = float(np.abs(ref - got).max()); print("ONNX parity max abs diff:", diff, "| size MB:", round(onnx_path.stat().st_size / 1e6, 1))
assert diff < 1e-2, "ONNX export does not match PyTorch!"
card = {
    "name": "flood_unet", "architecture": "U-Net / ResNet-34 encoder (segmentation-models-pytorch)", "file": "flood_unet.onnx",
    "task": "3-class SAR change detection: 0 no water, 1 permanent water, 2 new flood water",
    "input": "7 channels: post VV, post VH, pre VV, pre VH (dB, scaled), smoothed change VV/VH, slope; see floodsys/flood/model.py",
    "training_data": "Kuro Siwo GRD (Bountos et al., NeurIPS 2024, CC BY)",
    "trained_on": f"{len(train_ds)} patches from {len(train_files)} train shards; epochs={EPOCHS}",
    "metrics_all_test_shard_patches_NOT_event_held_out": {k: v["all"]["flood"] for k, v in results.items() if isinstance(v, dict) and "all" in v},
    "unseen_event_metrics": {k: v.get("unseen_events_pooled", {}).get("flood") for k, v in results.items() if isinstance(v, dict) and "all" in v},
    "caveat": "only unseen_event_metrics are event-held-out",
    "false_alarm_rate_flood_free": fpr, "created": time.strftime("%Y-%m-%d"),
    "limitations": "Trained mostly on low-relief floods; debris flows are not a label class; unseen terrain may degrade.",
}
json.dump(card, open(OUT / "flood_unet.json", "w"), indent=2, default=float)
print(json.dumps(card["unseen_event_metrics"], indent=2, default=float))
print("\nDONE. Files are in", OUT, "\n  flood_unet.onnx + flood_unet.json  ->  copy into the repo's models/ folder.")
