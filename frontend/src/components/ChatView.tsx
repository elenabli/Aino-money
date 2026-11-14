import { useEffect, useRef, useState } from 'react'
import { fetchWelcome, sendChat, type ChatMsg, type ChatResponse, type CoachPrompt, type SpendingScope, type ExperimentDraft } from '../api'
import { Message } from './Message'

const STARTERS = [
  { id: 'weekly_budget', label: 'Check my weekly budget', question: 'How much is safe to spend this week?' },
  { id: 'spending_profile', label: 'See where my money goes', question: 'How is my spending split?' },
  { id: 'dining_savings', label: 'Find savings from eating out', question: 'How much could I save by eating out 20% less?' },
] as const satisfies ReadonlyArray<{ id: CoachPrompt; label: string; question: string }>

export type CoachTurn = {
  question: string
  prompt?: CoachPrompt
  scope?: SpendingScope & { month_offset?: number }
}

export function ChatView({
  customerId,
  active,
  onOpenSimulation,
  onOpenGoals,
  onOpenTransactions,
  onOpenPayday,
  linkedTurn,
  onConsumeTurn,
}: {
  customerId: string
  active: boolean
  onOpenSimulation: () => void
  onOpenGoals: (draft: ExperimentDraft) => void
  onOpenTransactions: (scope: SpendingScope) => void
  onOpenPayday: () => void
  linkedTurn: CoachTurn | null
  onConsumeTurn: () => void
}) {
  const [welcome, setWelcome] = useState<Awaited<ReturnType<typeof fetchWelcome>> | null>(null)
  const [messages, setMessages] = useState<(ChatMsg & Partial<Omit<ChatResponse, 'answer'>>)[]>([])
  const [lastTurn, setLastTurn] = useState<CoachTurn>()
  const [pending, setPending] = useState<CoachTurn | null>(null)
  const [failed, setFailed] = useState<CoachTurn | null>(null)
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (active && (messages.length || pending || failed || linkedTurn)) {
      bottomRef.current?.scrollIntoView({ block: 'end' })
    }
  }, [active, messages, pending, failed, linkedTurn])

  useEffect(() => {
    let active = true
    fetchWelcome(customerId)
      .then((welcome) => { if (active) setWelcome(welcome) })
      .catch(() => {})
    return () => { active = false }
  }, [customerId])

  async function ask({ question, prompt, scope }: CoachTurn) {
    if (!question.trim() || pending) return
    const history: ChatMsg[] = [
      ...messages.map(({ role, content }) => ({ role, content })),
      { role: 'user', content: question.trim() },
    ]
    setPending({ question, prompt, scope })
    setFailed(null)
    if (!prompt) setInput('')
    try {
      const res = await sendChat(history, customerId, prompt, scope)
      setMessages([...messages, history[history.length - 1], {
        role: 'assistant', content: res.answer, trace: res.trace, chart: res.chart, evidence: res.evidence, experiment: res.experiment,
      }])
      setLastTurn({ question, prompt, scope })
    } catch {
      setFailed({ question, prompt, scope })
    } finally {
      setPending(null)
    }
  }

  const displayedTurn = pending ?? failed
  const lastPrompt = lastTurn?.prompt
  const offset = lastTurn?.scope?.month_offset ?? 1

  return (
    <>
      <main>
        <div className="welcome">
          <h1>Meet Aino, your money coach</h1>
          <p>{welcome?.message ?? 'Explore your budget and spending using this persona’s demo transactions.'}</p>
          <div className="chips" aria-label="Starter questions">
            {STARTERS.map(({ id, label, question }) => (
              <button key={id} disabled={!!pending} onClick={() => ask({ question, prompt: id })}>
                {label}
              </button>
            ))}
            <button disabled={!!pending} onClick={() => ask({
              question: 'How much did I spend on taxis last month?', prompt: 'monthly_spending', scope: { category: 'taxis' },
            })}>See last month’s taxi spending</button>
            <button disabled={!!pending} onClick={() => ask({
              question: 'How much did I spend eating out last month?', prompt: 'monthly_spending', scope: { category: 'Restaurants' },
            })}>See last month’s dining spending</button>
          </div>
        </div>

        {messages.map((msg, i) => (
          <Message key={i} msg={msg} onOpenTransactions={onOpenTransactions} onOpenGoals={onOpenGoals} />
        ))}
        {linkedTurn && (
          <div className="welcome">
            <p>{linkedTurn.question}</p>
            <button className="reset-btn" disabled={!!pending} onClick={() => {
              onConsumeTurn()
              ask(linkedTurn)
            }}>Ask about these transactions</button>
          </div>
        )}
        {lastPrompt && !displayedTurn && (
          <div className="chips coach-actions">
            {lastPrompt === 'weekly_budget' && (
              <>
                <button onClick={onOpenPayday}>Check what fits before payday</button>
                <button onClick={onOpenSimulation}>Try a simulated purchase</button>
                <button onClick={() => ask({
                  question: STARTERS[0].question, prompt: STARTERS[0].id,
                })}>Refresh my weekly budget</button>
              </>
            )}
            {lastPrompt === 'monthly_spending' && offset < 24 && (
              <button onClick={() => ask({
                question: 'What about the previous calendar month?', prompt: 'monthly_spending',
                scope: { ...lastTurn?.scope, month_offset: offset + 1 },
              })}>See the previous month</button>
            )}
            {lastPrompt === 'monthly_spending' && lastTurn?.scope?.category === 'Restaurants' && (
              <button onClick={() => ask({
                question: 'What if I ate out 20% less?', prompt: 'dining_savings',
              })}>What if I ate out 20% less?</button>
            )}
            {lastPrompt === 'spending_profile' && (
              <button onClick={() => ask({
                question: STARTERS[0].question, prompt: STARTERS[0].id,
              })}>Check my weekly budget</button>
            )}
          </div>
        )}
        {displayedTurn && <Message msg={{ role: 'user', content: displayedTurn.question }} />}
        {pending && <Message msg={{ role: 'assistant', content: '', pending: true }} />}
        {failed && (
          <div className="welcome">
            <p role="alert">{failed.prompt
              ? 'Aino couldn’t load this answer. Try again.'
              : 'Free-form chat is temporarily unavailable. Try again or choose a starter question.'}</p>
            <button className="reset-btn" onClick={() => ask(failed)}>Retry question</button>
          </div>
        )}
        <div ref={bottomRef} />
      </main>

      <footer>
        {welcome?.chat_available === false ? (
          <p className="coach-note">Use the starter questions in this demo. Free-form chat requires an AI provider.</p>
        ) : (
          <form onSubmit={(e) => {
            e.preventDefault()
            ask({ question: input })
          }}>
            <input
              aria-label="Ask Aino about your money"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about your money…"
              disabled={!!pending}
            />
            <button disabled={!!pending || !input.trim()}>Send</button>
          </form>
        )}
      </footer>
    </>
  )
}
