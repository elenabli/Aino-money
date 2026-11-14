import { ChartCard, type ChartSpec } from './ChartCard'

interface Msg {
  role: 'user' | 'assistant'
  content: string
  trace?: { tool: string; args: Record<string, unknown> }[]
  chart?: ChartSpec
  pending?: boolean
}

export function Message({ msg }: { msg: Msg }) {
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
            msg.content
          )}
        </div>
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
