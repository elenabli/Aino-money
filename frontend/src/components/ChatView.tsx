import { useEffect, useRef, useState } from 'react'
import { fetchWelcome, sendChat, type ChatMsg, type ChatResponse, type CoachPrompt } from '../api'
import { Message } from './Message'

const STARTERS = [
  { id: 'weekly_budget', label: 'Check my weekly budget', question: 'How much is safe to spend this week?' },
  { id: 'spending_profile', label: 'See where my money goes', question: 'How is my spending split?' },
  { id: 'dining_savings', label: 'Find savings from eating out', question: 'How much could I save by eating out 20% less?' },
] as const satisfies ReadonlyArray<{ id: CoachPrompt; label: string; question: string }>

type Turn = { question: string; prompt?: CoachPrompt }

export function ChatView({
  customerId,
  active,
  onOpenSimulation,
  onOpenGoals,
}: {
  customerId: string
  active: boolean
  onOpenSimulation: () => void
  onOpenGoals: () => void
}) {
  const [welcome, setWelcome] = useState<Awaited<ReturnType<typeof fetchWelcome>> | null>(null)
  const [messages, setMessages] = useState<(ChatMsg & Partial<Omit<ChatResponse, 'answer'>>)[]>([])
  const [lastPrompt, setLastPrompt] = useState<CoachPrompt>()
  const [pending, setPending] = useState<Turn | null>(null)
  const [failed, setFailed] = useState<Turn | null>(null)
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (active && (messages.length || pending || failed)) {
      bottomRef.current?.scrollIntoView({ block: 'end' })
    }
  }, [active, messages, pending, failed])

  useEffect(() => {
    let active = true
    fetchWelcome(customerId)
      .then((welcome) => { if (active) setWelcome(welcome) })
      .catch(() => {})
    return () => { active = false }
  }, [customerId])

  async function ask({ question, prompt }: Turn) {
    if (!question.trim() || pending) return
    const history: ChatMsg[] = [
      ...messages.map(({ role, content }) => ({ role, content })),
      { role: 'user', content: question.trim() },
    ]
    setPending({ question, prompt })
    setFailed(null)
    if (!prompt) setInput('')
    try {
      const res = await sendChat(history, customerId, prompt)
      setMessages([...messages, history[history.length - 1], {
        role: 'assistant', content: res.answer, trace: res.trace, chart: res.chart,
      }])
      setLastPrompt(prompt)
    } catch {
      setFailed({ question, prompt })
    } finally {
      setPending(null)
    }
  }

  const displayedTurn = pending ?? failed

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
          </div>
        </div>

        {messages.map((msg, i) => <Message key={i} msg={msg} />)}
        {lastPrompt && !displayedTurn && (
          <div className="chips coach-actions">
            {lastPrompt === 'weekly_budget' && (
              <>
                <button onClick={onOpenSimulation}>Try a simulated purchase</button>
                <button onClick={() => ask({
                  question: STARTERS[0].question, prompt: STARTERS[0].id,
                })}>Refresh my weekly budget</button>
              </>
            )}
            {lastPrompt === 'dining_savings' && <button onClick={onOpenGoals}>Set a goal or try an experiment</button>}
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
