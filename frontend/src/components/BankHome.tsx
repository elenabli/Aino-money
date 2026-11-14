import { useEffect, useState } from 'react'
import { fetchWelcome, type AdviserCheckIn, type Persona } from '../api'
import { SendIcon, SparkIcon } from './icons'

const euros = new Intl.NumberFormat('fi-FI', { style: 'currency', currency: 'EUR' })
const whole = new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })

type CheckIn = AdviserCheckIn & { recent_categories?: { category: string; amount_eur: number }[] }

const QUICK = ['What kind of spender am I?', 'Am I spending more than people my age?']

export function BankHome({ persona, failed, onRetry, onChat, onAsk, onAccount, onPersona }: {
  persona: Persona | null
  failed: boolean
  onRetry: () => void
  onChat: () => void
  onAsk: (question: string) => void
  onAccount: () => void
  onPersona: () => void
}) {
  const [checkIn, setCheckIn] = useState<CheckIn | null>(null)
  const [aiReady, setAiReady] = useState(false)
  const [question, setQuestion] = useState('')
  const id = persona?.id

  useEffect(() => {
    if (!id) return
    let current = true
    fetchWelcome(id).then((w) => {
      if (!current) return
      setCheckIn(w.check_in as CheckIn)
      setAiReady(w.chat_available)
    }).catch(() => {})
    return () => { current = false }
  }, [id])

  const top = (checkIn?.recent_categories ?? []).slice(0, 3)
  const max = Math.max(1, ...top.map((row) => row.amount_eur))
  const change = checkIn ? checkIn.spend_eur - checkIn.previous_eur : 0
  const goal = checkIn?.goal

  return (
    <main className="bank-home">
      <div className="home-top">
        <span>Hei{persona ? `, ${persona.name}` : ''} 👋</span>
        <button onClick={onPersona}>{persona ? `${persona.name}, ${persona.age}` : 'Demo profile'} ▾</button>
      </div>

      <section className="aino-hero" aria-label="Aino, your AI money coach">
        <div className="aino-hero-head">
          <span className="avatar ai"><SparkIcon size={18} /></span>
          <div>
            <strong>Aino noticed</strong>
            <small>AI money coach · last 14 days</small>
          </div>
        </div>

        {checkIn ? (
          <>
            <p className="aino-hero-insight">
              You spent <strong>{whole.format(checkIn.spend_eur)}</strong> on everyday things
              {Math.abs(change) >= 1 && <>, <strong className={change > 0 ? 'up' : 'down'}>
                {whole.format(Math.abs(change))} {change > 0 ? 'more' : 'less'}
              </strong> than the two weeks before</>}.
            </p>
            {top.length > 0 && (
              <ul className="aino-bars" aria-label="Biggest everyday categories">
                {top.map((row) => (
                  <li key={row.category}>
                    <span>{row.category}</span>
                    <i style={{ width: `${(row.amount_eur / max) * 100}%` }} />
                    <b>{whole.format(row.amount_eur)}</b>
                  </li>
                ))}
              </ul>
            )}
            {goal && (
              <p className="aino-goal">🎯 {goal.name}: <b>{whole.format(goal.saved_so_far_eur)}</b> of {whole.format(goal.target_eur)}</p>
            )}
          </>
        ) : (
          <p className="aino-hero-insight muted">{failed ? 'Couldn’t load your check-in.' : 'Aino is reading your recent transactions…'}</p>
        )}

        {aiReady ? (
          <>
            <form className="aino-ask" onSubmit={(e) => {
              e.preventDefault()
              if (question.trim()) onAsk(question.trim())
            }}>
              <input aria-label="Ask Aino" value={question} onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask Aino anything…" disabled={!persona} />
              <button aria-label="Ask" disabled={!question.trim()}><SendIcon /></button>
            </form>
            <div className="aino-quick">
              {QUICK.map((q) => <button key={q} disabled={!persona} onClick={() => onAsk(q)}><SparkIcon size={12} />{q}</button>)}
            </div>
          </>
        ) : (
          <button className="big-cta" disabled={!persona} onClick={onChat}>Talk to Aino</button>
        )}
      </section>

      <section className="bank-accounts" aria-labelledby="bank-accounts-title">
        <h2 id="bank-accounts-title">Tilit ja kortit</h2>
        <div className="bank-account-card">
          <button className="bank-account" disabled={!persona} onClick={onAccount}>
            <span>S-Tili</span>
            {persona && <strong>{euros.format(persona.balance_eur)}</strong>}
            {!persona && !failed && <small role="status">Loading balance…</small>}
          </button>
          {failed && !persona && (
            <p role="alert">Couldn’t load the demo account. <button onClick={onRetry}>Try again</button></p>
          )}
          <div className="bank-card-label">
            <strong>S-Etukortti Visa Debit</strong>
            <small>Demokortti · synthetic data</small>
          </div>
        </div>
      </section>
    </main>
  )
}
