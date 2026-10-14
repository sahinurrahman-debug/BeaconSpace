# BeaconSpace — training the flood-segmentation model on Google Colab (free T4 GPU)

Total time: **≈ 1.5–2.5 h** (mostly streaming data). Cost: free. Nothing here needs a Kuro Siwo download to your PC.

## Before you start (once)
* A Google account with ≥ **2 GB free on Google Drive** (only the model + metrics are saved there, ≈ 150 MB).
* The file `notebooks/train_flood_unet.ipynb` from this repo on your computer.

## Step by step
1. Open <https://colab.research.google.com> → **File ▸ Upload notebook** → choose `train_flood_unet.ipynb`.
2. **Runtime ▸ Change runtime type ▸ T4 GPU ▸ Save.** (Free tier is enough. If "T4 not available", try later or use *CPU*, which is far too slow.)
3. Run **cell 1** (install + GPU check). It must print `CUDA: True | Tesla T4`.
4. Run **cell 2**. A pop-up asks to connect Google Drive → *Connect to Google Drive* → choose your account → *Allow*. Results will be stored in `MyDrive/floodsys_out/`.
5. Read the *Configuration* cell. The defaults are sensible for a free T4:

   | Setting | Default | Meaning / when to change |
   |---|---|---|
   | `TRAIN_SHARDS` | 5 shards (all) | each ≈ 11 GB streamed, ~3–6 min each. Use `[0,1,2]` if you are short of time. |
   | `POS_KEEP / NEG_KEEP` | 0.5 / 0.15 | fraction of flood / flood-free patches kept → ≈ 8–12 k patches, ~5 GB on the Colab disk. |
   | `TEST_SHARDS` | 12 shards, first 1 200 patches each | held-out events; streaming stops early so it is ≈ 2 GB per shard. Use `[0,2,4,6,8,10]` for a faster test. |
   | `EPOCHS` | 14 | ≈ 2–3 min per epoch on a T4. |

6. Run the remaining cells **in order** (or *Runtime ▸ Run all*). You will see:
   * "`[train shard 0] streaming …`" progress – the long part (≈ 30–40 min). Everything is cached on the Colab disk, so a crash only repeats the unfinished shard.
   * The lists of **train events** and **test events** – these prove the evaluation is on events the model never saw.
   * Per-epoch lines `val flood IoU …`. A healthy run reaches validation flood IoU ≳ 0.55–0.70 within 6–8 epochs.
   * The **evaluation** cell: held-out IoU / F1 / precision / recall at 10 m and 20 m, the *mountain subset*, the physics baseline comparison and the false-alarm rate.
   * `ONNX parity max abs diff: …` (must be tiny) and `DONE`.
7. In Google Drive open **My Drive ▸ floodsys_out** and download:
   * `flood_unet.onnx` and `flood_unet.json` → copy both into this repo's **`models/`** folder (required)
   * `metrics.json`, `training_curves.png`, `examples_heldout.png` → into `docs/results/` (for the report)
8. Re-run the system: `python -m floodsys run --preset trishuli`. The log now says `AI model: loaded flood_unet.onnx` and `provenance.json` records its model card.

## If something goes wrong
| Symptom | Fix |
|---|---|
| `No GPU!` | Runtime ▸ Change runtime type ▸ T4 GPU, then Runtime ▸ Restart and run all. |
| Colab disconnects / "runtime was recycled" | Reconnect, run cell 1–2 again, then continue; shards already cached on the local disk are reused *unless the VM was reset* (then they are re-streamed). |
| `stream error … retry` repeated | Hugging Face is rate-limiting. Wait 10 min; the cell retries automatically. You can also reduce `N_*_SHARDS`. |
| Out of RAM / disk | lower `POS_KEEP` (e.g. 0.3) and `TRAIN_SHARDS`. |
| Validation IoU stays near 0 | check the printed *class weights* and *class pixel share*; the flood class should be 1–10 % of pixels. Increase `POS_KEEP`. |

## What to say about the model (for the report / Q&A)
* **Input**: pre (mean of 2) and post Sentinel-1 VV/VH, change channels, terrain slope → **3 classes**. Same 7-channel contract as the live system (`floodsys/flood/model.py`; a unit test checks that notebook and system build identical features).
* **Training data**: Kuro Siwo GRD; **cite** Bountos et al., NeurIPS 2024.
* **Why trust it on the Himalaya?** (1) held-out events, (2) mountain subset, (3) physics baseline, (4) false-alarm rate on flood-free patches, (5) EMSR927 comparison and null-event pairs from this repo. **Be explicit that Kuro Siwo has no debris-flow labels** and few high-relief scenes.
* **Augmentations**: ±1.5 dB global gain (σ⁰ in training vs γ⁰ RTC in the system), random 2× down-scaling (the system runs at 20 m by default).
