# Aino Money — chat with your money (S-Bank Junction)

Mobile chat coach over synthetic transaction data. LLM (OpenAI-compatible API) answers
questions via tools; Jev (TypeSafe) classifies merchants into the three pedagogical baskets.

See [FEATURES.md](FEATURES.md) for the feature map and how each piece is supposed to work.

## Setup

1. For free-form chat with Claude, use `backend/.env.example` as a reference for
   `backend/.env`. Set `CHAT_PROVIDER=anthropic` and add your Claude Console key
   as `ANTHROPIC_API_KEY`. The default model is `claude-sonnet-4-6`. Set
   `ANTHROPIC_MODEL` to override it, or `ANTHROPIC_WORKSPACE_ID` if your key
   requires an explicit workspace. Aino Money uses Anthropic’s compatibility endpoint
   to reuse its transaction tool calls. Restart the backend after changing settings.
   Set `TYPESAFE_API_KEY` for live Jev classification. Starter questions and the
   purchase simulation also run with the local database and no provider keys.
2. Install backend deps (uv): `uv venv backend/.venv && uv pip install -p backend/.venv -r backend/requirements.txt`
3. Install frontend deps: `cd frontend && npm install`

## Pipeline

Keep the provided transaction and customer exports at the workspace root. Raw datasets, generated receipts and local database files are ignored by Git.

If `backend/data/aino-money.duckdb` already exists, use it for the demo. Run the
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
2. Return to **Chat** to compare the previous month or ask **What if I ate out 20% less?**. Open the suggested experiment to review its prefilled settings and euro target, then start and fast-forward it.
3. Select **Check my weekly budget**, then **Check what fits before payday**. Enter a purchase and the reserve to keep. Expand the assumptions to see which predicted bills were counted.
4. Open **Spending → Browse transactions** at any time. **Pay attention** highlights flexible and unexpected expenses. **Good** marks routine essentials and savings. Both labels describe the basket and are review cues.
5. From the weekly budget answer, select **Try a simulated purchase** to replay a purchase to see the change in the demo’s budget. Historical evidence always shows recorded expenses. Use **Reset simulated spending** to clear projections for that persona.

## How it works

- `db.py` — CSV -> DuckDB (3.6M tx, 515 merchants, 5100 customers)
- `jev.py` — one Jev request per merchant: Choice (basket) + Noul (subscription,
  irregular risk); cached in `backend/data/jev_merchant_cache.json`; confidence < 0.7 falls back to rules
- `tools.py` — deterministic per-customer basket assignment (rules + Jev labels +
  regular-pattern/statistical anomaly detection) and the query functions the LLM can call
  (`safe_to_spend`, `what_if`, `spender_profile`, `subscriptions`, ...)
- `chat.py` — LLM tool-calling loop; all numbers come from tools, never from the model
- frontend — Vite + React mobile chat UI with tool-trace transparency

### S-Etukortti demo persona

Import the local receipt export after creating the database.

```bash
cd backend
.venv/bin/python -m app.receipts ~/Downloads/S-Etukortti_receipts_2025-11-14_to_2026-11-14.html
```

Select **Sofia → Chat → Show me the first step**. The demo starts with a €15,000
apartment deposit goal over 36 months. Aino compares that target with the latest
full month's cash flow, explains the three envelopes, and offers a dining
experiment with links to the supporting transactions. The goal is editable under
**Goals**.

Select **Sofia → Spending** to see the latest complete month's bank categories and
**Inside your grocery spending** for the latest 12 weeks of supermarket receipts.
Open **See grocery purchases** to drill down to transactions and itemised receipts.
**Ask Aino for a plan** works without an AI provider. Free-form chat can query the
same receipt aggregates for a date range.

Sofia combines a synthetic bank history shifted two months forward with one demo
purchase per receipt. The importer replaces the template's grocery and fuel
purchases and recalculates the account balance from a €6,000 opening balance.
Each receipt purchase is linked by `receipt_id` and takes its bank category from
the store. Detailed product categories are inferred from Finnish receipt labels.
Promotional bundles retain the component names and their combined net price.

Reimporting the same file refreshes classifications without duplicate receipts.
Running the transaction pipeline again restores the combined profile.

## Cloudflare demo

The Worker serves the Vite build and forwards `/api/*` to the Python container.
The cloud database is built from the challenge's synthetic transaction exports
and generated synthetic receipts. Generate the receipt CSVs with
`python3 scripts/generate_synthetic_receipts.py` if needed.

With Docker running and Cloudflare Containers available in your account:

```bash
backend/.venv/bin/python deploy/prepare_demo.py
npm --prefix frontend run build
npx wrangler@4.162.0 login
npx wrangler@4.162.0 deploy
```

For free-form chat, add a deployment-specific `ANTHROPIC_API_KEY` or
`OPENAI_API_KEY` as a Worker secret. Set the matching provider settings in
`wrangler.jsonc` if they differ from the default. Use a budget-limited key for a
shared demo. Starter questions work without a provider key.

The container starts from a clean DuckDB image. Goal edits, experiments and
simulated transactions are shared within this demo while that container is
running and reset when Cloudflare replaces it or it goes to sleep.

### Hetzner VPS with Cloudflare Tunnel

Build the synthetic demo database and frontend locally using the first two
commands above. From the repository root, package only the VPS inputs:

```bash
tar -czf /tmp/aino-money-vps.tar.gz .dockerignore backend/app/*.py backend/requirements.txt \
  deploy/Dockerfile deploy/compose.yaml deploy/nginx.conf deploy/data/aino-money.duckdb frontend/dist
scp /tmp/aino-money-vps.tar.gz USER@VPS:~/
```

On the VPS, with Docker and Docker Compose installed:

```bash
mkdir -p ~/aino-money
tar -xzf ~/aino-money-vps.tar.gz -C ~/aino-money
cd ~/aino-money
docker compose -f deploy/compose.yaml up -d --build
curl --fail http://127.0.0.1:8080/api/health
```

In Cloudflare, open **Networking → Tunnels**, create a tunnel, and run the
Linux install and service commands shown there on the VPS. Add a **Published
application** route for a subdomain in your Cloudflare zone with service URL
`http://127.0.0.1:8080`. Verify `https://YOUR_SUBDOMAIN/api/health`. Allow
outbound port 7844 if egress is restricted. The app listens on loopback.

For free-form chat, add the provider settings to `deploy/vps.env` on the VPS
and rerun Compose. Keep provider credentials and tunnel tokens out of the
archive. DuckDB changes survive container restarts in the `aino-money-data` volume.
An existing volume takes precedence over the seed database in a rebuilt image.
