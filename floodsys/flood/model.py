"""Trained flood-segmentation network (U-Net, exported to ONNX) -- inference side.

Feature contract (7 channels, identical to ``notebooks/train_flood_unet_colab.ipynb``):

    0  post VV  dB   (x + 12) / 6
    1  post VH  dB   (x + 19) / 6
    2  pre  VV  dB   (x + 12) / 6        pre = linear-domain mean of the same-track pre-event images
    3  pre  VH  dB   (x + 19) / 6
    4  smoothed change VV (dB)  clip(+-15) / 5
    5  smoothed change VH (dB)  clip(+-15) / 5
    6  terrain slope (deg)      clip(0, 60) / 30

Output: 3 classes -> 0 no water, 1 permanent water, 2 flood (new water). NaN input -> 0 after scaling.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from .detect import smoothed_change_db

N_CHANNELS = 7


def build_features(db: dict, slope: np.ndarray, res: float) -> np.ndarray:
    svv = smoothed_change_db(db["post_vv"], db["pre_vv"], res)
    svh = smoothed_change_db(db["post_vh"], db["pre_vh"], res)
    f = np.stack([
        (db["post_vv"] + 12) / 6, (db["post_vh"] + 19) / 6,
        (db["pre_vv"] + 12) / 6, (db["pre_vh"] + 19) / 6,
        np.clip(svv, -15, 15) / 5, np.clip(svh, -15, 15) / 5,
        np.clip(slope, 0, 60) / 30,
    ]).astype("float32")
    return np.nan_to_num(f, nan=0.0, posinf=0.0, neginf=0.0)


class FloodModel:
    def __init__(self, path: Path):
        import onnxruntime as ort
        self.path = Path(path)
        self.sess = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
        self.input_name = self.sess.get_inputs()[0].name
        card = self.path.with_suffix(".json")
        self.card = json.loads(card.read_text()) if card.exists() else {}

    @classmethod
    def load_if_available(cls, path: Path):
        p = Path(path)
        if p.exists():
            try:
                return cls(p)
            except Exception as exc:  # corrupt file / missing onnxruntime
                print(f"[model] could not load {p}: {exc}")
        return None

    def predict(self, feats: np.ndarray, tile: int = 256, overlap: int = 32) -> np.ndarray:
        """Per-pixel probability of the *flood* class, tiled with overlap blending."""
        c, h, w = feats.shape
        step = tile - 2 * overlap
        pad_h = (-(h - 2 * overlap) % step) if h > tile else tile - h
        pad_w = (-(w - 2 * overlap) % step) if w > tile else tile - w
        x = np.pad(feats, ((0, 0), (overlap, overlap + pad_h), (overlap, overlap + pad_w)), mode="reflect")
        H, W = x.shape[1:]
        prob = np.zeros((H, W), "float32")
        weight = np.zeros((H, W), "float32")
        win = np.outer(np.hanning(tile + 2)[1:-1], np.hanning(tile + 2)[1:-1]).astype("float32") + 1e-3
        for r in range(0, max(H - tile, 0) + 1, step):
            for cc in range(0, max(W - tile, 0) + 1, step):
                patch = x[:, r:r + tile, cc:cc + tile][None]
                logits = self.sess.run(None, {self.input_name: patch})[0][0]
                e = np.exp(logits - logits.max(axis=0, keepdims=True))
                p = (e / e.sum(axis=0, keepdims=True))[2]
                prob[r:r + tile, cc:cc + tile] += p * win
                weight[r:r + tile, cc:cc + tile] += win
        prob = prob / np.maximum(weight, 1e-6)
        return prob[overlap:overlap + h, overlap:overlap + w]
