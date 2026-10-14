"""Convert a '# %%' percent-format script into a Jupyter notebook:  python scripts/py2ipynb.py notebooks/train_flood_unet.py"""
import json, re, sys
from pathlib import Path

src = Path(sys.argv[1])
text = src.read_text(encoding="utf-8")
chunks = re.split(r"(?m)^# %%(.*)$", text)
cells = []
for head, body in zip(chunks[1::2], chunks[2::2]):
    body = body.strip("\n")
    if "[markdown]" in head:
        md = "\n".join(l[2:] if l.startswith("# ") else l.lstrip("#") for l in body.splitlines())
        cells.append({"cell_type": "markdown", "metadata": {}, "source": md.splitlines(True)})
    elif body.strip():
        cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": body.splitlines(True)})
nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"gpuType": "T4", "provenance": []},
      "kernelspec": {"display_name": "Python 3", "name": "python3"}, "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
out = src.with_suffix(".ipynb")
out.write_text(json.dumps(nb, indent=1), encoding="utf-8")
print("wrote", out, len(cells), "cells")
