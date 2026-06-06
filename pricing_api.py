"""
Florence pricing API — the pricing engine exposed over HTTP.

A thin, stateless FastAPI wrapper around `pricing_engine.price()`. No data files,
no secrets: you POST a hospital wage/agency profile and get back the v2
buyer-facing pricing numbers. This is the shared "pricing brain" that a future
customer-facing React app calls instead of re-implementing the math.

Run locally:
    pip install -r requirements-api.txt
    uvicorn pricing_api:app --reload --port 8000
    open http://localhost:8000/docs        # interactive OpenAPI docs

Endpoints:
    GET  /health   → {"status": "ok"}       (liveness; used by Render + smoke-check)
    GET  /         → service metadata
    POST /price    → PriceResponse
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from pricing_engine import Calibration, CohortMix, HospitalProfile, price

app = FastAPI(
    title="Florence Pricing API",
    version="1.0.0",
    description="Stateless v2 FICA-offset pricing. Wraps pricing_engine.price().",
)

# A React product on another origin calls this. Default open for dev; lock down
# in production by setting PRICING_API_CORS_ORIGINS to a comma-separated allowlist.
_origins = os.environ.get("PRICING_API_CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()] or ["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request models — mirror the engine's dataclasses
# ---------------------------------------------------------------------------
class HospitalProfileIn(BaseModel):
    name: str = Field(..., examples=["Kaiser Permanente — Oakland"])
    state: str = Field(..., examples=["CA"])
    city: str = ""
    role: str = "RN — Med/Surg"
    taxable_wage_per_hour: float = Field(..., ge=0, examples=[66.85])
    benefit_load_per_hour: float = Field(0.0, ge=0, examples=[17.50])
    all_in_agency_per_hour: float = Field(0.0, ge=0, examples=[121.73])
    agency_rate_confidence: float = Field(0.85, ge=0, le=1)
    agency_rate_source: str = "api_request"
    notes: str = ""


class CohortIn(BaseModel):
    eta: float = Field(1.0, ge=0, le=1, description="FICA-eligible share of the cohort")
    eligible_months: Optional[int] = Field(None, ge=0)


class CalibrationIn(BaseModel):
    """All optional. Anything left null inherits the engine's own default, so the
    API never hard-codes pricing constants (no drift if the engine changes)."""
    target_offset_pct: Optional[float] = Field(None, gt=0, le=1)
    price_floor_monthly: Optional[float] = Field(None, ge=0)
    price_ceiling_monthly: Optional[float] = Field(None, ge=0)
    term_months: Optional[int] = Field(None, gt=0)
    direct_partner_markup_pct: Optional[float] = Field(None, ge=0)
    amn_partner_markup_pct: Optional[float] = Field(None, ge=0)
    immigration_addon_enabled: Optional[bool] = None
    use_standard_fee_for_low_confidence: Optional[bool] = None
    standard_monthly_fee: Optional[float] = Field(None, ge=0)


class PriceRequest(BaseModel):
    hospital: HospitalProfileIn
    cohort: CohortIn = CohortIn()
    calibration: CalibrationIn = CalibrationIn()


# ---------------------------------------------------------------------------
# Response model — the stable, curated pricing contract
# ---------------------------------------------------------------------------
class PriceResponse(BaseModel):
    hospital: str
    state: str
    channel: str
    feasible: bool
    manual_review_flag: bool
    manual_review_reason: str

    # v2 primary buyer-facing numbers
    florence_monthly_fee_per_rn: float
    employer_fica_savings_per_rn_per_month: float
    fica_adjusted_effective_cost_per_rn_month: float
    actual_fica_offset_pct: float
    net_monthly_savings_per_rn: float
    # customer-safe headline (no tax mechanics): the travel/agency premium per
    # RN/month the employer stops paying — drives the "Today vs Florence" compare.
    monthly_agency_premium_avoided_per_rn: float

    # fee detail + partner economics (markup atop the protected core fee)
    final_fee_constrained_by: str
    term_months: int
    all_in_florence_fee_per_rn_month: float
    immigration_addon_monthly: float
    partner_markup_pct: float
    partner_revenue_monthly: float
    florence_net_monthly: float
    customer_total_monthly: float


def _calibration_from(cal_in: CalibrationIn) -> Calibration:
    """Only pass through knobs the caller actually set; the rest stay at the
    engine's defaults."""
    overrides = {k: v for k, v in cal_in.model_dump().items() if v is not None}
    return Calibration(**overrides)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/")
def root() -> dict:
    return {
        "service": "Florence Pricing API",
        "version": app.version,
        "docs": "/docs",
        "price": "POST /price",
    }


@app.post("/price", response_model=PriceResponse)
def price_endpoint(req: PriceRequest) -> PriceResponse:
    profile = HospitalProfile(
        name=req.hospital.name, city=req.hospital.city, state=req.hospital.state,
        role=req.hospital.role,
        taxable_wage_per_hour=req.hospital.taxable_wage_per_hour,
        benefit_load_per_hour=req.hospital.benefit_load_per_hour,
        all_in_agency_per_hour=req.hospital.all_in_agency_per_hour,
        agency_rate_confidence=req.hospital.agency_rate_confidence,
        agency_rate_source=req.hospital.agency_rate_source,
        notes=req.hospital.notes,
    )
    cohort = CohortMix(eta=req.cohort.eta, eligible_months=req.cohort.eligible_months)
    r = price(profile, cohort, _calibration_from(req.calibration))

    return PriceResponse(
        hospital=r.hospital, state=req.hospital.state,
        channel=r.channel.value if hasattr(r.channel, "value") else str(r.channel),
        feasible=r.feasible, manual_review_flag=r.manual_review_flag,
        manual_review_reason=r.manual_review_reason,
        florence_monthly_fee_per_rn=r.florence_monthly_fee_per_rn,
        employer_fica_savings_per_rn_per_month=r.employer_fica_savings_per_rn_per_month,
        fica_adjusted_effective_cost_per_rn_month=r.fica_adjusted_effective_cost_per_rn_month,
        actual_fica_offset_pct=r.actual_fica_offset_pct,
        net_monthly_savings_per_rn=r.net_monthly_savings_per_rn,
        monthly_agency_premium_avoided_per_rn=r.monthly_agency_premium_avoided_per_rn,
        final_fee_constrained_by=r.final_fee_constrained_by,
        term_months=r.term_months,
        all_in_florence_fee_per_rn_month=r.all_in_florence_fee_per_rn_month,
        immigration_addon_monthly=r.immigration_addon_monthly,
        partner_markup_pct=r.partner_share,
        partner_revenue_monthly=r.partner_revenue_monthly,
        florence_net_monthly=r.florence_net_monthly,
        customer_total_monthly=r.customer_total_monthly,
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("pricing_api:app", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
