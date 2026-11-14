import { useEffect, useRef, useState } from 'react'
import { fetchWelcome, sendChat, type ChatMsg, type ChatResponse, type ChatTopic, type ChatScope, type SpendingScope, type ExperimentDraft } from '../api'
import { Message } from './Message'
import { CheckIn } from './CheckIn'

const WEEKLY_BUDGET = {
  prompt: 'weekly_budget', label: 'Check my weekly budget', question: 'How much is safe to spend this week?',
} satisfies ChatTopic

const SPENDING_PROFILE = {
  prompt: 'spending_profile', label: 'See where my money goes', question: 'How is my spending split?',
} satisfies ChatTopic

const GROCERIES = {
  label: 'Explore my grocery receipts', question: 'What patterns show up in my grocery receipts?', prompt: 'grocery_plan',
} satisfies ChatTopic

const DINING = {
  label: 'See last month’s dining spending', question: 'How much did I spend eating out last month?',
  prompt: 'monthly_spending', scope: { category: 'Restaurants' },
} satisfies ChatTopic & { scope: ChatScope }

export type CoachTurn = Pick<ChatTopic, 'question' | 'prompt'> & { scope?: ChatScope }

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
  const consumedTurn = useRef<CoachTurn | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (active && (messages.length || pending || failed || linkedTurn)) {
      bottomRef.current?.scrollIntoView({ block: 'end' })
    }
  }, [active, messages, pending, failed, linkedTurn])

  useEffect(() => {
    if (!active) return
    let current = true
    fetchWelcome(customerId)
      .then((welcome) => { if (current) setWelcome(welcome) })
      .catch(() => {})
    return () => { current = false }
  }, [active, customerId])

  async function ask({ question, prompt, scope }: CoachTurn) {
    if (!question.trim() || pending) return
    const history: ChatMsg[] = [
      ...messages.map(({ role, content }) => ({ role, content })),
      { role: 'user', content: question.trim() },
    ]
    setPending({ question, prompt, scope })
    setFailed(null)
    if (!prompt && question === input) setInput('')
    try {
      const res = await sendChat(history, customerId, prompt, scope)
      setMessages([...messages, history[history.length - 1], {
        role: 'assistant', content: res.answer, trace: res.trace, chart: res.chart, evidence: res.evidence,
        experiment: res.experiment, topics: res.topics,
      }])
      setLastTurn({ question, prompt, scope })
    } catch {
      setFailed({ question, prompt, scope })
    } finally {
      setPending(null)
    }
  }

  useEffect(() => {
    if (!active || !linkedTurn || pending || consumedTurn.current === linkedTurn) return
    consumedTurn.current = linkedTurn
    onConsumeTurn()
    void ask(linkedTurn)
  })

  const goal = welcome?.goal_plan
  const displayedTurn = pending ?? failed
  const lastPrompt = lastTurn?.prompt
  const offset = lastTurn?.scope?.month_offset ?? 1

  const responseTopics = messages.at(-1)?.topics
  const starterTopics = (
    <div className="chips" aria-label="Topics to explore">
      {(customerId === 'CUST00001' || customerId === 'CUST02220'
        ? [WEEKLY_BUDGET, SPENDING_PROFILE]
        : [SPENDING_PROFILE, WEEKLY_BUDGET]
      ).map((topic) => <button key={topic.prompt} onClick={() => ask(topic)}>{topic.label}</button>)}
      {welcome?.has_grocery_receipts && <button onClick={() => ask(GROCERIES)}>{GROCERIES.label}</button>}
      <button onClick={() => ask(DINING)}>{DINING.label}</button>
      {goal && <button onClick={() => ask({
        question: 'What’s my first step towards my apartment deposit?', prompt: 'apartment_plan',
      })}>Plan my apartment deposit</button>}
      {welcome?.chat_available && <button onClick={() => ask({
        question: 'What stands out about my spending last month compared with the month before? Use my transactions and explain one change with the category and amounts.',
      })}>Spot a change in my spending</button>}
    </div>
  )

  return (
    <>
      <main>
        {!messages.length && !displayedTurn && !linkedTurn && (
          <section className="welcome chat-overview">
            {welcome?.check_in ? (
              <CheckIn data={welcome.check_in} onOpenTransactions={onOpenTransactions} onOpenPayday={onOpenPayday} />
            ) : (
              <>
                <h1>Your spending check-in</h1>
                <p>{welcome?.message ?? 'Aino can help you explore your spending and budget.'}</p>
              </>
            )}
            {starterTopics}
          </section>
        )}

        {messages.map((msg, i) => (
          <Message key={i} msg={msg} onOpenTransactions={onOpenTransactions} onOpenGoals={onOpenGoals} />
        ))}
        {!displayedTurn && !!responseTopics?.length && (
          <section className="welcome chat-overview" aria-label="Suggested topics">
            <h2>Explore this spending</h2>
            <div className="chips">
              {responseTopics.map(({ label, ...topic }) => (
                <button key={label} onClick={() => ask({ ...topic, scope: lastTurn?.scope })}>{label}</button>
              ))}
              {welcome?.chat_available && lastPrompt === 'transaction_detail' && (
                <button onClick={() => ask({
                  question: 'What stands out about this purchase compared with my recent spending in the same category?',
                })}>Compare with my usual spending</button>
              )}
            </div>
          </section>
        )}
        {lastPrompt === 'apartment_plan' && !displayedTurn && (
          <button className="coach-next" onClick={() => ask({
            question: 'What could I change in my grocery spending?', prompt: 'grocery_plan',
          })}>Find savings in my grocery receipts</button>
        )}
        {lastPrompt && lastPrompt !== 'apartment_plan' && !displayedTurn && (
          <div className="chips coach-actions">
            {lastPrompt === 'weekly_budget' && (
              <>
                <button onClick={onOpenPayday}>Check what fits before payday</button>
                <button onClick={onOpenSimulation}>Try a simulated purchase</button>
              </>
            )}
            {lastPrompt === 'monthly_spending' && offset < 24 && (
              <button onClick={() => ask({
                question: 'What about the previous calendar month?', prompt: 'monthly_spending',
                scope: { ...lastTurn?.scope, month_offset: offset + 1, compare: true },
              })}>Compare with the previous month</button>
            )}
            {lastPrompt === 'monthly_spending' && lastTurn?.scope?.category === 'Restaurants' && (
              <button onClick={() => ask({
                question: 'What if I ate out 20% less?', prompt: 'dining_savings',
              })}>What if I ate out 20% less?</button>
            )}
            {lastPrompt === 'spending_profile' && (
              <button onClick={() => ask(WEEKLY_BUDGET)}>{WEEKLY_BUDGET.label}</button>
            )}
          </div>
        )}
        {displayedTurn && <Message msg={{ role: 'user', content: displayedTurn.question }} />}
        {pending && <Message msg={{ role: 'assistant', content: '', pending: true }} />}
        {failed && (
          <div className="welcome">
            <p role="alert">{failed.prompt
              ? 'Aino couldn’t load this answer. Try again.'
              : 'Free-form chat is temporarily unavailable. Try again or choose another topic.'}</p>
            <button className="reset-btn" onClick={() => ask(failed)}>Retry question</button>
            <button className="reset-btn" onClick={() => setFailed(null)}>Choose another topic</button>
          </div>
        )}
        {!!messages.length && !displayedTurn && (
          <details className="welcome chat-topics">
            <summary>More ways to explore</summary>
            {starterTopics}
          </details>
        )}
        {!!messages.length && !displayedTurn && welcome?.check_in && (
          <details className="welcome chat-overview chat-topics">
            <summary>14-day spending check-in</summary>
            <CheckIn data={welcome.check_in} onOpenTransactions={onOpenTransactions} onOpenPayday={onOpenPayday} />
          </details>
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
