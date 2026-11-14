import { useEffect, useState } from 'react'
import { fetchPersonas, type Persona } from '../api'
import { SparkIcon } from './icons'

const AVATAR_COLORS = ['#007a4d', '#5b7ea8', '#c2557a', '#8f6bb8', '#e0654a', '#2a9d9d', '#b07d1a']
const euros = new Intl.NumberFormat('fi-FI', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })

/** Start screen: choose whose (synthetic) money to explore before entering the bank app. */
export function PersonaView({
  selected,
  onSelect,
}: {
  selected: string | null
  onSelect: (p: Persona) => void
}) {
  const [personas, setPersonas] = useState<Persona[]>([])
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>('loading')
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    fetchPersonas()
      .then((items) => {
        if (!active) return
        setPersonas(items)
        setStatus(items.length ? 'ready' : 'error')
      })
      .catch(() => {
        if (active) setStatus('error')
      })
    return () => { active = false }
  }, [attempt])

  return (
    <main className="persona-start">
      <section className="persona-hero">
        <span className="avatar ai"><SparkIcon size={22} /></span>
        <h1>Aino Money</h1>
        <p>An AI money coach inside the S-Pankki app. Choose whose money to explore.</p>
        <small>All people and transactions are synthetic demo data.</small>
      </section>

      {status === 'loading' && <p role="status" className="loading">Loading personas…</p>}
      {status === 'error' && (
        <div className="welcome">
          <p role="alert">The demo personas couldn’t load. Check that the backend is running and try again.</p>
          <button className="reset-btn" onClick={() => {
            setStatus('loading')
            setAttempt((n) => n + 1)
          }}>Try again</button>
        </div>
      )}

      <div className="persona-list">
        {personas.map((p, i) => (
          <button
            key={p.id}
            className={`persona-card ${selected === p.id ? 'active' : ''}`}
            onClick={() => onSelect(p)}
          >
            <div className="persona-avatar" style={{ background: AVATAR_COLORS[i % AVATAR_COLORS.length] }}>{p.name[0]}</div>
            <div className="persona-info">
              <strong>{p.name}, {p.age}</strong>
              <span className="persona-label">{p.label}</span>
              <small>{p.description}</small>
              <small className="persona-stats">
                {euros.format(p.median_income_eur)}/mo income · {euros.format(p.balance_eur)} balance
              </small>
            </div>
            <span className="persona-go" aria-hidden="true">{i === 0 ? 'Demo ›' : '›'}</span>
          </button>
        ))}
      </div>
    </main>
  )
}
