# models/

`flood_unet.onnx` (≈ 98 MB, the trained U-Net) is **not stored in this repository** (too large for git). 

* Without it the system still runs end to end with its physics-based change detector (`provenance.json` then records `model: null`).
* To use the AI model: download `flood_unet.onnx` from **<ADD YOUR GOOGLE DRIVE / HUGGING FACE LINK HERE>** and place it in this folder next to `flood_unet.json` (the model card). It is loaded automatically.
* To re-create it yourself: `docs/COLAB_GUIDE.md` (≈ 1–2 h on a free Colab T4).
* Measured effect on the Trishuli case study is small (IoU 0.483 with vs 0.477 without) — see `docs/Report.pdf` §4–5.
