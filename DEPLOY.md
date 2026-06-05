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

## Roadmap (after this lands)

- **Phase 2 — customer-facing product in React.** Build the calculator / pitch /
  activation surfaces in your existing Vite/React stack (Pathway, Academy), calling
  `florence-pricing-api`. The internal economist stays Streamlit. The API is ready —
  point a React dev server at the local API (`uvicorn pricing_api:app --port 8000`)
  and build against `POST /price` (interactive docs at `/docs`).
- **Postgres** for mutable state (replaces the disk-backed CSVs).
- **Alternative hosts:** the `Dockerfile` is portable — the same image runs on
  Railway, Fly.io, or any VM if you ever outgrow Render.
