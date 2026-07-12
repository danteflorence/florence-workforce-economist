# Deploy & host the Florence Workforce Economist

This moves the internal economist **off Streamlit Community Cloud** onto a host you
control, so you can:

1. **Share a clean link with AMN / investors** — no Streamlit login, gated by
   Cloudflare Access (email magic-link, revocable).
2. **Stop losing mutable state on deploy** — a persistent disk keeps auth users,
   CRM overrides, the mail log, activations, and the activity log across redeploys.
3. **Expose pricing as an API** — `florence-pricing-api` is the shared brain a
   future customer-facing React product calls.

Everything here is already wired in the repo: `Dockerfile`, `docker-entrypoint.sh`,
`render.yaml`, `pricing_api.py`, `requirements-api.txt`, `scripts/smoke_check.py`.
**The steps below are the parts only you can do** (create accounts, set secrets,
point DNS, click deploy).

---

## What gets deployed

`render.yaml` is a Render **Blueprint**. The two services you need now:

| Service | What | Runtime | Notes |
|---|---|---|---|
| `florence-economist` | the internal Streamlit app | Docker + 1 GB disk | the tool we work in |
| `florence-pricing-api` | pricing engine as JSON API | Python | the React-product seam |

The Blueprint **also** contains 4 older services (public calculator, market-intel,
nurse portal, 2 surveillance crons). **You don't have to deploy those yet** — see
"Deploy a subset" below. Deploying all of them runs ~$42/mo; the two core services
are ~$14/mo.

---

## Part A — Render (the app + the API)

1. **Create a Render account** at render.com and connect your GitHub
   (`danteflorence/florence-workforce-economist`).
2. **New → Blueprint** → pick the repo → Render reads `render.yaml`.
   - **Deploy a subset (recommended first):** before applying, comment out the
     services you're not ready for (calculator / market-intel / nurses / crons) by
     prefixing their lines with `#`, leaving `florence-economist` and
     `florence-pricing-api`. (Or apply all and **Suspend** the extras in the dashboard.)
3. Click **Apply**. First build takes ~5–10 min (the Docker image installs the deps).
4. When it's live, note the two URLs Render assigns, e.g.
   `https://florence-economist.onrender.com` and
   `https://florence-pricing-api.onrender.com`.

> The economist runs as a **Docker** service so the entrypoint can seed read-only
> reference data onto the persistent disk on every boot while leaving your mutable
> runtime files untouched. You don't need Docker installed locally — Render builds it.

## Part B — Secrets (Render dashboard, never in git)

On the `florence-economist` service → **Environment**, set the values for the keys
declared as `sync: false` in `render.yaml`:

- `ANTHROPIC_API_KEY` — only if you use the AI Q&A / sales-brief features.
- `BLS_REGISTRATION_KEY` — only if you use live BLS pulls.
- Leave `FLORENCE_INTERNAL_AUTH=0` (Cloudflare Access will gate access — Part D).
  Set it to `1` instead if you'd rather use the app's own email-OTP / Google sign-in.

If you use in-app Google sign-in, also add a Streamlit `[auth]` secret per
`florence_auth.py` (otherwise it no-ops and the app runs open behind CF Access).

### Error monitoring (optional, 5 min)

Errors always append to `data/errors.log` on the persistent disk. To also get
alerts: create a free Sentry project (sentry.io → Create Project → Python),
copy its DSN, and set `SENTRY_DSN` on `florence-economist` and
`florence-pricing-api`. Nothing else to configure — `error_monitoring.py`
tags each event with the service name and sends no PII.

### Backups (local always; offsite optional, 10 min)

`docker-entrypoint.sh` snapshots all mutable state (leads, pipeline, contacts,
outcomes, auth) to `data/backups/` daily, keeping the last 14
(`BACKUP_KEEP`). That survives redeploys but not disk loss — for offsite
copies, create any S3-compatible bucket (AWS S3 or Cloudflare R2) plus an
access key, and set on `florence-economist`:

- `BACKUP_S3_BUCKET` (enables offsite), `BACKUP_S3_REGION`
- `BACKUP_S3_ENDPOINT` — only for non-AWS (e.g. `<account>.r2.cloudflarestorage.com`)
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`

Restore drill: download a `state-*.tar.gz`, `tar -xzf` it into `data/`, redeploy.

## Part C — Custom domain

1. On `florence-economist` → **Settings → Custom Domains** → add
   `economist.florenceedu.com`. Render shows a CNAME target.
2. In your DNS (Cloudflare — see Part D), add that **CNAME**, proxied (orange cloud).
3. Render issues TLS automatically once DNS resolves.

## Part D — Cloudflare Access (the clean-sharing unlock)

This is what fixes "share with AMN/investors without a Streamlit login."

1. Make sure `florenceedu.com` is on **Cloudflare** (free plan is fine).
2. **Zero Trust → Access → Applications → Add a self-hosted application**:
   - Application domain: `economist.florenceedu.com`
   - **Policies:**
     - *Staff* — Allow → emails ending in `@florenceedu.com`.
     - *Guests (AMN / investors)* — Allow → specific email addresses; login method
       **One-time PIN**. They enter their email, get a code, and they're in. No account.
3. Save. Now visiting the domain shows Cloudflare's email-code prompt, then proxies
   straight to the app. Revoke a guest anytime by removing their email.

> The **pricing API** is a backend the React app calls; leave it off CF Access. Lock
> it down later with an API key or a CF Access **service token**, and restrict
> browser origins via the `PRICING_API_CORS_ORIGINS` env var (comma-separated).

## Part E — Verify the deploy (the "did it actually work?" check)

From your laptop (stdlib only, no installs needed):

```bash
python3 scripts/smoke_check.py \
  --app-url https://economist.florenceedu.com \
  --api-url https://florence-pricing-api.onrender.com
```

- The **API** checks must say `SMOKE PASS` (health + a live `$/RN/mo` quote in range).
- The **app** check will warn `redirect … likely Cloudflare Access` — that's expected
  once CF Access is on; Render's own health check already proves the app booted.
- To check the app *through* CF Access, create a CF Access **service token** and run
  with `CF_ACCESS_CLIENT_ID=… CF_ACCESS_CLIENT_SECRET=… python3 scripts/smoke_check.py …`.

---

## What persists, what resets

| Data | Where | Survives redeploy? |
|---|---|---|
| Read-only reference (universe, recommendations, geo, contacts) | baked into the image, reseeded on boot | refreshed each deploy ✅ |
| Mutable runtime (auth users/sessions, CRM overrides, mail log, activations, activity log) | persistent disk at `/app/data` | **yes** ✅ |
| Secrets | Render env vars | yes ✅ |

> **Backups:** snapshot the Render disk periodically, or — better, when you're ready —
> move the mutable CSV stores to **Render Postgres** (managed, backed up). That's the
> real long-term hardening; the disk is the no-refactor bridge that stops the
> deploy-time data loss today.

## Cost (ballpark)

- `florence-economist` (Docker, Starter) + 1 GB disk ≈ **$7.25/mo**
- `florence-pricing-api` (Starter, or **Free** for dev) ≈ **$7/mo** (or $0)
- Cloudflare Access — **free** up to 50 users · Custom domain — **free**
- **Core total ≈ $14/mo.** The 4 optional services add ~$28/mo if you deploy them.

---

## Direct mail — Lob postcards (`florence_postcard.py` / `lob_send.py`)

Personalized, market-priced postcards for the non-hospital universe (home health,
surgery centers, skilled nursing, dialysis, hospice), mailed via Lob. Files:
`florence_postcard.py` (themed creative + QR), `lob_send.py` (gated batch sender),
`lob_webhook.py` (delivery tracking), `postcard_copy.json` (copy source of truth),
`assets/` (RN photo + white wordmark). The existing in-app `lob_mailer.py` is
untouched — this is the upgraded creative + batch path alongside it.

**One-time setup**
- Host `assets/nurse-rn.png` + `assets/florence-white.svg` on a public HTTPS URL
  (CDN / S3); Lob's renderer fetches them by URL.
- Env (Render dashboard / `.env`, never in git):
  - `LOB_API_KEY` — `test_…` first (renders a real preview PDF, no mail, no
    charge); swap to `live_…` only for an approved segment.
  - `FLORENCE_SIGNUP_URL=https://florenceedu.com/activate` (the QR target)
  - `FLORENCE_NURSE_IMG`, `FLORENCE_LOGO_WHITE` — the two hosted asset URLs
  - `LOB_WEBHOOK_SECRET` — only if you deploy the tracking webhook

**Sending is always gated**
1. Dry-run the whole segment: `lob_send.run_segment(rows, live=False)` — builds
   every payload, mails nothing, charges nothing. Eyeball the count.
2. A human approves the segment.
3. Flip `live=True` to mail. Idempotency keys mean a retried batch never
   double-mails a facility.

**Tracking webhook (optional)** — `lob_webhook.py` is a small Flask receiver
(`pip install -r requirements-webhook.txt`). Deploy as its own service, set
`LOB_WEBHOOK_SECRET`, register the URL + events in the Lob dashboard, and wire
the `persist()` TODO to your datastore. Not in the Blueprint yet — it needs that
datastore wire first.

**Compliance** — copy is value + activation only; no FICA / IRS / visa / tax
language, verified on the rendered HTML.

## Roadmap (after this lands)

- **Phase 2 — customer-facing product in React.** Build the calculator / pitch /
  activation surfaces in your existing Vite/React stack (Pathway, Academy), calling
  `florence-pricing-api`. The internal economist stays Streamlit. The API is ready —
  point a React dev server at the local API (`uvicorn pricing_api:app --port 8000`)
  and build against `POST /price` (interactive docs at `/docs`).
- **Postgres** for mutable state (replaces the disk-backed CSVs).
- **Alternative hosts:** the `Dockerfile` is portable — the same image runs on
  Railway, Fly.io, or any VM if you ever outgrow Render.
