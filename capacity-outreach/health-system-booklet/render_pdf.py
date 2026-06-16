"""
render_pdf.py
=============
Batch-render print-ready PDFs of the Florence Hospital Booklet — one PDF per
health system — for vendor printing, proofs, or low-volume sends that fall under
Lob's booklet minimum.

Uses Playwright (headless Chromium) to print the SAME static HTML the design
tool produces, at exactly 9×6 in, one booklet page per sheet. This is the most
faithful path: it renders the real fonts, gradients, and layout.

Setup:
    pip install playwright jinja2
    playwright install chromium

How it works:
    1. build_hospital_booklet.html → "Download Lob template" gives you the
       Handlebars template (florence-hospital-booklet-teal.html).
    2. hospital_audience.build_audience_csv(...) gives you per-system values.
    3. This script fills the template per row and prints each to PDF.

For a single ad-hoc proof you can skip the template and let the design tool's
"Print / Save PDF" button do it interactively. This script is for batches.
"""
from __future__ import annotations

import asyncio
import csv
import os
import re

from playwright.async_api import async_playwright


def fill_handlebars(template: str, row: dict) -> str:
    """Minimal {{var}} substitution + {{#if x}}…{{/if}} for the logo-style gates.
    Sufficient for this template (no loops, no nested conditionals)."""
    html = template
    # {{#if key}}...{{/if}} — keep block only if the value is truthy
    def _if(m):
        key, inner = m.group(1), m.group(2)
        return inner if str(row.get(key, "")).strip() else ""
    html = re.sub(r"\{\{#if\s+(\w+)\}\}(.*?)\{\{/if\}\}", _if, html, flags=re.S)
    # {{key}}
    html = re.sub(r"\{\{(\w+)\}\}", lambda m: str(row.get(m.group(1), "")), html)
    return html


async def render_all(template_path: str, csv_path: str, out_dir: str = "./pdfs"):
    os.makedirs(out_dir, exist_ok=True)
    template = open(template_path, encoding="utf-8").read()
    rows = list(csv.DictReader(open(csv_path, encoding="utf-8")))

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        for r in rows:
            html = fill_handlebars(template, r)
            await page.set_content(html, wait_until="networkidle")
            slug = re.sub(r"[^a-z0-9]+", "-", r.get("system_name", "system").lower()).strip("-")
            pdf_path = os.path.join(out_dir, f"{slug}.pdf")
            await page.pdf(path=pdf_path, width="9in", height="6in",
                           print_background=True, prefer_css_page_size=True)
            print("✓", pdf_path)
        await browser.close()
    print(f"\nRendered {len(rows)} booklet PDFs → {out_dir}")


if __name__ == "__main__":
    import sys
    tpl = sys.argv[1] if len(sys.argv) > 1 else "florence-hospital-booklet-teal.html"
    csvp = sys.argv[2] if len(sys.argv) > 2 else "hospital_run.csv"
    asyncio.run(render_all(tpl, csvp))
