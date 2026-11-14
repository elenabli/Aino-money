# Aino Money — features & how they work

AI money coach over synthetic S-Bank transaction data. Mobile web app (Vite/React)
+ FastAPI backend + DuckDB. Two AI services: an OpenAI-compatible chat LLM
(tool-calling) and **Jev** (TypeSafe) for structured transaction decisions.

## Tabs

| Tab | What it does | Data flow |
|---|---|---|
| Start screen | The app opens on a persona picker (Sofia 35 with receipts, Emma 20, Mikko 29, Riitta 63, Laura 38 spending above income, Antti 37 overdrawn after an unexpected cost, Pekka 53 with irregular income). Choosing one opens Home; the profile pill on Home switches persona. Persisted in localStorage. | `GET /personas` |
| Coach | Opens after persona selection with a heads-up and three data-backed starter questions. Free-form chat uses the configured AI provider. | `POST /chat` |
| Month | Balance/income/spent/safe-to-spend cards; "What do you want to track?" — category donut, basket donut, balance line, peer benchmark bars; coaching plan card, recorded transactions with basket labels and links to Aino, and a payday affordability check. | `GET /monthly`, `/benchmark`, `/coaching_plan` |
| Goals | Savings goal (weekly target, months, progress from real savings deposits) + Money experiment (spend-cap challenge with fast-forward). | `GET/POST /goal`, `/challenges` |
| Simulate | Random spend from the user's own history → Jev or demo rules classify → persisted as simulated → budget burns down. Alternatives: wait for salary / trim / make a goal. | `GET /random_tx`, `POST/DELETE /simulate` |

**AI chat, live (`POST /chat/stream`).** Free-form questions stream as server-sent events: each
tool Aino calls appears as a step ("Comparing with peers your age"), charts arrive as they are
drawn, then the answer text, then 2–3 AI-generated follow-up questions. The model can request a
chart with the `show_chart` tool (`category_trend`, `category_split`, `baskets`, `peers`,
`what_if`, `budget`, `merchants`). The model picks the view, and `app/charts.py` computes every
value from the ledger. Answers keep a **How Aino worked this out** record of the steps.
**Receipt insight.** On an itemised Prisma receipt in the transaction list, **See more: Aino's insight
on this receipt** opens the chat with `receipt_id`. `app/receipt_insight.py` groups the classified
lines into shopping groups (fruit & veg, dairy & eggs, protein, snacks & sweets, drinks, household…)
and labels each group as an essential, treat, convenience or extra. For each group it compares this
month so far with the user's usual for the same days (3-month average) and gives an evaluation
(*On your usual pace*, *45% above usual*, flagged amber for treats). The card renders instantly, then
Claude explains it. The `grocery_groups` chart view shows every group this month vs usual.
Home keeps the S-Pankki look (bonus banner, accounts) with a compact **Aino noticed something** card on top: a one-line 14-day insight that opens the chat.

Coach answers link to their date- and category-filtered transaction evidence. What-if savings answers can prefill a spend-cap experiment, with the euro budget previewed before confirmation.

## Core concepts

**Three baskets (S-Bank pedagogy).** Every expense is classified into:
`mandatory_regular` (rent, bills, subs) · `mandatory_irregular` (broken washing machine)
· `everyday_discretionary` (slippage) — plus `savings_investing` and `income`.

Classification pipeline (`app.pipeline`): rules (transaction_type) →
**Jev** per-merchant Choice + Nouls (subscription, irregular risk), cached in
`backend/data/jev_merchant_cache.json` → per-customer deterministic refinements
(regular-payment pattern, amount outliers 2.5× median) → basket column in
`tx_enriched`. Low Jev confidence (<0.7) falls back to category rules.

**Chat with data.** The LLM never sees raw rows: it calls tools
(`spend_by_category`, `basket_breakdown`, `safe_to_spend`, `what_if`,
`spender_profile`, `subscriptions`, `upcoming_events`, `benchmark`,
`coaching_plan`, `goal_plan`, `challenge`, `challenge_progress`, …), gets
numbers back, and writes a 1–3 sentence takeaway. Charts are generated
server-side from tool results and rendered above the text.

**Safe-to-spend.** median salary (6 mo) − avg mandatory − irregular buffer
(50%) − 10% savings goal − simulated spends this month. Weekly = monthly / 4.33.
Presented as an estimate; simulated spends burn it down in real time.

**Upcoming events / forecast.** Median day-of-month per recurring payment type
(rent, utilities, detected subscriptions) → predicted next dates, days until
next salary, and a forward balance simulation flagging low-balance risk.

**Benchmarks.** "You vs your peers": user's 3-month category averages vs the
average customer of the same age group in the dataset (Statistics
Finland-inspired, calibrated to demo scale). Always labeled as demo peers,
never "average Finn".

**Experiments (challenges).** Spend-cap: baseline daily spend (3-mo avg) →
target daily = baseline × (1−pct). "Fast-forward 7 days" samples the user's own
historical purchases into future days (capped by the daily budget) and reports
days elapsed, budget vs actual, saved-vs-pace, on/off track. Progress is read
from the same transaction table the chat uses.

**Simulated transactions.** Inserted into `tx_enriched` with `simulated=1`:
they affect balance, month totals, safe-to-spend, charts and chat answers.
`DELETE /simulate` (Reset) clears them. Re-running the ingest pipeline rebuilds
`tx_enriched` and also clears them.

## Backend layout (`backend/app/`)

- `db.py` — DuckDB ingest (`tx`, `customers`, `merchants`, `merchant_classification`,
  app tables `goals`, `challenges`), `ensure_app_tables()` migration
- `jev.py` — TypeSafe client: batch merchant classification + single-transaction
  classification (`classify_transaction`)
- `tools.py` — all query/analytics functions the tools wrap (safe-to-spend,
  forecast, benchmark, coaching plan, goals, challenges, fast-forward)
- `chat.py` — system prompt, tool specs, OpenAI-compatible tool loop, chart specs
- `main.py` — FastAPI routes
- `pipeline.py` — ingest → Jev batch → enrich

## API surface

`GET /personas /profile /overview /monthly /welcome /benchmark /coaching_plan
/random_tx /jev/status` · `POST /chat /simulate /goal /challenges` ·
`POST /challenges/fast_forward` · `DELETE /simulate`. All accept
`customer_id` (default `DEMO_CUSTOMER_ID`).

## Known simplifications (demo-scope)

- Simulated rows live only in `tx_enriched` (wiped on pipeline re-run).
- Challenge "progress" is generated by fast-forward, not real future data.
- Benchmarks are dataset-calibrated, not a cited Statistics Finland table.
- One active challenge per customer; goals are per-customer singletons.
- No auth: `customer_id` is passed openly (synthetic data).
