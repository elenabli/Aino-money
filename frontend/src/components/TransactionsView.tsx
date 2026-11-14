import { useEffect, useState } from 'react'
import { fetchTransactions, type SpendingScope, type TransactionPage } from '../api'

const BASKETS: Record<string, { label: string; reason: string; attention?: boolean }> = {
  mandatory_regular: { label: 'Regular essentials', reason: 'Classified as a bill or recurring essential.' },
  mandatory_irregular: { label: 'Unexpected essentials', reason: 'Classified as a necessary expense outside the usual pattern.', attention: true },
  everyday_discretionary: { label: 'Everyday spending', reason: 'Classified as flexible spending you can review.', attention: true },
  savings_investing: { label: 'Savings and investing', reason: 'Classified as money you set aside.' },
}

export function TransactionsView({ customerId, scope, onAsk, onClear }: {
  customerId: string
  scope: SpendingScope
  onAsk: (scope: SpendingScope, question: string) => void
  onClear: () => void
}) {
  const [data, setData] = useState<TransactionPage | null>(null)
  const [offset, setOffset] = useState(0)
  const [filter, setFilter] = useState(scope.attention ?? false)
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    const request = new AbortController()
    fetchTransactions(customerId, { ...scope, attention: filter }, offset, request.signal)
      .then((page) => { setData(page); setStatus('ready') })
      .catch(() => { if (!request.signal.aborted) setStatus('error') })
    return () => request.abort()
  }, [customerId, scope, filter, offset, attempt])

  function changePage(next: number) {
    setStatus('loading')
    setOffset(next)
  }

  return (
    <main>
      <section className="welcome">
        <h1>Transactions</h1>
        <p>Recorded demo spending. Aino flags flexible and unexpected expenses you might want to review.</p>
        {(scope.category || scope.basket || scope.start) && (
          <button className="reset-btn" onClick={onClear}>Show all recent spending</button>
        )}
        <div className="track-chips transaction-filters">
          <button aria-pressed={!filter} className={filter ? '' : 'active'} onClick={() => {
            if (filter) { setStatus('loading'); setFilter(false); setOffset(0) }
          }}>All</button>
          <button aria-pressed={filter} className={filter ? 'active' : ''} onClick={() => {
            if (!filter) { setStatus('loading'); setFilter(true); setOffset(0) }
          }}>Pay attention</button>
        </div>
      </section>
      {status === 'loading' && <p className="loading" role="status">Loading transactions…</p>}
      {status === 'error' && (
        <div className="welcome" role="alert">
          <p>Couldn’t load transactions.</p>
          <button className="reset-btn" onClick={() => { setStatus('loading'); setAttempt(attempt + 1) }}>Try again</button>
        </div>
      )}
      {status === 'ready' && data && (
        <>
          <section className="welcome transaction-summary">
            <strong>{scope.category ?? (scope.basket ? BASKETS[scope.basket]?.label : 'Spending')} · €{data.total_eur.toFixed(2)}</strong>
            <p>{data.start} to {data.end} · {data.count} matching</p>
          </section>
          {data.rows.map((row, index) => {
            const basket = BASKETS[row.basket]
            return (
              <article className="welcome transaction-row" key={offset + index}>
                <div className="transaction-heading">
                  <strong>{row.category}</strong>
                  <strong>€{row.amount_eur.toFixed(2)}</strong>
                </div>
                <small>{row.date}{row.merchant ? ` · ${row.merchant}` : ''}</small>
                {basket && (
                  <p><span className={`review-label ${basket.attention ? 'attention' : 'good'}`}>
                    {basket.attention ? 'Pay attention' : 'Good'}
                  </span> {basket.label}. {basket.reason}</p>
                )}
                <button className="reset-btn" onClick={() => onAsk({
                  category: scope.category ?? row.category, basket: scope.basket, start: row.date, end: row.date,
                }, `How much did I spend on ${(scope.category ?? row.category).toLowerCase()} on ${row.date}?`)}>Ask Aino about this spending</button>
              </article>
            )
          })}
          {data.count === 0 && <p className="coach-note">No transactions match these filters.</p>}
          {data.count > 25 && (
            <div className="transaction-pages">
              <button className="reset-btn" disabled={offset === 0} onClick={() => changePage(offset - 25)}>Previous</button>
              <button className="reset-btn" disabled={offset + 25 >= data.count} onClick={() => changePage(offset + 25)}>Next</button>
            </div>
          )}
        </>
      )}
    </main>
  )
}
