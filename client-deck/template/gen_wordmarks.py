#!/usr/bin/env python3
"""
gen_wordmarks.py
=====================================================================
Generate clean, export-safe typographic wordmark logos (one per top
health system) for the client deck covers, in each system's researched
brand color. These are ORIGINAL wordmarks — the system name set in a
serif face in the brand color — NOT reproductions of any brand's logo
artwork. They give each system's deck a branded cover mark until a real
brand file is dropped in to replace it.

Source of truth: brand_logos.json  (id, name, hex — committed, regenerable).
Writes:          ../assets/systems/<id>.svg  for every entry (except those
                 pointing at a real logo file via "file").

The SVG renders inside an <img> (isolated context, no page @font-face), so
it uses a web-safe serif stack and bakes the color in. Too-light brand
colors are darkened so the wordmark stays legible on a white cover.

    python gen_wordmarks.py        # reads brand_logos.json, writes the SVGs
"""
from __future__ import annotations

import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
BRAND_JSON = os.path.join(_HERE, "brand_logos.json")
SYS_DIR = os.path.join(_HERE, "..", "assets", "systems")

FONT = "Georgia, 'Times New Roman', 'Iowan Old Style', serif"
FSIZE = 100                 # font size in the SVG's own user units
CHAR_W = 0.54               # avg advance per char (serif bold), em
LINE_H = 1.06
PAD = 14


def _rgb(hex_: str) -> tuple:
    h = hex_.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb: tuple) -> str:
    return "#" + "".join(f"{max(0, min(255, int(c))):02X}" for c in rgb)


def legible(hex_: str) -> str:
    """Darken a too-light brand color so the wordmark reads on white."""
    r, g, b = _rgb(hex_)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b           # 0..255
    if lum <= 150:
        return hex_.upper()
    scale = 150.0 / lum                                  # pull toward darker
    return _hex((r * scale, g * scale, b * scale))


def _wrap(name: str) -> list:
    """1 line if short, else 2 balanced lines (break near the middle word)."""
    if len(name) <= 18:
        return [name]
    words = name.split()
    if len(words) < 2:
        return [name]
    best, best_diff = None, 1e9
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        diff = abs(len(a) - len(b))
        if diff < best_diff:
            best, best_diff = (a, b), diff
    return list(best)


def wordmark_svg(name: str, hex_: str) -> str:
    color = legible(hex_)
    lines = _wrap(name)
    line_w = max(len(s) for s in lines) * FSIZE * CHAR_W
    w = round(line_w + PAD * 2)
    h = round(len(lines) * FSIZE * LINE_H + PAD * 2)
    texts = []
    for i, s in enumerate(lines):
        y = round(PAD + FSIZE * 0.80 + i * FSIZE * LINE_H)
        s_esc = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        texts.append(
            f'<text x="{PAD}" y="{y}" font-family="{FONT}" font-weight="700" '
            f'font-size="{FSIZE}" letter-spacing="-1.5" fill="{color}">{s_esc}</text>'
        )
    body = "\n  ".join(texts)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{name}">\n  {body}\n</svg>\n'
    )


def main() -> None:
    os.makedirs(SYS_DIR, exist_ok=True)
    brand = json.load(open(BRAND_JSON, encoding="utf-8"))
    n = 0
    for r in brand:
        if r.get("file"):           # entry points at a real logo file → don't overwrite
            continue
        svg = wordmark_svg(r["name"], r["hex"])
        with open(os.path.join(SYS_DIR, r["id"] + ".svg"), "w", encoding="utf-8") as fh:
            fh.write(svg)
        n += 1
    print(f"wrote {n} wordmark SVGs to assets/systems/ "
          f"({len(brand) - n} entries kept a real logo file)")


if __name__ == "__main__":
    main()
