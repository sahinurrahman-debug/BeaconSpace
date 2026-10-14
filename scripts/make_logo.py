"""Generate the BeaconSpace mark: app/assets/beaconspace.svg (light bg), beaconspace-dark.svg (dark bg), favicon.png.
A bright beacon core sending three expanding signal arcs; a small satellite dot rides the outer arc.
    python scripts/make_logo.py"""
import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "app" / "assets"
CX, CY = 13.0, 35.0            # beacon core centre (48 x 48 box)
RADII = (11.0, 19.0, 27.0)     # signal arcs
OPAC = (1.0, 0.62, 0.34)
SAT = (CX + 27 * math.cos(math.radians(-45)), CY + 27 * math.sin(math.radians(-45)))


def body(accent, sat_color):
    arcs = "".join(f"<path d='M{CX} {CY - r}A{r} {r} 0 0 1 {CX + r} {CY}' fill='none' stroke='{accent}' stroke-width='3.2' stroke-linecap='round' opacity='{o}'/>"
                   for r, o in zip(RADII, OPAC))
    return (arcs + f"<circle cx='{CX}' cy='{CY}' r='5.6' fill='{accent}'/>"
            f"<circle cx='{SAT[0]:.1f}' cy='{SAT[1]:.1f}' r='3.3' fill='{sat_color}'/>")


def svg(accent, sat_color, size=96):
    return (f"<svg xmlns='http://www.w3.org/2000/svg' width='{size}' height='{size}' viewBox='0 0 48 48' role='img' aria-label='BeaconSpace logo'>"
            f"{body(accent, sat_color)}</svg>")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "beaconspace.svg").write_text(svg("#BE185D", "#2A1423"), encoding="utf-8")
    (OUT / "beaconspace-dark.svg").write_text(svg("#F472B6", "#F6E9F2"), encoding="utf-8")
    S, N = 512, 64
    k = S / 48
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for r, o in zip(RADII, OPAC):
        d.arc([(CX - r) * k, (CY - r) * k, (CX + r) * k, (CY + r) * k], 270, 360, fill=(244, 114, 182, int(255 * o)), width=int(3.2 * k))
        for ang in (270, 360):                                   # round caps
            x, y = CX + r * math.cos(math.radians(ang)), CY + r * math.sin(math.radians(ang))
            d.ellipse([(x - 1.6) * k, (y - 1.6) * k, (x + 1.6) * k, (y + 1.6) * k], fill=(244, 114, 182, int(255 * o)))
    d.ellipse([(CX - 5.6) * k, (CY - 5.6) * k, (CX + 5.6) * k, (CY + 5.6) * k], fill=(244, 114, 182, 255))
    d.ellipse([(SAT[0] - 3.3) * k, (SAT[1] - 3.3) * k, (SAT[0] + 3.3) * k, (SAT[1] + 3.3) * k], fill=(246, 233, 242, 255))
    img.resize((N, N), Image.LANCZOS).save(OUT / "favicon.png")
    print("wrote", sorted(p.name for p in OUT.iterdir()))
