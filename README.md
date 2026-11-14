# Spanki — chat with your money (S-Bank Junction)

Mobile chat coach over synthetic transaction data. LLM (OpenAI-compatible API) answers
questions via tools; Jev (TypeSafe) classifies merchants into the three pedagogical baskets.

See [FEATURES.md](FEATURES.md) for the feature map and how each piece is supposed to work.

## Setup

1. For free-form chat with Claude, use `backend/.env.example` as a reference for
   `backend/.env`. Set `CHAT_PROVIDER=anthropic` and add your Claude Console key
   as `ANTHROPIC_API_KEY`. The default model is `claude-sonnet-4-6`. Set
   `ANTHROPIC_MODEL` to override it, or `ANTHROPIC_WORKSPACE_ID` if your key
   requires an explicit workspace. Spanki uses Anthropic’s compatibility endpoint
   to reuse its transaction tool calls. Restart the backend after changing settings.
   Set `TYPESAFE_API_KEY` for live Jev classification. Starter questions and the
   purchase simulation also run with the local database and no provider keys.
2. Install backend deps (uv): `uv venv backend/.venv && uv pip install -p backend/.venv -r backend/requirements.txt`
3. Install frontend deps: `cd frontend && npm install`

## Pipeline

Keep the provided transaction and customer exports at the workspace root. Raw datasets, generated receipts and local database files are ignored by Git.

If `backend/data/spanki.duckdb` already exists, use it for the demo. Run the
pipeline to create it or after changing the source data.

```bash
cd backend
.venv/bin/python -m app.pipeline            # ingest + Jev classify (515 merchants) + enrich
.venv/bin/python -m app.pipeline --skip-jev # rule-based fallback only (no TypeSafe key)
```

## Run

```bash
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8000 --reload
cd frontend && npm run dev   # http://localhost:5173, proxies /api -> :8000
```

## Walk through the coach demo

1. Choose a persona and select **See last month’s dining spending** or **See last month’s taxi spending**. Open **Show transactions** to inspect the exact date range and matching recorded expenses. Use **Ask Aino about this spending** on a row to return to the coach.
2. Return to **Coach** to compare the previous month or ask **What if I ate out 20% less?**. Open the suggested experiment to review its prefilled settings and euro target, then start and fast-forward it.
3. Select **Check my weekly budget**, then **Check what fits before payday**. Enter a purchase and the reserve to keep. Expand the assumptions to see which predicted bills were counted.
4. Open **Month → Browse transactions** at any time. **Pay attention** highlights flexible and unexpected expenses. **Good** marks routine essentials and savings. Both labels describe the basket and are review cues.
5. In **Simulate**, replay a purchase to see the change in the demo’s budget. Historical evidence always shows recorded expenses. Use **Reset simulated spending** to clear projections for that persona.

## How it works

- `db.py` — CSV -> DuckDB (3.6M tx, 515 merchants, 5100 customers)
- `jev.py` — one Jev request per merchant: Choice (basket) + Noul (subscription,
  irregular risk); cached in `backend/data/jev_merchant_cache.json`; confidence < 0.7 falls back to rules
- `tools.py` — deterministic per-customer basket assignment (rules + Jev labels +
  regular-pattern/statistical anomaly detection) and the query functions the LLM can call
  (`safe_to_spend`, `what_if`, `spender_profile`, `subscriptions`, ...)
- `chat.py` — LLM tool-calling loop; all numbers come from tools, never from the model
- frontend — Vite + React mobile chat UI with tool-trace transparency
