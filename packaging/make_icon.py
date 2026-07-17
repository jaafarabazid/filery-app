"""Generate the app icon from scratch: icon.icns (macOS), icon.ico (Windows), icon.png.

Run from the repo root:  python packaging/make_icon.py

Everything is drawn at 4x and downsampled, which is cheaper than shipping a pile of
hand-tuned bitmaps and keeps the icon reproducible from source.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw

S = 1024          # macOS icon canvas
SS = 4            # supersample factor
MARGIN = 100      # Big Sur squircles don't fill the canvas
RADIUS = 185

BLUE_TOP = (44, 141, 224)
BLUE_BOT = (17, 78, 150)
ORANGE = (242, 101, 34)
WHITE = (255, 255, 255)


def _lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _squircle(size: int) -> Image.Image:
    """Rounded-rect body with a vertical gradient."""
    grad = Image.new("RGB", (1, size))
    for y in range(size):
        grad.putpixel((0, y), _lerp(BLUE_TOP, BLUE_BOT, y / max(1, size - 1)))
    grad = grad.resize((size, size))

    mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle(
        [MARGIN * SS, MARGIN * SS, size - MARGIN * SS, size - MARGIN * SS],
        radius=RADIUS * SS, fill=255,
    )
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask)
    return out


def draw() -> Image.Image:
    size = S * SS
    img = _squircle(size)
    d = ImageDraw.Draw(img)
    k = SS  # scale helper: coordinates below are in 1024-space

    # --- document sheet, with a folded top-right corner ---
    x0, y0, x1, y1 = 322 * k, 210 * k, 702 * k, 730 * k
    fold = 92 * k
    d.rounded_rectangle([x0, y0, x1, y1], radius=26 * k, fill=WHITE)
    # cut the corner out, then lay the fold back over it
    d.polygon([(x1 - fold, y0), (x1, y0), (x1, y0 + fold)], fill=BLUE_TOP)
    d.polygon([(x1 - fold, y0), (x1, y0 + fold), (x1 - fold, y0 + fold)],
              fill=(226, 234, 242))

    # --- text lines: says "document", and they survive optimization untouched ---
    for i, y in enumerate((266, 300, 334)):
        x_end = 660 * k if i < 2 else 590 * k
        d.rounded_rectangle([364 * k, y * k, x_end, (y + 15) * k],
                            radius=7 * k, fill=(205, 216, 228))

    # --- two arrows converging on a line: the compression idiom.
    # A single down-arrow onto a baseline reads as "download" instead.
    cx = 512 * k
    half = 23 * k
    d.rounded_rectangle([cx - half, 392 * k, cx + half, 462 * k], radius=10 * k, fill=ORANGE)
    d.polygon([(cx - 76 * k, 452 * k), (cx + 76 * k, 452 * k), (cx, 528 * k)], fill=ORANGE)

    d.rounded_rectangle([362 * k, 546 * k, 662 * k, 570 * k], radius=12 * k, fill=ORANGE)

    d.polygon([(cx - 76 * k, 664 * k), (cx + 76 * k, 664 * k), (cx, 588 * k)], fill=ORANGE)
    d.rounded_rectangle([cx - half, 654 * k, cx + half, 700 * k], radius=10 * k, fill=ORANGE)

    return img.resize((S, S), Image.LANCZOS)


def main() -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    icon = draw()
    png = os.path.join(here, "icon.png")
    icon.save(png)
    print("wrote", png)

    ico = os.path.join(here, "icon.ico")
    icon.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                          (128, 128), (256, 256)])
    print("wrote", ico)

    if sys.platform == "darwin" and shutil.which("iconutil"):
        iconset = os.path.join(here, "icon.iconset")
        shutil.rmtree(iconset, ignore_errors=True)
        os.makedirs(iconset)
        for sz in (16, 32, 128, 256, 512):
            icon.resize((sz, sz), Image.LANCZOS).save(
                os.path.join(iconset, f"icon_{sz}x{sz}.png"))
            icon.resize((sz * 2, sz * 2), Image.LANCZOS).save(
                os.path.join(iconset, f"icon_{sz}x{sz}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", iconset,
                        "-o", os.path.join(here, "icon.icns")], check=True)
        shutil.rmtree(iconset, ignore_errors=True)
        print("wrote", os.path.join(here, "icon.icns"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
