"""
client_deck_export.py
=====================================================================
Export ONE health system's Florence Client Deck as a single, portable,
self-contained HTML file — every script, style, and image inlined, the
live Tweaks panel (React/Babel) stripped — so a rep can download it from
the Streamlit app and email/open it with no server or assets folder.

It reuses the design bundle in `client-deck/` as-is (TEMPLATE.html +
template/{universe,logos,presets,render}.js + deck-stage.js + assets/),
so the deck stays in lockstep with the design — we only inline + pin the
chosen client; the slides/pricing logic are untouched.

CLI:  python client_deck_export.py kaiser_permanente [out.html]
App:  export_deck_html("hca") -> str
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
DECK_DIR = os.path.join(_HERE, "client-deck")

# Universe ids that have a hand-tuned featured preset (mirrors presets.js
# FLORENCE_FEATURED) — pass the preset key so the showcase deck is used.
_FEATURED = {"kaiser_permanente": "kaiser", "sutter_health": "sutter"}


def _read(*parts: str) -> str:
    with open(os.path.join(DECK_DIR, *parts), encoding="utf-8") as fh:
        return fh.read()


def _universe() -> dict:
    """Parse template/universe.js -> {id: entry}."""
    text = _read("template", "universe.js")
    body = text.split("window.FLORENCE_UNIVERSE = ", 1)[1]
    obj = body.split(";\nwindow.FLORENCE_UNIVERSE_ORDER", 1)[0].rstrip().rstrip(";")
    return json.loads(obj)


def _asset_data_uris() -> dict:
    """Map every 'assets/<relpath>' -> data: URI (base64)."""
    out = {}
    root = os.path.join(DECK_DIR, "assets")
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            full = os.path.join(dirpath, f)
            rel = "assets/" + os.path.relpath(full, root).replace(os.sep, "/")
            mime = mimetypes.guess_type(full)[0] or "application/octet-stream"
            if rel.endswith(".svg"):
                mime = "image/svg+xml"
            with open(full, "rb") as fh:
                b64 = base64.b64encode(fh.read()).decode("ascii")
            out[rel] = f"data:{mime};base64,{b64}"
    return out


def _inline_script(js: str) -> str:
    """Wrap JS in a <script>, escaping any literal </script> so the page parses."""
    return "<script>" + js.replace("</script>", "<\\/script>") + "</script>"


def available_systems() -> set:
    """System ids that can be exported (in the deck universe, or featured)."""
    return set(_universe().keys()) | set(_FEATURED.values()) | set(_FEATURED.keys())


def export_deck_html(system_id: str) -> str | None:
    """Return a fully self-contained deck HTML for `system_id`, or None if the
    system isn't in the deck universe (e.g. no priced facilities)."""
    uni = _universe()
    cid = _FEATURED.get(system_id, system_id)
    # Need either a featured preset key, or a universe entry to render.
    entry = uni.get(system_id) or uni.get(cid)
    if entry is None and cid not in _FEATURED.values():
        return None

    html = _read("Florence Client Deck - TEMPLATE.html")
    css = _read("assets", "colors_and_type.css")
    logos_js = _read("template", "logos.js")
    presets_js = _read("template", "presets.js")
    render_js = _read("template", "render.js")
    stage_js = _read("deck-stage.js")

    # 1) inline the stylesheet
    html = html.replace(
        '<link rel="stylesheet" href="assets/colors_and_type.css" />',
        "<style>\n" + css + "\n</style>",
    )

    # 2) replace the 5 <script src> tags with inlined, client-pinned scripts.
    #    universe is filtered to just this system (keeps the file tiny); the
    #    override pins FLORENCE_ACTIVE_CONFIG after presets.js' own resolver runs.
    uni_min = {system_id: entry} if entry is not None else {}
    pin = (
        f"window.FLORENCE_UNIVERSE = {json.dumps(uni_min)};\n"
        f"window.FLORENCE_UNIVERSE_ORDER = {json.dumps(list(uni_min.keys()))};"
    )
    force = (
        f'window.FLORENCE_ACTIVE_CLIENT = {json.dumps(cid)};\n'
        f'window.FLORENCE_ACTIVE_CONFIG = window.FLORENCE_PRESETS[{json.dumps(cid)}]'
        f' || window.configFromUniverse({json.dumps(cid)}) || window.FLORENCE_PRESETS.kaiser;'
    )
    script_block = (
        '<script src="template/universe.js"></script>\n'
        '<script src="template/logos.js"></script>\n'
        '<script src="template/presets.js"></script>\n'
        '<script src="template/render.js"></script>\n'
        '<script src="deck-stage.js"></script>'
    )
    inlined = "\n".join([
        _inline_script(pin),
        _inline_script(logos_js),
        _inline_script(presets_js),
        _inline_script(force),
        _inline_script(render_js),
        _inline_script(stage_js),
    ])
    html = html.replace(script_block, inlined)

    # 3) drop the live Tweaks panel (React/Babel + tweaks-panel.jsx) — static export
    cut = html.find("<!-- ============ Tweaks ============ -->")
    if cut != -1:
        end = html.find("</body>", cut)
        html = html[:cut] + html[end:]

    # 4) inline every asset reference as a data: URI (longest paths first so a
    #    shorter path is never a prefix of a longer one)
    for rel, uri in sorted(_asset_data_uris().items(), key=lambda kv: -len(kv[0])):
        html = html.replace(rel, uri)

    return html


if __name__ == "__main__":
    import sys
    sid = sys.argv[1] if len(sys.argv) > 1 else "kaiser_permanente"
    out = sys.argv[2] if len(sys.argv) > 2 else f"/tmp/florence_deck_{sid}.html"
    h = export_deck_html(sid)
    if h is None:
        print(f"no deck for '{sid}' (not in the deck universe)")
        raise SystemExit(1)
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(h)
    print(f"wrote {out}  ({len(h):,} bytes)")
