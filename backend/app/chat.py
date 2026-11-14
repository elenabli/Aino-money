import datetime
import hashlib
import json
from typing import Literal

from openai import OpenAI

from . import config, tools


def _log_chat(customer_id: str, messages: list[dict], result: dict) -> None:
    try:
        import csv

        path = config.DATA_DIR / "chat_log.csv"
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        new = not path.exists()
        with open(path, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["ts", "customer_id", "messages_json", "answer", "trace_json"])
            w.writerow([
                datetime.datetime.now().isoformat(timespec="seconds"),
                customer_id,
                json.dumps(messages, ensure_ascii=False),
                result.get("answer", ""),
                json.dumps(result.get("trace", []), ensure_ascii=False),
            ])
    except Exception:
        pass


def _client_headers(customer_id: str, messages: list[dict]) -> dict:
    headers = dict(config.CHAT_HEADERS)
    if "opencode.ai" in config.CHAT_BASE_URL and "x-opencode-session" not in headers:
        first_user = next((m["content"] for m in messages if m["role"] == "user"), "")
        digest = hashlib.sha256(f"{customer_id}:{first_user}".encode()).hexdigest()[:32]
        headers["x-opencode-session"] = f"ses_{digest}"
    return headers

SYSTEM_PROMPT = """You are Aino, a friendly financial coach inside the S-Bank app. You have read-only access
to the user's own transaction data (synthetic demo data). Your mission: help people understand where their
money goes, in plain language, and nudge them towards healthier habits.

Pedagogy: explain spending using three baskets:
1. Mandatory & regular (rent, utilities, subscriptions) - fixed costs
2. Mandatory & irregular (unexpected necessities: broken washing machine, car repair)
3. Everyday spending that slips through your fingers (coffees, eating out, impulse buys)

Rules:
- Answer ONLY with numbers returned by your tools. Never invent or estimate figures.
- BE BRIEF: 1-3 short sentences, flowing text. No markdown lists, no bold, no bullet points unless the user explicitly asks for a breakdown.
- A chart is shown next to your answer when relevant: don't repeat its numbers, just give the one-line takeaway (e.g. "You spent most on housing - about 30% of your money went there.").
- Merchant identifiers are anonymized codes like MRC-RES-0068. Never invent merchant names;
  refer to them as "a restaurant you visit" or by their code.
- YOU ARE THE FINANCIAL COACH. Never tell the user to "consult a financial advisor", "speak to your bank", or give
  similar deflections. The whole point of this app is that the coaching comes from you. Always give concrete,
  numbers-based guidance from the data: which categories to trim and by how much, or offer to start a savings
  goal or an experiment right here. When a scenario doesn't fit the budget, use the scenario tool and present
  its cover options.
- When the user describes a hypothetical change ("what if my rent goes up by X", "if I bought Y"), use the
  scenario tool with the monthly amount.
- When the user asks about upcoming payments, the next salary, bills, or whether money will last,
  use the upcoming_events tool. If it reports a low-balance risk, lead with that warning.
- Use euros, format like 42.10 EUR. Prefer weekly/monthly framing.
- Be warm, short and concrete. Use simple Finnish everyday language vibes but reply in the language the user writes in.
- When relevant, mention the basket a number belongs to.
- If the user asks about other people or other customers, politely decline - you only see their own data.
- Never give investment advice. Safe-to-spend guidance is fine.
"""

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "spend_by_category",
            "description": "Monthly spending per category for the last N months (default 3). Optional category filter. Valid categories: Entertainment, Groceries, Health, Home & Tech, Housing, Restaurants, Transportation, Travel, Utilities. Use category 'taxis' for taxi rides. For calendar periods pass inclusive start and end dates.",
            "parameters": {
                "type": "object",
                "properties": {
                    "months": {"type": "integer", "minimum": 1, "maximum": 24},
                    "start": {"type": "string", "description": "Inclusive YYYY-MM-DD"},
                    "end": {"type": "string", "description": "Inclusive YYYY-MM-DD"},
                    "category": {"type": "string", "description": "Optional category name, e.g. Restaurants, or 'taxis'"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "basket_breakdown",
            "description": "Spending split by the three baskets plus income/savings, with top merchants per basket.",
            "parameters": {
                "type": "object",
                "properties": {"months": {"type": "integer", "minimum": 1, "maximum": 24}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "monthly_income",
            "description": "User's median monthly salary income and salary by month.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "current_balance",
            "description": "Current account balance.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "subscriptions",
            "description": "Detected recurring subscriptions/bills and their estimated monthly cost.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "safe_to_spend",
            "description": "How much the user can safely spend this month/week after mandatory costs, buffer and a 10% savings goal.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "what_if",
            "description": "Simulate savings if spending in a category changed by a percentage.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Category like Restaurants"},
                    "change_pct": {"type": "number", "description": "Percent change, negative means less spending"},
                },
                "required": ["category", "change_pct"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "spender_profile",
            "description": "User's spender profile: basket shares and impulse score.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "benchmark",
            "description": "Compares the user's monthly spending by category with the average customer of the same age in this demo dataset (Statistics Finland-inspired). Use for questions like 'am I spending more than others' or 'is this normal'. Call the comparison 'your peers', never 'average Finn'.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "coaching_plan",
            "description": "Top 3 concrete coaching actions computed from the user's data, with monthly/yearly impact in euros. Use when the user asks what they should do, how to save, or for advice.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "goal_plan",
            "description": "Creates a savings goal plan: how much to save weekly, how many months to reach the target at the current safe-to-save rate.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "What the user is saving for, e.g. a bike"},
                    "target_eur": {"type": "number", "description": "Target amount in euros"},
                    "months": {"type": "integer", "description": "Optional desired timeline in months"},
                },
                "required": ["name", "target_eur"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "challenge",
            "description": "Starts a spend-cap experiment: the user tries spending pct% less on a category for N days, with a daily budget. Use when the user wants to try a change or an experiment, e.g. 'let me try spending 20% less on restaurants for two weeks'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Category like Restaurants"},
                    "pct": {"type": "number", "description": "Percent reduction, e.g. 20"},
                    "days": {"type": "integer", "description": "Days, default 14"},
                },
                "required": ["category", "pct"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scenario",
            "description": "Simulates a monthly fixed-cost change (e.g. rent increase of X per month) on safe-to-spend. Returns the new safe-to-spend and, if negative, concrete cover options from the user's coaching plan (which categories to trim and how much).",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "What changed, e.g. rent increase"},
                    "monthly_eur": {"type": "number", "description": "Extra monthly cost in euros"},
                },
                "required": ["description", "monthly_eur"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "challenge_progress",
            "description": "Reports progress of the user's active experiment: days elapsed, budget vs actual spend, and how much they saved compared with their usual pace.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "upcoming_events",
            "description": "Predicts upcoming recurring payments (rent, utilities, subscriptions) and the next salary, with days-until and a low-balance risk check. Use for questions about the future, upcoming bills, when salary arrives, or whether money will last.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "recent_transactions",
            "description": "Latest transactions of the user.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 30}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "top_merchants",
            "description": "Merchants where the user spends the most, optionally filtered by category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "months": {"type": "integer", "minimum": 1, "maximum": 24},
                },
                "required": [],
            },
        },
    },
]

TOOL_IMPL = {
    "spend_by_category": lambda cid, a: tools.spend_by_category(cid, a.get("months", 3), a.get("category"), a.get("start"), a.get("end")),
    "basket_breakdown": lambda cid, a: tools.basket_breakdown(cid, a.get("months", 3)),
    "monthly_income": lambda cid, a: tools.monthly_income(cid),
    "current_balance": lambda cid, a: tools.current_balance(cid),
    "subscriptions": lambda cid, a: tools.subscriptions(cid),
    "safe_to_spend": lambda cid, a: tools.safe_to_spend(cid),
    "what_if": lambda cid, a: tools.what_if(cid, a["category"], float(a["change_pct"])),
    "spender_profile": lambda cid, a: tools.spender_profile(cid),
    "upcoming_events": lambda cid, a: tools.upcoming_events(cid),
    "benchmark": lambda cid, a: tools.benchmark(cid),
    "coaching_plan": lambda cid, a: tools.coaching_plan(cid),
    "goal_plan": lambda cid, a: tools.set_goal(cid, a["name"], float(a["target_eur"]), a.get("months")),
    "challenge": lambda cid, a: tools.create_challenge(cid, a["category"], float(a["pct"]), int(a.get("days", 14))),
    "challenge_progress": lambda cid, a: tools.challenge_progress(cid),
    "recent_transactions": lambda cid, a: tools.recent_transactions(cid, a.get("limit", 10)),
    "top_merchants": lambda cid, a: tools.top_merchants(cid, a.get("category"), a.get("months", 3)),
}

BASKET_LABELS = {
    "mandatory_regular": "Must-pays",
    "mandatory_irregular": "Unexpected",
    "everyday_discretionary": "Everyday",
    "savings_investing": "Saving",
    "income": "Income",
}

CHART_COLORS = ["#007a4d", "#3fae6a", "#ffb03a", "#e0654a", "#5b7ea8", "#8f6bb8"]

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _short_month(ym: str) -> str:
    try:
        return _MONTHS[int(ym[5:7]) - 1]
    except (ValueError, IndexError):
        return ym


def _make_chart(tool_name: str, result: dict) -> dict | None:
    if tool_name == "spend_by_category":
        rows = result.get("rows", [])
        if not rows:
            return None
        months = sorted({r["month"] for r in rows})
        cats = sorted({r["category"] for r in rows})
        totals = {c: sum(r["spent_eur"] for r in rows if r["category"] == c) for c in cats}
        top = sorted(cats, key=lambda c: -totals[c])[:6]
        if len(months) < 2:
            return {"kind": "donut", "title": "Spending by category", "labels": top, "values": [round(totals[c], 2) for c in top], "unit": "eur"}
        series = [
            {
                "name": c,
                "data": [
                    next((r["spent_eur"] for r in rows if r["category"] == c and r["month"] == m), 0)
                    for m in months
                ],
            }
            for c in top
        ]
        return {
            "kind": "line",
            "title": "Spending by category",
            "labels": [_short_month(m) for m in months],
            "series": series,
        }

    if tool_name == "basket_breakdown":
        totals = result.get("totals", [])
        if not totals:
            return None
        return {
            "kind": "donut",
            "title": "Where the money went",
            "labels": [BASKET_LABELS.get(t["basket"], t["basket"]) for t in totals],
            "values": [t["total_eur"] for t in totals],
            "unit": "eur",
        }

    if tool_name == "benchmark":
        rows = result.get("rows", [])
        if not rows:
            return None
        return {
            "kind": "bar",
            "title": "You vs your peers (EUR/month)",
            "labels": [r["category"] for r in rows],
            "values": [r["user_monthly_eur"] for r in rows],
            "values2": [r["finn_monthly_eur"] for r in rows],
            "series_names": ["You", "Your peers"],
        }

    if tool_name == "spender_profile":
        shares = result.get("basket_shares_pct", {})
        if not shares:
            return None
        order = ["mandatory_regular", "mandatory_irregular", "everyday_discretionary", "savings_investing"]
        labels = [BASKET_LABELS.get(k, k) for k in order if k in shares]
        values = [shares[k] for k in order if k in shares]
        return {
            "kind": "donut",
            "title": "Your spending profile",
            "labels": labels,
            "values": values,
            "unit": "pct",
            "secondary": {
                "label": "Impulse score",
                "value": result.get("impulse_score_0_100", 0),
                "max": 100,
            },
        }

    if tool_name == "safe_to_spend":
        avg = result.get("avg_monthly", {})
        if not avg:
            return None
        items = [("Must-pays", avg.get("mandatory_regular", 0)),
                 ("Unexpected", avg.get("mandatory_irregular", 0)),
                 ("Everyday", avg.get("everyday_discretionary", 0)),
                 ("Savings goal", result.get("savings_goal_10pct", 0)),
                 ("Safe to spend", result.get("safe_to_spend_monthly", 0))]
        return {"kind": "bar", "title": "Monthly budget", "labels": [i[0] for i in items], "values": [round(i[1], 2) for i in items]}

    return None


CoachPrompt = Literal["weekly_budget", "spending_profile", "dining_savings", "monthly_spending", "transaction_spending"]


def _answer_metadata(trace: list[dict]) -> dict:
    metadata: dict = {"evidence": []}
    for entry in trace:
        tool, result = entry["tool"], entry["result"]
        if tool in {"spend_by_category", "transaction_list", "basket_breakdown"}:
            scope = {"start": result["start"], "end": result["end"], "category": result.get("category")}
            if tool == "basket_breakdown":
                for row in result["totals"]:
                    metadata["evidence"].append({
                        **scope, "basket": row["basket"], "label": BASKET_LABELS.get(row["basket"], row["basket"]),
                    })
            else:
                metadata["evidence"].append({
                    **scope, "basket": result.get("basket"), "count": result["count"],
                    "label": result.get("category") or BASKET_LABELS.get(result.get("basket"), "Spending"),
                })
        if (
            tool == "what_if"
            and result.get("resolved_category")
            and tools.resolve_category(result["category"])[1] is None
            and -100 < result["change_pct"] < 0
        ):
            metadata["experiment"] = {
                "category": result["resolved_category"], "pct": -result["change_pct"], "days": 14,
            }
    return metadata


def starter_answer(prompt: CoachPrompt, customer_id: str, category: str | None = None,
                   month_offset: int = 1, start: str | None = None, end: str | None = None,
                   basket: str | None = None, compare: bool = False) -> dict:
    args = {}
    comparison = None
    if prompt == "weekly_budget":
        tool_name = "safe_to_spend"
        result = tools.safe_to_spend(customer_id)
        weekly = result["safe_to_spend_weekly"]
        if weekly >= 0:
            answer = f"Your estimated safe-to-spend is €{weekly:.2f} per week after bills, an unexpected-expense buffer and savings."
        else:
            answer = f"Your estimated weekly budget falls €{abs(weekly):.2f} short after bills, an unexpected-expense buffer and savings."
    elif prompt == "spending_profile":
        tool_name = "basket_breakdown"
        args = {"months": 3}
        result = tools.basket_breakdown(customer_id, **args)
        if result["totals"]:
            top = max(result["totals"], key=lambda row: row["total_eur"])
            label = BASKET_LABELS.get(top["basket"], top["basket"])
            answer = f"{label} was your largest spending basket across the three months shown (€{top['total_eur']:.2f})."
        else:
            answer = "There’s no spending in the three months covered by this demo."
    elif prompt in {"monthly_spending", "transaction_spending"}:
        if prompt == "monthly_spending":
            start = tools.months_ago(month_offset + 1)
            end = (datetime.date.fromisoformat(tools.months_ago(month_offset)) - datetime.timedelta(days=1)).isoformat()
        tool_name = "transaction_list"
        args = {"start": start, "end": end, "category": category, "basket": basket}
        result = tools.transaction_list(customer_id, **args)
        count = result["count"]
        answer = (
            f"From {result['start']} to {result['end']}, you spent €{result['total_eur']:.2f} "
            f"across {count} {'transaction' if count == 1 else 'transactions'}."
        )
        # Row-level evidence is fetched from the transactions endpoint when opened.
        result.pop("rows")
        if prompt == "monthly_spending" and compare and month_offset >= 2:
            comparison_args = {
                **args,
                "start": tools.months_ago(month_offset),
                "end": (datetime.date.fromisoformat(tools.months_ago(month_offset - 1)) - datetime.timedelta(days=1)).isoformat(),
            }
            comparison = tools.transaction_list(customer_id, **comparison_args)
            comparison.pop("rows")
            change = round(result["total_eur"] - comparison["total_eur"], 2)
            direction = "more" if change > 0 else "less"
            if change:
                answer += f" That’s €{abs(change):.2f} {direction} than the following month (€{comparison['total_eur']:.2f})."
            else:
                answer += " That’s the same amount as the following month."
    else:
        tool_name = "what_if"
        args = {"category": category or "Restaurants", "change_pct": -20}
        result = tools.what_if(customer_id, **args)
        answer = (
            f"Spending 20% less on {args['category'].lower()} could free up €{result['saved_monthly_eur']:.2f} a month, "
            f"or €{result['saved_yearly_eur']:.2f} a year, based on your recent spending."
        )

    trace = [{"tool": tool_name, "args": args, "result": result}]
    if comparison is not None:
        trace.append({"tool": tool_name, "args": comparison_args, "result": comparison})
    return {"answer": answer, "trace": trace, "chart": _make_chart(tool_name, result), **_answer_metadata(trace)}


def chat(messages: list[dict], customer_id: str) -> dict:
    client = OpenAI(
        api_key=config.CHAT_API_KEY,
        base_url=config.CHAT_BASE_URL,
        default_headers=_client_headers(customer_id, messages),
        timeout=20.0,
        max_retries=0,
    )
    system = f"{SYSTEM_PROMPT}\nThe demo transaction date is {tools.ref_date().isoformat()}. Resolve relative dates against it."
    msgs = [{"role": "system", "content": system}, *messages]

    trace: list[dict] = []
    chart: dict | None = None
    for _ in range(5):
        resp = client.chat.completions.create(
            model=config.CHAT_MODEL,
            messages=msgs,
            tools=TOOL_SPECS,
            tool_choice="auto",
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            result = {"answer": msg.content or "", "trace": trace, "chart": chart, **_answer_metadata(trace)}
            _log_chat(customer_id, messages, result)
            return result

        msgs.append(msg)
        for call in msg.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments or "{}")
            result = TOOL_IMPL[name](customer_id, args)
            trace.append({"tool": name, "args": args, "result": result})
            if chart is None:
                chart = _make_chart(name, result)
            msgs.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    result = {"answer": "Sorry, I could not compute that.", "trace": trace, "chart": chart}
    _log_chat(customer_id, messages, result)
    return result
