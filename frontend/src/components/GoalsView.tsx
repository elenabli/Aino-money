import { useEffect, useState } from 'react'
import {
  clearSimulated,
  createChallenge,
  createGoal,
  fastForward,
  fetchChallenges,
  fetchChallengeQuote,
  fetchGoal,
  type ChallengeProgress,
  type Goal,
  type ExperimentDraft,
} from '../api'

const CATEGORIES = ['Restaurants', 'Entertainment', 'Groceries', 'Lifestyle', 'Travel']

export function GoalsView({
  customerId,
  draft,
  onResetSimulation,
}: {
  customerId: string
  draft?: ExperimentDraft
  onResetSimulation: () => void
}) {
  const [goal, setGoal] = useState<Goal | null>(null)
  const [name, setName] = useState('')
  const [amount, setAmount] = useState('')
  const [months, setMonths] = useState('')
  const [busy, setBusy] = useState(false)
  const [goalError, setGoalError] = useState('')
  const [experimentError, setExperimentError] = useState('')

  const [challenge, setChallenge] = useState<ChallengeProgress | null>(null)
  const [chCategory, setChCategory] = useState(draft?.category ?? CATEGORIES[0])
  const [chPct, setChPct] = useState(draft?.pct ?? 20)
  const [chDays, setChDays] = useState(draft?.days ?? 14)
  const [replace, setReplace] = useState(false)
  const [challengeLoaded, setChallengeLoaded] = useState(false)
  const [chBusy, setChBusy] = useState(false)
  const [ffBusy, setFfBusy] = useState(false)
  const [resetBusy, setResetBusy] = useState(false)
  const [quote, setQuote] = useState<{ key: string; budget?: number }>()
  const quoteKey = JSON.stringify([chCategory, chPct, chDays])
  const showingDraft = challengeLoaded && (!challenge?.active || replace)

  useEffect(() => {
    if (!showingDraft) return
    const controller = new AbortController()
    fetchChallengeQuote(customerId, { category: chCategory, pct: chPct, days: chDays }, controller.signal)
      .then(({ budget_eur }) => setQuote({ key: quoteKey, budget: budget_eur }))
      .catch(() => { if (!controller.signal.aborted) setQuote({ key: quoteKey }) })
    return () => controller.abort()
  }, [customerId, chCategory, chPct, chDays, showingDraft, quoteKey])

  useEffect(() => {
    setGoal(null)
    setChallenge(null)
    fetchGoal(customerId).then(setGoal).catch(() => setGoalError('Couldn’t load your savings goal.'))
    fetchChallenges(customerId).then((result) => { setChallenge(result); setChallengeLoaded(true) }).catch(() => setExperimentError('Couldn’t load experiment progress.'))
  }, [customerId])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (busy || !name.trim() || Number(amount) < 0.01) return
    setBusy(true)
    setGoalError('')
    try {
      setGoal(await createGoal(customerId, name.trim(), Number(amount), months ? Number(months) : undefined))
    } catch {
      setGoalError('Couldn’t save your goal. Try again.')
    } finally {
      setBusy(false)
    }
  }

  async function startChallenge() {
    setChBusy(true)
    setExperimentError('')
    try {
      await createChallenge(customerId, chCategory, chPct, chDays)
      setChallenge(await fetchChallenges(customerId))
      setReplace(false)
      onResetSimulation()
    } catch {
      setExperimentError('Couldn’t start your experiment. Try again.')
    } finally {
      setChBusy(false)
    }
  }

  async function ff(days: number) {
    setFfBusy(true)
    setExperimentError('')
    try {
      setChallenge(await fastForward(customerId, days))
    } catch {
      setExperimentError('Couldn’t fast-forward the experiment. Try again.')
    } finally {
      setFfBusy(false)
    }
  }

  async function resetExperiment() {
    setResetBusy(true)
    setExperimentError('')
    try {
      await clearSimulated(customerId)
      onResetSimulation()
      setChallenge(await fetchChallenges(customerId))
    } catch {
      setExperimentError('Couldn’t reset simulated spending. Try again.')
    } finally {
      setResetBusy(false)
    }
  }

  const pct = goal && goal.target_eur > 0 ? Math.min(100, (goal.saved_so_far_eur / goal.target_eur) * 100) : 0
  const a = challenge?.active ?? null
  const advanceDays = a ? Math.min(7, a.total_days - a.days_elapsed) : 0

  return (
    <main>
      <div className="welcome">
        <h1>Savings goal</h1>
        <p>
          Tell me what you're saving for. I'll turn your safe-to-save into a weekly plan.
        </p>
        <form className="goal-form" onSubmit={submit}>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            aria-label="Savings goal name"
            placeholder="What for? e.g. a bike"
          />
          <div className="goal-form-row">
            <input
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              aria-label="Target amount in euros"
              placeholder="Amount (EUR)"
              min="0.01"
              step="0.01"
              required
              type="number"
              inputMode="decimal"
            />
            <input
              value={months}
              onChange={(e) => setMonths(e.target.value)}
              aria-label="Months to reach the goal"
              placeholder="Months (optional)"
              min="1"
              type="number"
              inputMode="numeric"
            />
          </div>
          <button className="big-cta" disabled={busy || !name.trim() || Number(amount) < 0.01}>
            {busy ? 'Planning…' : 'Build my plan'}
          </button>
        </form>
        {goalError && <p role="alert">{goalError}</p>}
      </div>

      {goal && (
        <div className="goal-card">
          <div className="goal-title">
            <strong>{goal.name}</strong>
            <span>{goal.target_eur.toFixed(0)} €</span>
          </div>

          <div className="goal-track">
            <div className="goal-fill" style={{ width: `${pct}%` }} />
          </div>
          <small className="goal-progress">
            {goal.saved_so_far_eur.toFixed(2)} € saved · {pct.toFixed(0)}% of target
          </small>

          <div className="sim-rows">
            <div className="sim-row">
              <span>Your safe-to-save</span>
              <strong>{goal.safe_to_save_monthly.toFixed(2)} €/month</strong>
            </div>
            {goal.weekly_eur && (
              <div className="sim-row">
                <span>Weekly target</span>
                <strong>{goal.weekly_eur.toFixed(2)} €/week</strong>
              </div>
            )}
            {goal.months && (
              <div className="sim-row">
                <span>Time to goal</span>
                <strong>{goal.months} months</strong>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="welcome">
        <h1>Money experiment</h1>
        {draft && <p>Aino suggested {draft.pct}% less on {draft.category.toLowerCase()} for {draft.days} days.</p>}
        <p>
          Turn advice into a measurable test. I'll track your progress from your transactions.
        </p>

        {experimentError && <p role="alert">{experimentError}</p>}
        {draft && a && !replace && (
          <button className="reset-btn" onClick={() => setReplace(true)}>Set up the suggested experiment</button>
        )}
        {!a || replace ? (
          <div className="goal-form">
            <div className="ch-row">
              <select aria-label="Spending category" value={chCategory} onChange={(e) => setChCategory(e.target.value)}>
                {Array.from(new Set([...CATEGORIES, chCategory])).map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
              <select aria-label="Spending reduction" value={chPct} onChange={(e) => setChPct(Number(e.target.value))}>
                {Array.from(new Set([10, 20, 30, 50, chPct])).sort((a, b) => a - b).map((p) => (
                  <option key={p} value={p}>
                    −{p}%
                  </option>
                ))}
              </select>
              <select aria-label="Experiment duration" value={chDays} onChange={(e) => setChDays(Number(e.target.value))}>
                {[7, 14, 30].map((d) => (
                  <option key={d} value={d}>
                    {d} days
                  </option>
                ))}
              </select>
            </div>
            {showingDraft && (
              <p role="status">{quote?.key !== quoteKey
                ? 'Calculating the suggested budget…'
                : quote.budget === undefined ? 'The budget preview is unavailable.'
                  : `Target for ${chDays} days: €${quote.budget.toFixed(2)}.`}</p>
            )}
            {replace && <p>Replacing the experiment clears its simulated progress.</p>}
            <button className="big-cta" onClick={startChallenge} disabled={chBusy || !challengeLoaded}>
              {chBusy ? 'Starting…' : replace ? 'Replace current experiment' : 'Start experiment'}
            </button>
          </div>
        ) : (
          <div className="challenge-card">
            <div className="goal-title">
              <strong>
                {a.category} −{a.pct}%
              </strong>
              <span>
                day {a.days_elapsed}/{a.total_days}
              </span>
            </div>

            <div className="goal-track">
              <div
                className="goal-fill"
                style={{ width: `${Math.min(100, (a.days_elapsed / a.total_days) * 100)}%` }}
              />
            </div>
            <small className="goal-progress">
              budget {a.budget_so_far_eur.toFixed(2)} € · spent {a.actual_so_far_eur.toFixed(2)} €
            </small>

            <div className={`verdict ${a.on_track ? 'good' : 'bad'}`}>
              {a.days_elapsed === 0
                ? 'Ready to start. Fast-forward to see how the experiment works.'
                : a.on_track
                  ? `${advanceDays === 0 ? 'Experiment complete' : 'On track'}. Simulated spending was ${a.saved_vs_pace_eur.toFixed(2)} € below your usual pace.`
                  : `Over budget by ${a.overspent_eur.toFixed(2)} € this period`}
            </div>

            <div className="ff-row">
              {advanceDays > 0 && (
                <button className="big-cta" onClick={() => ff(advanceDays)} disabled={ffBusy || resetBusy}>
                  {ffBusy ? 'Simulating…' : `Fast-forward ${advanceDays} ${advanceDays === 1 ? 'day' : 'days'}`}
                </button>
              )}
              <button className="reset-btn" onClick={resetExperiment} disabled={ffBusy || resetBusy}>
                {resetBusy ? 'Resetting…' : 'Reset simulated spending'}
              </button>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}
