"""PDF web-optimization engine.

Recompresses the images in a print-ready PDF for web delivery while leaving text,
vectors, fonts and layout untouched. The whole size problem in a print PDF is
almost always the images: CMYK at 300+ ppi. Text is already tiny.

Pipeline per image:
    decode -> CMYK/Gray to RGB -> downsample to real placement -> reencode -> replace

Then: strip metadata, drop thumbnails, garbage-collect, linearize (Fast Web View).
"""

from __future__ import annotations

import io
import os
import tempfile
import zlib
from dataclasses import dataclass, field
from typing import Callable, Optional

import fitz  # PyMuPDF (AGPL)
import numpy as np
import pikepdf  # MPL-2.0 - used for linearization; MuPDF dropped it
from PIL import Image

# MuPDF no longer linearizes, so Fast Web View comes from qpdf via pikepdf.
Image.MAX_IMAGE_PIXELS = None  # print scans legitimately exceed the decompression-bomb guard

ProgressFn = Callable[[float, str], None]


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    ppi: int
    quality: int
    blurb: str


PROFILES: dict[str, Profile] = {
    "high": Profile(
        "high", "High Quality", 200, 88,
        "Best fidelity. For pages that will be zoomed or printed casually.",
    ),
    "balanced": Profile(
        "balanced", "Balanced", 150, 82,
        "Recommended. Retina-sharp at full-page zoom, ~90% smaller.",
    ),
    "max": Profile(
        "max", "Maximum Compression", 110, 74,
        "Smallest practical size while staying comfortably readable.",
    ),
}

# Images smaller than this aren't worth the round-trip (and the risk).
MIN_STREAM_BYTES = 8192
# At or below this many distinct colours we treat an image as line art, not a photo.
LINEART_MAX_COLORS = 256


@dataclass
class Stats:
    pages: int = 0
    images_total: int = 0
    recompressed: int = 0
    lossless: int = 0
    grayscaled: int = 0
    downsampled: int = 0
    skipped_lineart: int = 0
    skipped_small: int = 0
    skipped_nogain: int = 0
    failed: int = 0
    image_bytes_before: int = 0
    image_bytes_after: int = 0
    size_before: int = 0
    size_after: int = 0
    linearized: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def reduction_pct(self) -> float:
        if not self.size_before:
            return 0.0
        return (self.size_before - self.size_after) * 100.0 / self.size_before


class Cancelled(Exception):
    """Raised when the caller asks us to stop mid-run."""


def _resolve_colorspace(doc: fitz.Document, xref: int) -> str:
    """/ColorSpace is often an indirect ref, e.g. '55 0 R' -> [/Indexed /DeviceCMYK 255 54 0 R].

    Resolving it matters: a string match on the raw value silently misses indexed
    line art and JPEGs it, which rings around the edges.
    """
    kind, val = doc.xref_get_key(xref, "ColorSpace")
    if kind == "xref":
        try:
            return doc.xref_object(int(val.split()[0]), compressed=True)
        except Exception:
            return val or ""
    return val or ""


def _effective_ppi(doc: fitz.Document) -> dict[int, float]:
    """Real resolution of each image *as placed on the page*.

    Nominal DPI lies: a 411 ppi image dropped into a small frame is even higher
    resolution than it claims, and one stretched full-bleed is lower.
    """
    ppi: dict[int, float] = {}
    for page in doc:
        for img in page.get_images(full=True):
            xref, _, w, h = img[0], img[1], img[2], img[3]
            try:
                rects = page.get_image_rects(xref)
            except Exception:
                continue
            for r in rects:
                if r.width > 0 and r.height > 0:
                    e = max(w / r.width, h / r.height) * 72.0
                    if e > ppi.get(xref, 0.0):
                        ppi[xref] = e
    return ppi


def analyze(path: str) -> dict:
    """Cheap inspection used to show the user what they're dealing with."""
    doc = fitz.open(path)
    try:
        ppi = _effective_ppi(doc)
        seen: set[int] = set()
        img_bytes = 0
        cmyk = 0
        for page in doc:
            for img in page.get_images(full=True):
                xref = img[0]
                if xref in seen:
                    continue
                seen.add(xref)
                img_bytes += len(doc.xref_stream_raw(xref) or b"")
                if "CMYK" in (_resolve_colorspace(doc, xref) or ""):
                    cmyk += 1
        vals = sorted(ppi.values()) or [0.0]
        return {
            "pages": len(doc),
            "size": os.path.getsize(path),
            "images": len(seen),
            "image_bytes": img_bytes,
            "cmyk_images": cmyk,
            "ppi_median": vals[len(vals) // 2],
            "ppi_max": vals[-1],
            "encrypted": doc.is_encrypted,
        }
    finally:
        doc.close()


def _replace(doc: fitz.Document, xref: int, data: bytes, w: int, h: int,
             csname: str, filt: str) -> None:
    doc.update_stream(xref, data, new=True, compress=False)
    doc.xref_set_key(xref, "Width", str(w))
    doc.xref_set_key(xref, "Height", str(h))
    doc.xref_set_key(xref, "ColorSpace", csname)
    doc.xref_set_key(xref, "BitsPerComponent", "8")
    doc.xref_set_key(xref, "Filter", filt)
    doc.xref_set_key(xref, "DecodeParms", "null")
    doc.xref_set_key(xref, "Decode", "null")


def optimize(
    src: str,
    dst: str,
    profile: Profile,
    progress: Optional[ProgressFn] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> Stats:
    """Optimize `src` into `dst`. Returns Stats. Raises Cancelled if aborted."""

    def tick(frac: float, msg: str) -> None:
        if should_cancel and should_cancel():
            raise Cancelled()
        if progress:
            progress(frac, msg)

    st = Stats()
    st.size_before = os.path.getsize(src)
    tick(0.0, "Opening…")

    doc = fitz.open(src)
    try:
        if doc.is_encrypted:
            raise ValueError("This PDF is encrypted; decrypt it before optimizing.")
        st.pages = len(doc)

        tick(0.03, "Measuring image placement…")
        ppi = _effective_ppi(doc)

        xrefs: list[int] = []
        for page in doc:
            for img in page.get_images(full=True):
                if img[0] not in xrefs:
                    xrefs.append(img[0])
        st.images_total = len(xrefs)

        for i, xref in enumerate(xrefs):
            tick(0.05 + 0.80 * (i / max(1, len(xrefs))),
                 f"Image {i + 1} of {len(xrefs)}…")
            try:
                raw = doc.xref_stream_raw(xref) or b""
            except Exception:
                st.failed += 1
                continue
            before = len(raw)
            st.image_bytes_before += before

            # Indexed images are palette line art: already lossless and compact.
            # Touching them can only make them worse.
            if "Indexed" in _resolve_colorspace(doc, xref):
                st.skipped_lineart += 1
                st.image_bytes_after += before
                continue
            if before < MIN_STREAM_BYTES:
                st.skipped_small += 1
                st.image_bytes_after += before
                continue

            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.alpha:  # transparency lives in the separate /SMask object
                    pix = fitz.Pixmap(pix, 0)
                if pix.colorspace is None:
                    st.skipped_nogain += 1
                    st.image_bytes_after += before
                    continue
                if pix.colorspace.n != 3:
                    # Decode via MuPDF so our RGB matches what a viewer already renders.
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                del pix
            except Cancelled:
                raise
            except Exception as e:
                st.failed += 1
                st.image_bytes_after += before
                st.notes.append(f"image {xref}: left as-is ({e})")
                continue

            cur = ppi.get(xref, 0.0)
            scale = min(1.0, profile.ppi / cur) if cur else 1.0
            nw, nh = max(1, round(img.width * scale)), max(1, round(img.height * scale))
            if (nw, nh) != img.size:
                img = img.resize((nw, nh), Image.LANCZOS)
                st.downsampled += 1

            a = np.asarray(img)
            # Some "colour" images are actually grey; emitting one channel instead of
            # three is free size with pixel-identical output.
            is_gray = bool(
                np.abs(a[:, :, 0].astype(np.int16) - a[:, :, 1]).max() <= 2
                and np.abs(a[:, :, 1].astype(np.int16) - a[:, :, 2]).max() <= 2
            )
            out = img.convert("L") if is_gray else img
            csname = "/DeviceGray" if is_gray else "/DeviceRGB"

            # Flat-colour images (charts, logos, screenshots) get lossless treatment:
            # JPEG would ring around hard edges.
            if len(np.unique(a.reshape(-1, 3), axis=0)) <= LINEART_MAX_COLORS:
                data = zlib.compress(out.tobytes(), 9)
                if len(data) < before:
                    _replace(doc, xref, data, out.width, out.height, csname, "/FlateDecode")
                    st.lossless += 1
                    st.grayscaled += int(is_gray)
                    st.image_bytes_after += len(data)
                else:
                    st.skipped_nogain += 1
                    st.image_bytes_after += before
                continue

            buf = io.BytesIO()
            out.save(buf, "JPEG", quality=profile.quality, optimize=True,
                     progressive=False,  # baseline only: /DCTDecode compatibility
                     subsampling=(2 if profile.quality < 85 else 0))
            data = buf.getvalue()

            if len(data) >= before:  # never make an object bigger
                st.skipped_nogain += 1
                st.image_bytes_after += before
                continue

            _replace(doc, xref, data, out.width, out.height, csname, "/DCTDecode")
            st.recompressed += 1
            st.grayscaled += int(is_gray)
            st.image_bytes_after += len(data)

        tick(0.88, "Stripping metadata…")
        doc.set_metadata({})
        doc.del_xml_metadata()
        for page in doc:
            if doc.xref_get_key(page.xref, "Thumb")[0] != "null":
                doc.xref_set_key(page.xref, "Thumb", "null")

        tick(0.92, "Rebuilding…")
        tmp = tempfile.mktemp(suffix=".pdf")
        doc.save(tmp, garbage=4, deflate=True, deflate_fonts=True,
                 deflate_images=False, clean=True, use_objstms=1)
    finally:
        doc.close()

    try:
        tick(0.96, "Linearizing for Fast Web View…")
        with pikepdf.open(tmp) as p:
            p.save(dst, linearize=True,
                   object_stream_mode=pikepdf.ObjectStreamMode.generate,
                   compress_streams=True)
        st.linearized = True
    except Cancelled:
        raise
    except Exception as e:
        # Fast Web View is an optimization, not correctness: keep the smaller file.
        os.replace(tmp, dst)
        st.linearized = False
        st.notes.append(f"linearization skipped ({e})")
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

    st.size_after = os.path.getsize(dst)
    tick(1.0, "Done")
    return st
