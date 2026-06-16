# Project Plan — Hospital Booklet in the Platform

Goal: let an operator pick a health system in the platform, preview the
personalized 8-page booklet, and either **queue it to Lob** or **export a
print-ready PDF** — with a human approving before anything mails.

Estimated: ~2–3 engineer-weeks for a first working version, depending on how
much of the existing postcard/Lob plumbing you reuse.

---

## Phase 0 — Foundations (½ week)

- [ ] Stand up the asset host (public HTTPS): `assets/florence-color.svg`,
      `assets/florence-white.svg`. Record the base URL.
- [ ] Load the data source: the full `hospital_universe` (614 systems; CMS HCRIS
      2023 + BLS OEWS) with `nFacilities, totalRnNeed, medianFee, effectiveLow`.
      The repo ships a 40-system preview subset; wire the full set.
- [ ] Join HQ mailing addresses (CRM / facility list) to each system id.
- [ ] Add `LOB_API_KEY` (test) + asset base to secrets/env.

## Phase 1 — Render in the platform (½–1 week)

- [ ] Embed the renderer (`renderer/*.js` + `*.css`) behind a “Booklet preview”
      view. It already exposes `renderHospitalPage(pageId, system, ctx)` and
      `HOSPITAL_BOOKLET_PAGES`.
- [ ] System picker → live 8-page preview with the teal/purple toggle.
- [ ] Verify every page reflows for the largest values (HCA: 41,294 RN need,
      158 facilities) and the longest names. No overflow.

## Phase 2 — PDF export (½ week)

- [ ] Server route that fills the template per system and prints 9×6 via
      headless Chromium (`render_pdf.py` is the reference; port to your stack).
- [ ] “Export PDF” button in the preview view (single system).
- [ ] Batch export for a selected list → zip of PDFs.

## Phase 3 — Lob campaign (1 week)

- [ ] Generate the static Lob template from the renderer (the
      `HB_TEMPLATE_SYSTEM` token system → Handlebars `{{vars}}`; see
      `build_hospital_booklet.html`). Store/version it.
- [ ] Build the audience CSV server-side (`hospital_audience.py` logic):
      address columns + the six merge vars, all pre-formatted.
- [ ] Wire the Campaigns API flow (`lob_booklet.py`): template → campaign →
      creative → upload → **dry run**. Surface campaign/creative/upload IDs.
- [ ] **CONFIRM with Lob:** booklet `resource_type`, page count, 9×6 size,
      Enterprise access, 5,000-piece minimum. Gate the UI on these.
- [ ] Human-approval step before `send_campaign()`. No auto-send.

## Phase 4 — Tracking & polish (½ week)

- [ ] Webhook receiver for Lob tracking events (reuse the postcard handoff’s
      `lob_webhook.py`); map events back to system id via `metadata`.
- [ ] Per-system status in the platform (queued → in transit → delivered).
- [ ] QA: 10-system test print + one Lob test-key campaign end to end.

---

## Decisions to make

| Decision | Options | Default |
|---|---|---|
| Volume per send | Tier-1 short list (PDF/vendor) vs ≥5,000 (Lob booklet) | Both paths; pick per campaign |
| QR target | Generic `florenceedu.com/sprint` (baked) vs per-system tracked (Lob native `qr_code`) | Generic now; native later |
| Theme | Teal default vs purple | Teal |
| Addressing for PDF path | In-house vs vendor mail house | TBD |

## Guardrails (non-negotiable)

- **Human approves every send.** Dry-run the whole list; flip live only on approval.
- **Mail-safe copy only** — no FICA / visa / tax / immigration language.
- **Idempotency** on any Lob call so retries never double-mail.

## What to reuse from existing handoffs

- `integration/` (postcard) — Lob auth pattern, webhook receiver, address verification.
- `lob-booklet/` (university) — the Campaigns API sender this folder’s `lob_booklet.py` is based on.
