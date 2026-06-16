# Florence Client Deck — package & file inventory

A data-driven HTML pitch-deck generator for US health systems. One template,
~600 systems, live tweaks. This README is the map.

## File inventory

```
Florence Client Deck - TEMPLATE.html   ← the deck (open this)
deck-stage.js                          ← slide-stage web component (scaling, nav, rail, print)
tweaks-panel.jsx                       ← Tweaks panel UI primitives

template/
  presets.js          ← featured hand-tuned configs (Kaiser, Sutter) + global
                         constants (CONTACT, SIGNUP_URL, NURSES_DEFAULT) +
                         configFromUniverse() + active-config resolver
  render.js           ← the 6–8 slide builder (all slides, channel/pricing/
                         profiles logic, speaker notes, live re-render)
  universe.js         ← AUTO-GENERATED: every system + per-facility pricing
  logos.js            ← AUTO-GENERATED: system_id → { domain, file }
  build_deck_data.py  ← regenerates universe.js + logos.js from the CSVs

assets/
  colors_and_type.css ← Florence design tokens (colors, type scale)
  logos/              ← florence-color.svg, florence-white.svg
  partners/           ← amn-logo.jpeg, kp-logo.png, …
  systems/            ← curated per-system logos you drop in (see below)

data/
  hospital_universe.csv   ← pricing/universe source (CMS HCRIS + BLS OEWS)
  system_directory.csv    ← logo/domain source
```

## Load order (in the HTML)
```
universe.js → logos.js → presets.js → render.js → deck-stage.js
```
`render.js` fills the empty `<deck-stage>` and writes speaker notes; then
`deck-stage.js` upgrades the populated element. The Tweaks panel mounts
separately (React/Babel) and calls `window.FLORENCE_RENDER()` to re-render live.

## Pick a system
- URL: `…/TEMPLATE.html?client=<system_id>` (e.g. `?client=hca`)
- or the **Client** dropdown in the Tweaks panel.
Defaults to `kaiser`. Selection persists per browser via `localStorage`.

## Regenerate the data (after a CSV refresh)
```
python template/build_deck_data.py            # reads data/, writes template/
```
Keeps the pricing constants in one place (top of the script) — must match
`playbook/04_pricing_methodology.md`.

## Add a real system logo
1. Drop the file: `assets/systems/<system_id>.svg` (or `.png`, ≥200px tall).
2. Register it in **two** places so it survives a data rebuild:
   - `template/logos.js` → set `file` for that system, AND
   - `template/build_deck_data.py` → add to `CURATED_LOGOS`.
Deck cover uses the curated file; dropdown uses the domain favicon as a
browsing icon (never on the cover — too low-res / not export-safe).

## Promote a system to a hand-tuned preset
Copy the object printed by `configFromUniverse('<id>')`, paste it into
`FLORENCE_PRESETS` in `presets.js`, hand-tune (flat price, partner channel,
custom waves, logo), and add it to `FLORENCE_FEATURED` so it overrides the
auto-generated version and pins to the top of the dropdown. Kaiser and Sutter
are the worked examples.

## Global knobs (top of presets.js)
- `FLORENCE_CONTACT` — CTA email
- `FLORENCE_SIGNUP_URL` / `FLORENCE_SIGNUP_LABEL` — CTA button (UTM auto-appended)
- `FLORENCE_NURSES_DEFAULT` — degrees, origins, sample profile cards
- pricing constants live in `build_deck_data.py` (`MONTHLY_HOURS`, `FICA_RATE`,
  `OFFSET_TARGET`, `FEE_MIN/MAX`, `TERM_MONTHS`)

See `PROJECT_PLAN.md` (repo root) for the platform-integration milestones.
