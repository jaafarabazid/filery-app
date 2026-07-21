"""Build the app icon set from the hand-designed master.

Source of truth is packaging/filery-icon.svg (edit that). packaging/icon-master.png
is a 1024x1024 render of it, committed so CI needs no SVG rasterizer, only Pillow.
If you change the SVG, re-render the master:

    resvg --width 1024 --height 1024 packaging/filery-icon.svg packaging/icon-master.png

Outputs:
    icon.png   full-square master copy (used by the Windows Inno Setup wizard)
    icon.ico   Windows icon, full square (Windows draws icons square)
    icon.icns  macOS icon, rounded + padded to match the Dock convention

Run:  python packaging/make_icon.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.join(HERE, "icon-master.png")

# macOS icon grid: the artwork sits inside a rounded rect with a transparent
# margin. These match Apple's proportions closely enough for a native look.
MAC_CONTENT = 0.86      # artwork fills 86% of the tile, ~7% margin each side
MAC_RADIUS = 0.2237     # corner radius as a fraction of the artwork size


def load_master() -> Image.Image:
    if not os.path.exists(MASTER):
        sys.exit(f"missing {MASTER} - render it from filery-icon.svg (see this file's header)")
    return Image.open(MASTER).convert("RGBA")


def rounded(img: Image.Image, radius_frac: float) -> Image.Image:
    """Return img with rounded corners (antialiased)."""
    w, h = img.size
    scale = 4
    mask = Image.new("L", (w * scale, h * scale), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, w * scale, h * scale], radius=int(min(w, h) * scale * radius_frac), fill=255
    )
    mask = mask.resize((w, h), Image.LANCZOS)
    out = img.copy()
    out.putalpha(mask)
    return out


def mac_tile(master: Image.Image, size: int) -> Image.Image:
    """Rounded, padded macOS-style tile at the given size."""
    content = int(size * MAC_CONTENT)
    art = rounded(master.resize((content, content), Image.LANCZOS), MAC_RADIUS)
    tile = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    off = (size - content) // 2
    tile.alpha_composite(art, (off, off))
    return tile


def main() -> int:
    master = load_master()

    png = os.path.join(HERE, "icon.png")
    master.save(png)
    print("wrote", png)

    # Windows: full square, multiple resolutions
    ico = os.path.join(HERE, "icon.ico")
    master.save(ico, sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                            (64, 64), (128, 128), (256, 256)])
    print("wrote", ico)

    # macOS: rounded + padded iconset compiled to .icns
    if sys.platform == "darwin" and shutil.which("iconutil"):
        iconset = os.path.join(HERE, "icon.iconset")
        shutil.rmtree(iconset, ignore_errors=True)
        os.makedirs(iconset)
        for base in (16, 32, 128, 256, 512):
            mac_tile(master, base).save(os.path.join(iconset, f"icon_{base}x{base}.png"))
            mac_tile(master, base * 2).save(os.path.join(iconset, f"icon_{base}x{base}@2x.png"))
        subprocess.run(["iconutil", "-c", "icns", iconset,
                        "-o", os.path.join(HERE, "icon.icns")], check=True)
        shutil.rmtree(iconset, ignore_errors=True)
        print("wrote", os.path.join(HERE, "icon.icns"))
    else:
        # Non-macOS build host: emit a rounded PNG so the icns can be made on a Mac.
        mac_tile(master, 1024).save(os.path.join(HERE, "icon-macos.png"))
        print("wrote icon-macos.png (icns is only compiled on macOS)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
