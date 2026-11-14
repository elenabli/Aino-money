import { useEffect, useRef, useState } from 'react'
import {
  fetchWelcome, sendChat, streamChat,
  type ChatMsg, type ChatResponse, type ChatTopic, type ChatScope, type SpendingScope, type ExperimentDraft,
} from '../api'
import { Message, type Msg } from './Message'
import { SendIcon, SparkIcon } from './icons'

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

/** The challenge's own example questions: answered live by the AI with tools and charts. */
const AI_STARTERS = [
  'What kind of spender am I?',
  'Am I spending more than people my age?',
  'What if I ate out 20% less?',
]
const AI_MORE = [
  'How much did I spend on taxis last month?',
  'What is safe for me to spend this week?',
  'Show my restaurant spending over 6 months',
  'Which bills are coming up before payday?',
]

export type CoachTurn = Pick<ChatTopic, 'question' | 'prompt'> & { scope?: ChatScope }
type Entry = ChatMsg & Partial<Omit<ChatResponse, 'answer'>> & { steps?: string[] }

export function ChatView({
  customerId,
  firstName,
  active,
  onOpenSimulation,
  onOpenGoals,
  onViewGoal,
  onOpenTransactions,
  onOpenPayday,
  linkedTurn,
  onConsumeTurn,
}: {
  customerId: string
  firstName: string
  active: boolean
  onOpenSimulation: () => void
  onViewGoal: () => void
  onOpenGoals: (draft: ExperimentDraft) => void
  onOpenTransactions: (scope: SpendingScope) => void
  onOpenPayday: () => void
  linkedTurn: CoachTurn | null
  onConsumeTurn: () => void
}) {
  const [welcome, setWelcome] = useState<Awaited<ReturnType<typeof fetchWelcome>> | null>(null)
  const [messages, setMessages] = useState<Entry[]>([])
  const [lastTurn, setLastTurn] = useState<CoachTurn>()
  const [pending, setPending] = useState<CoachTurn | null>(null)
  const [live, setLive] = useState<Msg | null>(null)
  const [failed, setFailed] = useState<CoachTurn | null>(null)
  const [input, setInput] = useState('')
  const consumedTurn = useRef<CoachTurn | null>(null)
  const questionRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  // Pin the new question to the top; the steps, chart and answer then unfold below it.
  useEffect(() => {
    if (active && pending) questionRef.current?.scrollIntoView({ block: 'start', behavior: 'smooth' })
  }, [active, pending])
  useEffect(() => {
    if (active && failed) bottomRef.current?.scrollIntoView({ block: 'end', behavior: 'smooth' })
  }, [active, failed])

  useEffect(() => {
    if (!active) return
    let current = true
    fetchWelcome(customerId)
      .then((welcome) => { if (current) setWelcome(welcome) })
      .catch(() => {})
    return () => { current = false }
  }, [active, customerId])

  const aiReady = welcome?.chat_available === true

  async function ask(turn: CoachTurn) {
    // Without an AI provider, a tapped purchase falls back to the built-in transaction answer.
    const { question, prompt, scope } = !turn.prompt && turn.scope?.transaction_id !== undefined && welcome?.chat_available === false
      ? { ...turn, prompt: 'transaction_detail' as const } : turn
    if (!question.trim() || pending) return
    const history: ChatMsg[] = [
      ...messages.map(({ role, content }) => ({ role, content })),
      { role: 'user', content: question.trim() },
    ]
    setPending({ question, prompt, scope })
    setFailed(null)
    if (!prompt) setInput('')
    try {
      let res: ChatResponse
      let steps: string[] | undefined
      if (prompt) {
        res = await sendChat(history, customerId, prompt, scope)
      } else {
        const draft: Msg = { role: 'assistant', content: '', steps: [], charts: [], streaming: true }
        setLive(draft)
        res = await streamChat(history, customerId, (event) => {
          if (event.type === 'tool') draft.steps = [...(draft.steps ?? []), event.label]
          else if (event.type === 'chart') draft.charts = [...(draft.charts ?? []), event.chart]
          else if (event.type === 'text') draft.content += event.delta
          else if (event.type === 'reset') draft.content = ''
          else if (event.type === 'receipt') draft.receipt = event.receipt
          setLive({ ...draft })
        }, { receipt_id: scope?.receipt_id, transaction_id: scope?.transaction_id })
        steps = draft.steps
      }
      setMessages([...messages, history[history.length - 1], {
        role: 'assistant', content: res.answer, trace: res.trace, chart: res.chart, charts: res.charts,
        evidence: res.evidence, experiment: res.experiment, topics: res.topics, followups: res.followups,
        receipt: res.receipt,
        steps,
      }])
      setLastTurn({ question, prompt, scope })
    } catch {
      setFailed({ question, prompt, scope })
    } finally {
      setLive(null)
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

  const checkIn = welcome?.check_in
  const recent = checkIn?.top_category
  const money = (amount: number) => new Intl.NumberFormat('en-IE', {
    style: 'currency', currency: 'EUR', maximumFractionDigits: 0,
  }).format(amount)
  const opening = !checkIn
    ? `Hi ${firstName}, I’m Aino, your money coach. Ask me anything about your spending, bills or goals.`
    : recent
      ? `Hi ${firstName}! I’ve gone through your last two weeks. **${recent.category}** was your biggest everyday cost at **${money(recent.amount_eur)}**.\n\nAsk me anything about your money. I’ll check your transactions and draw the numbers for you.`
      : `Hi ${firstName}! I’ve gone through your last two weeks. Ask me anything about your money and I’ll check your transactions for you.`

  const last = messages.at(-1)
  const responseTopics = last?.topics
  const followups = last?.followups ?? []
  const askAi = (question: string) => ask({ question })

  const starterTopics = (
    <div className="chips" aria-label="Topics to explore">
      {aiReady && AI_MORE.map((q) => (
        <button key={q} className="ai" onClick={() => askAi(q)}><SparkIcon size={12} /> {q}</button>
      ))}
      {[SPENDING_PROFILE, WEEKLY_BUDGET].map((topic) => <button key={topic.prompt} onClick={() => ask(topic)}>{topic.label}</button>)}
      {welcome?.has_grocery_receipts && <button onClick={() => ask(GROCERIES)}>{GROCERIES.label}</button>}
      <button onClick={() => ask(DINING)}>{DINING.label}</button>
      {goal && <button onClick={() => ask({
        question: 'What’s my first step towards my apartment deposit?', prompt: 'apartment_plan',
      })}>Plan my apartment deposit</button>}
    </div>
  )

  return (
    <>
      <main className={pending ? "chat-main streaming" : "chat-main"}>
        {!messages.length && !displayedTurn && !linkedTurn && (
          <>
            <Message msg={{ role: 'assistant', content: opening }} />
            <div className="chat-replies" aria-label="Suggested questions">
              {aiReady ? AI_STARTERS.map((q) => (
                <button key={q} onClick={() => askAi(q)}><SparkIcon size={13} />{q}</button>
              )) : (
                <>
                  <button onClick={() => ask({ question: 'Where did my money go?', prompt: 'recent_check_in' })}>Where did my money go?</button>
                  <button onClick={() => ask({ question: 'What if I spent a little less?', prompt: 'spending_outlook' })}>What if I spent a little less?</button>
                  {checkIn?.goal && (
                    <button onClick={goal ? () => ask({
                      question: 'What’s my first step towards my apartment deposit?', prompt: 'apartment_plan',
                    }) : onViewGoal}>How’s my savings goal?</button>
                  )}
                </>
              )}
            </div>
          </>
        )}

        {messages.map((msg, i) => (
          <Message key={i} msg={msg} onOpenTransactions={onOpenTransactions} onOpenGoals={onOpenGoals} />
        ))}

        {!displayedTurn && followups.length > 0 && (
          <div className="chat-replies followups" aria-label="Suggested follow-ups">
            {followups.map((q) => <button key={q} onClick={() => askAi(q)}><SparkIcon size={13} />{q}</button>)}
          </div>
        )}
        {!displayedTurn && !!responseTopics?.length && (
          <div className="chat-replies" aria-label="Suggested topics">
            {responseTopics.map(({ label, ...topic }) => (
              <button key={label} onClick={() => ask({ ...topic, scope: lastTurn?.scope })}>{label}</button>
            ))}
            {aiReady && lastPrompt === 'transaction_detail' && (
              <button onClick={() => askAi('What stands out about this purchase compared with my recent spending in the same category?')}>
                <SparkIcon size={13} />Compare with my usual spending
              </button>
            )}
          </div>
        )}
        {!displayedTurn && lastPrompt === 'spending_outlook' && checkIn?.estimated_payday && (
          <div className="chat-replies"><button onClick={onOpenPayday}>Look at my bills and payday</button></div>
        )}
        {!displayedTurn && lastPrompt === 'recent_check_in' && (
          <div className="chat-replies">
            <button onClick={() => ask({ question: 'What if I spent a little less?', prompt: 'spending_outlook' })}>What if I spent a little less?</button>
          </div>
        )}
        {lastPrompt === 'apartment_plan' && !displayedTurn && (
          <div className="chat-replies">
            <button onClick={() => ask({ question: 'What could I change in my grocery spending?', prompt: 'grocery_plan' })}>
              Find savings in my grocery receipts
            </button>
          </div>
        )}
        {lastPrompt && !displayedTurn && (
          <div className="chat-replies">
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
              <button onClick={() => ask({ question: 'What if I ate out 20% less?', prompt: 'dining_savings' })}>What if I ate out 20% less?</button>
            )}
            {lastPrompt === 'spending_profile' && (
              <button onClick={() => ask(WEEKLY_BUDGET)}>{WEEKLY_BUDGET.label}</button>
            )}
          </div>
        )}

        {displayedTurn && <div ref={questionRef} className="question-anchor"><Message msg={{ role: 'user', content: displayedTurn.question }} /></div>}
        {pending && <Message msg={live ?? { role: 'assistant', content: '', pending: true }} />}
        {failed && (
          <div className="welcome">
            <p role="alert">{failed.prompt
              ? 'Aino couldn’t load this answer. Try again.'
              : 'Aino is temporarily unavailable. Try again or choose another topic.'}</p>
            <button className="reset-btn" onClick={() => ask(failed)}>Retry question</button>
            <button className="reset-btn" onClick={() => setFailed(null)}>Choose another topic</button>
          </div>
        )}
        {!displayedTurn && (
          <details className="chat-more">
            <summary>More questions to try</summary>
            {starterTopics}
          </details>
        )}
        <div ref={bottomRef} />
      </main>

      <footer>
        {welcome?.chat_available === false ? (
          <p className="coach-note">Use the suggested questions in this demo. Free-form chat requires an AI provider.</p>
        ) : (
          <form onSubmit={(e) => {
            e.preventDefault()
            ask({ question: input })
          }}>
            <input
              aria-label="Ask Aino about your money"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask Aino about your money…"
              disabled={!!pending}
            />
            <button aria-label="Send" disabled={!!pending || !input.trim()}><SendIcon /></button>
          </form>
        )}
        <p className="footer-note">AI answers are computed from your own transactions · estimates, not financial advice</p>
      </footer>
    </>
  )
}
