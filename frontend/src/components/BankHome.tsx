import { useEffect, useState } from 'react'
import { fetchWelcome, type AdviserCheckIn, type Persona } from '../api'
import { SparkIcon } from './icons'

const euros = new Intl.NumberFormat('fi-FI', { style: 'currency', currency: 'EUR' })
const whole = new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })

function insight(checkIn: AdviserCheckIn | null): string {
  if (!checkIn) return 'Recent spending and what you can change'
  const change = checkIn.spend_eur - checkIn.previous_eur
  const trend = checkIn.previous_eur > 0 && Math.abs(change) >= 1 ? ` · ${whole.format(Math.abs(change))} ${change > 0 ? 'more' : 'less'} than before` : ''
  return `${whole.format(checkIn.spend_eur)} on everyday things in 2 weeks${trend}`
}

export function BankHome({ persona, failed, onRetry, onChat, onAccount, onPersona }: {
  persona: Persona | null
  failed: boolean
  onRetry: () => void
  onChat: () => void
  onAccount: () => void
  onPersona: () => void
}) {
  const [checkIn, setCheckIn] = useState<AdviserCheckIn | null>(null)
  const id = persona?.id

  useEffect(() => {
    if (!id) return
    let current = true
    fetchWelcome(id).then((w) => { if (current) setCheckIn(w.check_in) }).catch(() => {})
    return () => { current = false }
  }, [id])

  return (
    <main className="bank-home">
      <section className="bank-home-entry" aria-label="Aino, your AI money coach">
        <button className="bank-coach" disabled={!persona} onClick={onChat}>
          <span className="bank-coach-icon ai"><SparkIcon size={21} /></span>
          <span>
            <strong>Aino noticed something <em className="bank-coach-dot" aria-hidden="true" /></strong>
            <small>{insight(checkIn)}</small>
          </span>
          <span aria-hidden="true">›</span>
        </button>
      </section>

      <section className="bank-bonus" aria-labelledby="bank-home-title">
        <div className="bank-home-top">
          <span>Aino Money</span>
          <button onClick={onPersona}>{persona?.name ?? 'Demo profile'}</button>
        </div>
        <h1 id="bank-home-title">Seuraavaan tasoon 98,55 €</h1>
        <p>Kuukauden bonusostot 301,45 €</p>
        <div className="bonus-level next"><span>2,5 %</span><span>400 €</span></div>
        <div className="bonus-level"><span>2,0 %</span><span>300 €</span></div>
        <div className="bonus-house">
          <span>Bonusta tulossa</span>
          <strong>6,03 €</strong>
        </div>
        <small>Esimerkkibonus · demo</small>
      </section>

      <section className="bank-accounts" aria-labelledby="bank-accounts-title">
        <h2 id="bank-accounts-title">Tilit ja kortit</h2>
        <div className="bank-account-card">
          <button className="bank-account" disabled={!persona} onClick={onAccount}>
            <span>S-Tili</span>
            {persona && <strong className={persona.balance_eur < 0 ? 'negative' : undefined}>{euros.format(persona.balance_eur)}</strong>}
            {!persona && !failed && <small role="status">Loading balance…</small>}
          </button>
          {failed && !persona && (
            <p role="alert">Couldn’t load the demo account. <button onClick={onRetry}>Try again</button></p>
          )}
          <div className="bank-card-label">
            <strong>S-Etukortti Visa Debit</strong>
            <small>Demokortti</small>
          </div>
        </div>
      </section>
    </main>
  )
}
