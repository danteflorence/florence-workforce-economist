# Florence Hospital Booklet — Engineering Handoff

> **Landed in the platform (2026-06-15)** as the first family of the
> [FlorenceRN Capacity Outreach Engine](../README.md). Changes applied on intake:
> - **Wired to real data** — `hospital_universe_audience.py` aggregates the full
>   `data/hospital_universe.csv` by health system and prices each via `pricing_engine.price()`
>   (`list_rate` + `effective_cost` are engine-derived, never invented). The shipped 40-system
>   `renderer/hospital-systems.js` is now just the preview subset.
> - **Per-system tracked QR + UTM is the default** — `campaign_links.py` builds
>   `go.florencern.com/...?utm_*&frn_campaign_id&frn_account_id` (no PII); carried as
>   `landing_url`/`qr_url` merge vars in the audience CSV + Lob mapping + template.
> - **Lob merge-mapping bug fixed** — `lob_booklet.upload_payload()` now maps the hospital
>   fields (it shipped with stale `university`/`logo_url` mappings).
> - **Mail-safe copy** — "after eligible offsets" → "modeled for your market" (no FICA/visa/tax/immigration).
> - **Offline check:** `python3 verify_capacity_outreach.py` (17/17, no network / no Lob key).
>
> New files: `campaign_links.py`, `hospital_universe_audience.py`, `verify_capacity_outreach.py`.

Generate a personalized **8-page, 9×6″ booklet** for any U.S. health system and
deliver it two ways: **mailed through Lob** (Campaigns API) or **print-ready PDF**
(vendor / proofs / low-volume). One design, two outputs.

The booklet is the premium, short-list companion to the flat 6×11 hospital
mailer. It carries the full pitch-deck story — capacity, near-zero risk,
effective cost, activation waves, the 30-day sprint ask — **mail-safe**: no FICA,
visa, tax, or immigration language anywhere (same rule as every Florence
mailpiece).

---

## What's in this folder

| File | What it is |
|---|---|
| `renderer/` | The design itself — `hospital-booklet.js` (8-page renderer), `hospital-booklet.css`, `booklet-base.css` (tokens + page frame), `hospital-systems.js` (40-system preview subset), `assets/` (logos). **This is the source of truth for the layout.** |
| `build_hospital_booklet.html` | Open in a browser. Preview any system, **Download Lob template** (static HTML + Handlebars merge vars), or **Print / Save PDF** (real values, 9×6). |
| `hospital_audience.py` | Universe → Lob audience CSV. Pre-computes every merge var (short name, formatted `$`, etc.). |
| `lob_booklet.py` | Lob **Campaigns API** sender: template → campaign → creative → upload → execute. `dry_run=True` builds without sending. |
| `render_pdf.py` | Playwright batch: fills the template per system and prints one 9×6 PDF each. |
| `requirements.txt`, `.env.example` | Deps + config. |

---

## The merge variables (the contract)

The template exposes six per-system merge variables. `hospital_audience.py`
resolves all of them into the CSV; nothing is computed at render time (Lob can't
run JS).

| Variable | Example | Source field |
|---|---|---|
| `{{system_name}}` | Cleveland Clinic | `name` |
| `{{short_name}}` | Cleveland | derived from `name` |
| `{{effective_cost}}` | $542 | `effectiveLow` |
| `{{list_rate}}` | $1,079 | `medianFee` |
| `{{rn_need}}` | 41,294 | `totalRnNeed` |
| `{{n_facilities}}` | 158 | `nFacilities` |

Plus the standard Lob address columns: `contact_name, address_line1,
address_line2, address_city, address_state, address_zip`.

---

## Path A — Mail through Lob (Campaigns API)

> ⚠️ Lob **booklets are Enterprise Edition** with a **5,000-piece minimum** per
> campaign, submitted as a static HTML template + audience CSV. Confirm the
> booklet creative spec (`resource_type`, page count, 9×6 size) with your Lob
> account team — those fields are marked `# CONFIRM` in `lob_booklet.py`.

```bash
pip install -r requirements.txt
export LOB_API_KEY="test_xxx"     # test key first
```

```python
# 1. Template: open build_hospital_booklet.html, set Asset base, pick theme,
#    "Download Lob template" → florence-hospital-booklet-teal.html
# 2. Audience CSV (economics from hospital_universe, addresses from CRM):
from hospital_audience import build_audience_csv
build_audience_csv(systems, "hospital_run.csv")
# 3. Build the campaign (dry run — nothing mails):
from lob_booklet import run_booklet_campaign
html = open("florence-hospital-booklet-teal.html", encoding="utf-8").read()
out = run_booklet_campaign(template_html=html, csv_path="hospital_run.csv",
                           campaign_name="Florence Hospital Booklet — Tier 1",
                           label="teal", dry_run=True)
# 4. Review preview PDFs in the Lob dashboard, then:
from lob_booklet import send_campaign
send_campaign(out["campaign_id"])
```

## Path B — Print-ready PDF

For tier-1 short lists (below Lob's booklet minimum), a vendor, or proofs:

- **Ad-hoc / one system:** `build_hospital_booklet.html` → **Print / Save PDF**
  (opens the filled booklet at 9×6; Save as PDF).
- **Batch:** `render_pdf.py` fills the downloaded template per CSV row and prints
  one 9×6 PDF per system:

```bash
pip install playwright && playwright install chromium
python render_pdf.py florence-hospital-booklet-teal.html hospital_run.csv
# → ./pdfs/<system>.pdf
```

---

## Address handling & compliance

- The back cover leaves the **address zone blank** — Lob prints the recipient
  address, the Culver City return address, and the barcode there. (For PDF/vendor
  sends, add your own addressing/postage step.)
- **Mail-safe copy:** capacity / effective cost / near-zero risk only. **No**
  FICA, visa, tax, or immigration language. The full payroll-tax / F-1 economics
  stay in the in-person deck and the design-sprint conversation — never on a
  mailpiece.

See `PROJECT_PLAN.md` for the phased build plan and tickets.
