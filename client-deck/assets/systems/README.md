# Curated system logos

Drop a real logo here to use it on a system's deck (cover + section headers).

## How to add one
1. Save the logo as `assets/systems/<system_id>.svg` (or `.png`).
   - `<system_id>` is the Florence id, e.g. `hca`, `sutter_health`, `providence`.
   - Prefer SVG or a transparent PNG ≥ 200px tall.
2. Open `template/logos.js` and set the `file` for that system:
   ```js
   hca: { domain: "hcahealthcare.com", file: "assets/systems/hca.svg" },
   ```

## Resolution order on the deck
1. **Curated file** (this folder) — export-safe, used on the cover.
2. **Text wordmark** — clean fallback when no file is set.

Favicons (by domain, via Google s2) are used **only** as small icons in the
Client dropdown for quick recognition while browsing — never on the cover,
because they're too low-res for an exec deck and won't survive PDF/PPTX export.

## Sourcing tips
- Use the system's official brand/press-kit logo where possible.
- Wikipedia/Wikimedia often has clean SVG logos.
- A customer's own logo on a proposal to that customer is standard practice;
  quality is the only real concern — keep the systems you actively pitch on
  curated files here.
