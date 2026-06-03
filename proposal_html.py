"""
HTML deck renderer for ProposalData.

Produces a self-contained .html file with embedded CSS — opens in any browser,
prints to PDF cleanly, can be uploaded as-is to a Notion/Slack share link.

Visual style is intentionally brand-neutral for v1; restyle in the CSS block
to match Florence brand once the design system is established.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from proposal_data import (
    HospitalRow,
    ProposalData,
    build_hospital_proposal,
    build_system_proposal,
)


def _fmt_money(v: float) -> str:
    if v is None or not isinstance(v, (int, float)):
        return "—"
    if abs(v) >= 1e9:
        return f"${v/1e9:,.2f}B"
    if abs(v) >= 1e6:
        return f"${v/1e6:,.2f}M"
    if abs(v) >= 1e3:
        return f"${v/1e3:,.2f}K"
    return f"${v:,.2f}"


def _fmt_money_full(v: float) -> str:
    if v is None:
        return "—"
    return f"${v:,.0f}"


def _fmt_pct(v: Optional[float]) -> str:
    if v is None or not isinstance(v, (int, float)):
        return "—"
    return f"{v*100:.1f}%"


def render_html(data: ProposalData) -> str:
    es = data.executive_summary
    m = data.methodology

    # Per-hospital table rows
    hosp_rows = []
    for h in data.hospitals:
        hosp_rows.append(f"""
            <tr>
              <td><strong>{h.name}</strong><br/><span class="muted">{h.city}, {h.state}</span></td>
              <td class="num">{h.rn_need_fte:,.0f}</td>
              <td class="num">${h.loaded_staff_per_hr:.2f}</td>
              <td class="num">${h.agency_per_hr:.2f}</td>
              <td class="num"><strong>${h.delta_per_hr:.2f}</strong></td>
              <td class="num">${h.fee_per_nurse:,.2f}</td>
              <td class="num">${h.florence_net_per_nurse:,.2f}</td>
              <td class="num">{_fmt_pct(h.contract_labor_share)}</td>
            </tr>
        """)
    hosp_table_html = "\n".join(hosp_rows)

    title = data.cover.target_name
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Florence Pricing Proposal — {title}</title>
<style>
:root {{
  --navy: #0b2545;
  --teal: #1e6091;
  --accent: #2db8a3;
  --warn: #c97a3b;
  --bg: #f7f8fb;
  --card: #ffffff;
  --muted: #6b7280;
  --border: #e2e6ee;
  --text: #1a2230;
}}
* {{ box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif;
  margin: 0;
  background: var(--bg);
  color: var(--text);
  line-height: 1.5;
}}
.deck {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
.slide {{
  background: var(--card);
  border-radius: 12px;
  padding: 48px 56px;
  margin-bottom: 24px;
  border: 1px solid var(--border);
  page-break-after: always;
  min-height: 600px;
}}
.slide-number {{ font-size: 11px; color: var(--muted); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 8px; }}
h1 {{ font-size: 36px; margin: 0 0 8px 0; color: var(--navy); letter-spacing: -0.02em; }}
h1.cover {{ font-size: 48px; line-height: 1.1; }}
h2 {{ font-size: 26px; margin: 0 0 12px 0; color: var(--navy); letter-spacing: -0.01em; }}
h3 {{ font-size: 18px; margin: 24px 0 8px 0; color: var(--teal); }}
.subtitle {{ font-size: 17px; color: var(--muted); margin-top: 4px; margin-bottom: 32px; }}
.headline-box {{
  background: linear-gradient(135deg, var(--navy), var(--teal));
  color: white;
  border-radius: 8px;
  padding: 24px 32px;
  margin: 32px 0;
  font-size: 18px;
  line-height: 1.4;
}}
.kpi-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 24px 0; }}
.kpi {{
  background: var(--bg);
  border-radius: 8px;
  padding: 18px 20px;
  border-left: 4px solid var(--teal);
}}
.kpi.accent {{ border-left-color: var(--accent); }}
.kpi.warn {{ border-left-color: var(--warn); }}
.kpi-label {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }}
.kpi-value {{ font-size: 26px; font-weight: 600; color: var(--navy); }}
.kpi-sub {{ font-size: 12px; color: var(--muted); margin-top: 4px; }}
.split-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin: 16px 0 32px; }}
.split-card {{
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 20px;
  text-align: left;
}}
.split-card.hospital {{ border-top: 4px solid var(--teal); }}
.split-card.savings {{ border-top: 4px solid var(--accent); }}
.split-card.partner {{ border-top: 4px solid var(--warn); }}
.split-card.florence {{ border-top: 4px solid var(--navy); background: #f0f5fa; }}
.split-label {{ font-size: 13px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }}
.split-amount {{ font-size: 28px; font-weight: 700; color: var(--navy); margin-top: 6px; }}
.split-note {{ font-size: 12px; color: var(--muted); margin-top: 6px; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 13px; }}
th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
th {{ background: var(--bg); font-weight: 600; color: var(--navy); font-size: 12px; text-transform: uppercase; letter-spacing: 0.5px; }}
td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
.muted {{ color: var(--muted); font-size: 12px; }}
.formula {{
  background: #f0f5fa;
  border-radius: 6px;
  padding: 18px 20px;
  font-family: "SF Mono", Monaco, "Courier New", monospace;
  font-size: 14px;
  margin: 16px 0;
  color: var(--navy);
}}
.calibration-grid {{
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px 28px;
  margin: 16px 0; font-size: 14px;
}}
.calibration-grid div span:first-child {{ color: var(--muted); }}
.disclaimer {{
  background: #fff8e6;
  border-left: 4px solid var(--warn);
  border-radius: 6px;
  padding: 16px 20px;
  font-size: 12px;
  color: #6b5824;
  line-height: 1.6;
  margin-top: 16px;
}}
.footer {{
  font-size: 11px; color: var(--muted); margin-top: 32px;
  padding-top: 16px; border-top: 1px solid var(--border);
}}
.cover-meta {{ margin-top: 64px; font-size: 14px; color: var(--muted); }}
.cover-meta div {{ margin: 4px 0; }}
@media print {{
  body {{ background: white; }}
  .deck {{ padding: 0; max-width: none; }}
  .slide {{ box-shadow: none; border: none; margin: 0; }}
}}
</style>
</head>
<body>
<div class="deck">

<!-- Slide 1: Cover -->
<section class="slide">
  <div class="slide-number">01 — Cover</div>
  <h1 class="cover">{title}</h1>
  <div class="subtitle">{data.cover.subtitle}</div>
  <div class="headline-box">{es.headline_one_liner}</div>
  <div class="cover-meta">
    <div><strong>Type:</strong> {data.cover.target_type}</div>
    <div><strong>Generated:</strong> {data.cover.generated_date}</div>
    <div><strong>Pricing engine:</strong> Florence Labor Economics Agent</div>
    <div><strong>Calibration version:</strong> {data.cover.calibration_version}</div>
  </div>
</section>

<!-- Slide 2: Executive Summary -->
<section class="slide">
  <div class="slide-number">02 — Executive Summary</div>
  <h1>The financial picture</h1>
  <div class="subtitle">What each party gets at full RN-need conversion under the current calibration.</div>

  <div class="split-grid">
    <div class="split-card hospital">
      <div class="split-label">Hospital pays (gross)</div>
      <div class="split-amount">{_fmt_money(es.gross_revenue_total)}</div>
      <div class="split-note">across {es.total_rn_need_fte:,.0f} FTE of RN need</div>
    </div>
    <div class="split-card savings">
      <div class="split-label">Hospital saves vs agency</div>
      <div class="split-amount">{_fmt_money(es.hospital_savings_total)}</div>
      <div class="split-note">vs all-in agency labor over commitment</div>
    </div>
    <div class="split-card partner">
      <div class="split-label">Partner channel revenue</div>
      <div class="split-amount">{_fmt_money(es.partner_revenue_total)}</div>
      <div class="split-note">at {m.partner_share_amn:.0%} share when routed to AMN</div>
    </div>
    <div class="split-card florence">
      <div class="split-label">Florence net revenue</div>
      <div class="split-amount">{_fmt_money(es.florence_net_total)}</div>
      <div class="split-note">after partner split</div>
    </div>
  </div>

  <h3>Market posture</h3>
  <div class="kpi-grid">
    <div class="kpi">
      <div class="kpi-label">Hospitals in scope</div>
      <div class="kpi-value">{es.n_hospitals:,}</div>
      <div class="kpi-sub">{es.n_feasible:,} feasible at current calibration</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Median loaded staff cost</div>
      <div class="kpi-value">${es.median_loaded_staff_per_hr:,.0f}/hr</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Median all-in agency rate</div>
      <div class="kpi-value">${es.median_agency_per_hr:,.0f}/hr</div>
    </div>
    <div class="kpi accent">
      <div class="kpi-label">Median agency premium</div>
      <div class="kpi-value">${es.median_agency_premium_per_hr:,.0f}/hr</div>
      <div class="kpi-sub">spread the engine is converting into pricing</div>
    </div>
  </div>
</section>

<!-- Slide 3: Pricing methodology -->
<section class="slide">
  <div class="slide-number">03 — Methodology</div>
  <h1>Market-sensitive pricing</h1>
  <div class="subtitle">Every hospital gets a price reflecting its local labor economics, not a flat fee.</div>

  <h3>The formula</h3>
  <div class="formula">
    δ<sub>per_hospital</sub> = clamp(α × (M − ζ), δ<sub>floor</sub>, δ<sub>cap</sub>)<br/>
    F<sub>total</sub> = H<sub>c</sub> × δ<sub>chosen</sub> + η × T<sub>emp</sub> × H<sub>exempt</sub><br/><br/>
    Florence net = F<sub>total</sub> × (1 − partner_share)
  </div>
  <p style="font-size: 14px; color: var(--text);">
    <strong>M</strong> = local agency premium (all-in agency hourly rate minus loaded staff cost).
    <strong>α</strong> is Florence's share of that premium; the hospital captures (1 − α).
    <strong>ζ</strong> is the required hospital savings buffer vs agency.
    <strong>η</strong> is the FICA-exempt share of the placed cohort (F-1/J-1 only).
  </p>

  <h3>Calibration values used</h3>
  <div class="calibration-grid">
    <div><span>α (Florence share of M − ζ):</span> <strong>{m.alpha:.2f}</strong></div>
    <div><span>ζ (hospital savings buffer):</span> <strong>${m.zeta:.2f}/hr</strong></div>
    <div><span>δ floor:</span> <strong>${m.delta_floor:.2f}/hr</strong></div>
    <div><span>δ cap:</span> <strong>${m.delta_cap:.2f}/hr</strong></div>
    <div><span>Commitment:</span> <strong>{m.commitment_years} years × {m.annual_hours:,} hrs/yr</strong></div>
    <div><span>Cohort visa-exempt share (η):</span> <strong>{m.cohort_eta:.2f}</strong></div>
    <div><span>Direct enterprise partner share:</span> <strong>{m.partner_share_direct:.0%}</strong></div>
    <div><span>AMN wholesale partner share:</span> <strong>{m.partner_share_amn:.0%}</strong></div>
  </div>
</section>

<!-- Slide 4+: Per-hospital pricing table -->
<section class="slide">
  <div class="slide-number">04 — Per-hospital pricing</div>
  <h1>Hospital-level breakdown</h1>
  <div class="subtitle">
    Top {len(data.hospitals)} hospitals by Florence net revenue. Each price is
    calibrated to that hospital's local labor economics.
  </div>
  <table>
    <thead>
      <tr>
        <th>Hospital</th>
        <th class="num">RN need (FTE)</th>
        <th class="num">Loaded staff $/hr</th>
        <th class="num">Agency $/hr</th>
        <th class="num">δ chosen $/hr</th>
        <th class="num">Fee / nurse</th>
        <th class="num">Florence net / nurse</th>
        <th class="num">CL share</th>
      </tr>
    </thead>
    <tbody>
      {hosp_table_html}
    </tbody>
  </table>
</section>

<!-- Slide 5: Market context -->
<section class="slide">
  <div class="slide-number">05 — Market context</div>
  <h1>Why the pricing works</h1>
  <div class="subtitle">Contract labor share is the empirical signal that an agency premium exists to compete against.</div>

  <div class="kpi-grid">
    <div class="kpi">
      <div class="kpi-label">States covered</div>
      <div class="kpi-value">{len(data.market_context.states_covered)}</div>
      <div class="kpi-sub">{", ".join(data.market_context.states_covered[:5])}{"..." if len(data.market_context.states_covered) > 5 else ""}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Median contract labor share</div>
      <div class="kpi-value">{data.market_context.median_contract_labor_share*100:.1f}%</div>
      <div class="kpi-sub">of total comp paid to agency (HCRIS)</div>
    </div>
    <div class="kpi accent">
      <div class="kpi-label">Hospitals with high CL share</div>
      <div class="kpi-value">{data.market_context.n_hospitals_high_cl:,}</div>
      <div class="kpi-sub">CL ≥ 15% — prime market sensitivity</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Aggregate workforce (HCRIS)</div>
      <div class="kpi-value">{data.market_context.aggregate_total_fte:,.0f}</div>
      <div class="kpi-sub">total FTE across in-scope hospitals</div>
    </div>
  </div>

  <h3>Why this matters</h3>
  <p style="font-size: 14px;">
    Hospitals with a high contract-labor share have a real, durable agency premium.
    Florence's market-sensitive engine sets δ as a function of that premium, so each
    hospital is quoted a price the local market can support — without breaking the
    savings story the CFO needs to approve.
  </p>
</section>

<!-- Slide 6: Tax assumption -->
<section class="slide">
  <div class="slide-number">06 — Tax assumption</div>
  <h1>FICA / visa disclaimer</h1>
  <div class="subtitle">Required reading before relying on the FICA component of this pricing.</div>
  <div class="disclaimer">
    {data.tax_assumption.text}
  </div>
  <div class="footer">
    References: IRC §3121(b)(19); IRS Publication 519; IRS Publication 15 (Circular E).<br/>
    Calibration version: {data.cover.calibration_version} · Generated {data.cover.generated_date}
  </div>
</section>

</div>
</body>
</html>
"""


def save_html(data: ProposalData, output_path: Path) -> Path:
    output_path = Path(output_path)
    output_path.write_text(render_html(data), encoding="utf-8")
    return output_path


if __name__ == "__main__":
    # Smoke test: generate Kaiser HTML deck
    print("Generating Kaiser Permanente HTML deck...")
    data = build_system_proposal("Kaiser Permanente")
    out = save_html(data, Path("proposals/kaiser_permanente.html"))
    print(f"  Wrote {out}")
    print(f"  Open in browser: file://{out.resolve()}")
