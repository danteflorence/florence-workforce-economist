"""
Account dossier — a one-page, on-brand HTML handoff/leave-behind per system.

Combines the hero numbers, contact + owner + stage, the call opening + top
objections, the outreach intro, and the recent activity timeline into a single
self-contained HTML file that prints cleanly. Internal rep doc — still
compliance-clean (no FICA/visa/tax). Florence editorial palette.
"""
from __future__ import annotations

import html as _html


def _esc(s) -> str:
    return _html.escape(str(s if s is not None else ""))


_CSS = """
*{box-sizing:border-box}
body{margin:0;font-family:'Inter',Helvetica,Arial,sans-serif;color:#101828;background:#fff;}
.wrap{max-width:820px;margin:0 auto;padding:32px 36px;}
.wm{font-family:'Playfair Display',Georgia,serif;font-weight:700;font-size:22px;color:#067F7B;}
.rule{height:3px;background:#0ABAB5;margin:8px 0 20px;}
h1{font-family:'Playfair Display',Georgia,serif;font-weight:500;font-size:28px;margin:0 0 4px;}
.meta{color:#475467;font-size:13px;margin-bottom:18px;}
.chip{display:inline-block;padding:2px 10px;border-radius:999px;font-size:11px;font-weight:600;
      background:#E6F8F7;color:#067F7B;margin-right:6px;}
.chip.pur{background:#F4F0FB;color:#5B2DA8;}
.kpis{display:flex;gap:14px;margin:14px 0 22px;flex-wrap:wrap;}
.kpi{flex:1;min-width:130px;border:1px solid #E4E7EC;border-radius:10px;padding:12px 14px;}
.kpi .l{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:#475467;}
.kpi .v{font-family:'Playfair Display',Georgia,serif;font-size:22px;color:#101828;margin-top:3px;}
.kpi .v.hero{color:#067F7B;font-weight:700;}
h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#5B2DA8;margin:22px 0 8px;}
p{margin:0 0 10px;line-height:1.5;font-size:13px;}
.box{border-left:3px solid #0ABAB5;background:#F7FBFB;padding:10px 14px;border-radius:0 8px 8px 0;font-size:13px;white-space:pre-wrap;}
.obj{font-size:12.5px;margin:0 0 8px;} .obj b{color:#101828;}
.tl{font-size:12.5px;border-left:2px solid #E4E7EC;padding:2px 0 8px 12px;margin:0 0 2px;}
.tl .t{font-family:'JetBrains Mono',monospace;font-size:11px;color:#475467;}
.mono{font-family:'JetBrains Mono',monospace;}
.foot{color:#98A2B3;font-size:11px;margin-top:24px;border-top:1px solid #E4E7EC;padding-top:10px;}
@media print{.wrap{padding:0}.kpi{break-inside:avoid}}
"""

_FONTS = ('<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:wght@500;700&'
          'family=Inter:wght@400;600;700&family=JetBrains+Mono:wght@500&display=swap" rel="stylesheet">')


def render_html(*, system_name: str, metrics: dict, contact: dict, script: dict,
                email_intro: str = "", timeline: list = None, owner: str = "",
                stage: str = "") -> str:
    n = script.get("numbers", {})
    timeline = timeline or []
    who = " · ".join(x for x in (contact.get("contact_name"), contact.get("title")) if x) or "No named contact"
    chips = ""
    if stage:
        chips += f"<span class='chip'>{_esc(stage)}</span>"
    if owner:
        chips += f"<span class='chip pur'>Owner: {_esc(owner)}</span>"

    kpis = "".join(
        f"<div class='kpi'><div class='l'>{lbl}</div><div class='v{cls}'>{_esc(val)}</div></div>"
        for lbl, val, cls in [
            ("Est. savings / yr", n.get("hero_annual", "—"), " hero"),
            ("Per nurse / mo", n.get("per_nurse_mo", "—"), ""),
            ("24-mo impact", n.get("term_24mo", "—"), ""),
            ("RN need", f"{int(metrics.get('rn_need') or 0):,}", ""),
            ("Facilities", f"{int(metrics.get('n_facilities') or 0):,}", ""),
        ])

    objs = "".join(f"<p class='obj'><b>{_esc(q)}</b><br>{_esc(a)}</p>"
                   for q, a in script.get("objections", [])[:3])
    tl = "".join(
        f"<div class='tl'><span class='t'>{_esc(str(e.get('ts',''))[:16].replace('T',' '))}</span> · "
        f"<b>{_esc(e.get('kind',''))}</b> — {_esc(e.get('detail',''))}</div>"
        for e in timeline[:10]) or "<p class='meta'>No activity logged yet.</p>"

    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>{_esc(system_name)} — Florence dossier</title>"
        f"{_FONTS}<style>{_CSS}</style></head><body><div class='wrap'>"
        f"<div class='wm'>Florence</div><div class='rule'></div>"
        f"<h1>{_esc(system_name)}</h1><div class='meta'>{chips}</div>"
        f"<div class='kpis'>{kpis}</div>"
        f"<h2>Contact</h2><p>{_esc(who)}<br><span class='mono'>Tel {_esc(contact.get('phone') or '—')} · "
        f"Email {_esc(contact.get('email') or '—')}</span><br>{_esc(contact.get('address1') or '')} "
        f"{_esc(contact.get('city') or '')} {_esc(contact.get('state') or '')} {_esc(contact.get('zip') or '')}</p>"
        f"<h2>Call opening</h2><div class='box'>{_esc(script.get('opening',''))}</div>"
        f"<h2>Top objections</h2>{objs}"
        + (f"<h2>Outreach intro</h2><div class='box'>{_esc(email_intro)}</div>" if email_intro else "")
        + f"<h2>Recent activity</h2>{tl}"
        f"<div class='foot'>Florence Workforce Economist — internal account dossier. Figures are "
        f"estimates from public CMS + wage data; confirm before contracting.</div>"
        f"</div></body></html>"
    )
