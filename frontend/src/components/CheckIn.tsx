import type { AdviserCheckIn, SpendingScope } from '../api'

const euros = new Intl.NumberFormat('en-IE', { style: 'currency', currency: 'EUR' })
const dates = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' })
const money = (value: number) => euros.format(value)
const dateLabel = (date: string) => dates.format(new Date(date))

export function CheckIn({ data, onOpenTransactions, onOpenPayday }: {
  data: AdviserCheckIn
  onOpenTransactions: (scope: SpendingScope) => void
  onOpenPayday: () => void
}) {
  const { goal, scenarios, top_category: top, start, end } = data
  const change = Math.abs(data.spend_eur - data.previous_eur)
  const hasPayday = data.estimated_payday !== null
  const difference = Math.round((scenarios[0].spend_eur - scenarios[2].spend_eur) * 100) / 100
  const scope = { start, end, basket: 'everyday_discretionary' }

  return (
    <div className="adviser-check-in">
      <p className="adviser-period">Last 14 days · {dateLabel(start)}–{dateLabel(end)}</p>
      <h1>{data.title}</h1>
      <p>
        <strong>{money(data.spend_eur)}</strong> in everyday spending
        {change >= 0.01
          ? <>, {money(change)} {data.spend_eur > data.previous_eur ? 'more' : 'less'} than the previous 14 days.</>
          : <>, unchanged from the previous 14 days.</>}
      </p>
      {top && (
        <button className="reset-btn" onClick={() => onOpenTransactions({ ...scope, category: top.category })}>
          See {top.category.toLowerCase()} · {money(top.amount_eur)}
        </button>
      )}

      <section className="adviser-outlook" aria-label="Spending scenarios">
        <h2>{data.estimated_payday ? `Before estimated payday · ${dateLabel(data.estimated_payday)}` : 'Over the next 7 days'}</h2>
        <p>{hasPayday
          ? `Estimated balance after ${money(data.bills_eur ?? 0)} in predicted bills and everyday spending.`
          : 'Estimated everyday spending at your recent pace.'}</p>
        <dl>
          {scenarios.map((scenario) => (
            <div key={scenario.reduction_pct}>
              <dt>{scenario.reduction_pct ? `Spend ${scenario.reduction_pct}% less` : 'Keep this pace'}</dt>
              <dd>{money(scenario.balance_eur ?? scenario.spend_eur)}</dd>
            </div>
          ))}
        </dl>
        {hasPayday && <button className="reset-btn" onClick={onOpenPayday}>Check bills and payday</button>}
      </section>

      {goal && (
        <section className="adviser-outlook" aria-label="Current goal">
          <h2>{goal.name}</h2>
          <p><strong>{money(goal.saved_so_far_eur)}</strong> of {money(goal.target_eur)} saved.</p>
          {difference > 0 && (
            <p>{goal.saved_so_far_eur < goal.target_eur && (scenarios[2].balance_eur ?? 0) > 0
              ? `Spending 20% less could leave ${money(difference)} more. If it’s still available after bills and your buffer, you could put it toward this goal.`
              : `Spending 20% less could free up ${money(difference)}. Check that upcoming costs are covered first.`}</p>
          )}
        </section>
      )}
    </div>
  )
}
