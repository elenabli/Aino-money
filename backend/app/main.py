from datetime import date

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from openai import APIError
from pydantic import BaseModel, Field

from . import chat, config, db, tools

app = FastAPI(title="spanki")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

PERSONAS = [
    {
        "id": "CUST02220",
        "name": "Emma",
        "age": 20,
        "label": "Student",
        "description": "First job, student budget, lots of small everyday purchases.",
    },
    {
        "id": "CUST05013",
        "name": "Mikko",
        "age": 29,
        "label": "Young professional",
        "description": "Steady salary, saving for bigger life goals.",
    },
    {
        "id": "CUST00001",
        "name": "Riitta",
        "age": 63,
        "label": "Pensioner",
        "description": "Fixed income, wants clarity on everyday spending.",
    },
]


def _cid(customer_id: str | None) -> str:
    return customer_id or config.DEMO_CUSTOMER_ID


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    prompt: chat.CoachPrompt | None = None
    category: str | None = Field(default=None, max_length=100)
    month_offset: int = Field(default=1, ge=1, le=24)
    start: date | None = None
    end: date | None = None
    basket: str | None = Field(default=None, max_length=40)
    customer_id: str | None = None


@app.get("/health")
def health():
    return {"ok": True, "model": config.OPENAI_MODEL, "jev": config.TYPESAFE_MODEL}


@app.get("/personas")
def personas():
    out = []
    for p in PERSONAS:
        bal = tools.current_balance(p["id"])["balance_eur"] or 0
        income = tools.monthly_income(p["id"])["median_monthly_income"]
        out.append({**p, "balance_eur": bal, "median_income_eur": income})
    return out


@app.get("/profile")
def profile(customer_id: str | None = Query(default=None)):
    cid = _cid(customer_id)
    con = db.connect()
    row = con.execute(
        "SELECT customer_id, customer_postal_code, customer_age FROM customers WHERE customer_id = ?",
        [cid],
    ).fetchone()
    con.close()
    return {"customer_id": row[0], "postal_code": row[1], "age": row[2]}


@app.post("/chat")
def chat_endpoint(req: ChatRequest):
    cid = req.customer_id or config.DEMO_CUSTOMER_ID
    msgs = [m.model_dump() for m in req.messages]
    if req.prompt is not None:
        return chat.starter_answer(
            req.prompt, cid, req.category, req.month_offset,
            req.start.isoformat() if req.start else None, req.end.isoformat() if req.end else None, req.basket,
        )
    if not config.OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="Free-form chat requires an AI provider.")
    try:
        return chat.chat(msgs, cid)
    except APIError as exc:
        raise HTTPException(status_code=503, detail="The chat provider is unavailable.") from exc


@app.get("/transactions")
def transactions(customer_id: str | None = None, start: date | None = None, end: date | None = None,
                 category: str | None = None, basket: str | None = None, attention: bool = False,
                 offset: int = Query(default=0, ge=0)):
    return tools.transaction_list(
        _cid(customer_id), start.isoformat() if start else None, end.isoformat() if end else None,
        category, basket, attention, offset,
    )


@app.get("/payday")
def payday(customer_id: str | None = None, purchase_eur: float = Query(default=0, ge=0, le=1e7),
           buffer_eur: float = Query(default=100, ge=0, le=1e7)):
    return tools.payday_check(_cid(customer_id), purchase_eur, buffer_eur)


@app.get("/overview")
def overview(customer_id: str | None = Query(default=None)):
    cid = _cid(customer_id)
    return {
        "balance": tools.current_balance(cid),
        "safe_to_spend": tools.safe_to_spend(cid),
        "baskets": tools.basket_breakdown(cid, 1),
        "subscriptions": tools.subscriptions(cid),
    }


@app.get("/monthly")
def monthly(customer_id: str | None = Query(default=None)):
    return tools.monthly_overview(_cid(customer_id))


@app.get("/welcome")
def welcome(customer_id: str | None = Query(default=None)):
    return {
        "message": tools.welcome_message(_cid(customer_id)),
        "chat_available": bool(config.OPENAI_API_KEY),
    }


class SimulateRequest(BaseModel):
    amount: float
    description: str = ""
    category: str | None = None
    merchant_id: str | None = None
    mcc: str | int | None = None
    customer_id: str | None = None
    prior: list[dict] | None = None


@app.post("/simulate")
def simulate(req: SimulateRequest):
    cid = _cid(req.customer_id)
    return tools.simulate_transaction(cid, req.amount, req.description, req.category, req.merchant_id, req.mcc, req.prior)


@app.delete("/simulate")
def clear_simulate(customer_id: str | None = Query(default=None)):
    cid = _cid(customer_id)
    return {"cleared": tools.clear_simulated(cid)}


@app.get("/random_tx")
def random_tx(customer_id: str | None = Query(default=None)):
    return tools.random_transaction(_cid(customer_id))


@app.get("/benchmark")
def benchmark(customer_id: str | None = Query(default=None)):
    return tools.benchmark(_cid(customer_id))


@app.get("/coaching_plan")
def coaching_plan(customer_id: str | None = Query(default=None)):
    return tools.coaching_plan(_cid(customer_id))


class GoalRequest(BaseModel):
    name: str
    target_eur: float = Field(ge=0.01, allow_inf_nan=False)
    months: int | None = Field(default=None, gt=0)
    customer_id: str | None = None


@app.post("/goal")
def set_goal(req: GoalRequest):
    return tools.set_goal(_cid(req.customer_id), req.name, req.target_eur, req.months)


@app.get("/goal")
def get_goal(customer_id: str | None = Query(default=None)):
    return tools.get_goal(_cid(customer_id))


class ChallengeRequest(BaseModel):
    category: str = Field(min_length=1, max_length=100)
    pct: float = Field(gt=0, lt=100)
    days: int = Field(default=14, ge=1, le=30)
    customer_id: str | None = None


@app.get("/challenges/quote")
def challenge_quote(category: str, pct: float = Query(gt=0, lt=100), days: int = Query(default=14, ge=1, le=30),
                    customer_id: str | None = None):
    return tools.challenge_quote(_cid(customer_id), category, pct, days)


@app.post("/challenges")
def create_challenge(req: ChallengeRequest):
    return tools.create_challenge(_cid(req.customer_id), req.category, req.pct, req.days)


@app.get("/challenges")
def challenges(customer_id: str | None = Query(default=None)):
    return tools.challenge_progress(_cid(customer_id))


@app.post("/challenges/fast_forward")
def fast_forward(customer_id: str | None = Query(default=None), days: int = Query(default=7, ge=1, le=30)):
    return tools.fast_forward(_cid(customer_id), days)


@app.get("/jev/status")
def jev_status():
    import json

    cache = {}
    if config.JEV_CACHE_PATH.exists():
        cache = json.loads(config.JEV_CACHE_PATH.read_text())
    con = db.connect()
    n = con.execute("SELECT count(*) FROM merchants").fetchone()[0]
    con.close()
    return {"classified": len(cache), "total_merchants": n}
