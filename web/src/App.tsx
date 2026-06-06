import Calculator from './Calculator'

export default function App() {
  return (
    <div className="page">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">F</span>
          <span className="brand-name">Florence</span>
        </div>
        <span className="brand-tag">Permanent RN staffing</span>
      </header>

      <main className="hero">
        <h1 className="hero-title">Same hours. Two prices.</h1>
        <p className="hero-sub">
          See what permanent Florence nurses cost versus what you pay for travel
          and agency coverage today — per nurse, per month.
        </p>
        <Calculator />
      </main>

      <footer className="foot">
        <span>florenceedu.com</span>
        <span className="foot-note">
          Estimate only. Final pricing is confirmed in your Florence proposal.
        </span>
      </footer>
    </div>
  )
}
