import type { ReactNode } from 'react'
import type { SpendingEvidence, SpendingScope, ExperimentDraft, ReceiptInsight } from '../api'
import { ReceiptInsightCard } from './ReceiptInsightCard'
import { ChartCard, type ChartSpec } from './ChartCard'
import { SparkIcon } from './icons'

const STEP_LABELS: Record<string, string> = {
  savings_goal_plan: 'Reviewed your savings goal',
  grocery_receipt_insights: 'Read your grocery receipts',
  spend_by_category: 'Added up spending by category',
  transaction_list: 'Matched your transactions',
  basket_breakdown: 'Sorted spending into the three baskets',
  safe_to_spend: 'Worked out your safe-to-spend',
  what_if: 'Simulated the change',
  receipt_insights: 'Read and classified the itemised receipt',
}

function inline(text: string, key: string): ReactNode[] {
  return text.split(/\*\*(?=\S)([^*\n]*?\S)\*\*/g).flatMap((part, index) =>
    index % 2 === 1
      ? [<strong key={`${key}-${index}`}>{part}</strong>]
      : part.split(/(?<![*\w])\*(?=\S)([^*\n]*?\S)\*(?!\*)/g).map((piece, j) =>
          j % 2 === 0 ? piece : <em key={`${key}-${index}-${j}`}>{piece}</em>),
  )
}

/** Minimal markdown: paragraphs, bullet lists, bold. Enough for the coach's short answers. */
function renderAssistantText(content: string) {
  const blocks = content.replace(/^#+\s*/gm, '').split(/\n{2,}/)
  return blocks.map((block, b) => {
    const lines = block.split('\n').filter((line) => line.trim())
    const bullets = lines.filter((line) => /^\s*([-*•]|\d+\.)\s+/.test(line))
    if (bullets.length && bullets.length === lines.length) {
      return (
        <ul key={b}>
          {lines.map((line, i) => <li key={i}>{inline(line.replace(/^\s*([-*•]|\d+\.)\s+/, ''), `${b}-${i}`)}</li>)}
        </ul>
      )
    }
    return (
      <p key={b}>
        {lines.map((line, i) => (
          <span key={i}>{i > 0 && <br />}{inline(line.replace(/^\s*[-*•]\s+/, '• '), `${b}-${i}`)}</span>
        ))}
      </p>
    )
  })
}

export interface Msg {
  role: 'user' | 'assistant'
  content: string
  trace?: { tool: string; args: Record<string, unknown> }[]
  chart?: ChartSpec
  charts?: ChartSpec[]
  steps?: string[]
  receipt?: ReceiptInsight | null
  pending?: boolean
  streaming?: boolean
  evidence?: SpendingEvidence[]
  experiment?: ExperimentDraft
}

export function Message({ msg, onOpenTransactions, onOpenGoals }: {
  msg: Msg
  onOpenTransactions?: (scope: SpendingScope) => void
  onOpenGoals?: (draft: ExperimentDraft) => void
}) {
  if (msg.role === 'user') {
    return (
      <div className="row user">
        <div className="bubble">{msg.content}</div>
      </div>
    )
  }
  const charts = msg.charts?.length ? msg.charts : msg.chart ? [msg.chart] : []
  const steps = msg.steps?.length
    ? msg.steps
    : (msg.trace ?? []).map((t) => STEP_LABELS[t.tool] ?? t.tool.replace(/_/g, ' '))
  const working = msg.pending || msg.streaming
  const visibleText = msg.content.split('<followups')[0].replace(/<[a-z/]*$/i, '')

  return (
    <div className="row assistant">
      <div className="avatar ai" aria-hidden="true"><SparkIcon size={16} /></div>
      <div className="stack">
        <span className="chat-sender">Aino</span>
        {working && (
          <ol className="steps live" aria-live="polite">
            {steps.map((step, i) => (
              <li key={i} className={i < steps.length - 1 || visibleText ? 'done' : 'active'}>{step}</li>
            ))}
            {!steps.length && <li className="active">Reading your question</li>}
          </ol>
        )}
        {/* A finished streamed answer replaces the live one: don't replay the intro animations. */}
        {msg.receipt && <ReceiptInsightCard data={msg.receipt} settled={!working && !!msg.steps?.length} />}
        {charts.map((chart, i) => <ChartCard key={i} chart={chart} animate={working || !msg.steps?.length} />)}
        {(visibleText || (msg.pending && !steps.length)) && (
          <div className="bubble">
            {visibleText ? renderAssistantText(visibleText) : (
              <span className="dots"><i /> <i /> <i /></span>
            )}
            {msg.streaming && visibleText && <span className="caret" aria-hidden="true" />}
          </div>
        )}
        {!working && (!!msg.evidence?.length || msg.experiment) && (
          <div className="message-actions">
            {onOpenTransactions && msg.evidence?.map(({ label, count, ...scope }, index) => (
              <button className="reset-btn" key={index} onClick={() => onOpenTransactions(scope)}>
                {count === undefined ? `${label} transactions` : `See ${count} ${label.toLowerCase()} transactions`}
              </button>
            ))}
            {msg.experiment && onOpenGoals && (
              <button className="reset-btn primary" onClick={() => onOpenGoals(msg.experiment!)}>
                Try {msg.experiment.pct}% less on {msg.experiment.category.toLowerCase()} for 14 days
              </button>
            )}
          </div>
        )}
        {!working && steps.length > 0 && (
          <details className="trace">
            <summary>How Aino worked this out · {steps.length} {steps.length === 1 ? 'step' : 'steps'}</summary>
            <ol className="steps">
              {steps.map((step, i) => <li key={i} className="done">{step}</li>)}
            </ol>
            <p className="trace-note">Every number comes from your own transactions. Aino reads data, it never moves money.</p>
          </details>
        )}
      </div>
    </div>
  )
}
