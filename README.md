# Spanki — chat with your money (S-Bank Junction)

Mobile chat coach over synthetic transaction data. LLM (OpenAI-compatible API) answers
questions via tools; Jev (TypeSafe) classifies merchants into the three pedagogical baskets.

See [FEATURES.md](FEATURES.md) for the feature map and how each piece is supposed to work.

## Setup

1. Optional provider keys: copy `backend/.env.example` to `backend/.env`. Set
   `OPENAI_API_KEY` (and `OPENAI_BASE_URL` / `OPENAI_MODEL` if needed) for free-form chat,
   and `TYPESAFE_API_KEY` for live Jev classification. The starter questions and
   demo purchase simulation run with the local database.
2. Install backend deps (uv): `uv venv backend/.venv && uv pip install -p backend/.venv -r backend/requirements.txt`
3. Install frontend deps: `cd frontend && npm install`

## Pipeline

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

1. Choose a persona to open Aino. Start with **Check my weekly budget**.
2. Select **Try a simulated purchase** and replay a purchase. Compare the weekly
   estimates before and after, then return to **Coach** and select **Refresh my weekly budget**.
3. Choose **Find savings from eating out**. Follow the link to **Goals** to build
   a savings plan or start a restaurant spending experiment.
4. Fast-forward the experiment to see simulated progress. Use **Reset simulated spending**
   to replay it. This also clears simulated purchases for that persona.

## How it works

- `db.py` — CSV -> DuckDB (3.6M tx, 515 merchants, 5100 customers)
- `jev.py` — one Jev request per merchant: Choice (basket) + Noul (subscription,
  irregular risk); cached in `backend/data/jev_merchant_cache.json`; confidence < 0.7 falls back to rules
- `tools.py` — deterministic per-customer basket assignment (rules + Jev labels +
  regular-pattern/statistical anomaly detection) and the query functions the LLM can call
  (`safe_to_spend`, `what_if`, `spender_profile`, `subscriptions`, ...)
- `chat.py` — LLM tool-calling loop; all numbers come from tools, never from the model
- frontend — Vite + React mobile chat UI with tool-trace transparency
