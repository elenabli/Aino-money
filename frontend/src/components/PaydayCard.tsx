import { useEffect, useState } from 'react'
import { fetchPayday, type PaydayCheck } from '../api'

export function PaydayCard({ customerId }: { customerId: string }) {
  const [purchase, setPurchase] = useState('0')
  const [buffer, setBuffer] = useState('100')
  const [request, setRequest] = useState({ purchase: 0, buffer: 100 })
  const [data, setData] = useState<PaydayCheck>()
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetchPayday(customerId, request.purchase, request.buffer, controller.signal)
      .then(setData)
      .catch(() => { if (!controller.signal.aborted) setError(true) })
    return () => controller.abort()
  }, [customerId, request])

  return (
    <section className="welcome payday-card">
      <h1>Before payday</h1>
      <form className="goal-form" onSubmit={(event) => {
        event.preventDefault()
        setData(undefined)
        setError(false)
        setRequest({ purchase: Number(purchase), buffer: Number(buffer) })
      }}>
        <div className="goal-form-row">
          <label>Purchase (€)<input type="number" min="0" max="10000000" step="0.01" required value={purchase} onChange={(e) => setPurchase(e.target.value)} /></label>
          <label>Keep in reserve (€)<input type="number" min="0" max="10000000" step="0.01" required value={buffer} onChange={(e) => setBuffer(e.target.value)} /></label>
        </div>
        <button className="big-cta">Check affordability</button>
      </form>
      {error && <p role="alert">Couldn’t load the payday estimate. Try again.</p>}
      {!data && !error && <p role="status">Calculating…</p>}
      {data && !data.estimated_payday && <p>There’s no estimated payday for this persona.</p>}
      {data?.estimated_payday && (
        <>
          <div className={`verdict ${data.projected_after_eur >= data.buffer_eur ? 'good' : 'warn'}`}>
            {data.projected_after_eur >= data.buffer_eur ? 'Good · Reserve covered' : 'Pay attention · Below your reserve'}
          </div>
          <p>Estimated room before payday is €{data.room_eur.toFixed(2)}. With this purchase, the projected balance is €{data.projected_after_eur.toFixed(2)}.</p>
          <details className="payday-details">
            <summary>See forecast assumptions</summary>
            <p>Demo date {data.as_of}. Estimated payday {data.estimated_payday}.</p>
            <p>Balance €{data.balance_eur.toFixed(2)} − expected bills €{data.bill_total_eur.toFixed(2)} = €{data.projected_before_eur.toFixed(2)} before this purchase. Reserve €{data.buffer_eur.toFixed(2)}.</p>
            {data.bills.map((bill, index) => <p key={index}>{bill.predicted_date} · {bill.name} · €{bill.amount_eur.toFixed(2)}</p>)}
          </details>
        </>
      )}
    </section>
  )
}
