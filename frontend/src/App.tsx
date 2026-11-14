import { useState } from 'react'
import { type Persona } from './api'
import { ChatView } from './components/ChatView'
import { GoalsView } from './components/GoalsView'
import { MonthView } from './components/MonthView'
import { PersonaView } from './components/PersonaView'
import { SimulateView } from './components/SimulateView'
import { ChartIcon, ChatIcon, DiceIcon, TargetIcon, UserIcon } from './components/icons'

const TABS = [
  { id: 'persona', label: 'Persona', Icon: UserIcon },
  { id: 'chat', label: 'Coach', Icon: ChatIcon },
  { id: 'month', label: 'Month', Icon: ChartIcon },
  { id: 'goals', label: 'Goals', Icon: TargetIcon },
  { id: 'sim', label: 'Simulate', Icon: DiceIcon },
] as const

type Tab = (typeof TABS)[number]['id']

function storedPersona(): Persona | null {
  try {
    const raw = localStorage.getItem('spanki_persona')
    if (!raw) return null
    const persona = JSON.parse(raw)
    return typeof persona?.id === 'string' && typeof persona.name === 'string' ? persona : null
  } catch {
    return null
  }
}

export default function App() {
  const [persona, setPersona] = useState(storedPersona)
  const [tab, setTab] = useState<Tab>(persona ? 'chat' : 'persona')
  const [hasOpenedSimulation, setHasOpenedSimulation] = useState(false)
  const [simulationVersion, setSimulationVersion] = useState(0)

  function openTab(next: Tab) {
    if (next === 'sim') setHasOpenedSimulation(true)
    setTab(next)
  }

  function selectPersona(p: Persona) {
    if (persona?.id !== p.id) setHasOpenedSimulation(false)
    setPersona(p)
    setTab('chat')
    try {
      localStorage.setItem('spanki_persona', JSON.stringify(p))
    } catch {
      // The demo still works when the browser blocks storage.
    }
  }

  const cid = persona?.id

  return (
    <div className="phone">
      <header>
        <div className="avatar">{persona ? persona.name[0] : 'S'}</div>
        <div className="who">
          <strong>{persona ? `${persona.name}, ${persona.age} · S-Bank demo` : 'Aino · Money coach'}</strong>
          <small>{persona ? `${persona.label} · Synthetic data` : 'Choose a persona to begin'}</small>
        </div>
      </header>

      {tab === 'persona' && (
        <div className="view">
          <PersonaView selected={cid ?? null} onSelect={selectPersona} />
        </div>
      )}
      {cid && (
        <div className="view" style={{ display: tab === 'chat' ? 'flex' : 'none' }}>
          <ChatView key={cid} customerId={cid} active={tab === 'chat'} onOpenSimulation={() => openTab('sim')} onOpenGoals={() => openTab('goals')} />
        </div>
      )}
      {cid && tab === 'month' && (
        <div className="view"><MonthView customerId={cid} /></div>
      )}
      {cid && tab === 'goals' && (
        <div className="view"><GoalsView customerId={cid} onResetSimulation={() => setSimulationVersion((version) => version + 1)} /></div>
      )}
      {cid && hasOpenedSimulation && (
        <div className="view" style={{ display: tab === 'sim' ? 'flex' : 'none' }}>
          <SimulateView key={`${cid}:${simulationVersion}`} customerId={cid} onReturnToCoach={() => openTab('chat')} />
        </div>
      )}

      <nav className="tabbar" aria-label="Demo navigation">
        {TABS.map(({ id, label, Icon }) => (
          <button
            key={id}
            className={tab === id ? 'active' : ''}
            aria-current={tab === id ? 'page' : undefined}
            disabled={id !== 'persona' && !cid}
            onClick={() => openTab(id)}
          >
            <Icon />
            <span>{label}</span>
          </button>
        ))}
      </nav>
    </div>
  )
}
