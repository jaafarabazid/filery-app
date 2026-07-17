"""Command-line interface: pdfoptimize input.pdf [-p balanced] [-o out.pdf]"""

from __future__ import annotations

import argparse
import os
import sys

from .optimizers.pdf import PROFILES, analyze, optimize


def _mb(n: float) -> str:
    return f"{n / 1048576:.2f} MB"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="pdfoptimize",
        description="Optimize print-ready PDFs for web delivery without touching text.",
    )
    ap.add_argument("input", nargs="+", help="PDF file(s) to optimize")
    ap.add_argument("-p", "--profile", default="balanced", choices=list(PROFILES),
                    help="default: balanced")
    ap.add_argument("-o", "--output", help="output file (single input only)")
    ap.add_argument("--all", action="store_true",
                    help="write all three profiles for each input")
    ap.add_argument("--analyze", action="store_true", help="inspect only, change nothing")
    args = ap.parse_args(argv)

    if args.output and (len(args.input) > 1 or args.all):
        ap.error("--output only works with a single input and without --all")

    for path in args.input:
        if not os.path.isfile(path):
            print(f"error: no such file: {path}", file=sys.stderr)
            return 2

        info = analyze(path)
        print(f"\n{os.path.basename(path)}")
        print(f"  {info['pages']} pages, {_mb(info['size'])}, {info['images']} images "
              f"({_mb(info['image_bytes'])} of image data, {info['cmyk_images']} CMYK)")
        print(f"  effective ppi: median {info['ppi_median']:.0f}, max {info['ppi_max']:.0f}")
        if args.analyze:
            continue

        keys = list(PROFILES) if args.all else [args.profile]
        for key in keys:
            prof = PROFILES[key]
            if args.output:
                out = args.output
            else:
                stem, ext = os.path.splitext(path)
                suffix = f" - {prof.label}" if args.all or key != "balanced" else " - Balanced"
                out = f"{stem}{suffix}{ext}"

            last = [-1]

            def show(frac: float, msg: str) -> None:
                pct = int(frac * 100)
                if pct != last[0]:
                    last[0] = pct
                    print(f"\r  [{prof.label}] {pct:3d}%  {msg:<32}", end="", flush=True)

            st = optimize(path, out, prof, progress=show)
            print(f"\r  [{prof.label}] {_mb(st.size_before)} -> {_mb(st.size_after)} "
                  f"({st.reduction_pct:.1f}% smaller)"
                  f"{'' if st.linearized else '  [not linearized]'}"
                  f"{'':<12}")
            print(f"      recompressed={st.recompressed} lossless={st.lossless} "
                  f"gray={st.grayscaled} downsampled={st.downsampled} "
                  f"kept(line-art={st.skipped_lineart} small={st.skipped_small} "
                  f"no-gain={st.skipped_nogain}) failed={st.failed}")
            for n in st.notes:
                print(f"      note: {n}")
            print(f"      -> {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
