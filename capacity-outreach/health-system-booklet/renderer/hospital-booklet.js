/* ============================================================
   Florence Hospital Booklet — content + page renderers
   8 pages · 9x6" landscape (864×576) · Lob personalizable booklet
   MAIL-SAFE: permanent RN capacity, effective cost, near-zero risk.
   NO FICA / visa / tax / immigration language anywhere.
   renderHospitalPage(pageId, system, ctx) -> "<div class='page …'>…"
   ctx = { qr (dataURI) }
   ============================================================ */
(function(){
  const esc = s => String(s==null?"":s).replace(/[&<>]/g, m=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[m]));
  // Formatters pass Handlebars tokens through untouched, so the SAME renderer
  // emits real values (preview / PDF) or {{merge_var}} templates (Lob).
  const isTok = v => typeof v === "string" && v.indexOf("{{") === 0;
  const usd = n => isTok(n) ? n : "$" + Math.round(n).toLocaleString("en-US");
  const num = n => isTok(n) ? n : Math.round(n).toLocaleString("en-US");
  const SH = u => u._short || shortName(u.name);  // short name (or token in template mode)

  const PHASE_I = 200, WAVE1 = 50, TERM = 24;
  const META = {
    fromLine: "Florence\n4130 Overland Ave.\nCulver City, CA 90230",
    contactEmail: "partnerships@florenceedu.com",
    contactLead: "Hospital Partnerships",
    urlLabel: "florenceedu.com/sprint",
  };

  function shortName(name){
    let s = name.replace(/\s+(Health System|Healthcare|Health Care|Health|System|Corporation)$/i,"").trim();
    if(s.length>26) s = name.split(/\s+/).slice(0,2).join(" ");
    return s || name;
  }
  function statesLabel(arr){ return arr.slice(0,5).join(" · ") + (arr.length>5 ? " +"+(arr.length-5) : ""); }

  const WM_WHITE = `<img class="wm" src="assets/florence-white.svg" alt="Florence">`;
  const WM_COLOR = `<img class="wm" src="assets/florence-color.svg" alt="Florence">`;
  const CK = '<svg class="hb-ck" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>';

  function lockup(u){
    return `<div class="hb-lockup"><img src="assets/florence-color.svg" alt="Florence"><span class="hb-sep"></span><span class="hb-cli">${esc(u.name)}</span></div>`;
  }

  /* ── 1 · Cover ── */
  function cover(u,c){
    return `<div class="hb-cover">
      <div class="hb-cov-top">
        <div class="hb-lockup on-dark"><img src="assets/florence-white.svg" alt="Florence"><span class="hb-sep"></span><span class="hb-cli">${esc(u.name)}</span></div>
        <span class="hb-conf">For health-system leadership</span>
      </div>
      <div class="hb-cov-mid">
        <div class="hb-eyebrow on-dark">Permanent RN capacity</div>
        <h1 class="hb-hero">${PHASE_I} permanent nurses for ${esc(SH(u))}.</h1>
        <span class="hb-rule"></span>
        <p class="hb-cov-sub">Readiness-scored global RNs, hired direct as your full-time employees — no agency in the middle.</p>
      </div>
      <div class="hb-cov-bot">
        <div class="hb-costcard">
          <span class="n">${usd(u.effectiveLow)}</span>
          <span class="meta"><span class="u">effective / RN / month</span><span class="x">Modeled for your market · billed only after a nurse starts</span></span>
        </div>
        <span class="hb-turn">Inside: the program &amp; the ask →</span>
      </div>
    </div>`;
  }

  /* ── 2 · The opportunity ── */
  function opportunity(u,c){
    return `<div class="hb-pad">
      ${hbHead("The opportunity","02")}
      <div class="hb-two">
        <div>
          <h2 class="hb-h2">U.S. healthcare has a nurse-production problem.</h2>
          <p class="hb-body">The country faces a structural shortfall of registered nurses. Staffing agencies move scarce nurses around the system; they do not create new ones. Florence creates new permanent capacity — and routes it directly onto your payroll.</p>
          <div class="hb-transition">${esc(SH(u))} alone carries an estimated <b>${num(u.totalRnNeed)} RN need</b> across <b>${u.nFacilities} facilities</b>.</div>
        </div>
        <div class="hb-statbox">
          <div class="hb-stat">189,100</div>
          <div class="hb-stat-l">projected U.S. RN openings per year, through 2032</div>
        </div>
      </div>
    </div>`;
  }

  /* ── 3 · What you get ── */
  function whatyouget(u,c){
    const short = SH(u);
    return `<div class="hb-pad">
      ${hbHead("What you get","03")}
      <h2 class="hb-h2 narrow">Permanent RNs, hired direct — not contractors.</h2>
      <p class="hb-body wide">Florence produces employer-ready RN slates. ${esc(short)} interviews, hires, and onboards them as full-time employees through your standard process. No agency markup, no rotating travelers, no loss of control.</p>
      <div class="hb-roles">
        <div class="hb-role fl"><div class="rl">Florence produces</div><div class="rw">Readiness-scored global RNs</div><div class="rt">Academy, licensure, and employer-ready packets — new cohorts every month.</div></div>
        <div class="hb-role"><div class="rl">${esc(short)} employs</div><div class="rw">Your process, full control</div><div class="rt">Interview, hire, and onboard permanent employees through your own gates.</div></div>
      </div>
    </div>`;
  }

  /* ── 4 · Commercial structure / near-zero risk ── */
  function risk(u,c){
    const items = [
      ["No upfront fee","Nothing is owed to begin."],
      ["Billed only after a nurse starts","You pay against working capacity, not promises."],
      ["Billing stops if a nurse leaves","Risk sits with Florence, not your budget."],
      ["Your own hiring gates","Every candidate clears your standard process first."],
    ];
    return `<div class="hb-pad">
      ${hbHead("Commercial structure","04")}
      <h2 class="hb-h2 narrow">Near-zero risk, by design.</h2>
      <div class="hb-risk-grid">
        ${items.map(([t,d])=>`<div class="hb-risk-card"><span class="hb-risk-ck">${CK}</span><div class="hb-risk-t">${esc(t)}</div><div class="hb-risk-d">${esc(d)}</div></div>`).join("")}
      </div>
      <div class="hb-term">${TERM}-month service term · permanent RNs on your payroll · month-over-month capacity you control.</div>
    </div>`;
  }

  /* ── 5 · Effective cost ── */
  function cost(u,c){
    return `<div class="hb-pad">
      ${hbHead("Effective cost","05")}
      <div class="hb-cost-grid">
        <div class="hb-cost-l">
          <h2 class="hb-h2">${usd(u.effectiveLow)} effective, per RN, per month.</h2>
          <p class="hb-body">Your effective monthly cost lands well below the list rate — and you are billed only once a nurse is working. The number below is modeled for the ${esc(SH(u))} market.</p>
          <div class="hb-cost-note">Estimate based on prevailing market wages and your facility mix. Exact figures confirmed in the design sprint.</div>
        </div>
        <div class="hb-cost-r">
          <div class="hb-cost-row"><span class="cl">List monthly rate</span><span class="cv strike">${usd(u.medianFee)}</span></div>
          <div class="hb-cost-arrow">↓ modeled for your market</div>
          <div class="hb-cost-row big"><span class="cl">Effective monthly cost</span><span class="cv">${usd(u.effectiveLow)}</span></div>
          <div class="hb-cost-foot">per RN · billed only after a nurse starts</div>
        </div>
      </div>
    </div>`;
  }

  /* ── 6 · Activation waves ── */
  function waves(u,c){
    const wave2 = PHASE_I - WAVE1;
    return `<div class="hb-pad">
      ${hbHead("Activation","06")}
      <h2 class="hb-h2 narrow">Start small. Scale on proof.</h2>
      <div class="hb-waves">
        <div class="hb-wv"><div class="wl">Wave 1</div><div class="wn">${WAVE1}</div><div class="wp">First slate. Process, credentialing, and manager acceptance proven on real hires.</div></div>
        <div class="hb-arrow">→</div>
        <div class="hb-wv fin"><div class="wl">Wave 2</div><div class="wn">${wave2}</div><div class="wp">Scale to the ${PHASE_I}-RN Phase I once the first slate is validated.</div></div>
        <div class="hb-arrow">→</div>
        <div class="hb-wv"><div class="wl">Then</div><div class="wn sm">Gated growth</div><div class="wp">Expansion only after quality and retention clear your thresholds.</div></div>
      </div>
    </div>`;
  }

  /* ── 7 · How it works ── */
  function loop(u,c){
    const stages = ["Source","Screen","Admit","Finance","Prepare","Interview","Start","Service","Recycle"];
    const node = "Interview";
    const chips = stages.map(s=>`<span class="hb-chip ${s===node?'is-you':''}">${esc(s)}</span>`).join('<span class="hb-arw">→</span>');
    return `<div class="hb-pad">
      ${hbHead("How it works","07")}
      <h2 class="hb-h2 narrow">A closed loop. Florence runs the rail.</h2>
      <div class="hb-pipeline">${chips}</div>
      <p class="hb-body wide">Florence sources and screens globally, then routes employer-ready candidates to your team. You interview and hire. From there — onboarding, servicing, and the next cohort — Florence operates the rail. Every cohort makes the next one better.</p>
      <div class="hb-split">
        <div class="hb-split-cell fl"><div class="ss-who">Florence</div><div class="ss-does">Source, finance, prepare, service.</div></div>
        <div class="hb-split-cell"><div class="ss-who">${esc(SH(u))}</div><div class="ss-does">Interview, hire, employ.</div></div>
      </div>
    </div>`;
  }

  /* ── 8 · Back cover / the ask ── */
  function ask(u,c){
    const weeks = [
      ["Wk 1","You select facilities, roles, and start windows."],
      ["Wk 2","Onboarding &amp; credentialing gates mapped to your process."],
      ["Wk 3","First candidate slate — real people, readiness scores."],
      ["Wk 4","Metrics, structure, and a clean go / no-go."],
    ];
    return `<div class="hb-ask">
      <div class="hb-ask-l">
        ${WM_WHITE}
        <div class="hb-ask-k">The ask</div>
        <h2 class="hb-ask-head">Approve a 30-day design sprint.</h2>
        <div class="hb-weeks">
          ${weeks.map(([w,t])=>`<div class="hb-wk"><b>${w}</b><span>${t}</span></div>`).join("")}
        </div>
        <div class="hb-ask-row">
          <div class="qr-box"><img src="${c.qr}" alt="Book a design sprint"></div>
          <div class="hb-ask-ct">
            <div class="u">${esc(c.urlLabel || META.urlLabel)}</div>
            <div class="lead">${esc(META.contactLead)}</div>
            <div class="em">${esc(META.contactEmail)}</div>
          </div>
        </div>
      </div>
      <div class="hb-ask-r">
        ${WM_COLOR}
        <div class="hb-from">${esc(META.fromLine)}</div>
        <div class="inkfree" style="left:34px;right:34px;bottom:40px;height:150px;"><span class="note">↓ Lob prints the delivery address + barcode here ↓</span></div>
      </div>
    </div>`;
  }

  function hbHead(kick,no){ return `<div class="hb-khead"><span class="hb-kick">${esc(kick)}</span><span class="hb-pno">${esc(no)}</span></div>`; }

  const RENDER = {cover, opportunity, whatyouget, risk, cost, waves, loop, ask};

  window.renderHospitalPage = function(pageId, u, c){
    const fn = RENDER[pageId] || (()=>`<div class="hb-pad"></div>`);
    const theme = (c && c.theme) ? c.theme : "teal";
    return `<div class="page hb theme-${theme}" data-page="${pageId}">${fn(u, c||{})}</div>`;
  };
  window.HOSPITAL_BOOKLET_PAGES = [
    {id:"cover", name:"Cover"},
    {id:"opportunity", name:"The opportunity"},
    {id:"whatyouget", name:"What you get"},
    {id:"risk", name:"Commercial structure"},
    {id:"cost", name:"Effective cost"},
    {id:"waves", name:"Activation"},
    {id:"loop", name:"How it works"},
    {id:"ask", name:"The ask"},
  ];
  window.HB_SHORT = shortName;
  window.HB_STATES = statesLabel;
  // Template-mode system object: every per-system field is a Handlebars merge var.
  // Feed this to renderHospitalPage to emit a Lob-ready {{...}} template.
  window.HB_TEMPLATE_SYSTEM = {
    name:"{{system_name}}", _short:"{{short_name}}",
    effectiveLow:"{{effective_cost}}", medianFee:"{{list_rate}}",
    totalRnNeed:"{{rn_need}}", nFacilities:"{{n_facilities}}",
  };
})();
