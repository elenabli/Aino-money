import { useState } from 'react'
import { clearSimulated, fetchRandomTx, simulateTx, type SimulateResult } from '../api'

const BASKET_LABELS: Record<string, string> = {
  mandatory_regular: 'Must-pay',
  mandatory_irregular: 'Unexpected',
  everyday_discretionary: 'Everyday',
  savings_investing: 'Saving',
}

export function SimulateView({
  customerId,
  onReturnToCoach,
}: {
  customerId: string
  onReturnToCoach: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [results, setResults] = useState<SimulateResult[]>([])
  const [current, setCurrent] = useState<SimulateResult | null>(null)

  async function spawn() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const tx = await fetchRandomTx(customerId)
      const res = await simulateTx(tx, customerId)
      setResults((rs) => [res, ...rs])
      setCurrent(res)
    } catch {
      setError('Couldn’t simulate a purchase. Try again.')
    } finally {
      setBusy(false)
    }
  }

  async function reset() {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await clearSimulated(customerId)
      setResults([])
      setCurrent(null)
    } catch {
      setError('Couldn’t reset simulated spending. Try again.')
    } finally {
      setBusy(false)
    }
  }

  const cls = current?.classification
  const conf = cls ? Math.round((cls.confidence ?? 0) * 100) : 0

  return (
    <main>
      <div className="welcome">
        <h1>Simulate a new spend</h1>
        <p>
          Replay a purchase from this persona’s history and see how it changes their demo budget.
        </p>
        <button className="big-cta" onClick={spawn} disabled={busy}>
          {busy ? 'Working…' : 'Simulate a random spend'}
        </button>
        <button className="reset-btn" onClick={reset} disabled={busy}>
          Reset all simulated spends
        </button>
      </div>

      {busy && !current && (
        <div className="sim-card pending">
          <span className="dots">
            <i /> <i /> <i />
          </span>{' '}
          Checking the purchase…
        </div>
      )}

      {error && <div className="verdict bad" role="alert">{error}</div>}

      {current && (
        <div className="sim-card">
          <div className="sim-head">
            <div>
              <strong>{current.description}</strong>
              <small>
                {current.category} · {current.amount.toFixed(2)} €
              </small>
            </div>
            <div className={`basket-chip ${current.tone}`}>
              {BASKET_LABELS[current.classification.basket] ?? current.classification.basket}
              <small>{cls?.source === 'rules' ? 'Demo rules' : `Jev · ${conf}%`}</small>
            </div>
          </div>

          <div className="sim-rows">
            <div className="sim-row">
              <span>{current.category} this month</span>
              <strong>
                {current.category_month_spent_eur.toFixed(2)} →{' '}
                {current.category_month_after_eur.toFixed(2)} €
              </strong>
            </div>
            <div className="sim-row">
              <span>Balance</span>
              <strong>
                {current.balance_now_eur.toFixed(2)} → {current.balance_after_eur.toFixed(2)} €
              </strong>
            </div>
            <div className="sim-row">
              <span>Estimated safe-to-spend per week</span>
              <strong>
                {current.safe_to_spend_weekly_eur.toFixed(2)} →{' '}
                {current.safe_to_spend_weekly_after_eur.toFixed(2)} €
              </strong>
            </div>
          </div>

          <div className={`verdict ${current.tone}`}>{current.verdict}</div>
          <button className="reset-btn" onClick={onReturnToCoach}>Back to Aino</button>
        </div>
      )}

      {results.length > 0 && (
        <div className="sim-history">
          {results.map((r, i) => (
            <div key={i} className="sim-history-row">
              <span>{r.description}</span>
              <strong>{r.amount.toFixed(2)} €</strong>
              <small className={`basket-chip ${r.tone}`}>
                {BASKET_LABELS[r.classification.basket] ?? r.classification.basket}
              </small>
            </div>
          ))}
        </div>
      )}
    </main>
  )
}
