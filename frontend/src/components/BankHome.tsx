import type { Persona } from '../api'
import { ChatIcon } from './icons'

const euros = new Intl.NumberFormat('fi-FI', { style: 'currency', currency: 'EUR' })

export function BankHome({ persona, failed, onRetry, onChat, onAccount, onPersona }: {
  persona: Persona | null
  failed: boolean
  onRetry: () => void
  onChat: () => void
  onAccount: () => void
  onPersona: () => void
}) {
  return (
    <main className="bank-home">
      <section className="bank-home-entry" aria-label="Money coach">
        <button className="bank-coach" disabled={!persona} onClick={onChat}>
          <span className="bank-coach-icon"><ChatIcon size={23} /></span>
          <span><strong>Your Aino check-in</strong><small>Recent spending and what you can change</small></span>
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
            {persona && <strong>{euros.format(persona.balance_eur)}</strong>}
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
