import { useEffect, useState } from 'react'
import { fetchPersonas, type Persona, type SpendingScope, type ExperimentDraft } from './api'
import { ChatView, type CoachTurn } from './components/ChatView'
import { GoalsView } from './components/GoalsView'
import { MonthView } from './components/MonthView'
import { PersonaView } from './components/PersonaView'
import { TransactionsView } from './components/TransactionsView'
import { PaydayCard } from './components/PaydayCard'
import { SimulateView } from './components/SimulateView'
import { ChartIcon, ChatIcon, DiceIcon, HomeIcon, SparkIcon, TargetIcon } from './components/icons'

import { BankHome } from './components/BankHome'

const TABS = [
  { id: 'home', label: 'Koti', Icon: HomeIcon },
  { id: 'chat', label: 'Chat', Icon: ChatIcon },
  { id: 'month', label: 'Spending', Icon: ChartIcon },
  { id: 'goals', label: 'Goals', Icon: TargetIcon },
  { id: 'sim', label: 'Simulate', Icon: DiceIcon },
] as const

type Tab = (typeof TABS)[number]['id'] | 'persona' | 'transactions' | 'payday'

function storedPersona(): Persona | null {
  try {
    const raw = localStorage.getItem('aino_money_persona')
    if (!raw) return null
    const persona = JSON.parse(raw)
    return typeof persona?.id === 'string' && typeof persona.name === 'string' ? persona : null
  } catch {
    return null
  }
}

export default function App() {
  const [persona, setPersona] = useState(storedPersona)
  // The demo always starts by choosing whose money to explore.
  const [tab, setTab] = useState<Tab>('persona')
  const [homeLoadFailed, setHomeLoadFailed] = useState(false)
  const [homeAttempt, setHomeAttempt] = useState(0)
  const personaId = persona?.id

  useEffect(() => {
    let current = true
    fetchPersonas().then((profiles) => {
      if (!current) return
      const selected = profiles.find((profile) => profile.id === personaId)
        ?? profiles.find((profile) => profile.id === 'DEMO-SETUKORTTI')
        ?? profiles[0]
      if (selected) setPersona(selected)
      else setHomeLoadFailed(true)
    }).catch(() => { if (current) setHomeLoadFailed(true) })
    return () => { current = false }
  }, [personaId, homeAttempt])
  const [hasOpenedSimulation, setHasOpenedSimulation] = useState(false)
  const [simulationVersion, setSimulationVersion] = useState(0)
  const [scope, setScope] = useState<SpendingScope>({})
  const [draft, setDraft] = useState<ExperimentDraft>()
  const [linkedTurn, setLinkedTurn] = useState<CoachTurn | null>(null)

  function openTransactions(nextScope: SpendingScope = {}) {
    setScope(nextScope)
    setTab('transactions')
  }

  function openTab(next: Tab) {
    if (next === 'goals') setDraft(undefined)
    if (next === 'sim') setHasOpenedSimulation(true)
    setTab(next)
  }

  function selectPersona(p: Persona) {
    if (persona?.id !== p.id) {
      setHasOpenedSimulation(false)
      setScope({})
      setLinkedTurn(null)
      setDraft(undefined)
    }
    setPersona(p)
    setTab('home')
    try {
      localStorage.setItem('aino_money_persona', JSON.stringify(p))
    } catch {
      // The demo still works when the browser blocks storage.
    }
  }

  const cid = persona?.id

  return (
    <div className="phone">
      {tab !== 'home' && tab !== 'persona' && <header>
        <div className={tab === 'chat' ? 'avatar ai' : 'avatar'}>{tab === 'chat' ? <SparkIcon /> : persona ? persona.name[0] : 'S'}</div>
        <div className="who">
          <strong>{tab === 'chat' ? <>Aino<span className="ai-badge">AI COACH</span></> : persona ? `${persona.name}, ${persona.age} · Aino Money` : 'Aino Money · Money coach'}</strong>
          <small>{tab === 'chat' && persona ? `Talks with ${persona.name}’s own transactions · synthetic data` : persona ? `${persona.label} · Synthetic data` : 'Choose a persona to begin'}</small>
        </div>
      </header>}

      {tab === 'home' && (
        <div className="view">
          <BankHome
            persona={persona}
            failed={homeLoadFailed}
            onRetry={() => { setHomeLoadFailed(false); setHomeAttempt((attempt) => attempt + 1) }}
            onChat={() => openTab('chat')}
            onAccount={() => openTransactions()}
            onPersona={() => openTab('persona')}
          />
        </div>
      )}

      {tab === 'persona' && (
        <div className="view">
          <PersonaView selected={cid ?? null} onSelect={selectPersona} />
        </div>
      )}
      {cid && (
        <div className="view" style={{ display: tab === 'chat' ? 'flex' : 'none' }}>
          <ChatView
            key={cid}
            customerId={cid}
            firstName={persona!.name}
            active={tab === 'chat'}
            linkedTurn={linkedTurn}
            onConsumeTurn={() => setLinkedTurn(null)}
            onOpenSimulation={() => openTab('sim')}
            onOpenPayday={() => openTab('payday')}
            onOpenTransactions={openTransactions}
            onViewGoal={() => openTab('goals')}
            onOpenGoals={(experiment) => { setDraft(experiment); setTab('goals') }}
          />
        </div>
      )}
      {cid && tab === 'month' && (
        <div className="view"><MonthView customerId={cid} onOpenTransactions={openTransactions} onOpenPayday={() => openTab('payday')}
          onAskGroceryPlan={() => {
            setLinkedTurn({ question: 'How can I spend less on groceries?', prompt: 'grocery_plan' })
            setTab('chat')
          }} /></div>
      )}
      {cid && tab === 'goals' && (
        <div className="view"><GoalsView customerId={cid} draft={draft} onResetSimulation={() => setSimulationVersion((version) => version + 1)}
          onAsk={(question) => { setLinkedTurn({ question }); setTab('chat') }} /></div>
      )}
      {cid && tab === 'transactions' && (
        <div className="view">
          <TransactionsView
            key={JSON.stringify(scope)}
            customerId={cid}
            scope={scope}
            onClear={() => openTransactions()}
            onAskReceipt={(receiptId) => {
              setLinkedTurn({ question: 'What does this receipt tell me about my spending?', scope: { receipt_id: receiptId } })
              setTab('chat')
            }}
            onAsk={(transactionId, question) => {
              setLinkedTurn({ question, scope: { transaction_id: transactionId } })
              setTab('chat')
            }}
          />
        </div>
      )}
      {cid && tab === 'payday' && (
        <div className="view"><main><PaydayCard customerId={cid} /></main></div>
      )}
      {cid && hasOpenedSimulation && (
        <div className="view" style={{ display: tab === 'sim' ? 'flex' : 'none' }}>
          <SimulateView key={`${cid}:${simulationVersion}`} customerId={cid} onReturnToCoach={() => openTab('chat')} />
        </div>
      )}

      {tab !== 'persona' && <nav className="tabbar" aria-label="Demo navigation">
        {TABS.filter(({ id }) => id !== 'sim' || tab === 'sim').map(({ id, label, Icon }) => (
          <button
            key={id}
            className={tab === id || (id === 'month' && (tab === 'transactions' || tab === 'payday')) ? 'active' : ''}
            aria-current={tab === id ? 'page' : undefined}
            disabled={id !== 'home' && !cid}
            onClick={() => openTab(id)}
          >
            <Icon />
            <span>{label}</span>
          </button>
        ))}
      </nav>}
    </div>
  )
}
