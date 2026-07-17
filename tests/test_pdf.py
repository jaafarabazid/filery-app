"""Invariants that must hold for every optimized file.

The point of this tool is that it only ever touches images. These tests exist to
catch the day that stops being true.
"""

from __future__ import annotations

import io
import os

import fitz
import numpy as np
import pytest
from PIL import Image

from filery.optimizers.pdf import PROFILES, analyze, optimize

TEXT = "The quick brown fox jumps over the lazy dog. 0123456789"


def _photo(w: int, h: int, seed: int = 0) -> bytes:
    """Noisy gradient: compresses like a photograph, not like flat colour."""
    rng = np.random.default_rng(seed)
    x = np.linspace(0, 255, w, dtype=np.float64)[None, :, None]
    y = np.linspace(0, 255, h, dtype=np.float64)[:, None, None]
    base = (x * 0.5 + y * 0.5) * np.array([1.0, 0.7, 0.4])
    noisy = np.clip(base + rng.normal(0, 18, (h, w, 3)), 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(noisy).save(buf, "JPEG", quality=95)
    return buf.getvalue()


@pytest.fixture
def sample(tmp_path):
    """A page with real text plus a deliberately over-resolution photo."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)  # A4
    page.insert_text((60, 80), TEXT, fontsize=12)
    page.insert_text((60, 110), TEXT, fontsize=9)
    # ~1200 ppi as placed: 2400px across a 144pt-wide box
    page.insert_image(fitz.Rect(60, 140, 204, 284), stream=_photo(2400, 2400))
    p = tmp_path / "in.pdf"
    doc.save(str(p))
    doc.close()
    return str(p)


def test_analyze_reports_placement_resolution(sample):
    info = analyze(sample)
    assert info["pages"] == 1
    assert info["images"] == 1
    # nominal size says nothing; placement is what matters
    assert info["ppi_max"] > 900


@pytest.mark.parametrize("key", list(PROFILES))
def test_text_and_geometry_survive(sample, tmp_path, key):
    out = str(tmp_path / f"{key}.pdf")
    optimize(sample, out, PROFILES[key])

    a, b = fitz.open(sample), fitz.open(out)
    try:
        assert len(a) == len(b)
        for i in range(len(a)):
            assert a[i].get_text("text") == b[i].get_text("text"), "text must be untouched"
            assert abs(a[i].rect.width - b[i].rect.width) < 0.01
            assert abs(a[i].rect.height - b[i].rect.height) < 0.01
            assert a[i].rotation == b[i].rotation
    finally:
        a.close()
        b.close()


def test_fonts_stay_embedded(sample, tmp_path):
    out = str(tmp_path / "b.pdf")
    optimize(sample, out, PROFILES["balanced"])
    doc = fitz.open(out)
    try:
        for page in doc:
            for f in page.get_fonts(full=True):
                assert f[3], "font must remain embedded (no rasterized text)"
    finally:
        doc.close()


def test_it_actually_shrinks(sample, tmp_path):
    out = str(tmp_path / "b.pdf")
    st = optimize(sample, out, PROFILES["balanced"])
    assert st.size_after < st.size_before
    assert st.reduction_pct > 50
    assert st.downsampled == 1


def test_downsamples_to_profile_ppi(sample, tmp_path):
    out = str(tmp_path / "b.pdf")
    optimize(sample, out, PROFILES["balanced"])
    doc = fitz.open(out)
    try:
        page = doc[0]
        img = page.get_images(full=True)[0]
        xref, w = img[0], img[2]
        rect = page.get_image_rects(xref)[0]
        ppi = w / rect.width * 72
        assert ppi == pytest.approx(PROFILES["balanced"].ppi, rel=0.08)
    finally:
        doc.close()


def test_never_upscales_a_low_res_image(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    # 60 ppi as placed - already far below every profile target
    page.insert_image(fitz.Rect(0, 0, 480, 480), stream=_photo(400, 400, seed=3))
    src = str(tmp_path / "low.pdf")
    doc.save(src)
    doc.close()

    out = str(tmp_path / "low_out.pdf")
    optimize(src, out, PROFILES["high"])
    d = fitz.open(out)
    try:
        assert d[0].get_images(full=True)[0][2] <= 400, "must never invent pixels"
    finally:
        d.close()


def test_indexed_line_art_is_left_alone(tmp_path):
    """Palette images are lossless line art; JPEG would ring around the edges."""
    art = Image.new("P", (600, 600))
    art.putpalette([0, 0, 0, 255, 255, 255] + [0] * 762)
    px = art.load()
    for i in range(600):
        for j in range(600):
            px[i, j] = 1 if (i // 20 + j // 20) % 2 else 0
    p = tmp_path / "art.png"
    art.save(p)

    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(fitz.Rect(50, 50, 350, 350), filename=str(p))
    src = str(tmp_path / "art.pdf")
    doc.save(src)
    doc.close()

    before = fitz.open(src)
    raw_before = before.xref_stream_raw(before[0].get_images(full=True)[0][0])
    before.close()

    out = str(tmp_path / "art_out.pdf")
    st = optimize(src, out, PROFILES["max"])
    after = fitz.open(out)
    try:
        raw_after = after.xref_stream_raw(after[0].get_images(full=True)[0][0])
    finally:
        after.close()

    if st.skipped_lineart:
        assert raw_after == raw_before, "indexed art must be byte-identical"
    else:
        # if it was rewritten it must at least have stayed lossless
        assert st.lossless >= 1


def test_metadata_is_stripped(sample, tmp_path):
    doc = fitz.open(sample)
    doc.set_metadata({"author": "Somebody", "title": "Private", "keywords": "secret"})
    tagged = str(tmp_path / "tagged.pdf")
    doc.save(tagged)
    doc.close()

    out = str(tmp_path / "clean.pdf")
    optimize(tagged, out, PROFILES["balanced"])
    d = fitz.open(out)
    try:
        md = d.metadata or {}
        assert not md.get("author")
        assert not md.get("title")
        assert not md.get("keywords")
    finally:
        d.close()


def test_cancellation_stops_and_raises(sample, tmp_path):
    from filery.optimizers.pdf import Cancelled

    out = str(tmp_path / "never.pdf")
    with pytest.raises(Cancelled):
        optimize(sample, out, PROFILES["balanced"], should_cancel=lambda: True)


def test_encrypted_input_is_rejected(tmp_path):
    doc = fitz.open()
    doc.new_page()
    enc = str(tmp_path / "enc.pdf")
    doc.save(enc, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw="o", user_pw="u")
    doc.close()
    with pytest.raises(Exception):
        optimize(enc, str(tmp_path / "o.pdf"), PROFILES["balanced"])
