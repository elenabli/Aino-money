export interface ChatMsg {
  role: 'user' | 'assistant'
  content: string
}

export interface ToolTrace {
  tool: string
  args: Record<string, unknown>
  result: unknown
}

export interface ChartSpec {
  kind: 'line' | 'bar' | 'donut'
  title: string
  labels: string[]
  values?: number[]
  values2?: number[]
  series_names?: [string, string]
  series?: { name: string; data: number[] }[]
  unit?: 'eur' | 'pct'
  secondary?: { label: string; value: number; max: number }
}

export type CoachPrompt = 'weekly_budget' | 'spending_profile' | 'dining_savings' | 'monthly_spending' | 'transaction_spending' | 'grocery_plan' | 'apartment_plan' | 'transaction_detail' | 'receipt_breakdown' | 'category_context'

export interface ChatTopic {
  label: string
  question: string
  prompt?: CoachPrompt
}

export interface ChatScope extends SpendingScope {
  month_offset?: number
  compare?: boolean
  transaction_id?: number
}

export interface ChatResponse {
  answer: string
  trace: ToolTrace[]
  chart?: ChartSpec
  evidence?: SpendingEvidence[]
  experiment?: ExperimentDraft
  topics?: ChatTopic[]
}

const API = '/api'

export async function sendChat(
  messages: ChatMsg[],
  customerId: string,
  prompt?: CoachPrompt,
  scope?: ChatScope,
): Promise<ChatResponse> {
  const res = await fetch(`${API}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages, customer_id: customerId, prompt, ...scope }),
  })
  if (!res.ok) throw new Error(`chat failed: ${res.status}`)
  return res.json()
}

export interface Persona {
  id: string
  name: string
  age: number
  label: string
  description: string
  balance_eur: number
  median_income_eur: number
}

export async function fetchPersonas(): Promise<Persona[]> {
  const res = await fetch(`${API}/personas`)
  if (!res.ok) throw new Error('personas failed')
  return res.json()
}

export async function fetchProfile(customerId: string) {
  const res = await fetch(`${API}/profile?customer_id=${customerId}`)
  if (!res.ok) throw new Error('profile failed')
  return res.json()
}

export async function fetchOverview(customerId: string) {
  const res = await fetch(`${API}/overview?customer_id=${customerId}`)
  if (!res.ok) throw new Error('overview failed')
  return res.json()
}

export interface GroceryInsights {
  start: string
  end: string
  visits: number
  trips_per_week: number
  total_eur: number
  small_trips: number
  small_trip_total_eur: number
  categories: { name: string; spent_eur: number; visits: number; on_small_trips_eur: number }[]
  experiment: { category: string; baseline_eur: number; target_eur: number; savings_eur: number } | null
}

export interface MonthlyOverview {
  groceries?: GroceryInsights | null
  month: string
  income: number
  expense: number
  net: number
  balance: number
  per_category: { category: string; spent_eur: number }[]
  per_basket: { basket: string; spent_eur: number }[]
  balance_trend: { day: string; balance_eur: number }[]
  safe_to_spend: {
    safe_to_spend_weekly: number
    safe_to_spend_monthly: number
    avg_monthly: Record<string, number>
  }
}

export async function fetchMonthly(customerId: string): Promise<MonthlyOverview> {
  const res = await fetch(`${API}/monthly?customer_id=${customerId}`)
  if (!res.ok) throw new Error('monthly failed')
  return res.json()
}

export interface RandomTx {
  description: string
  category: string
  amount: number
  merchant_id: string | null
}

export async function fetchRandomTx(customerId: string): Promise<RandomTx> {
  const res = await fetch(`${API}/random_tx?customer_id=${customerId}`)
  if (!res.ok) throw new Error('random tx failed')
  return res.json()
}

export interface AdviserCheckIn {
  title: string
  start: string
  end: string
  spend_eur: number
  previous_eur: number
  top_category: { category: string; amount_eur: number; count: number } | null
  days: number
  estimated_payday: string | null
  bills_eur: number | null
  scenarios: { reduction_pct: number; spend_eur: number; balance_eur?: number }[]
  goal: { name: string; target_eur: number; saved_so_far_eur: number; weekly_eur: number | null } | null
}

export async function fetchWelcome(customerId: string): Promise<{
  message: string
  chat_available: boolean
  has_grocery_receipts: boolean
  check_in: AdviserCheckIn
  goal_plan?: { goal: string; target_eur: number; saved_eur: number; net_eur: number } | null
}> {
  const res = await fetch(`${API}/welcome?customer_id=${customerId}`)
  if (!res.ok) throw new Error('welcome failed')
  return res.json()
}

export interface BenchmarkRow {
  category: string
  user_monthly_eur: number
  finn_monthly_eur: number
  delta_pct: number
  delta_eur: number
}

export interface Benchmark {
  age_group: string
  age: number
  rows: BenchmarkRow[]
  user_total_monthly: number
  finn_total_monthly: number
  total_delta_eur: number
  story: {
    top_over: BenchmarkRow | null
    over: BenchmarkRow[]
    under: BenchmarkRow[]
  }
  note: string
}

export async function fetchBenchmark(customerId: string): Promise<Benchmark> {
  const res = await fetch(`${API}/benchmark?customer_id=${customerId}`)
  if (!res.ok) throw new Error('benchmark failed')
  return res.json()
}

export interface CoachingAction {
  kind: string
  title: string
  detail: string
  impact_eur: number
  impact_label: string
}

export interface CoachingPlan {
  safe_to_save_monthly: number
  actions: CoachingAction[]
}

export async function fetchCoachingPlan(customerId: string): Promise<CoachingPlan> {
  const res = await fetch(`${API}/coaching_plan?customer_id=${customerId}`)
  if (!res.ok) throw new Error('coaching plan failed')
  return res.json()
}

export interface Goal {
  name: string
  target_eur: number
  months: number | null
  weekly_eur: number | null
  safe_to_save_monthly: number
  saved_so_far_eur: number
  note: string
  suggestion: string | null
}

export async function fetchGoal(customerId: string): Promise<Goal | null> {
  const res = await fetch(`${API}/goal?customer_id=${customerId}`)
  if (!res.ok) throw new Error('goal failed')
  return res.json()
}

export async function createGoal(
  customerId: string,
  name: string,
  target_eur: number,
  months?: number,
): Promise<Goal> {
  const res = await fetch(`${API}/goal`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ customer_id: customerId, name, target_eur, months }),
  })
  if (!res.ok) throw new Error('create goal failed')
  return res.json()
}

export interface Challenge {
  id: number
  kind: string
  category: string
  pct: number
  days: number
  baseline_daily_eur: number
  target_daily_eur: number
  budget_eur: number
  start_date: string
  end_date: string
  status: string
}

export interface ChallengeProgress {
  active: {
    id: number
    kind: string
    category: string
    pct: number
    baseline_daily_eur: number
    target_daily_eur: number
    start_date: string
    end_date: string
    total_days: number
    days_elapsed: number
    budget_so_far_eur: number
    actual_so_far_eur: number
    on_track: boolean
    saved_vs_pace_eur: number
    overspent_eur: number
    fast_forwarded: boolean
  } | null
}

export async function createChallenge(
  customerId: string,
  category: string,
  pct: number,
  days = 14,
): Promise<Challenge> {
  const res = await fetch(`${API}/challenges`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ customer_id: customerId, category, pct, days }),
  })
  if (!res.ok) throw new Error('create challenge failed')
  return res.json()
}

export async function fetchChallenges(customerId: string): Promise<ChallengeProgress> {
  const res = await fetch(`${API}/challenges?customer_id=${customerId}`)
  if (!res.ok) throw new Error('fetch challenges failed')
  return res.json()
}

export async function fastForward(customerId: string, days = 7): Promise<ChallengeProgress> {
  const res = await fetch(`${API}/challenges/fast_forward?customer_id=${customerId}&days=${days}`, {
    method: 'POST',
  })
  if (!res.ok) throw new Error('fast forward failed')
  return res.json()
}

export interface SimulateResult {
  classification: {
    basket: string
    probabilities: Record<string, number>
    confidence: number
    is_subscription: number
    source?: 'jev' | 'rules'
  }
  amount: number
  description: string
  category: string
  category_month_spent_eur: number
  category_month_after_eur: number
  balance_now_eur: number
  balance_after_eur: number
  safe_to_spend_weekly_eur: number
  safe_to_spend_weekly_after_eur: number
  remaining_after_eur: number
  verdict: string
  tone: 'good' | 'warn' | 'bad'
  persisted: boolean
}

export async function simulateTx(
  tx: { amount: number; description: string; category: string; merchant_id?: string | null; mcc?: string | null },
  customerId: string,
): Promise<SimulateResult> {
  const res = await fetch(`${API}/simulate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...tx, customer_id: customerId }),
  })
  if (!res.ok) throw new Error('simulate failed')
  return res.json()
}

export async function clearSimulated(customerId: string): Promise<{ cleared: number }> {
  const res = await fetch(`${API}/simulate?customer_id=${customerId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('clear failed')
  return res.json()
}

export interface SpendingScope {
  start?: string
  end?: string
  category?: string | null
  basket?: string | null
  attention?: boolean
}

export interface SpendingEvidence extends SpendingScope {
  label: string
  count?: number
}

export interface ExperimentDraft {
  category: string
  pct: number
  days: number
}

export interface TransactionPage {
  start: string
  end: string
  count: number
  total_eur: number
  rows: {
    id: number
    date: string
    category: string
    merchant: string | null
    amount_eur: number
    basket: string
    transaction_type: string
    receipt_id?: string
  }[]
}

export interface Receipt {
  total_eur: number
  food_eur: number
  non_food_eur: number
  categories: { name: string; amount_eur: number }[]
  items: { name: string; amount_eur: number; category: string; group: 'Food' | 'Non-food' }[]
}

export async function fetchReceipt(customerId: string, receiptId: string, signal: AbortSignal): Promise<Receipt> {
  const query = new URLSearchParams({ customer_id: customerId })
  const res = await fetch(`${API}/receipts/${encodeURIComponent(receiptId)}?${query}`, { signal })
  if (!res.ok) throw new Error(`receipt failed: ${res.status}`)
  return res.json()
}

export async function fetchTransactions(customerId: string, scope: SpendingScope, offset: number, signal: AbortSignal): Promise<TransactionPage> {
  const query = new URLSearchParams({ customer_id: customerId, offset: String(offset) })
  for (const [key, value] of Object.entries(scope)) {
    if (value) query.set(key, String(value))
  }
  const res = await fetch(`${API}/transactions?${query}`, { signal })
  if (!res.ok) throw new Error('transactions failed')
  return res.json()
}

export interface PaydayCheck {
  as_of: string
  estimated_payday: string | null
  balance_eur: number
  bills: { name: string; predicted_date: string; amount_eur: number }[]
  bill_total_eur: number
  buffer_eur: number
  purchase_eur: number
  projected_before_eur: number
  projected_after_eur: number
  room_eur: number
}

export async function fetchPayday(customerId: string, purchase: number, buffer: number, signal: AbortSignal): Promise<PaydayCheck> {
  const query = new URLSearchParams({ customer_id: customerId, purchase_eur: String(purchase), buffer_eur: String(buffer) })
  const res = await fetch(`${API}/payday?${query}`, { signal })
  if (!res.ok) throw new Error('payday forecast failed')
  return res.json()
}

export async function fetchChallengeQuote(customerId: string, draft: ExperimentDraft, signal: AbortSignal): Promise<{ budget_eur: number }> {
  const query = new URLSearchParams({
    customer_id: customerId, category: draft.category, pct: String(draft.pct), days: String(draft.days),
  })
  const res = await fetch(`${API}/challenges/quote?${query}`, { signal })
  if (!res.ok) throw new Error('challenge quote failed')
  return res.json()
}
