/* =====================================================================
   Florence Client Deck — CONFIG PRESETS
   ---------------------------------------------------------------------
   This is the "merge-field sheet" for the template. Each preset is one
   client. To spin up a new client deck, copy a preset, paste the values
   from the workforce-economist platform, set `channel`, and you're done.

   THREE FLEX AXES (everything else is the fixed Florence chassis):
     1. channel ............ "partner" (AMN-sponsored) | "direct" (Florence-direct)
     2. pricing.mode ....... "flat"  (one price, e.g. Kaiser $2,000/RN/mo)
                             "market" (per-hospital table, national clients)
     3. integration ........ shown ONLY in direct mode (ATS + tracked UTM links)

   Pick the active client with ?client=kaiser in the URL, or the Tweaks
   panel's client switcher.
   ===================================================================== */

window.FLORENCE_PRESETS = {

  /* ===================================================================
     KAISER PERMANENTE — partner channel, flat pricing
     The reference deck. AMN-sponsored. Flat $2,000/RN/mo.
     =================================================================== */
  kaiser: {
    id: "kaiser",
    displayName: "Kaiser Permanente",
    shortName: "Kaiser",
    logo: "assets/partners/kp-logo.png",
    accent: "#006BA6",                 // KP blue — drives the "Employs" role label
    meta: { nFacilities: 41, states: ["CA", "HI", "OR", "TX", "WA"], totalRnNeed: 12404 },
    date: "June 2026",

    channel: "partner",
    partner: {
      name: "AMN",
      logo: "assets/partners/amn-logo.jpeg",
      role: "Leads the Kaiser relationship, coordinates workflow, manages the commercial structure.",
      footerLine: "AMN-sponsored program",
    },

    // Phase I volume + how it activates in gated waves
    volume: {
      total: 200,
      waves: [
        { label: "Wave 1", n: 50,  purpose: "First slate, first interviews, full process validation — quality, conversion, onboarding, and start timing proven at meaningful scale.", gate: "Gate: process validated & manager acceptance", final: false },
        { label: "Wave 2", n: 150, purpose: "Scale once hiring, onboarding, and pathway timing are validated — completing the 200-RN Phase I and feeding the Phase II expansion decision.", gate: "Gate: expansion decision — Phase II review", final: true },
      ],
    },

    pricing: {
      mode: "flat",
      feePerRnMonth: 2000,
      // effective range = fee minus eligible payroll-tax (FICA) offset
      effectiveLow: 1100,
      effectiveHigh: 1200,
      taxOffsetLow: 800,
      taxOffsetHigh: 900,
      // illustrative hourly view (slide 4)
      illustrativePayRate: 70,
      illustrativeTaxPerHour: 5.36,
      illustrativeTaxPerMonth: 835,
      // program totals
      programGross: "$9.6M",
      termMonths: 24,
    },

    sprint: [
      { wk: "Week 1", t: "Kaiser selects facilities, roles, criteria, and start windows." },
      { wk: "Week 2", t: "Onboarding & credentialing gates mapped into the AMN-led workflow." },
      { wk: "Week 3", t: "First Wave-1 candidate slate — real people, readiness scores, start windows." },
      { wk: "Week 4", t: "Metrics, commercial structure, and a clean go / no-go decision." },
    ],

    askHeadline: "Approve a 30-day design sprint to finalize the 200-RN Phase I.",
    deRisk: "Near-fully de-risked for Kaiser: no upfront fee, billing only after a nurse starts, billing stops the moment one leaves — and every hire clears Kaiser's own clinical, credentialing, and onboarding gates.",

    source: "tool.nashp.org",
  },

  /* ===================================================================
     SUTTER HEALTH — direct channel, per-market pricing
     Florence-direct (no AMN). National-style multi-market pricing pulled
     from the workforce-economist platform (real per-hospital rows from
     the Sutter exec-summary export). Direct mode unlocks ATS + UTM.
     =================================================================== */
  sutter: {
    id: "sutter",
    displayName: "Sutter Health",
    shortName: "Sutter",
    logo: null,                        // no logo asset → render a text wordmark
    accent: "#1E6091",                 // Sutter blue
    meta: { nFacilities: 14, states: ["CA"], totalRnNeed: 2750 },
    date: "June 2026",

    channel: "direct",
    direct: {
      footerLine: "A Florence program",
      // Integration is the direct-only capability partner deals don't have
      integration: {
        ats: "Workday / Taleo",
        headline: "Florence plugs directly into your ATS.",
        points: [
          { t: "Native ATS integration", s: "Candidates flow into Workday / Taleo as Florence-sourced reqs — no parallel system, no re-keying." },
          { t: "Tracked candidate links", s: "Every slate ships with UTM-tagged links so your team attributes every Florence hire inside your own funnel." },
          { t: "One source of truth", s: "Pipeline, starts, and conversion reconcile against your ATS — not a Florence spreadsheet." },
        ],
      },
    },

    volume: {
      total: 250,
      waves: [
        { label: "Wave 1", n: 50,  purpose: "First slate across the two highest-need facilities — full process validation, manager acceptance, ATS integration proven live.", gate: "Gate: process validated & ATS live", final: false },
        { label: "Wave 2", n: 200, purpose: "Scale across the system once hiring, onboarding, and pathway timing are validated — completing the 250-RN Phase I.", gate: "Gate: expansion decision — Phase II review", final: true },
      ],
    },

    pricing: {
      mode: "market",
      // Median figures for the hero / effective-cost slide
      feePerRnMonth: 1655,
      effectiveLow: 800,
      effectiveHigh: 900,
      taxOffsetLow: 800,
      taxOffsetHigh: 900,
      illustrativePayRate: 62,
      illustrativeTaxPerHour: 4.74,
      illustrativeTaxPerMonth: 828,
      programGross: "$4.1M",
      termMonths: 24,
      // Per-hospital rows — locally calibrated, from the economist platform.
      // effective = fee minus eligible payroll-tax offset.
      markets: [
        { name: "Sutter Medical Center", location: "Sacramento, CA", rnNeed: 901, feePerRn: 1753, effectivePerRn: 877 },
        { name: "Sutter Roseville",       location: "Roseville, CA",  rnNeed: 711, feePerRn: 1753, effectivePerRn: 877 },
        { name: "Sutter Santa Rosa",      location: "Santa Rosa, CA", rnNeed: 207, feePerRn: 1574, effectivePerRn: 787 },
        { name: "Sutter Delta",           location: "Antioch, CA",    rnNeed: 146, feePerRn: 1884, effectivePerRn: 942 },
        { name: "Sutter Davis",           location: "Davis, CA",      rnNeed: 111, feePerRn: 1753, effectivePerRn: 877 },
        { name: "Sutter Solano",          location: "Vallejo, CA",    rnNeed: 123, feePerRn: 1574, effectivePerRn: 787 },
      ],
    },

    sprint: [
      { wk: "Week 1", t: "Sutter selects facilities, roles, criteria, and start windows." },
      { wk: "Week 2", t: "ATS integration stood up; onboarding & credentialing gates mapped to Florence workflow." },
      { wk: "Week 3", t: "First Wave-1 candidate slate — real people, readiness scores, tracked links live in your ATS." },
      { wk: "Week 4", t: "Metrics, commercial structure, and a clean go / no-go decision." },
    ],

    askHeadline: "Approve a 30-day design sprint to finalize the 250-RN Phase I.",
    deRisk: "Near-fully de-risked for Sutter: no upfront fee, billing only after a nurse starts, billing stops the moment one leaves — and every hire clears Sutter's own clinical, credentialing, and onboarding gates.",

    source: "tool.nashp.org · CMS HCRIS 2023 · BLS OEWS",
  },

};

/* ---------------------------------------------------------------------
   FEATURED OVERRIDES — universe ids that have a hand-tuned preset.
   These take precedence over the auto-generated universe config so the
   showcase decks (Kaiser flat $2,000 / Sutter) stay exactly as authored.
   --------------------------------------------------------------------- */
/* Global CTA contact + default nurse pipeline (shared across every client) */
window.FLORENCE_CONTACT = "dante@florenceedu.com";
window.FLORENCE_SIGNUP_URL = "https://www.florenceedu.com/providers";
window.FLORENCE_SIGNUP_LABEL = "Start your Phase I";
window.FLORENCE_NURSES_DEFAULT = {
  credentials: "BSN-prepared, Master\u2019s-seeking",
  degrees: ["MSN", "MBA", "MHA"],
  origins: ["United Kingdom", "Philippines", "Kenya", "Malaysia", "Indonesia", "Ghana"],
  profiles: [
    { name: "Maria S.", specialty: "Med/Surg",       origin: "Philippines",   status: "NCLEX passed \u00b7 CA RN", seeking: "MSN" },
    { name: "James K.", specialty: "ICU",            origin: "Kenya",         status: "NCLEX passed \u00b7 TX RN", seeking: "MBA" },
    { name: "Priya R.", specialty: "OR Circulating", origin: "Malaysia",      status: "NCLEX passed \u00b7 FL RN", seeking: "MHA" },
    { name: "David O.", specialty: "Emergency",      origin: "Ghana",         status: "In licensure \u00b7 CA",   seeking: "MSN" },
  ],
};

window.FLORENCE_FEATURED = { kaiser_permanente: "kaiser", sutter_health: "sutter" };

/* ---------------------------------------------------------------------
   BUILD A FULL DECK CONFIG FROM A UNIVERSE SYSTEM
   Defaults: direct channel, per-market pricing, standard 200-RN Phase I.
   Everything is overridable later by promoting the system to a featured
   preset (copy the generated object, hand-tune, drop it in above).
   --------------------------------------------------------------------- */
window.configFromUniverse = function (sysId) {
  const u = (window.FLORENCE_UNIVERSE || {})[sysId];
  if (!u) return null;

  const TERM = 24;
  const PILOT = 200;                       // standard Phase I ask
  const fmtM = (v) => "$" + (v / 1e6).toFixed(1) + "M";
  const programGross = fmtM(PILOT * u.medianFee * TERM);

  // short label for inline use ("Near-zero risk to {short}")
  let short = u.name
    .replace(/\s+(Health System|Healthcare|Health Care|Health|System)$/i, "")
    .trim();
  if (short.length > 24) short = u.name.split(/\s+/).slice(0, 2).join(" ");
  if (!short) short = u.name;

  return {
    id: sysId,
    displayName: u.name,
    shortName: short,
    logo: (window.florenceLogoFile && window.florenceLogoFile(sysId)) || null,   // curated file or text wordmark
    accent: "#1E6091",
    date: "June 2026",
    fromUniverse: true,
    meta: { nFacilities: u.nFacilities, states: u.states, totalRnNeed: u.totalRnNeed },

    channel: "direct",
    direct: {
      footerLine: "A Florence program",
      integration: {
        ats: "your ATS",
        headline: "Florence plugs directly into your ATS.",
        points: [
          { t: "Native ATS integration", s: "Candidates flow into your ATS as Florence-sourced reqs — no parallel system, no re-keying." },
          { t: "Tracked candidate links", s: "Every slate ships with UTM-tagged links so your team attributes every Florence hire inside your own funnel." },
          { t: "One source of truth", s: "Pipeline, starts, and conversion reconcile against your ATS — not a Florence spreadsheet." },
        ],
      },
    },

    volume: {
      total: PILOT,
      waves: [
        { label: "Wave 1", n: 50,  purpose: "First slate across the highest-need facilities — full process validation, manager acceptance, ATS integration proven live.", gate: "Gate: process validated & ATS live", final: false },
        { label: "Wave 2", n: 150, purpose: "Scale across the system once hiring, onboarding, and pathway timing are validated — completing the 200-RN Phase I.", gate: "Gate: expansion decision — Phase II review", final: true },
      ],
    },

    pricing: {
      mode: "market",
      feePerRnMonth: u.medianFee,
      effectiveLow: u.effectiveLow,
      effectiveHigh: u.effectiveLow,
      taxOffsetLow: u.ficaPerMonth,
      taxOffsetHigh: u.ficaPerMonth,
      illustrativePayRate: u.medianWage,
      illustrativeTaxPerHour: +(0.0765 * u.medianWage).toFixed(2),
      illustrativeTaxPerMonth: u.ficaPerMonth,
      programGross,
      termMonths: TERM,
      markets: u.topHospitals,
    },

    sprint: [
      { wk: "Week 1", t: short + " selects facilities, roles, criteria, and start windows." },
      { wk: "Week 2", t: "ATS integration stood up; onboarding & credentialing gates mapped to Florence workflow." },
      { wk: "Week 3", t: "First Wave-1 candidate slate — real people, readiness scores, tracked links live in your ATS." },
      { wk: "Week 4", t: "Metrics, commercial structure, and a clean go / no-go decision." },
    ],

    askHeadline: "Approve a 30-day design sprint to finalize the 200-RN Phase I.",
    deRisk: "Near-fully de-risked for " + short + ": no upfront fee, billing only after a nurse starts, billing stops the moment one leaves — and every hire clears " + short + "'s own clinical, credentialing, and onboarding gates.",
    source: "tool.nashp.org · CMS HCRIS 2023 · BLS OEWS",
  };
};

/* ---------------------------------------------------------------------
   RESOLVE THE ACTIVE CLIENT + CONFIG
   Accepts a featured key ("kaiser") OR any universe id ("hca").
   --------------------------------------------------------------------- */
window.FLORENCE_ACTIVE_CLIENT = (function () {
  function valid(id) {
    return id && (window.FLORENCE_PRESETS[id] || (window.FLORENCE_UNIVERSE && window.FLORENCE_UNIVERSE[id]));
  }
  try {
    const q = new URLSearchParams(location.search).get("client");
    if (valid(q)) return q;
  } catch (e) {}
  try {
    const saved = localStorage.getItem("florence_deck_client");
    if (valid(saved)) return saved;
  } catch (e) {}
  return "kaiser";
})();

window.FLORENCE_ACTIVE_CONFIG = (function () {
  const id = window.FLORENCE_ACTIVE_CLIENT;
  if (window.FLORENCE_PRESETS[id]) return window.FLORENCE_PRESETS[id];
  const cfg = window.configFromUniverse(id);
  return cfg || window.FLORENCE_PRESETS.kaiser;
})();
