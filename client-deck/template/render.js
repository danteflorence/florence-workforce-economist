/* =====================================================================
   Florence Client Deck — RENDER ENGINE
   Builds the full deck from a CLIENT config (see presets.js).
   Same fixed chassis for every client; only the config changes.
   ===================================================================== */
(function () {
  "use strict";

  /* Apply a per-system Phase I size override (set by the Tweaks slider,
     persisted per client id). Recomputes waves, program total, and the
     ask headline. Returns the base config unchanged when no override. */
  function applyPhaseSize(base) {
    let size;
    try { size = parseInt(localStorage.getItem("florence_phase_" + base.id), 10); } catch (e) {}
    if (!size || size < 1 || size === base.volume.total) return base;
    const c = JSON.parse(JSON.stringify(base));   // configs are pure data
    c.volume.total = size;
    const w1 = Math.max(10, Math.round(size * 0.25));
    const waves = c.volume.waves;
    if (waves.length >= 2) {
      waves[0].n = w1;
      waves[waves.length - 1].n = size - w1;
    }
    const term = c.pricing.termMonths || 24;
    c.pricing.programGross = "$" + ((size * c.pricing.feePerRnMonth * term) / 1e6).toFixed(1) + "M";
    c.askHeadline = c.askHeadline.replace(/\d[\d,]*(?=-RN Phase I)/, size);
    return c;
  }

  /* Apply a per-system channel override (Direct vs AMN-sponsored), set by
     the Tweaks toggle and persisted per client id. Synthesizes whichever
     channel block the base config is missing. */
  function applyChannel(base) {
    let ch;
    try { ch = localStorage.getItem("florence_channel_" + base.id); } catch (e) {}
    if (!ch || ch === base.channel) return base;
    const c = JSON.parse(JSON.stringify(base));
    c.channel = ch;
    const short = c.shortName || c.displayName;
    if (ch === "partner" && !c.partner) {
      c.partner = {
        name: "AMN",
        logo: "assets/partners/amn-logo.jpeg",
        role: "Leads the " + short + " relationship, coordinates workflow, manages the commercial structure.",
        footerLine: "AMN-sponsored program",
      };
    }
    if (ch === "direct" && !c.direct) {
      c.direct = {
        footerLine: "A Florence program",
        integration: {
          ats: "your ATS",
          headline: "Florence plugs directly into your ATS.",
          points: [
            { t: "Native ATS integration", s: "Candidates flow into your ATS as Florence-sourced reqs \u2014 no parallel system, no re-keying." },
            { t: "Tracked candidate links", s: "Every slate ships with UTM-tagged links so your team attributes every Florence hire inside your own funnel." },
            { t: "One source of truth", s: "Pipeline, starts, and conversion reconcile against your ATS \u2014 not a Florence spreadsheet." },
          ],
        },
      };
    }
    return c;
  }

  window.FLORENCE_RENDER = function () {

  const C = applyChannel(applyPhaseSize(window.FLORENCE_ACTIVE_CONFIG));
  const isPartner = C.channel === "partner";
  const short = C.shortName || C.displayName;
  const contact = C.contact || window.FLORENCE_CONTACT;
  const signupBase = C.signupUrl || window.FLORENCE_SIGNUP_URL;
  // UTM-tag the signup link so each system + channel attributes in analytics
  const utm = "utm_source=florence_deck&utm_medium=proposal" +
    "&utm_campaign=" + encodeURIComponent(C.id) +
    "&utm_content=" + encodeURIComponent(C.channel);
  const signupUrl = signupBase + (signupBase.indexOf("?") > -1 ? "&" : "?") + utm;
  const signupLabel = C.signupLabel || window.FLORENCE_SIGNUP_LABEL || "Get started";

  /* ---------- small helpers ---------- */
  const check = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';
  const checkSm = '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';

  // client mark: <img> if a logo file exists, else a serif text wordmark
  function clientMark(h, onDark) {
    if (C.logo) return `<img src="${C.logo}" alt="${C.displayName}" style="height:${h}px;" />`;
    return `<span style="font-family:var(--font-display);font-weight:800;font-size:${Math.round(h * 0.7)}px;letter-spacing:-0.015em;color:${onDark ? "#fff" : "var(--ink)"};">${C.displayName}</span>`;
  }
  function partnerMark(h) {
    return `<img src="${C.partner.logo}" alt="${C.partner.name}" style="height:${h}px;" />`;
  }
  const plus = `<span style="font-family:var(--font-display);font-style:italic;color:var(--ink-3);font-size:26px;line-height:1;">+</span>`;

  // footer line: "AMN + Florence + Kaiser"  |  "Florence + Sutter"
  const footerLine = isPartner
    ? `${C.partner.name} + <b>Florence</b> + ${short}`
    : `<b>Florence</b> + ${short}`;

  function footer(i, total) {
    return `<div class="slide-footer"><div class="left">${footerLine}</div><div class="pgnum">${String(i).padStart(2, "0")} / ${String(total).padStart(2, "0")}</div></div>`;
  }
  function splashFooter(i, total) {
    return `<div class="splash__footer"><div>${footerLine}</div><div style="color:rgba(255,255,255,0.85);font-variant-numeric:tabular-nums;">${String(i).padStart(2, "0")} / ${String(total).padStart(2, "0")}</div></div>`;
  }
  function header(eyebrowNum, eyebrowText) {
    return `<div class="slide-header">
      <div class="slide-header__brand">
        <img src="assets/logos/florence-color.svg" alt="Florence" />
        <span class="sep"></span>
        <span class="partner">For ${C.displayName}</span>
      </div>
      <span class="slide-eyebrow">${String(eyebrowNum).padStart(2, "0")} &middot; ${eyebrowText}</span>
    </div>`;
  }
  const money = (v) => `$${Number(v).toLocaleString()}`;

  /* ===================================================================
     SLIDE 1 — COVER (splash)
     =================================================================== */
  function slideCover(i, total) {
    const lockup = isPartner
      ? `${partnerMark(56)} ${plus} <img src="assets/logos/florence-color.svg" alt="Florence" style="height:42px;" /> ${plus} ${clientMark(56, false)}`
      : `<img src="assets/logos/florence-color.svg" alt="Florence" style="height:46px;" /> ${plus} ${clientMark(58, false)}`;
    const subtitle = isPartner
      ? `An AMN and Florence collaboration to bring global nurses to ${C.displayName}.`
      : `A Florence program to bring global nurses to ${C.displayName}.`;
    return `<section data-slide data-label="01 Cover" data-screen-label="01">
      <div class="splash">
        <div style="display:flex;align-items:center;justify-content:space-between;">
          <div style="display:inline-flex;align-items:center;gap:28px;background:#fff;border-radius:16px;padding:20px 36px;">${lockup}</div>
          <span style="font-family:var(--font-sans);font-weight:600;font-size:18px;letter-spacing:0.32em;text-transform:uppercase;color:rgba(255,255,255,0.78);">Confidential &middot; ${C.date}</span>
        </div>
        <div style="flex:1;display:flex;flex-direction:column;justify-content:center;">
          <h1 style="font-family:var(--font-display);font-weight:800;font-size:116px;line-height:1.0;letter-spacing:-0.028em;color:#fff;margin:0;max-width:1640px;text-wrap:balance;">${C.volume.total} full-time nurses<br/>for ${C.displayName}.</h1>
          <span style="display:block;width:220px;height:6px;border-radius:3px;background:rgba(255,255,255,0.9);margin-top:44px;"></span>
          <p style="font-family:var(--font-serif);font-style:italic;font-size:32px;line-height:1.4;color:rgba(255,255,255,0.88);margin:36px 0 0;max-width:1420px;">${subtitle}</p>
        </div>
        ${splashFooter(i, total)}
      </div>
    </section>`;
  }

  /* ===================================================================
     SLIDE 2 — WHAT THE CLIENT GETS (roles + de-risk banner + checks)
     =================================================================== */
  function slideWhatYouGet(i, total) {
    // role cells: partner = 3 (AMN/Florence/Client); direct = 2 (Florence/Client)
    const roleCells = [];
    if (isPartner) {
      roleCells.push(`<div class="role-cell"><span class="r-label">Sponsors</span><span class="r-who">${C.partner.name}</span><span class="r-what">${C.partner.role}</span></div>`);
    }
    roleCells.push(`<div class="role-cell --fl"><span class="r-label">Produces</span><span class="r-who">Florence</span><span class="r-what">Readiness-scored global RNs — Academy, NCLEX, licensure, employer-ready packets. New cohorts monthly.</span></div>`);
    roleCells.push(`<div class="role-cell --kp"><span class="r-label">Employs</span><span class="r-who">${short}</span><span class="r-what">Interviews, hires, and onboards full-time employees through its standard process. Full control.</span></div>`);
    const rolesCols = isPartner ? "1fr 1fr 1fr" : "1fr 1fr";

    // check grid — direct mode swaps "weekly visibility" for ATS integration
    const checks = [
      { t: `A ${C.volume.total}-RN candidate pipeline`, s: `Activated in gated waves — ${short}-selected roles and facilities.` },
      { t: "Employer-ready candidate packets", s: "Readiness score, credentials, licensure status, expected start window." },
      { t: "Standard clinical & compliance gates", s: "Licensure, occupational health, credentialing — unchanged." },
      isPartner
        ? { t: "Weekly operating visibility", s: `${C.partner.name}, ${short}, and Florence at the same table — pipeline, starts, issues.` }
        : { t: "Native ATS integration", s: `Candidates flow into ${C.direct.integration.ats} with tracked links — your funnel, your source of truth.` },
    ];
    const checkHtml = checks.map(c => `<div class="checkrow">${check}<span><b>${c.t}</b><span class="sub">${c.s}</span></span></div>`).join("");

    const banner = `<div style="display:flex;align-items:center;gap:28px;margin-top:32px;background:var(--florence-teal);border-radius:16px;padding:22px 34px;color:#fff;">
      <span style="font-family:var(--font-display);font-weight:800;font-size:23px;letter-spacing:-0.01em;white-space:nowrap;">Near-zero risk to ${short}</span>
      <span style="width:1px;height:36px;background:rgba(255,255,255,0.4);flex-shrink:0;"></span>
      <div style="display:flex;gap:38px;flex-wrap:wrap;font-family:var(--font-sans);font-size:20px;font-weight:500;">
        <span style="display:inline-flex;align-items:center;gap:10px;">${checkSm}No upfront fee</span>
        <span style="display:inline-flex;align-items:center;gap:10px;">${checkSm}Billed only after a nurse starts</span>
        <span style="display:inline-flex;align-items:center;gap:10px;">${checkSm}Billing stops if a nurse leaves</span>
        <span style="display:inline-flex;align-items:center;gap:10px;">${checkSm}${short}&rsquo;s own hiring gates</span>
      </div>
    </div>`;

    return `<section data-slide data-label="02 What ${short} gets" data-screen-label="02">
      <div class="slide-frame">
        ${header(i - 1, "What " + short + " gets")}
        <h2 class="slide-title">Hire ${C.volume.total} permanent RNs, ${isPartner ? "through " + C.partner.name + " + Florence partnership." : "direct with Florence."}</h2>
        <span class="accent-rule" style="margin-top:22px;"></span>
        ${banner}
        <div class="roles" style="margin-top:40px;grid-template-columns:${rolesCols};">${roleCells.join("")}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:22px 72px;margin-top:40px;flex:1;align-content:start;">${checkHtml}</div>
        ${footer(i, total)}
      </div>
    </section>`;
  }

  /* ===================================================================
     SLIDE 3 — COMMERCIAL STRUCTURE
     flat  → single hero price card + terms
     market → per-hospital table + aggregate hero
     =================================================================== */
  function slideCommercial(i, total) {
    const p = C.pricing;
    if (p.mode === "market") {
      const rows = p.markets.map(m => `<tr>
        <td><strong>${m.name}</strong><span class="note">${m.location} &middot; ${m.rnNeed.toLocaleString()} RN need</span></td>
        <td class="num money">${money(m.feePerRn)}</td>
        <td class="num money">~${money(m.effectivePerRn)}</td>
      </tr>`).join("");
      return `<section data-slide data-label="03 Commercial structure" data-screen-label="03">
        <div class="slide-frame">
          ${header(i - 1, "Commercial structure")}
          <h2 class="slide-title" style="font-size:54px;">Priced locally, per facility — billed per RN, per month, after start.</h2>
          <p class="slide-body" style="margin-top:12px;max-width:1650px;font-size:20px;">No upfront fee. Every facility is priced against its own labor economics from the Florence workforce-economist platform — never a national average. ${short} carries no recruitment risk and no committed-volume obligation; fees track actual starts.</p>
          <div style="display:grid;grid-template-columns:1.55fr 1fr;gap:48px;margin-top:24px;flex:1;align-items:start;">
            <table class="etable --compact">
              <thead><tr><th style="width:54%;">Facility</th><th class="num">Fee / RN / mo</th><th class="num">Effective*</th></tr></thead>
              <tbody>${rows}</tbody>
            </table>
            <div style="background:linear-gradient(160deg,var(--florence-teal) 0%,var(--florence-teal-deep) 100%);border-radius:22px;padding:40px;color:#fff;display:flex;flex-direction:column;gap:8px;box-shadow:0 18px 40px rgba(10,186,181,0.22);">
              <span style="font-family:var(--font-sans);font-weight:600;font-size:17px;letter-spacing:0.16em;text-transform:uppercase;color:rgba(255,255,255,0.8);">System median</span>
              <span class="money" style="font-family:var(--font-display);font-weight:800;font-size:84px;line-height:1;letter-spacing:-0.03em;">~${money(p.effectiveLow)}<span style="font-size:28px;font-weight:600;opacity:0.85;">/RN/mo</span></span>
              <span style="font-family:var(--font-display);font-weight:700;font-size:24px;line-height:1.2;">Effective cost after payroll-tax offset.</span>
              <div style="margin-top:14px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.3);font-family:var(--font-sans);font-size:18px;line-height:1.5;color:rgba(255,255,255,0.92);">
                Median gross fee ${money(p.feePerRnMonth)}/RN/mo. Billing follows each start; ${short} is never billed for a nurse who hasn&rsquo;t started.
              </div>
              <span style="font-family:var(--font-sans);font-size:15px;line-height:1.45;color:rgba(255,255,255,0.8);margin-top:14px;">*Fee minus eligible payroll-tax offset. Planning estimate, eligible cohorts only.</span>
            </div>
          </div>
          <p class="src" style="margin-top:14px;">Source: ${C.source}. Per-facility figures locally calibrated; final pricing confirmed during the design sprint.</p>
          ${footer(i, total)}
        </div>
      </section>`;
    }
    // flat mode
    return `<section data-slide data-label="03 Commercial structure" data-screen-label="03">
      <div class="slide-frame">
        ${header(i - 1, "Commercial structure")}
        <h2 class="slide-title">Simple to approve: per RN, per month, after start.</h2>
        <p class="slide-body" style="margin-top:16px;max-width:1650px;font-size:22px;">No large upfront placement fee. No payment for recruitment, preparation, or pipeline activity. ${short} carries no recruitment risk and no committed-volume obligation — at full deployment the entire program is <b class="money" style="color:var(--ink);">${p.programGross}</b>, billed monthly, only as nurses start.</p>
        <div style="display:grid;grid-template-columns:1fr 1.1fr;gap:72px;margin-top:40px;flex:1;align-items:start;">
          <div style="background:linear-gradient(160deg,var(--florence-teal) 0%,var(--florence-teal-deep) 100%);border-radius:22px;padding:44px 44px 36px;color:#fff;box-shadow:0 18px 40px rgba(10,186,181,0.22);display:flex;flex-direction:column;gap:10px;height:100%;box-sizing:border-box;">
            <span style="font-family:var(--font-sans);font-weight:600;font-size:18px;letter-spacing:0.16em;text-transform:uppercase;color:rgba(255,255,255,0.8);">Illustrative program option</span>
            <span class="money" style="font-family:var(--font-display);font-weight:800;font-size:110px;line-height:1;letter-spacing:-0.035em;display:flex;align-items:baseline;gap:6px;">${money(p.feePerRnMonth)}<span style="font-size:34px;font-weight:600;opacity:0.85;">/RN/mo</span></span>
            <span style="font-family:var(--font-display);font-weight:700;font-size:26px;line-height:1.2;">Gross monthly capacity fee.</span>
            <div style="display:flex;justify-content:space-between;align-items:baseline;gap:20px;margin-top:14px;padding-top:16px;border-top:1px solid rgba(255,255,255,0.3);">
              <span style="font-family:var(--font-sans);font-size:19px;color:rgba(255,255,255,0.85);">Less: eligible payroll-tax offset*</span>
              <span class="money" style="font-family:var(--font-display);font-weight:700;font-size:30px;font-variant-numeric:tabular-nums;white-space:nowrap;">(${money(p.taxOffsetLow)}&ndash;${money(p.taxOffsetHigh)})</span>
            </div>
            <div style="display:flex;justify-content:space-between;align-items:baseline;gap:20px;padding-top:12px;border-top:2px solid rgba(255,255,255,0.85);">
              <span style="font-family:var(--font-sans);font-weight:700;font-size:21px;color:#fff;">Effective ${short} cost</span>
              <span class="money" style="font-family:var(--font-display);font-weight:800;font-size:52px;font-variant-numeric:tabular-nums;letter-spacing:-0.02em;white-space:nowrap;">~${money(p.effectiveLow)}&ndash;${money(p.effectiveHigh)}<span style="font-size:22px;font-weight:600;opacity:0.85;">/RN/mo</span></span>
            </div>
            <span style="font-family:var(--font-sans);font-size:17px;line-height:1.45;color:rgba(255,255,255,0.8);margin-top:auto;padding-top:14px;">*Planning estimate, eligible cohorts only. Final customer-facing price and packaging structured through ${isPartner ? C.partner.name + " and " + short : "Florence and " + short}.</span>
          </div>
          <dl style="display:grid;grid-template-columns:max-content 1fr;gap:26px 36px;align-items:baseline;margin:8px 0 0;">
            <dt style="font-family:var(--font-sans);font-weight:600;font-size:21px;color:var(--ink-2);">Billing trigger</dt>
            <dd style="font-family:var(--font-sans);font-size:23px;color:var(--ink);margin:0;">RN start date — nothing before</dd>
            <dt style="font-family:var(--font-sans);font-weight:600;font-size:21px;color:var(--ink-2);">Term</dt>
            <dd style="font-family:var(--font-sans);font-size:23px;color:var(--ink);margin:0;">${p.termMonths} months per started RN</dd>
            <dt style="font-family:var(--font-sans);font-weight:600;font-size:21px;color:var(--ink-2);">Scaling</dt>
            <dd style="font-family:var(--font-sans);font-size:23px;color:var(--ink);margin:0;">Fees track actual starts — never committed volume. If a nurse leaves, billing stops.</dd>
            <dt style="font-family:var(--font-sans);font-weight:600;font-size:21px;color:var(--ink-2);">Program total</dt>
            <dd style="font-family:var(--font-sans);font-size:23px;color:var(--ink);margin:0;"><b class="money">${p.programGross}</b> gross at full ${C.volume.total}-RN deployment over ${p.termMonths} months</dd>
          </dl>
        </div>
        ${footer(i, total)}
      </div>
    </section>`;
  }

  /* ===================================================================
     SLIDE 4 — EFFECTIVE COST (payroll-tax exemption)
     =================================================================== */
  function slideEffectiveCost(i, total) {
    const p = C.pricing;
    return `<section data-slide data-label="04 Effective monthly cost" data-screen-label="04">
      <div class="slide-frame">
        ${header(i - 1, "Effective cost")}
        <h2 class="slide-title" style="font-size:64px;">These nurses are exempt from the 7.65% employer payroll tax.</h2>
        <p class="slide-body" style="margin-top:16px;max-width:1650px;font-size:22px;">Every Florence nurse is a BSN-holding, Master&rsquo;s-seeking RN on an F-1 visa — and F-1 student wages are exempt from FICA. ${short} keeps the employer&rsquo;s 7.65% on every hour they work.</p>
        <div style="display:grid;grid-template-columns:1fr 1.25fr;gap:40px;margin-top:44px;align-items:stretch;">
          <div style="background:var(--royal-purple-deep);border-radius:18px;padding:40px 44px;display:flex;flex-direction:column;justify-content:center;gap:28px;">
            <div style="font-family:var(--font-sans);font-size:15px;font-weight:700;letter-spacing:0.1em;text-transform:uppercase;color:rgba(255,255,255,0.65);">Illustrative hourly view</div>
            <div style="display:flex;align-items:baseline;gap:20px;"><span class="money" style="font-family:var(--font-display);font-weight:800;font-size:64px;line-height:1;color:#fff;letter-spacing:-0.02em;">$${p.illustrativePayRate}</span><span style="font-family:var(--font-sans);font-size:19px;color:rgba(255,255,255,0.8);">/ hr RN pay rate</span></div>
            <div style="display:flex;align-items:baseline;gap:20px;"><span class="money" style="font-family:var(--font-display);font-weight:800;font-size:64px;line-height:1;color:var(--florence-teal);letter-spacing:-0.02em;">$${p.illustrativeTaxPerHour}</span><span style="font-family:var(--font-sans);font-size:19px;color:rgba(255,255,255,0.8);">/ hr payroll tax ${short} doesn&rsquo;t pay</span></div>
            <div style="font-family:var(--font-sans);font-size:16px;color:rgba(255,255,255,0.6);line-height:1.5;">&asymp; $${p.illustrativeTaxPerMonth} per nurse per month at full-time hours.</div>
          </div>
          <table class="etable" style="align-self:center;">
            <thead><tr><th style="width:55%;">Per RN / month</th><th class="num" style="width:45%;"></th></tr></thead>
            <tbody>
              <tr><td>Florence fee${p.mode === "market" ? " (median)" : ""}</td><td class="num money">${money(p.feePerRnMonth)}</td></tr>
              <tr><td class="neg">Less: payroll-tax exemption</td><td class="num neg money">(~$${p.illustrativeTaxPerMonth})</td></tr>
              <tr class="total"><td>Effective ${short} cost</td><td class="num money">~${money(p.feePerRnMonth - p.illustrativeTaxPerMonth)}</td></tr>
            </tbody>
          </table>
        </div>
        <p class="src" style="margin-top:36px;max-width:1650px;">Illustrative at a $${p.illustrativePayRate}/hr pay rate and full-time hours. Eligibility and treatment to be validated by ${isPartner ? short + " / " + C.partner.name : short + " / Florence"} payroll, tax, and benefits teams during the design sprint.</p>
        ${footer(i, total)}
      </div>
    </section>`;
  }

  /* ===================================================================
     SLIDE (direct only) — ATS INTEGRATION
     =================================================================== */
  function slideIntegration(i, total) {
    const ig = C.direct.integration;
    const cards = ig.points.map(pt => `<div class="fcard --quiet" style="gap:10px;"><div style="display:flex;align-items:center;gap:14px;"><span style="color:var(--florence-teal);">${check}</span><span style="font-family:var(--font-display);font-weight:700;font-size:26px;color:var(--ink);">${pt.t}</span></div><p style="font-family:var(--font-sans);font-size:20px;line-height:1.5;color:var(--ink-2);margin:0;padding-left:40px;">${pt.s}</p></div>`).join("");
    return `<section data-slide data-label="0X Integration" data-screen-label="${String(i).padStart(2, "0")}">
      <div class="slide-frame">
        ${header(i - 1, "Integration")}
        <h2 class="slide-title">${ig.headline}</h2>
        <p class="slide-body" style="margin-top:16px;max-width:1650px;">Going direct means Florence works inside your systems — not alongside them. Every candidate is trackable in your own funnel from first touch to start.</p>
        <div style="display:grid;grid-template-columns:1fr;gap:22px;margin-top:44px;flex:1;align-content:center;">${cards}</div>
        ${footer(i, total)}
      </div>
    </section>`;
  }

  /* ===================================================================
     SLIDE 5 — ACTIVATION PLAN (waves)
     =================================================================== */
  function slideActivation(i, total) {
    const waves = C.volume.waves;
    const cols = waves.length === 2 ? "1fr 1.6fr" : "1fr 1fr 1.6fr";
    const waveHtml = waves.map(w => `<div class="wave${w.final ? " --final" : ""}">
      <span class="wave__label">${w.label}</span>
      <span class="wave__num">${w.n}</span>
      <p class="wave__purpose">${w.purpose}</p>
      <div class="wave__gate">${check}${w.gate}</div>
    </div>`).join("");
    return `<section data-slide data-label="05 Activation plan" data-screen-label="05">
      <div class="slide-frame">
        ${header(i - 1, "Activation plan")}
        <h2 class="slide-title">${C.volume.total} nurses, ${waves.length === 2 ? "two" : "three"} gated waves.</h2>
        <p class="slide-body" style="margin-top:18px;max-width:1600px;">The full Phase I commitment is ${C.volume.total} RNs. Activation is staged — each wave reviewed against quality, conversion, and onboarding gates before the next begins.</p>
        <div class="waves" style="margin-top:48px;flex:1;grid-template-columns:${cols};">${waveHtml}</div>
        <p class="src" style="margin-top:32px;"><b>Judged on:</b> hiring conversion &middot; start timing &middot; start completion &middot; 90-day retention &middot; manager satisfaction — metrics ${short} already tracks. Billing follows each start; ${short} is never billed for a nurse who hasn&rsquo;t started.</p>
        ${footer(i, total)}
      </div>
    </section>`;
  }

  /* ===================================================================
     SLIDE 6 — THE ASK (splash)
     =================================================================== */
  function slideAsk(i, total) {
    const p = C.pricing;
    const waveDesc = C.volume.waves.map(w => w.n).join(" + ");
    return `<section data-slide data-label="06 The ask" data-screen-label="06">
      <div class="splash">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:40px;">
          <div style="display:flex;align-items:center;gap:18px;">
            <img src="assets/logos/florence-white.svg" alt="Florence" style="height:36px;" />
            <span style="width:1px;height:24px;background:rgba(255,255,255,0.3);"></span>
            <span style="font-family:var(--font-sans);font-weight:600;font-size:18px;letter-spacing:0.02em;color:rgba(255,255,255,0.7);">For ${C.displayName}</span>
          </div>
          <span style="font-family:var(--font-sans);font-weight:600;font-size:18px;letter-spacing:0.32em;text-transform:uppercase;color:rgba(255,255,255,0.78);">${String(i - 1).padStart(2, "0")} &middot; The ask</span>
        </div>
        <div style="flex:1;display:flex;flex-direction:column;justify-content:center;">
          <h2 style="font-family:var(--font-display);font-weight:800;font-size:92px;line-height:1.0;letter-spacing:-0.028em;color:#fff;margin:0;max-width:1640px;text-wrap:balance;">${C.askHeadline}</h2>
          <div style="display:flex;align-items:flex-start;gap:18px;margin-top:34px;max-width:1500px;border-left:4px solid rgba(255,255,255,0.55);padding-left:22px;">
            <p style="font-family:var(--font-serif);font-style:italic;font-size:27px;line-height:1.45;color:rgba(255,255,255,0.92);margin:0;">${C.deRisk}</p>
          </div>
          <div style="align-self:flex-start;margin-top:34px;display:flex;align-items:center;gap:24px;flex-wrap:wrap;">
            <a href="${signupUrl}" style="display:inline-flex;align-items:center;gap:12px;background:#fff;color:var(--florence-teal-deep);font-family:var(--font-sans);font-weight:800;font-size:23px;padding:17px 32px;border-radius:14px;text-decoration:none;box-shadow:0 12px 30px rgba(0,0,0,0.16);">${signupLabel}<span style="font-weight:800;">&rarr;</span></a>
            <a href="mailto:${contact}" style="display:inline-flex;align-items:center;color:#fff;font-family:var(--font-sans);font-weight:600;font-size:21px;text-decoration:none;border-bottom:1px solid rgba(255,255,255,0.5);padding-bottom:2px;">or email ${contact}</a>
          </div>
        </div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:0;border-top:1px solid rgba(255,255,255,0.25);border-bottom:1px solid rgba(255,255,255,0.25);margin-top:36px;">
          <div style="padding:28px 36px;border-right:1px solid rgba(255,255,255,0.25);">
            <div style="font-family:var(--font-sans);font-weight:600;font-size:15px;letter-spacing:0.18em;text-transform:uppercase;color:rgba(255,255,255,0.7);margin-bottom:10px;">Phase I</div>
            <div style="font-family:var(--font-display);font-weight:800;font-size:52px;line-height:1;color:#fff;letter-spacing:-0.025em;">${C.volume.total} RNs</div>
            <div style="font-family:var(--font-sans);font-size:17px;color:rgba(255,255,255,0.78);margin-top:10px;line-height:1.4;">Activated ${waveDesc}, gated by ${C.volume.waves.length === 2 ? "a wave review" : "wave reviews"}.</div>
          </div>
          <div style="padding:28px 36px;border-right:1px solid rgba(255,255,255,0.25);">
            <div style="font-family:var(--font-sans);font-weight:600;font-size:15px;letter-spacing:0.18em;text-transform:uppercase;color:rgba(255,255,255,0.7);margin-bottom:10px;">The program</div>
            <div class="money" style="font-family:var(--font-display);font-weight:800;font-size:52px;line-height:1;color:#fff;letter-spacing:-0.025em;">${p.programGross}</div>
            <div style="font-family:var(--font-sans);font-size:17px;color:rgba(255,255,255,0.78);margin-top:10px;line-height:1.4;">Gross at full deployment — per RN per month, only after each start.</div>
          </div>
          <div style="padding:28px 36px;">
            <div style="font-family:var(--font-sans);font-weight:600;font-size:15px;letter-spacing:0.18em;text-transform:uppercase;color:rgba(255,255,255,0.7);margin-bottom:10px;">Then</div>
            <div style="font-family:var(--font-display);font-weight:800;font-size:52px;line-height:1;color:#fff;letter-spacing:-0.025em;">Gated growth</div>
            <div style="font-family:var(--font-sans);font-size:17px;color:rgba(255,255,255,0.78);margin-top:10px;line-height:1.4;">Expansion only after quality and retention proof.</div>
          </div>
        </div>
        ${splashFooter(i, total)}
      </div>
    </section>`;
  }

  /* ===================================================================
     SLIDE (optional) — WHO THESE NURSES ARE (profiles + degrees)
     =================================================================== */
  function slideProfiles(i, total) {
    const nz = C.nurses || window.FLORENCE_NURSES_DEFAULT;
    const chips = nz.degrees.map(d => `<span class="fl-pill --purple" style="font-size:21px;padding:11px 22px;">${d}</span>`).join("");
    const cards = nz.profiles.slice(0, 4).map(p => `
      <div class="fcard --quiet" style="gap:10px;">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;">
          <span style="font-family:var(--font-display);font-weight:800;font-size:30px;color:var(--ink);letter-spacing:-0.01em;">${p.name}</span>
          <span class="fl-pill --ink" style="font-size:15px;">${p.specialty}</span>
        </div>
        <div style="font-family:var(--font-sans);font-size:19px;color:var(--ink-2);">${p.origin} &middot; ${p.status}</div>
        <div style="display:inline-flex;align-items:center;gap:8px;font-family:var(--font-sans);font-size:17px;color:var(--royal-purple-deep);font-weight:600;margin-top:auto;"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>Pursuing ${p.seeking}</div>
      </div>`).join("");
    const eyebrow = (t) => `<div style="font-family:var(--font-sans);font-weight:600;font-size:15px;letter-spacing:0.16em;text-transform:uppercase;color:var(--ink-3);margin-bottom:14px;">${t}</div>`;
    return `<section data-slide data-label="0P Who these nurses are" data-screen-label="${String(i).padStart(2, "0")}">
      <div class="slide-frame">
        ${header(i - 1, "Who these nurses are")}
        <h2 class="slide-title" style="font-size:60px;">BSN-prepared, Master&rsquo;s-seeking &mdash; a global pipeline.</h2>
        <p class="slide-body" style="margin-top:14px;max-width:1650px;font-size:21px;">Every Florence nurse holds a BSN and is pursuing a US master&rsquo;s on an F-1 visa &mdash; exactly what makes the payroll-tax exemption hold, and why retention runs in years, not shifts.</p>
        <div style="display:grid;grid-template-columns:0.82fr 1.18fr;gap:52px;margin-top:34px;flex:1;align-items:start;">
          <div style="display:flex;flex-direction:column;gap:34px;">
            <div>${eyebrow("Degrees in progress")}<div style="display:flex;flex-wrap:wrap;gap:12px;">${chips}</div></div>
            <div>${eyebrow("Global, English-speaking pipeline")}<div style="font-family:var(--font-display);font-weight:700;font-size:27px;line-height:1.5;color:var(--ink);letter-spacing:-0.01em;">${nz.origins.join(" &middot; ")}</div></div>
            <div>${eyebrow("Cadence")}<div style="font-family:var(--font-sans);font-size:20px;line-height:1.5;color:var(--ink-2);">New cohorts onboard <b style="color:var(--ink);">monthly</b> &mdash; a live, continuous candidate flow, not a one-time batch.</div></div>
          </div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:22px;">${cards}</div>
        </div>
        <p class="src" style="margin-top:18px;">Representative cohort profiles, anonymized. Degrees, specialties, and license states reflect active Florence cohorts.</p>
        ${footer(i, total)}
      </div>
    </section>`;
  }

  /* ===================================================================
     ASSEMBLE
     =================================================================== */
  // slide order; integration slide injected only in direct mode (after slide 2)
  const showProfiles = (function () { try { return localStorage.getItem("florence_show_profiles") === "1"; } catch (e) { return false; } })();
  const builders = [slideCover, slideWhatYouGet];
  if (showProfiles) builders.push(slideProfiles);
  if (!isPartner) builders.push(slideIntegration);
  builders.push(slideCommercial, slideEffectiveCost, slideActivation, slideAsk);

  const total = builders.length;
  const html = builders.map((fn, idx) => fn(idx + 1, total)).join("\n");

  const stage = document.querySelector("deck-stage");
  stage.innerHTML = html;

  /* ----- speaker notes (generated per client) ----- */
  const partnerIntro = isPartner
    ? `${short} has always managed workforce through a blend of permanent, contingent, and partner-supported labor. ${C.partner.name} would like to bring an additional permanent-capacity option for targeted RN roles. `
    : `${short} has always managed workforce through a blend of permanent, contingent, and agency labor. Florence brings an additional permanent-capacity option for targeted RN roles, direct — no agency in the middle. `;
  const notes = [
    `${partnerIntro}Florence produces readiness-scored global RN candidates through its education, pathway, and licensure platform. ${short} interviews and hires them as full-time employees through its normal process. Phase I is ${C.volume.total} nurses, billed only after each nurse starts. Six slides, ten minutes, and the ask at the end is a 30-day design sprint.`,
    `What ${short} gets, in one view. The teal banner up top is the headline: near-zero risk — no upfront fee, billed only after a nurse starts, billing stops if a nurse leaves, and every hire clears ${short}'s own gates. Below that, who does what${isPartner ? ": " + C.partner.name + " sponsors, Florence produces, " + short + " employs" : ": Florence produces, " + short + " employs — direct"}. Then the operational proof points: a ${C.volume.total}-RN gated pipeline, employer-ready packets, unchanged clinical gates, and ${isPartner ? "weekly tri-party visibility" : "native ATS integration with tracked candidate links"}.`,
  ];
  if (showProfiles) {
    const nz = C.nurses || window.FLORENCE_NURSES_DEFAULT;
    notes.push(`Who these nurses are \u2014 a beat for any quality or retention skeptic. Every Florence nurse holds a BSN and is pursuing a US master's \u2014 ${nz.degrees.join(", ")} \u2014 on an F-1 visa. That's the same fact that powers the payroll-tax exemption, and it's why retention runs in years, not shifts. The cards are representative, anonymized cohort profiles: real specialties, NCLEX status, license state, from a global English-speaking pipeline. New cohorts onboard monthly, so this is a live, continuous flow.`);
  }
  if (!isPartner) {
    notes.push(`Integration is the direct advantage. Because there's no partner in the middle, Florence works inside your systems: candidates flow into ${C.direct.integration.ats} as Florence-sourced reqs, every slate ships with UTM-tagged links so your team attributes each hire inside your own funnel, and pipeline reconciles against your ATS — not a Florence spreadsheet. One source of truth.`);
  }
  if (C.pricing.mode === "market") {
    notes.push(`The commercial structure — priced locally, per facility. The table shows each facility quoted against its own labor economics from our workforce-economist platform, never a national average. The teal card holds the system median: roughly $${C.pricing.effectiveLow} effective per RN per month after the payroll-tax offset, on a median gross fee of ${money(C.pricing.feePerRnMonth)}. Billing follows each start; ${short} is never billed for a nurse who hasn't started. No upfront fee, no committed volume.`);
  } else {
    notes.push(`The commercial structure — this is the slide we want remembered. The teal card is the whole story: ${money(C.pricing.feePerRnMonth)} per RN per month gross, less an estimated $${C.pricing.taxOffsetLow} to $${C.pricing.taxOffsetHigh} of eligible payroll-tax offset, means ${short}'s effective cost is roughly $${C.pricing.effectiveLow} to $${C.pricing.effectiveHigh} per nurse per month. Billing trigger is the start date — nothing before. ${C.pricing.termMonths}-month term per started RN. Fees track actual starts, never committed volume, and if a nurse leaves billing stops. At full deployment the whole program is ${C.pricing.programGross}.`);
  }
  notes.push(`Why the cost drops below the fee. Every Florence nurse is a BSN-holding, Master's-seeking RN on an F-1 visa — F-1 student wages are exempt from FICA, so ${short} doesn't pay the employer's 7.65%. At an illustrative $${C.pricing.illustrativePayRate}/hr that's $${C.pricing.illustrativeTaxPerHour}/hr ${short} doesn't pay, roughly $${C.pricing.illustrativeTaxPerMonth} per nurse per month. Stated plainly: illustrative, and eligibility gets validated by payroll, tax, and benefits teams during the sprint.`);
  notes.push(`How the ${C.volume.total} gets activated: ${C.volume.waves.length === 2 ? "two" : "three"} gated waves (${C.volume.waves.map(w => w.n).join(" then ")}). A review gate between each. The scorecard — hiring conversion, start timing, start completion, 90-day retention, manager satisfaction — all metrics ${short} already tracks. Billing follows each start.`);
  notes.push(`The ask: approve a 30-day design sprint to finalize the ${C.volume.total}-RN Phase I. The line under the headline is the one to land on — near-fully de-risked. ${C.sprint.map(s => s.wk + ": " + s.t).join(" ")} ${C.volume.total} nurses, a ${C.pricing.programGross} program at full deployment, gated growth from there. Thank you — happy to take questions.`);

  let noteScript = document.getElementById("speaker-notes");
  if (!noteScript) {
    noteScript = document.createElement("script");
    noteScript.type = "application/json";
    noteScript.id = "speaker-notes";
    document.body.appendChild(noteScript);
  }
  noteScript.textContent = JSON.stringify(notes);

  // expose accent for role label
  document.documentElement.style.setProperty("--kp-blue", C.accent);
  document.title = `Florence — Full-Time RN Capacity for ${C.displayName}`;
  };

  window.FLORENCE_RENDER();
})();
