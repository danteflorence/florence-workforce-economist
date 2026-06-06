# Florence pricing calculator (web)

Customer-facing **permanent-RN pricing calculator** — a Vite + React + TypeScript
app that calls the Florence pricing API (`florence-pricing-api`, see `../pricing_api.py`)
and shows the "Today vs With Florence" comparison.

This is the Phase-2 product surface from `../DEPLOY.md`: customers/investors get a
polished, branded calculator; the internal economist stays in Streamlit.

> **Compliance:** this is a public surface. It shows only customer-safe numbers
> (Florence fee, agency premium, savings). It must never display tax/FICA/visa
> mechanics — those fields aren't even modeled in `src/api.ts`.

## Run it locally

```bash
# 1) start the pricing API (from the repo root)
uvicorn pricing_api:app --port 8000

# 2) start the web app (from this web/ folder)
cp .env.example .env          # VITE_API_URL=http://localhost:8000
npm install
npm run dev                   # http://localhost:5179
```

## Build

```bash
npm run build                 # type-checks (tsc --noEmit) then bundles to dist/
```

## Deploy (Render static site)

Point a Render Static Site at this folder: root `web`, build `npm run build`,
publish `web/dist`, and set `VITE_API_URL` to the deployed pricing-API URL.
See `../DEPLOY.md`.
