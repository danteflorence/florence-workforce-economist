import { useState, type FormEvent } from 'react'
import { priceQuote, type PriceResponse } from './api'

const STATES = [
  'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'DC', 'FL', 'GA', 'HI', 'ID',
  'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD', 'MA', 'MI', 'MN', 'MS', 'MO',
  'MT', 'NE', 'NV', 'NH', 'NJ', 'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA',
  'RI', 'SC', 'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
]

const usd0 = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })

export default function Calculator() {
  const [name, setName] = useState('Kaiser Permanente — Oakland')
  const [state, setState] = useState('CA')
  const [wage, setWage] = useState(66.85)
  const [benefit, setBenefit] = useState(17.5)
  const [agency, setAgency] = useState(121.73)
  const [term, setTerm] = useState(24)

  const [result, setResult] = useState<PriceResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      const r = await priceQuote({
        hospital: {
          name,
          state,
          taxable_wage_per_hour: wage,
          benefit_load_per_hour: benefit,
          all_in_agency_per_hour: agency,
        },
        calibration: { term_months: term },
      })
      setResult(r)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  const fee = result?.florence_monthly_fee_per_rn ?? 0
  const today = result?.monthly_agency_premium_avoided_per_rn ?? 0
  const monthlySavings = Math.max(today - fee, 0)
  const termTotal = monthlySavings * (result?.term_months ?? term)
  const showResult = result && result.feasible && !result.manual_review_flag

  return (
    <div className="calc">
      <form className="card inputs" onSubmit={onSubmit}>
        <h2 className="card-title">Your numbers</h2>

        <label className="field">
          <span>Facility</span>
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>

        <div className="row">
          <label className="field">
            <span>State</span>
            <select value={state} onChange={(e) => setState(e.target.value)}>
              {STATES.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span>Placement term</span>
            <select value={term} onChange={(e) => setTerm(Number(e.target.value))}>
              <option value={12}>12 months</option>
              <option value={24}>24 months</option>
              <option value={36}>36 months</option>
            </select>
          </label>
        </div>

        <label className="field">
          <span>RN base wage <em>($ / hour)</em></span>
          <input type="number" step="0.01" min="0" value={wage}
                 onChange={(e) => setWage(Number(e.target.value))} />
        </label>
        <label className="field">
          <span>Benefits load <em>($ / hour)</em></span>
          <input type="number" step="0.01" min="0" value={benefit}
                 onChange={(e) => setBenefit(Number(e.target.value))} />
        </label>
        <label className="field">
          <span>Current agency rate <em>(all-in $ / hour)</em></span>
          <input type="number" step="0.01" min="0" value={agency}
                 onChange={(e) => setAgency(Number(e.target.value))} />
        </label>

        <button className="cta" type="submit" disabled={loading}>
          {loading ? 'Calculating…' : 'Calculate my price'}
        </button>
        {error && <p className="error">{error}</p>}
      </form>

      <div className="card results">
        {!result && (
          <div className="placeholder">
            <p>Enter a facility's numbers and we'll show the two prices side by side.</p>
          </div>
        )}

        {result && !showResult && (
          <div className="placeholder">
            <h2 className="card-title">Let's talk</h2>
            <p>
              These inputs fall outside our standard model — your Florence
              representative can put together a tailored quote.
            </p>
          </div>
        )}

        {showResult && (
          <>
            <div className="compare">
              <div className="price-card today">
                <span className="price-label">Today — agency premium</span>
                <span className="price-value">{usd0(today)}</span>
                <span className="price-unit">per nurse / month</span>
              </div>
              <div className="vs">vs</div>
              <div className="price-card florence">
                <span className="price-label">With Florence</span>
                <span className="price-value">{usd0(fee)}</span>
                <span className="price-unit">per nurse / month</span>
              </div>
            </div>

            <div className="savings">
              <span className="savings-label">You save</span>
              <span className="savings-value">{usd0(monthlySavings)}</span>
              <span className="savings-unit">per nurse, every month</span>
            </div>

            <div className="term-line">
              <strong>{usd0(termTotal)}</strong> saved per nurse over {result.term_months} months
            </div>

            <p className="fineprint">
              {result.hospital}. Florence places permanent nurses you keep — not a
              rotating travel roster. Final pricing is confirmed in your proposal.
            </p>
          </>
        )}
      </div>
    </div>
  )
}
