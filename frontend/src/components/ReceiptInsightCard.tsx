import type { ReceiptInsight } from '../api'

const KIND_COLORS: Record<string, string> = {
  staple: '#007a4d',
  treat: '#f2a33a',
  convenience: '#e0654a',
  household: '#5b7ea8',
  fun: '#8f6bb8',
  transport: '#7a8a82',
}
const STAPLE_SHADES = ['#007a4d', '#3fae6a', '#2a9d9d', '#7cc49a', '#0f5e3e']

const eur = (v: number) => `€${v.toFixed(2)}`
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })

/** One classified receipt: composition, then per-category month pace with an evaluation. */
export function ReceiptInsightCard({ data }: { data: ReceiptInsight }) {
  const colors = data.groups.map((g, i) => {
    if (g.kind !== 'staple') return KIND_COLORS[g.kind]
    const nth = data.groups.slice(0, i).filter((prev) => prev.kind === 'staple').length
    return STAPLE_SHADES[nth % STAPLE_SHADES.length]
  })

  return (
    <figure className="receipt-card">
      <header className="receipt-card-head">
        <span className="receipt-icon" aria-hidden="true">🧾</span>
        <div>
          <strong>{data.merchant}</strong>
          <small>{day(data.date)}{data.time ? ` · ${data.time}` : ''} · {data.item_count} items</small>
        </div>
        <b>{eur(data.total_eur)}</b>
      </header>
      <p className="receipt-classified">✦ Every line classified by Aino into product categories</p>

      <div className="receipt-stack" role="img"
        aria-label={data.groups.map((g) => `${g.group} ${eur(g.receipt_eur)}`).join(', ')}>
        {data.groups.map((g, i) => (
          <i key={g.group} style={{ flexGrow: g.receipt_eur, background: colors[i] }} title={`${g.group} ${eur(g.receipt_eur)}`} />
        ))}
      </div>

      <div className="receipt-cols" aria-hidden="true">
        <span>Category · on this receipt</span>
        <span>{data.month_label}</span>
      </div>

      <ul className="receipt-groups">
        {data.groups.map((g, i) => {
          const scale = Math.max(g.month_eur, g.usual_eur, 1)
          return (
            <li key={g.group}>
              <details>
                <summary>
                  <span className="rg-dot" style={{ background: colors[i] }} />
                  <span className="rg-name">
                    <strong>{g.group}</strong>
                    <small>{g.kind_label} · {eur(g.receipt_eur)}</small>
                  </span>
                  <span className={`rg-eval ${g.eval.tone}`}>{g.eval.label}</span>
                </summary>
                <div className="rg-items">
                  <p>{g.eval.text}</p>
                  <ul>
                    {g.items.map((item, j) => (
                      <li key={j}><span>{item.name}<small>{item.category}</small></span><b>{eur(item.amount_eur)}</b></li>
                    ))}
                  </ul>
                </div>
              </details>
              <div className="rg-pace">
                <div className="rg-track">
                  <i className={g.eval.tone} style={{ width: `${(g.month_eur / scale) * 100}%` }} />
                  {g.usual_eur > 0 && <em style={{ left: `${(g.usual_eur / scale) * 100}%` }} title="Your usual" />}
                </div>
                <small><b>{eur(g.month_eur)}</b> so far · usual {eur(g.usual_eur)}</small>
              </div>
            </li>
          )
        })}
      </ul>
      <p className="chart-note">{data.comparison_note}. Tap a category to see its items.</p>
    </figure>
  )
}
