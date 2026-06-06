// Typed client for the Florence pricing API (florence-pricing-api).
//
// NOTE: this is a CUSTOMER-FACING surface. The API returns tax-mechanism fields
// (FICA offset, etc.); they are intentionally NOT modeled here and never shown.
// Only the customer-safe numbers belong in this type.

export const API_URL: string =
  (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

export interface PriceRequest {
  hospital: {
    name: string
    state: string
    city?: string
    taxable_wage_per_hour: number
    benefit_load_per_hour: number
    all_in_agency_per_hour: number
  }
  calibration?: {
    term_months?: number
  }
}

export interface PriceResponse {
  hospital: string
  state: string
  feasible: boolean
  manual_review_flag: boolean
  florence_monthly_fee_per_rn: number
  monthly_agency_premium_avoided_per_rn: number
  customer_total_monthly: number
  term_months: number
}

export async function priceQuote(req: PriceRequest): Promise<PriceResponse> {
  const res = await fetch(`${API_URL}/price`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(req),
  })
  if (!res.ok) {
    const text = await res.text().catch(() => '')
    throw new Error(`Pricing request failed (${res.status}). ${text}`.trim())
  }
  return (await res.json()) as PriceResponse
}
