"""
florence_postcard.py
====================
Themed non-hospital postcard renderer for Lob — the "photo + full-color panel"
design (Tiffany Blue or Royal Purple) with a per-piece QR code.

This is a drop-in upgrade for `lob_mailer.render_postcard_html()`. It returns
`{"front": <html>, "back": <html>}`, each a standalone document sized for Lob's
**6x11** postcard (11in x 6in canvas, 96px/in == 300dpi at print).

Compliance (standing rule): copy is value + activation ONLY.
No FICA / visa / tax / immigration language ever goes on a mailpiece.

Install:
    pip install "qrcode[pil]"        # QR generation (pulls in Pillow)

Host these two assets once, on any public HTTPS URL Lob's renderer can fetch
(your S3 / CloudFront / marketing CDN). Pass them in or set env vars:
    FLORENCE_NURSE_IMG    -> the RN photo            (assets/nurse-rn.png)
    FLORENCE_LOGO_WHITE   -> white Florence wordmark (assets/florence-white.svg)

NOTE ON THE BACK + ADDRESS: Lob automatically prints the recipient address,
your return address, postage indicia and the Intelligent Mail barcode in the
reserved zone on the RIGHT side of the back. So the production back leaves that
zone BLANK — you do not draw it. (The interactive preview tool fills it only to
visualize placement.)
"""
from __future__ import annotations

import base64
import io
import json
import os

import qrcode
from qrcode.constants import ERROR_CORRECT_M

SIGNUP_BASE = os.environ.get("FLORENCE_SIGNUP_URL", "https://florenceedu.com/activate")
NURSE_IMG = os.environ.get("FLORENCE_NURSE_IMG", "https://florenceedu.com/assets/nurse-rn.png")
LOGO_WHITE = os.environ.get("FLORENCE_LOGO_WHITE", "https://florenceedu.com/assets/florence-white.svg")

# ── Brand palette → per-theme accent set (mirrors the design system tokens) ──
THEMES = {
    # `sec` is the secondary (cross) accent fill used for the seam / band / top
    # stripe: teal cards accent with purple, purple cards accent with teal.
    "teal": dict(ac="#0ABAB5", ac_deep="#00A4B4", ac_text="#067F7B",
                 ac_wash="#E6F8F7", ac_tint="#B7EBE8",
                 sec="#7340C4", sec_text="#5B2DA8", sec_wash="#F1ECFB"),
    "purple": dict(ac="#7340C4", ac_deep="#5B2DA8", ac_text="#5B2DA8",
                   ac_wash="#F1ECFB", ac_tint="#AD8EDC",
                   sec="#0ABAB5", sec_text="#067F7B", sec_wash="#E6F8F7"),
}

# ── Copy: loaded from the shared postcard_copy.json (single source of truth,
#    also mirrored by Postcard Mailer.html). Falls back to the built-ins below. ──
_COPY_PATH = os.environ.get("FLORENCE_POSTCARD_COPY",
                           os.path.join(os.path.dirname(__file__), "postcard_copy.json"))
_DEFAULT_COPY = {
    "taglines": {
        "quote": {"head": "Permanent RNs, committed for two years. The capacity to care for more.",
                  "sub": "Globally-educated, U.S.-licensed RNs placed direct on your payroll. No travelers, no agency premium."},
        "market": {"head": "Your next nurse doesn't have to be a traveler.",
                   "sub": "Florence places permanent, globally-educated RNs, fully U.S.-licensed, direct on your payroll, to {verb} in {city} without agency markup."},
    },
    "types": {
        "HHA": {"label": "Home Health Agency", "short": "Home Health", "verb": "fill every visit",
                "recap": "Fill every visit on your own schedule. Permanent, globally-educated RNs, fully U.S.-licensed, on your payroll, not per-visit contractors."},
        "ASC": {"label": "Ambulatory Surgery Center", "short": "Surgery Center", "verb": "keep every OR staffed",
                "recap": "Keep every OR running with permanent, globally-educated RNs, fully U.S.-licensed, placed direct. No per-diem premium, no travelers."},
        "SNF": {"label": "Skilled Nursing Facility", "short": "Skilled Nursing", "verb": "cover every shift",
                "recap": "Cover every shift with permanent, globally-educated RNs, fully U.S.-licensed, on your payroll. No agency markup, no rotating travelers."},
        "DIALYSIS": {"label": "Dialysis Center", "short": "Dialysis", "verb": "staff every chair",
                     "recap": "Staff every chair with permanent, globally-educated RNs, fully U.S.-licensed, placed direct. Steady coverage, no agency premium."},
        "HOSPICE": {"label": "Hospice", "short": "Hospice", "verb": "cover every patient",
                    "recap": "A permanent RN for every patient. Globally-educated, fully U.S.-licensed, placed direct on your payroll, no agency."},
    },
}


def _load_copy() -> dict:
    try:
        with open(_COPY_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return {"taglines": {**_DEFAULT_COPY["taglines"], **data.get("taglines", {})},
                "types": {**_DEFAULT_COPY["types"], **data.get("types", {})}}
    except Exception:
        return _DEFAULT_COPY


_COPY = _load_copy()
TYPES = _COPY["types"]
TAGLINES = _COPY["taglines"]

# How much of the secondary color appears on the card (see render_postcard).
_SEAM = {"accent": 0, "split": 6, "duotone": 13}

# Google Fonts stand-ins (zero-setup). Swap to hosted GT Sectra for brand-exact —
# see the integration guide. Lob's renderer fetches Google Fonts fine.
_FONTS = (
    '<link href="https://fonts.googleapis.com/css2?'
    "family=Playfair+Display:ital,wght@0,500;0,700;0,800;1,500;1,700&"
    "family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@500;600&display=swap"
    '" rel="stylesheet">'
)
_DISPLAY = "'Playfair Display', Georgia, serif"   # -> 'GT Sectra Display' when hosted
_SANS = "'Inter', system-ui, Helvetica, Arial, sans-serif"
_MONO = "'JetBrains Mono', ui-monospace, Menlo, monospace"


def _usd(v) -> str:
    return "$" + format(int(round(float(v or 0))), ",d")


def qr_data_uri(url: str, dark: str = "#101828") -> str:
    """Render a QR PNG for `url` as an embedded data URI (self-contained — no
    asset hosting needed for the QR itself)."""
    qr = qrcode.QRCode(border=0, box_size=12, error_correction=ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=dark, back_color="white").convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


# ════════════════════════════════════════════════════════════════════
def render_postcard(
    *,
    org_name: str,
    facility_type: str,
    city: str,
    state: str,
    fee_per_rn_month: float,
    rn_estimate: int,
    code: str,
    theme: str = "teal",
    headline: str = "quote",           # "quote" | "market"
    color_mix: str = "split",          # "accent" | "split" | "duotone"  (how much secondary color)
    size: str = "6x11",                # "6x11" | "6x9"
    qr_mode: str = "embedded",         # "embedded" (we draw the QR) | "reserve" (Lob places a native QR)
    nurse_img: str = NURSE_IMG,
    logo_white: str = LOGO_WHITE,
    signup_base: str = SIGNUP_BASE,
    include_address_preview: bool = False,   # True only for on-screen preview
    contact_name: str = "",
    address1: str = "",
    zip: str = "",
) -> dict:
    """Return {"front": html, "back": html} for a single account — Lob-ready."""
    th = THEMES.get(theme, THEMES["teal"])
    t = TYPES.get(facility_type, {})
    city_t = (city or "").title()
    label = t.get("label", "Care Operator")
    recap = t.get("recap", "Permanent, globally-educated, U.S.-licensed RNs placed direct on your payroll.")
    verb = t.get("verb", "cover every shift")
    fee = _usd(fee_per_rn_month)
    account_mo = _usd(float(fee_per_rn_month) * int(rn_estimate or 1))
    url = f"{signup_base}?code={code}"

    # Page geometry (6x11 default; 6x9 is the cheaper-postage option).
    W = 9.0 if size == "6x9" else 11.0
    msg_w = round(W * 0.575, 2)
    # Color-mix: how much secondary color lands on the card.
    band_bg = "transparent" if color_mix == "accent" else th["sec"]
    seam_w = {"accent": 0, "split": 8, "duotone": 18}.get(color_mix, 8)
    qwrap_pt = 62 if color_mix == "duotone" else 18
    eyebrow_color = "rgba(255,255,255,.92)" if color_mix == "duotone" else "rgba(255,255,255,.82)"
    top_band = (".panel::before { content:''; position:absolute; top:0; left:0; right:0; "
                f"height:96px; background:{th['sec']}; z-index:0; }}") if color_mix == "duotone" else ""

    if headline == "market":
        eyebrow = f"{state} nurse market &middot; {t.get('short', label)}"
        head = TAGLINES["market"]["head"]
        sub = TAGLINES["market"]["sub"].format(verb=verb, city=city_t)
    else:
        eyebrow = f"Prepared for {org_name.title()[:32]}"
        head = TAGLINES["quote"]["head"]
        sub = TAGLINES["quote"]["sub"]

    front = f"""<!doctype html><html><head><meta charset="utf-8">{_FONTS}<style>
@page {{ size: {W}in 6in; margin: 0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html,body {{ width:{W}in; height:6in; }}
body {{ font-family:{_SANS}; color:#101828; }}
.front2 {{ display:flex; width:{W}in; height:6in; }}
.ph {{ flex:0 0 42%; height:100%; overflow:hidden; background:#0b2747; }}
.ph img {{ width:100%; height:100%; object-fit:cover; object-position:50% 18%; display:block; }}
.seam {{ flex:0 0 {seam_w}px; background:{th['sec']}; }}
.panel {{ flex:1; min-width:0; background:{th['ac']}; color:#fff; padding:42px 46px 36px; display:flex; flex-direction:column; position:relative; overflow:hidden; }}
{top_band}
.wm {{ height:44px; width:auto; position:relative; z-index:1; }}
.eyebrow {{ font-size:12px; font-weight:600; letter-spacing:.14em; text-transform:uppercase; color:{eyebrow_color}; margin-top:24px; position:relative; z-index:1; }}
.head {{ font-family:{_DISPLAY}; font-weight:700; font-size:35px; line-height:1.08; letter-spacing:-.015em; margin-top:12px; position:relative; z-index:1; }}
.head em {{ font-style:italic; }}
.sub {{ font-size:14.5px; line-height:1.45; color:rgba(255,255,255,.9); margin-top:13px; max-width:40ch; position:relative; z-index:1; }}
.qwrap {{ margin:auto -46px -36px; padding:{qwrap_pt}px 46px 30px; background:{band_bg}; display:flex; flex-direction:column; position:relative; z-index:1; }}
.quote {{ background:#fff; border-radius:14px; padding:15px 20px 16px; position:relative; }}
.q-tag {{ position:absolute; top:13px; right:15px; font-size:10px; font-weight:700; letter-spacing:.05em; text-transform:uppercase; color:{th['sec_text']}; background:{th['sec_wash']}; padding:4px 9px; border-radius:9999px; }}
.q-l {{ font-size:11px; font-weight:600; letter-spacing:.1em; text-transform:uppercase; color:#475467; }}
.q-stat {{ font-family:{_DISPLAY}; font-weight:800; font-size:44px; line-height:1; letter-spacing:-.03em; color:{th['ac_text']}; margin-top:4px; }}
.q-stat span {{ font-family:{_SANS}; font-size:14px; font-weight:600; color:#475467; margin-left:3px; }}
.q-note {{ font-size:12px; color:#98A2B3; margin-top:5px; }}
.foot {{ margin-top:13px; font-family:{_SANS}; font-weight:600; font-size:14px; color:rgba(255,255,255,.94); }}
</style></head><body><div class="front2">
  <div class="ph"><img src="{nurse_img}" alt="Florence registered nurse"></div>
  <div class="seam"></div>
  <div class="panel">
    <img class="wm" src="{logo_white}" alt="Florence">
    <div class="eyebrow">{eyebrow}</div>
    <h1 class="head">{head}</h1>
    <p class="sub">{sub}</p>
    <div class="qwrap">
      <div class="quote">
        <div class="q-tag">2-year term</div>
        <div class="q-l">Your monthly rate</div>
        <div class="q-stat">{fee}<span>/nurse/mo</span></div>
        <div class="q-note">Est. {rn_estimate}-RN cohort &middot; {city_t}, {state}</div>
      </div>
      <div class="foot">Flip over to activate &rarr;</div>
    </div>
  </div>
</div></body></html>"""

    qr = qr_data_uri(url)
    # qr_mode="reserve" leaves the QR box empty so Lob can drop a NATIVE, trackable
    # QR at that position (see lob_send.native_qr). "embedded" draws our own.
    qr_img = "" if qr_mode == "reserve" else f'<img src="{qr}" alt="Scan to activate">'
    # Right column: BLANK in production (Lob stamps address+barcode+postage there).
    addr_col = ""
    if include_address_preview:
        addr_col = f"""<div class="addr">
        <div class="note">&darr; Lob prints the verified delivery address + barcode here &darr;</div>
        <div class="blk"><b>{contact_name}</b><br>{org_name.title()}<br>{address1}<br>{city_t}, {state} {zip}</div>
      </div>"""

    back = f"""<!doctype html><html><head><meta charset="utf-8">{_FONTS}<style>
@page {{ size: {W}in 6in; margin: 0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
html,body {{ width:{W}in; height:6in; }}
body {{ font-family:{_SANS}; color:#101828; }}
.back {{ display:flex; width:{W}in; height:6in; }}
.msg {{ width:{msg_w}in; padding:46px 44px 38px 50px; display:flex; flex-direction:column; border-top:6px solid {th['ac']}; }}
.eyebrow {{ font-size:12px; font-weight:600; letter-spacing:.14em; text-transform:uppercase; color:{th['ac_text']}; }}
.org {{ font-family:{_DISPLAY}; font-weight:700; font-size:30px; line-height:1.08; letter-spacing:-.015em; margin-top:8px; }}
.recap {{ font-size:15px; line-height:1.5; color:#475467; margin-top:11px; max-width:42ch; }}
.specs {{ display:flex; border:1px solid #E4E7EC; border-radius:12px; overflow:hidden; margin-top:20px; }}
.spec {{ flex:1; padding:13px 15px; border-right:1px solid #E4E7EC; }}
.spec:last-child {{ border-right:0; }}
.sn {{ font-family:{_DISPLAY}; font-weight:800; font-size:22px; letter-spacing:-.02em; line-height:1; }}
.spec.hl .sn {{ color:{th['ac_text']}; }}
.spec.sec .sn {{ color:{th['sec_text']}; }}
.sl {{ font-size:11px; color:#98A2B3; margin-top:6px; }}
.act {{ display:flex; gap:18px; align-items:center; margin-top:auto; padding-top:22px; }}
.qr {{ width:120px; height:120px; border:1.5px solid #101828; border-radius:12px; padding:8px; }}
.qr img {{ width:100%; height:100%; display:block; }}
.a-head {{ font-family:{_DISPLAY}; font-weight:700; font-size:20px; line-height:1.12; }}
.a-url {{ font-family:{_MONO}; font-size:14px; font-weight:600; color:{th['ac_text']}; margin-top:8px; }}
.a-code {{ font-size:13px; color:#475467; margin-top:6px; }}
.a-code b {{ font-family:{_MONO}; color:{th['sec_text']}; background:{th['sec_wash']}; padding:2px 7px; border-radius:5px; }}
.fine {{ font-size:10.5px; color:#98A2B3; line-height:1.4; margin-top:14px; max-width:48ch; }}
.addr {{ flex:1; position:relative; padding:42px 40px; }}
.addr .note {{ font-size:10px; letter-spacing:.04em; text-transform:uppercase; color:#98A2B3; }}
.addr .blk {{ font-size:15px; line-height:1.5; margin-top:1.6in; }}
</style></head><body><div class="back">
  <div class="msg">
    <div class="eyebrow">Your Florence quote</div>
    <h2 class="org">{org_name.title()}</h2>
    <p class="recap">{recap}</p>
    <div class="specs">
      <div class="spec hl"><div class="sn">{fee}</div><div class="sl">per nurse / month</div></div>
      <div class="spec sec"><div class="sn">{rn_estimate} RNs</div><div class="sl">est. starting cohort</div></div>
      <div class="spec"><div class="sn">{account_mo}</div><div class="sl">est. monthly, full cohort</div></div>
    </div>
    <div class="act">
      <div class="qr">{qr_img}</div>
      <div>
        <div class="a-head">Scan to activate<br>your quote &amp; meet candidates</div>
        <div class="a-url">{signup_base.replace('https://','').replace('http://','')}</div>
        <div class="a-code">Activation code &nbsp;<b>{code}</b></div>
      </div>
    </div>
    <div class="fine">Estimate based on the prevailing registered-nurse wage in your market.
      Your exact monthly rate is confirmed at activation. Nurses commit to a two-year term,
      billed monthly. After two years they can stay on your staff, yours to keep.</div>
  </div>
  {addr_col}
</div></body></html>"""

    return {"front": front, "back": back}
