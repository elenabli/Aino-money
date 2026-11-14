import { useEffect, useState } from 'react'
import { fetchReceipt, fetchTransactions, type Receipt, type SpendingScope, type TransactionPage } from '../api'

const BASKETS: Record<string, { label: string; reason: string; attention?: boolean }> = {
  mandatory_regular: { label: 'Essentials', reason: 'A regular expense.' },
  mandatory_irregular: { label: 'Essentials', reason: 'An unexpected expense.', attention: true },
  everyday_discretionary: { label: 'Everyday spending', reason: 'Flexible spending.', attention: true },
  savings_investing: { label: 'Savings and investing', reason: 'Money set aside.' },
}

function ReceiptDetails({ customerId, receiptId }: { customerId: string; receiptId: string }) {
  const [open, setOpen] = useState(false)
  const [receipt, setReceipt] = useState<Receipt | null>(null)
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!open || receipt) return
    const request = new AbortController()
    fetchReceipt(customerId, receiptId, request.signal)
      .then(setReceipt)
      .catch(() => { if (!request.signal.aborted) setFailed(true) })
    return () => request.abort()
  }, [open, receipt, customerId, receiptId, attempt])

  return (
    <details className="receipt-details" onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary>View receipt</summary>
      {open && failed && !receipt && (
        <p role="alert">
          Couldn’t load the receipt.{' '}
          <button className="reset-btn" onClick={() => { setFailed(false); setAttempt(attempt + 1) }}>Try again</button>
        </p>
      )}
      {open && !receipt && !failed && <p role="status">Loading receipt…</p>}
      {receipt && (
        <>

          <h4>Spending by category</h4>
          <ul aria-label="Category totals">
            {receipt.categories.map((category) => (
              <li key={category.name}>
                <span>{category.name}</span>
                <strong>€{category.amount_eur.toFixed(2)}</strong>
              </li>
            ))}
          </ul>
          <details className="receipt-details">
            <summary>See items</summary>
            <ul aria-label="Receipt items">
              {receipt.items.map((item, index) => (
                <li key={index}>
                  <span>{item.name}<small>{item.category}</small></span>
                  <strong>€{item.amount_eur.toFixed(2)}</strong>
                </li>
              ))}
            </ul>
          </details>
        </>
      )}
    </details>
  )
}

export function TransactionsView({ customerId, scope, onAsk, onClear }: {
  customerId: string
  scope: SpendingScope
  onAsk: (transactionId: number, question: string) => void
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
          <button className="reset-btn" onClick={onClear}>Clear filters</button>
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
          {data.rows.map((row) => {
            const basket = BASKETS[row.basket]
            return (
              <article className="welcome transaction-row" key={row.id}>
                <div className="transaction-heading">
                  <strong>{row.category}</strong>
                  <strong>€{row.amount_eur.toFixed(2)}</strong>
                </div>
                <small>{row.date}{row.merchant ? ` · ${row.merchant}` : ''}</small>
                {basket && (
                  <p className="transaction-review">
                    <span className={`review-label ${basket.attention ? 'attention' : 'good'}`}>
                      {basket.attention ? 'Pay attention' : 'Good'}
                    </span>
                    {basket.label === 'Essentials' && <strong>Essentials</strong>}
                    <span>{basket.reason}</span>
                  </p>
                )}
                {row.receipt_id && <ReceiptDetails customerId={customerId} receiptId={row.receipt_id} />}
                <button className="reset-btn" onClick={() => onAsk(row.id, `Tell me about this €${row.amount_eur.toFixed(2)} ${row.category.toLowerCase()} purchase.`)}>Learn more</button>
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
