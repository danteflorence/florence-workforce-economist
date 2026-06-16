# FlorenceRN Capacity Outreach Engine

The personalized, physical+digital **employer outbound layer** for FlorenceRN. It turns
demand + economics into a personalized artifact (booklet / PDF / landing page / email),
puts a **per-system tracked QR + UTM** on it, and feeds engagement back into the funnel.

> **The loop:** Demand Radar finds the jobs → Workforce Economist prices the opportunity →
> **Capacity Outreach** generates the personalized mailer/PDF/landing page → tracked QR/UTM
> captures interest → Growth follows up → the employer **claims roles** or books a design
> sprint → the Production Ledger tracks conversion.

This is infrastructure, not a single mailpiece: one renderer + economic model per setting,
two delivery paths (Lob Campaigns API for ≥5,000-piece runs, print-ready 9×6 PDF for short
lists/vendors), human-approval before anything mails.

## Mailer families

| Family | Folder | Audience | Economic story |
|---|---|---|---|
| **Health-System Capacity Booklet** | `health-system-booklet/` ✅ shipped | HCA, Tenet, Kaiser, CommonSpirit, Sutter, Providence, Advocate… | Convert premium/agency labor spread into permanent RN capacity |
| Home Health Capacity Mailer | `home-health-mailer/` (staged) | Home health agencies | Stop turning away referrals / delaying starts of care for lack of RNs |
| SNF / Dialysis / Hospice / ASC / Clinic | `*-mailer/` (staged) | Post-acute & outpatient operators | Census, chair/throughput utilization, schedule reliability, access |

The same renderer architecture serves all families — only the **template copy + the
setting-specific variable model** change (see each family's README). The health-system
booklet is the first family and the reference implementation.

## Shipped now (health-system-booklet)
- Real data: `hospital_universe_audience.py` aggregates `../../data/hospital_universe.csv`
  by health system (nFacilities, totalRnNeed) and prices each via the existing
  `pricing_engine.price()` → `list_rate` (florence monthly fee) + `effective_cost`
  (FICA-adjusted effective cost). **Pricing is engine-derived — never invented.**
- Per-system **tracked QR + UTM is the default** (`campaign_links.py`): every mailpiece
  gets `go.florencern.com/<segment>/<slug>/<path>?utm_*&frn_campaign_id&frn_account_id`
  (no PII). Carried as `landing_url`/`qr_url` merge vars in the audience CSV + Lob mapping.
- Lob merge mapping **fixed** to the hospital contract (the package shipped with stale
  university mappings — `lob_booklet.upload_payload`).
- **Mail-safe copy:** no FICA / visa / tax / immigration language; "after eligible offsets"
  → "modeled for your market" (the offset explanation lives on the landing page / sales call).
- Offline contract check: `python3 health-system-booklet/verify_capacity_outreach.py` (17/17,
  no network/no Lob key).

## Staged (the broader roadmap, from operator feedback)
1. Home-health + SNF/dialysis/hospice/ASC setting-specific templates + variable models,
   driven by the **Long-Tail Demand Radar** (claimed agencies / market×role demand) in ATS Connect.
2. Personalized **landing-page generator** per mailer (the QR/UTM destination).
3. Lob **native trackable QR** (`qr_code` → `landing_url`) + webhook tracking → Production Ledger.
4. A **Capacity Campaign Builder** UI (Streamlit): pick audience → preview → dry-run Lob /
   export PDF → human-approve → send → track delivered→scanned→booked→claimed→start.
5. "Claim this role / request licensed RN packets" CTA for long-tail employers (lighter than a design sprint).

## User-owned / before a live send
- `LOB_API_KEY` (test first); Lob **Enterprise booklet** spec confirm (resource_type, 9×6,
  page count, 5,000-piece minimum) — marked `# CONFIRM` in `lob_booklet.py`.
- Public HTTPS **asset host** for `renderer/assets/florence-*.svg` (`FLORENCE_ASSET_BASE`).
- **CRM HQ mailing addresses** joined to each system (not in the universe).
- `FLORENCE_LINK_BASE` (default `https://go.florencern.com`) + the landing-page routes.
- Human approves every send; dry-run the whole list first.
