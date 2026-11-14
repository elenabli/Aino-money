import type { SpendingEvidence, SpendingScope, ExperimentDraft } from '../api'
import { ChartCard, type ChartSpec } from './ChartCard'

function renderAssistantText(content: string) {
  return content.split(/\*\*(?=\S)([^*\n]*?\S)\*\*/g).map((part, index) =>
    index % 2 === 0 ? part : <strong key={index}>{part}</strong>,
  )
}

interface Msg {
  role: 'user' | 'assistant'
  content: string
  trace?: { tool: string; args: Record<string, unknown> }[]
  chart?: ChartSpec
  pending?: boolean
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
  return (
    <div className="row assistant">
      <div className="avatar" aria-hidden="true">A</div>
      <div className="stack">
        {msg.chart && <ChartCard chart={msg.chart} />}
        <div className="bubble">
          {msg.pending ? (
            <span className="dots">
              <i /> <i /> <i />
            </span>
          ) : (
            renderAssistantText(msg.content)
          )}
        </div>
        {(!!msg.evidence?.length || msg.experiment) && (
          <div className="message-actions">
            {onOpenTransactions && msg.evidence?.map(({ label, count, ...scope }, index) => (
              <button className="reset-btn" key={index} onClick={() => onOpenTransactions(scope)}>
                {count === undefined ? label + ' transactions' : `Show transactions (${count}) · ${label}${scope.start ? ` · ${scope.start.slice(0, 7)}` : ''}`}
              </button>
            ))}
            {msg.experiment && onOpenGoals && (
              <button className="reset-btn" onClick={() => onOpenGoals(msg.experiment!)}>
                Try {msg.experiment.pct}% less on {msg.experiment.category.toLowerCase()} for 14 days
              </button>
            )}
          </div>
        )}
        {msg.trace && msg.trace.length > 0 && (
          <details className="trace">
            <summary>what I looked at ({msg.trace.length})</summary>
            {msg.trace.map((t, i) => (
              <div key={i} className="trace-item">
                <code>{t.tool}</code>{' '}
                {Object.values(t.args).filter((v) => v != null).join(' · ')}
              </div>
            ))}
          </details>
        )}
      </div>
    </div>
  )
}
