import { useEffect, useState } from 'react'
import {
  fetchBenchmark,
  fetchCoachingPlan,
  fetchMonthly,
  type Benchmark,
  type CoachingPlan,
  type MonthlyOverview,
  type SpendingScope,
} from '../api'
import { ChartCard, type ChartSpec } from './ChartCard'

const BASKET_LABELS: Record<string, string> = {
  mandatory_regular: 'Must-pays',
  mandatory_irregular: 'Unexpected',
  everyday_discretionary: 'Everyday',
  savings_investing: 'Saving',
}

type Track = 'category' | 'basket' | 'balance' | 'benchmark'

export function MonthView({ customerId, onOpenTransactions, onOpenPayday, onAskGroceryPlan }: {
  customerId: string
  onOpenTransactions: (scope?: SpendingScope) => void
  onAskGroceryPlan: () => void
  onOpenPayday: () => void
}) {
  const [data, setData] = useState<MonthlyOverview | null>(null)
  const [bench, setBench] = useState<Benchmark | null>(null)
  const [plan, setPlan] = useState<CoachingPlan | null>(null)
  const [track, setTrack] = useState<Track>('category')
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    setData(null)
    setBench(null)
    setPlan(null)
    fetchMonthly(customerId).then(setData).catch(() => setError(true))
    fetchBenchmark(customerId).then(setBench).catch(console.error)
    fetchCoachingPlan(customerId).then(setPlan).catch(console.error)
  }, [customerId, attempt])

  if (error) return (
    <main>
      <div className="welcome">
        <p role="alert">Couldn’t load the monthly summary.</p>
        <button className="reset-btn" onClick={() => {
          setError(false)
          setAttempt((n) => n + 1)
        }}>Try again</button>
      </div>
    </main>
  )

  if (!data) return <main className="loading">Loading…</main>

  const groceries = data.groceries
  const charts: Record<Track, ChartSpec> = {
    category: {
      kind: 'donut',
      title: `Spending by category · ${data.month}`,
      labels: data.per_category.map((c) => c.category),
      values: data.per_category.map((c) => c.spent_eur),
      unit: 'eur',
    },
    basket: {
      kind: 'donut',
      title: `Spending by basket · ${data.month}`,
      labels: data.per_basket.map((b) => BASKET_LABELS[b.basket] ?? b.basket),
      values: data.per_basket.map((b) => b.spent_eur),
      unit: 'eur',
    },
    balance: {
      kind: 'line',
      title: `Balance through ${data.month}`,
      labels: data.balance_trend.map((d: { day: string }) => d.day.slice(8)),
      series: [
        { name: 'Balance', data: data.balance_trend.map((d: { balance_eur: number }) => d.balance_eur) },
      ],
    },
    benchmark: bench
      ? {
          kind: 'bar',
          title: 'You vs your peers (EUR/month)',
          labels: bench.rows.map((r) => r.category),
          values: bench.rows.map((r) => r.user_monthly_eur),
          values2: bench.rows.map((r) => r.finn_monthly_eur),
          series_names: ['You', 'Your peers'],
        }
      : { kind: 'bar', title: 'Loading benchmark…', labels: [], values: [] },
  }

  return (
    <main>
      {groceries && <h1>Budget · {data.month}</h1>}
      <div className="stat-grid">
        <div className="stat">
          <small>Balance</small>
          <strong>{data.balance.toFixed(0)} €</strong>
        </div>
        <div className="stat">
          <small>Income</small>
          <strong>{data.income.toFixed(0)} €</strong>
        </div>
        <div className="stat">
          <small>Spent</small>
          <strong>{data.expense.toFixed(0)} €</strong>
        </div>
        <div className="stat accent">
          <small>Safe / week</small>
          <strong>{data.safe_to_spend.safe_to_spend_weekly.toFixed(0)} €</strong>
        </div>
      </div>

      <div className="track-chips">
        <button onClick={() => onOpenTransactions()}>Browse transactions</button>
        <button onClick={onOpenPayday}>Check before payday</button>
      </div>

      <div className="track-picker">
        <span>What do you want to track?</span>
        <div className="track-chips">
          {(['category', 'basket', 'balance', 'benchmark'] as Track[]).map((t) => (
            <button key={t} className={track === t ? 'active' : ''} onClick={() => setTrack(t)}>
              {t === 'category'
                ? 'By category'
                : t === 'basket'
                  ? 'By basket'
                  : t === 'balance'
                    ? 'Balance'
                    : 'Vs demo peers'}
            </button>
          ))}
        </div>
      </div>

      <ChartCard chart={charts[track]} />

      {groceries && (
        <section className="welcome grocery-insights">
          <h2>Inside your grocery spending</h2>
          <small>{groceries.start} to {groceries.end} · Based on store receipts</small>
          <p><strong>€{groceries.total_eur.toFixed(2)}</strong> across {groceries.visits} purchases,
            about {groceries.trips_per_week} per week.</p>
          {groceries.small_trips > 0 && (
            <p>{groceries.small_trips} purchases of €20 or less added up to €{groceries.small_trip_total_eur.toFixed(2)}.
              {groceries.trips_per_week > 1 && ' Try one planned shop each week and keep a list for top-ups.'}</p>
          )}
          {groceries.experiment && (
            <p><strong>Try a smaller treat budget.</strong> You spent €{groceries.experiment.baseline_eur.toFixed(2)} on{' '}
              {groceries.experiment.category.toLowerCase()}. Aim for €{groceries.experiment.target_eur.toFixed(2)} over a similar period.</p>
          )}
          <div className="track-chips">
            <button onClick={onAskGroceryPlan}>Ask Aino for a plan</button>
            <button onClick={() => onOpenTransactions({
              category: 'Groceries', start: groceries.start, end: groceries.end,
            })}>See grocery purchases</button>
          </div>
          <details className="receipt-details">
            <summary>See spending by product</summary>
            <ul>
              {groceries.categories.map((category) => (
                <li key={category.name}>
                  <span>{category.name}<small>In {category.visits} purchases</small></span>
                  <strong>€{category.spent_eur.toFixed(2)}</strong>
                </li>
              ))}
            </ul>
          </details>
        </section>
      )}

      {track === 'benchmark' && bench && (
        <div className="bench-story">
          {bench.story.top_over ? (
            <>
              <div className="bench-headline">
                <span className="bench-badge">Biggest outlier</span>
                <strong>
                  {bench.story.top_over.category}: +{bench.story.top_over.delta_eur.toFixed(0)} €
                  than average
                </strong>
                <small>
                  {bench.story.top_over.user_monthly_eur.toFixed(0)} € vs{' '}
                  {bench.story.top_over.finn_monthly_eur.toFixed(0)} € for your peers aged{' '}
                  {bench.age_group} — that's {bench.story.top_over.delta_eur.toFixed(0)} € a month,{' '}
                  {Math.round(bench.story.top_over.delta_eur * 12).toLocaleString()} € a year
                </small>
              </div>
              {bench.story.over.length > 0 && (
                <div className="bench-line">
                  Also above average:{' '}
                  {bench.story.over
                    .map((r) => `${r.category} +${r.delta_eur.toFixed(0)} €`)
                    .join(', ')}
                </div>
              )}
              {bench.story.under.length > 0 && (
                <div className="bench-line good">
                  Below average:{' '}
                  {bench.story.under
                    .map((r) => `${r.category} −${Math.abs(r.delta_eur).toFixed(0)} €`)
                    .join(', ')}{' '}
                  — nice
                </div>
              )}
            </>
          ) : (
            <div className="bench-headline">
              <span className="bench-badge">On track</span>
              <strong>You're close to the average on everything</strong>
            </div>
          )}
          <div className="bench-cta">
            Trimming the outlier is your biggest lever — see the coaching plan below.
          </div>
        </div>
      )}

      {plan && !groceries && (
        <div className="plan-card">
          <div className="plan-head">
            <strong>Your coaching plan</strong>
            <small>safe-to-save {plan.safe_to_save_monthly.toFixed(0)} €/mo</small>
          </div>
          {plan.actions.map((a, i) => (
            <div key={i} className="action">
              <span className={`action-dot ${a.kind}`} />
              <div className="action-body">
                <strong>{a.title}</strong>
                <small>{a.detail}</small>
              </div>
              <div className="action-impact">{a.impact_label}</div>
            </div>
          ))}
        </div>
      )}

      <div className="welcome">
        <p>
          Net this month: <strong>{data.net >= 0 ? '+' : ''}{data.net.toFixed(2)} €</strong>. Ask the
          coach in the chat tab for a deeper story.
        </p>
      </div>
    </main>
  )
}
