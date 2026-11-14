import { useEffect, useState } from 'react'
import { fetchPersonas, type Persona } from '../api'

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
    <main>
      <div className="welcome">
        <h1>Choose a demo persona</h1>
        <p>
          Pick a persona to open their coach and explore their synthetic transactions.
        </p>
      </div>

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
        {personas.map((p) => (
          <button
            key={p.id}
            className={`persona-card ${selected === p.id ? 'active' : ''}`}
            onClick={() => onSelect(p)}
          >
            <div className="persona-avatar">{p.name[0]}</div>
            <div className="persona-info">
              <strong>
                {p.name}, {p.age} · {p.label}
              </strong>
              <small>{p.description}</small>
              <small className="persona-stats">
                income {p.median_income_eur.toFixed(0)} €/mo · balance {p.balance_eur.toFixed(0)} €
              </small>
            </div>
            <span className="persona-check">{selected === p.id ? 'Active' : ''}</span>
          </button>
        ))}
      </div>
    </main>
  )
}
