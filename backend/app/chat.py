import datetime
import hashlib
import json
import os
import re
from typing import Literal

from fastapi.encoders import jsonable_encoder
from openai import OpenAI

from . import advice, config, receipts, tools
from . import charts as charts_mod
from .charts import CHART_TOOL_SPEC
from . import receipt_insight
from .receipt_insight import RECEIPT_TOOL_SPEC


def _log_chat(customer_id: str, messages: list[dict], result: dict) -> None:
    if os.getenv("AINO_MONEY_LOG_CHAT") == "0":
        return
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

SYSTEM_PROMPT = """You are Aino, a proactive personal money adviser inside the S-Bank app.
Help this user understand a purchase, anticipate the next week or two, and make progress on
what matters to them. Analyse the available evidence before replying; do not wait for the user
to ask you to investigate. Transaction data is synthetic demo data, accessible for this user only.
You can propose changes; creating a goal or starting an experiment requires the user's request.

On every turn:
- Answer the actual question first. Review the supplied persona, active goal, current 14-day
  check-in, upcoming commitments and conversation before deciding whether a nudge is useful.
- Use the latest 7-14 days for near-term advice, normally comparing the check-in's 14 days with
  the previous 14 days. Resolve dates against the supplied demo date, not the real calendar.
  Honour explicitly requested historical periods. Never compare a partial month to a full month
  as though both covered the same time. Fetch missing evidence with tools before making claims.
- Consider the check-in's three paths: current pace, 10% less flexible spending, and 20% less.
  These are alternatives, not cumulative savings or commitments. For a planning question,
  show the baseline and the two alternatives compactly, with the horizon and assumptions.
  For a narrow question, surface only the most relevant finding; do not dump scenarios every turn.
- Choose at most one proactive observation: an evidenced cash shortfall or upcoming bill first,
  then a material change affecting the user's goal, then a useful spending pattern. Connect it
  to the active goal by name when relevant. Acknowledge progress as well as risks. If nothing
  useful has changed, simply answer. Do not manufacture a problem to sound proactive.

Goals and personalisation:
- Persona preferences guide both tone and topic selection. The user's current words, priorities
  and requested level of detail override the demo profile. Never infer personality, ability,
  family circumstances or motives from age, purchases or an impulse score.
- Use the supplied saved goal, target and recorded progress. Do not invent a goal or assume
  its timeline is still desired. If no goal exists, give useful advice anyway; ask one brief
  question about priorities only when it would change your recommendation.
- Offer one achievable next step tied to the user's priorities, preserving essentials and a
  buffer. Explain a trade-off rather than prescribing austerity. Do not imply a simulated
  reduction is money already saved, or that a projected balance is all available for saving.
- Never call goal_plan or challenge merely to explore an option: they persist changes.
  Use what_if for category reductions and scenario for an added recurring monthly cost.
  Do not treat a one-off purchase as a new monthly expense. Use savings_goal_plan for the
  apartment demo's budget analysis, not as a substitute for another user's active goal.

When asked about a transaction:
- Investigate and report findings immediately, without asking 'Would you like me to analyse it?'.
  Identify the selected purchase from supplied context or recent_transactions; ask for clarification
  only if the purchase is ambiguous. Keep its amount separate from wider category totals.
- Use itemised receipt facts already supplied for this purchase. With receipt evidence, mention
  sweets/snacks or another meaningful group neutrally, including its actual cost. Without an
  itemised receipt, never infer products from the merchant or a supermarket category.
- For broader grocery patterns call grocery_receipt_insights with explicit dates for the relevant
  7-14-day window; its default is longer. Shopping visits are inferred from receipts.
  Use spend_by_category for broader category comparisons, with matching date windows.
- Explain one useful implication: how it compares with recent similar spending, or how a repeated
  pattern relates to the user's goal or budget. One purchase does not prove a habit.
  If evidence is insufficient, state that briefly and give the verified facts.
- Sweets and discretionary purchases are not automatically unnecessary or unhealthy. Only use
  'unnecessary' as the user's own description of spending they want to change. Respect treats,
  convenience and enjoyment. Do not shame, diagnose, moralise or assume a purchase was avoidable.

Stay helpful without becoming annoying:
- Normally use 2-4 short sentences: finding, implication, and optionally one gentle next step.
  Allow a compact list or more detail for scenario comparisons, breakdowns or explicit requests.
  Do not finish every answer with a question, a sales pitch or an invitation to do the analysis.
- Check conversation history before nudging. Do not repeat an unchanged recommendation, ask
  again about an answered goal, or keep pushing a declined suggestion. If the user wants facts
  only or no coaching, respect that preference. Do not claim memory outside supplied context.
- Be warm, clear and concrete; match the user's language. Avoid canned praise, jargon and
  paternalistic language. Explain numbers that matter without narrating every value in a chart.

Evidence and tool discipline:
- Financial amounts and comparisons must come from tools or the supplied grounded context.
  Never invent amounts, merchant names, progress, dates or forecast certainty. User-provided
  hypothetical amounts can be tool inputs. If data is missing or a tool fails, say what is unknown.
- Label projections and what-if results as estimates. State their period and assumptions:
  the check-in extrapolates recent flexible spending and, when available, subtracts it from
  balance after predicted bills before payday. It is not a complete guarantee of affordability;
  irregular costs or missing transactions may be absent. With no predicted payday, its horizon
  is the supplied number of days, not 'until payday'. Do not annualise a short spike as a fact.
- For upcoming payments, next income or whether money will last, call upcoming_events.
  Lead with an evidenced low-balance risk. If a recurring-cost scenario exceeds the budget,
  explain the remaining gap and feasible spending reductions; moving money to savings does
  not close a deficit. Check essentials and irregular expenses before suggesting a transfer.
- For a new savings plan, explain one next step: cover bills, allow for irregular expenses,
  cap flexible spending, then save verified surplus. An envelope is a limit for one kind of spending.
- For comparisons, include categories present in only one period as zero in the other. Use
  'largest increase' only after comparing all relevant categories. Do not treat heuristic
  impulse scores, inferred subscriptions or suggested cuts as proven needs or waste.
- Use the three spending baskets only when they clarify the answer: regular essentials,
  irregular essentials, and flexible everyday spending. Do not assume every flexible cost is expendable.
- Use euros (€42.10) and weekly/monthly framing with explicit dates where useful.
  Anonymised merchants remain codes or category descriptions; receipt merchant names are valid.
- Access only this user's data. Decline requests for other customers' personal information;
  benchmark may provide aggregate demo peer comparisons when requested, not an 'average Finn'.
- Stay within budgeting and spending guidance; do not recommend investments. Give useful answers
  within the available evidence rather than generic deflections to an adviser or bank.
"""

TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "savings_goal_plan",
            "description": "Savings goal and last full month's recorded cash flow for the apartment demo. Includes a 20% dining cut and its impact on the month.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grocery_receipt_insights",
            "description": "Grocery receipt breakdown by product category, shopping frequency, small trips (20 EUR or less), and a proposed 20% cut in the largest snack or treat category. Defaults to the latest 12 weeks with receipts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "start": {"type": "string", "description": "Inclusive YYYY-MM-DD"},
                    "end": {"type": "string", "description": "Inclusive YYYY-MM-DD"},
                },
            },
        },
    },
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

TOOL_SPECS.append(CHART_TOOL_SPEC)
TOOL_SPECS.append(RECEIPT_TOOL_SPEC)

TOOL_IMPL = {
    "spend_by_category": lambda cid, a: tools.spend_by_category(cid, a.get("months", 3), a.get("category"), a.get("start"), a.get("end")),
    "basket_breakdown": lambda cid, a: tools.basket_breakdown(cid, a.get("months", 3)),
    "monthly_income": lambda cid, a: tools.monthly_income(cid),
    "current_balance": lambda cid, a: tools.current_balance(cid),
    "subscriptions": lambda cid, a: tools.subscriptions(cid),
    "safe_to_spend": lambda cid, a: tools.safe_to_spend(cid),
    "scenario": lambda cid, a: tools.scenario(cid, a["description"], float(a["monthly_eur"])),
    "what_if": lambda cid, a: tools.what_if(cid, a["category"], float(a["change_pct"])),
    "spender_profile": lambda cid, a: tools.spender_profile(cid),
    "upcoming_events": lambda cid, a: tools.upcoming_events(cid),
    "benchmark": lambda cid, a: tools.benchmark(cid),
    "coaching_plan": lambda cid, a: tools.coaching_plan(cid),
    "goal_plan": lambda cid, a: tools.set_goal(cid, a["name"], float(a["target_eur"]), a.get("months")),
    "challenge": lambda cid, a: tools.create_challenge(cid, a["category"], float(a["pct"]), int(a.get("days", 14))),
    "challenge_progress": lambda cid, a: tools.challenge_progress(cid),
    "savings_goal_plan": lambda cid, a: tools.apartment_plan(cid),
    "grocery_receipt_insights": lambda cid, a: receipts.grocery_insights(cid, a.get("start"), a.get("end")),
    "recent_transactions": lambda cid, a: tools.recent_transactions(cid, a.get("limit", 10)),
    "top_merchants": lambda cid, a: tools.top_merchants(cid, a.get("category"), a.get("months", 3)),
    "receipt_insights": lambda cid, a: receipt_insight.receipt_insight(a["receipt_id"], cid) or {"error": "Receipt not found"},
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
        if len(months) < 2 and len(top) < 2:
            return None  # A one-slice donut adds nothing; the amount is in the answer.
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


StarterPrompt = Literal["recent_check_in", "spending_outlook", "weekly_budget", "spending_profile", "dining_savings", "monthly_spending", "transaction_spending", "grocery_plan", "apartment_plan"]
TransactionPrompt = Literal["transaction_detail", "receipt_breakdown", "category_context"]
CoachPrompt = StarterPrompt | TransactionPrompt



def _answer_metadata(trace: list[dict]) -> dict:
    metadata: dict = {"evidence": []}
    for entry in trace:
        tool, result = entry["tool"], entry["result"]
        if not isinstance(result, dict) or "error" in result:
            continue
        if tool == "savings_goal_plan" and result:
            metadata["evidence"].append({
                "start": result["start"], "end": result["end"], "category": "Restaurants", "label": "Dining",
            })
            if result["reduction_eur"] > 0:
                metadata["experiment"] = {"category": "Restaurants", "pct": 20, "days": 14}
        if tool == "transaction_context" and result.get("category_month"):
            cm = result["category_month"]
            metadata["evidence"].append({"start": cm["start"], "end": cm["end"], "category": result["purchase"]["category"],
                                         "count": cm["count"], "label": result["purchase"]["category"]})
        if tool == "receipt_insights" and result.get("groups"):
            metadata["evidence"].append({
                "start": result["month_start"], "end": result["month_through"], "category": "Groceries",
                "label": "This month’s grocery",
            })
        if tool == "grocery_receipt_insights" and result:
            metadata["evidence"].append({
                "start": result["start"], "end": result["end"], "category": "Groceries",
                "count": result["visits"], "label": "Grocery purchases",
            })
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
    seen, unique = set(), []
    for item in metadata["evidence"]:
        key = (item.get("start"), item.get("end"), item.get("category"), item.get("basket"))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    metadata["evidence"] = unique[:3]
    return metadata


TRANSACTION_EXPLANATIONS = {
    "mandatory_regular": "Aino groups this with regular essentials.",
    "mandatory_irregular": "Aino groups this with unexpected essentials that can make a month more expensive.",
    "everyday_discretionary": "Aino groups this with everyday spending you can review.",
    "savings_investing": "Aino groups this with money you set aside.",
}


def transaction_answer(prompt: TransactionPrompt, customer_id: str, row: dict) -> dict:
    category = row["category"]
    day = datetime.date.fromisoformat(row["date"])
    end = min(
        (day.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1),
        tools.ref_date(customer_id),
    )
    month_scope = {"category": category, "start": day.replace(day=1).isoformat(), "end": end.isoformat()}
    topics = [
        {"label": "See spending in this category", "question": f"How much did I spend on {category.lower()} in {day:%B}?",
         "prompt": "category_context"},
        {"label": "Check my weekly budget", "question": "How much is safe to spend this week?", "prompt": "weekly_budget"},
    ]
    receipt_id = row.get("receipt_id")
    if receipt_id:
        topics.insert(0, {"label": "Break down this receipt", "question": "What did I buy on this receipt?",
                          "prompt": "receipt_breakdown"})

    evidence = []
    if prompt == "category_context":
        totals = tools.transaction_list(customer_id, **month_scope)
        count = totals["count"]
        answer = (
            f"In {day:%B %Y} through {end:%d %B}, you spent **€{totals['total_eur']:.2f}** on "
            f"{category.lower()} across {count} {'purchase' if count == 1 else 'purchases'}. "
            f"This purchase accounted for €{row['amount_eur']:.2f} of that total."
        )
        evidence.append({**month_scope, "label": category, "count": count})
    elif prompt == "receipt_breakdown":
        receipt = receipts.details(receipt_id, customer_id) if receipt_id else None
        if receipt and receipt["categories"]:
            breakdown = ", ".join(f"{item['name']} (€{item['amount_eur']:.2f})" for item in receipt["categories"][:3])
            answer = f"This **€{receipt['total_eur']:.2f}** receipt includes {len(receipt['items'])} line items. The largest groups were {breakdown}."
        else:
            answer = "There is no itemised receipt for this purchase."
    else:
        merchant = f" at {row['merchant']}" if row["merchant"] else ""
        answer = f"You spent **€{row['amount_eur']:.2f}** on {category.lower()}{merchant} on {day:%d %B %Y}."
        receipt = receipts.details(receipt_id, customer_id) if receipt_id else None
        finding = advice.receipt_finding(receipt["categories"]) if receipt else None
        if finding is None:
            past = tools.transaction_list(
                customer_id, start=(day - datetime.timedelta(days=14)).isoformat(),
                end=(day - datetime.timedelta(days=1)).isoformat(), category=category, basket=row["basket"],
            )
            if past["count"]:
                typical = past["total_eur"] / past["count"]
                if typical > 0 and row["amount_eur"] >= typical * 1.25:
                    finding = f"This was above your €{typical:.2f} average across {past['count']} similar purchases in the prior 14 days."
                else:
                    finding = f"Similar purchases averaged €{typical:.2f} in the prior 14 days."
        finding = finding or TRANSACTION_EXPLANATIONS.get(row["basket"])
        if finding:
            answer += f" {finding}"

    return {"answer": answer, "trace": [], "evidence": evidence,
            "topics": [topic for topic in topics if topic["prompt"] != prompt]}


def starter_answer(prompt: StarterPrompt, customer_id: str, category: str | None = None,
                   month_offset: int = 1, start: str | None = None, end: str | None = None,
                   basket: str | None = None, compare: bool = False) -> dict:
    args = {}
    comparison = None
    if prompt in {"recent_check_in", "spending_outlook"}:
        report = advice.check_in(customer_id)
        top = report["top_category"]
        if prompt == "recent_check_in":
            answer = (
                f"Over the last 14 days, you spent **€{report['spend_eur']:.2f}** on everyday purchases "
                f"like groceries and meals out."
            )
            evidence = []
            if top:
                answer += f" Your biggest category was **{top['category'].lower()} (€{top['amount_eur']:.2f})**."
                evidence.append({"start": report["start"], "end": report["end"], "category": top["category"],
                                 "basket": "everyday_discretionary", "label": top["category"]})
            return {"answer": answer, "trace": [], "evidence": evidence}
        current, small, larger = report["scenarios"]
        small_gain = current["spend_eur"] - small["spend_eur"]
        gain = current["spend_eur"] - larger["spend_eur"]
        when = "by your estimated payday" if report["estimated_payday"] else "over the next week"
        if not gain:
            answer = f"Your recent pace suggests little everyday spending {when}. We can look at bills or your weekly budget next."
        else:
            answer = (
                f"At your current pace, you’re on track to spend **about €{current['spend_eur']:.2f}** on everyday purchases {when}. "
                f"\n\nSpend 10% less → **€{small_gain:.2f}** more left.\nSpend 20% less → **€{gain:.2f}** more left."
            )
            target = report["goal"]
            if target and target["saved_so_far_eur"] < target["target_eur"] and larger.get("balance_eur", 0) > 0:
                answer += f"\n\nIf there’s money left after bills and a buffer, it could go toward your {target['name'].lower()}."
        return {"answer": answer, "trace": []}
    if prompt == "apartment_plan":
        tool_name = "savings_goal_plan"
        result = tools.apartment_plan(customer_id)
        if result is None:
            return {"answer": "There is no apartment plan for this profile.", "trace": []}
        net = result["net_eur"]
        after = result["projected_net_eur"]
        needed = result["needed_monthly_eur"]
        goal = (
            f"Your {result['goal'].lower()} needs €{needed:.2f} a month at your chosen pace."
            if needed is not None else f"Your {result['goal'].lower()} is set up."
        )
        cash_flow = (
            f"Last month you spent €{-net:.2f} more than you earned."
            if net < 0 else f"Last month you had €{net:.2f} left after spending."
        )
        outcome = (
            f"That would still leave a €{-after:.2f} gap. Review another expense or adjust the timeline once the budget breaks even."
            if after < 0 else f"That would leave €{after:.2f} before setting aside a buffer."
        )
        answer = (
            f"{goal} {cash_flow} Start with three envelopes: bills, a buffer for irregular costs, "
            f"and everyday spending. An envelope is a limit you set before spending. "
            f"Try capping dining at €{result['dining_cap_eur']:.2f} next month, "
            f"down from €{result['dining_eur']:.2f}. {outcome}"
        )
    elif prompt == "grocery_plan":
        tool_name = "grocery_receipt_insights"
        result = receipts.grocery_insights(customer_id)
        if result is None:
            return {"answer": "There are no grocery receipts for this profile.", "trace": []}
        experiment = result["experiment"]
        answer = (
            f"From {result['start']} to {result['end']}, your receipts show {result['visits']} grocery trips "
            f"({result['trips_per_week']:g} per week)."
        )
        if result["trips_per_week"] > 1 and result["small_trips"]:
            answer += " Try one planned shop each week and keep a list for top-ups."
        if experiment:
            answer += (
                f" Over a similar period, aim for €{experiment['target_eur']:.2f} on "
                f"{experiment['category'].lower()}, down from €{experiment['baseline_eur']:.2f}."
            )
    elif prompt == "weekly_budget":
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
            start = tools.months_ago(month_offset + 1, customer_id)
            end = (datetime.date.fromisoformat(tools.months_ago(month_offset, customer_id)) - datetime.timedelta(days=1)).isoformat()
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
                "start": tools.months_ago(month_offset, customer_id),
                "end": (datetime.date.fromisoformat(tools.months_ago(month_offset - 1, customer_id)) - datetime.timedelta(days=1)).isoformat(),
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


CHAT_EXTRAS = """
Length and format (this is a phone chat):
- Hard limit: 60 words before the followups line. Structure: one headline finding with the key number in **bold**,
  then at most 3 short bullets or 1-2 sentences of implication / next step. No headings.
- Write amounts like €425 (no decimals unless under €10). Use **bold** only, never italics.

Charts:
- You can show charts with show_chart. Prefer one chart when it makes the answer easier to grasp:
  trends over time, splits, comparisons with peers, what-if scenarios, budgets. The chart is
  rendered above your text, so refer to it ("as the chart shows") instead of listing every value.

Follow-ups:
- End every reply with exactly one line in this format and nothing after it:
  <followups>question 1|question 2|question 3</followups>
  Give 2-3 short (max 7 words) questions the user would naturally ask next, in the user's voice,
  each answerable from the available tools. Make them build on what you just found.
"""

TOOL_LABELS = {
    "savings_goal_plan": "Reviewing your savings goal",
    "grocery_receipt_insights": "Reading your grocery receipts",
    "spend_by_category": "Adding up spending by category",
    "basket_breakdown": "Sorting spending into the three baskets",
    "monthly_income": "Checking your income",
    "current_balance": "Checking your balance",
    "subscriptions": "Looking for recurring payments",
    "safe_to_spend": "Working out your safe-to-spend",
    "what_if": "Simulating the change",
    "spender_profile": "Building your spender profile",
    "benchmark": "Comparing with peers your age",
    "coaching_plan": "Finding your biggest levers",
    "goal_plan": "Creating a goal plan",
    "challenge": "Setting up an experiment",
    "scenario": "Running the scenario",
    "challenge_progress": "Checking your experiment",
    "upcoming_events": "Forecasting bills and payday",
    "recent_transactions": "Reading recent transactions",
    "top_merchants": "Finding where you spend most",
    "show_chart": "Drawing a chart",
    "receipt_insights": "Reading the itemised receipt",
    "transaction_context": "Looking up the purchase",
}

_FOLLOWUP_RE = re.compile(r"<followups>(.*?)(?:</followups>|$)", re.S)


def _split_followups(text: str) -> tuple[str, list[str]]:
    match = _FOLLOWUP_RE.search(text)
    if not match:
        return text.strip(), []
    items = [q.strip() for q in match.group(1).split("|") if q.strip()][:3]
    return text[: match.start()].strip(), items


def _tool_label(name: str, args: dict) -> str:
    label = TOOL_LABELS.get(name, name.replace("_", " ").capitalize())
    detail = args.get("category") or args.get("view", "").replace("_", " ")
    if name == "what_if" and args.get("category"):
        return f"Simulating {abs(float(args.get('change_pct', 0))):g}% less on {args['category'].lower()}"
    return f"{label}{f' · {detail}' if detail and name != 'what_if' else ''}"


RECEIPT_BRIEF = """
The user opened Aino from an itemised receipt. Its classified insight is already in the
conversation as a receipt_insights result and is shown to the user as a card above your reply.
Do not list every group again. In under 60 words: name the one group that stands out most
(prefer a treat/convenience group running above usual; otherwise the biggest group) with its
month-to-date vs usual amounts, say one thing that is going well, and offer one small, kind,
concrete idea. Item names are Finnish product labels; you may translate them briefly.
Make one follow-up "Show all my grocery categories this month" (answer it with show_chart grocery_groups).
"""


TRANSACTION_BRIEF = """
The user tapped one purchase in their transaction list. Its facts and comparisons are already in
the conversation as a transaction_context result. In under 60 words: say what it was (amount,
category, merchant, date), how it compares with similar recent purchases and with this month's
category total, and one useful implication. Call show_chart category_trend for its category
so the user sees the pattern. One purchase does not prove a habit; never shame.
"""


def transaction_context(customer_id: str, row: dict) -> dict:
    """Ground a single purchase: this month's category total and how it compares with similar ones."""
    day = datetime.date.fromisoformat(row["date"])
    category, basket = row["category"], row["basket"]
    month_end = min(tools.ref_date(customer_id), (day.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1))
    month = tools.transaction_list(customer_id, start=day.replace(day=1).isoformat(), end=month_end.isoformat(), category=category)
    prior = tools.transaction_list(customer_id, start=(day - datetime.timedelta(days=60)).isoformat(),
                                   end=(day - datetime.timedelta(days=1)).isoformat(), category=category)
    typical = round(prior["total_eur"] / prior["count"], 2) if prior["count"] else None
    usual = tools.what_if(customer_id, category, 0)["current_monthly_eur"]
    days_in_month = ((day.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)).day
    usual_to_date = round(usual * month_end.day / days_in_month, 2)
    return {
        "purchase": {k: row[k] for k in ("date", "category", "merchant", "amount_eur", "basket")},
        "basket_meaning": BASKET_LABELS.get(basket, basket),
        "category_month": {"start": day.replace(day=1).isoformat(), "end": month_end.isoformat(),
                           "total_eur": month["total_eur"], "count": month["count"]},
        "similar_prior_60_days": {"count": prior["count"], "average_eur": typical},
        "usual_monthly_category_eur": usual,
        "usual_for_same_days_eur": usual_to_date,
        "category_month_vs_usual_same_days_pct": round((month["total_eur"] / usual_to_date - 1) * 100) if usual_to_date else None,
        "this_purchase_vs_typical_purchase_pct": round((row["amount_eur"] / typical - 1) * 100) if typical else None,
        "note": "Compare the month total only with usual_for_same_days_eur; the purchase % is about this one purchase.",
    }


def chat_events(messages: list[dict], customer_id: str, receipt_id: str | None = None,
                transaction_id: int | None = None):
    """Run the tool loop and yield UI events: tool steps, charts, text deltas, then done."""
    client = OpenAI(
        api_key=config.CHAT_API_KEY,
        base_url=config.CHAT_BASE_URL,
        default_headers=_client_headers(customer_id, messages),
        timeout=30.0,
        max_retries=1,
    )
    system = f"{SYSTEM_PROMPT}{CHAT_EXTRAS}\nThe demo transaction date is {tools.ref_date(customer_id).isoformat()}. Resolve relative dates against it."
    system += f"\nPersona preferences: {advice.profile(customer_id)[1]}"
    system += "\nCurrent check-in (grounded in demo data): " + json.dumps(advice.check_in(customer_id), ensure_ascii=False)
    msgs = [{"role": "system", "content": system}, *messages]

    trace: list[dict] = []
    charts: list[dict] = []
    auto_chart: dict | None = None
    text = ""
    receipt_card = None
    transaction = tools.spending_transaction(customer_id, transaction_id) if transaction_id is not None else None
    if transaction and transaction.get("receipt_id") and not receipt_id:
        receipt_id = transaction["receipt_id"]
    if transaction and not receipt_id:
        context = jsonable_encoder(transaction_context(customer_id, transaction))
        msgs[0]["content"] += TRANSACTION_BRIEF
        yield {"type": "tool", "tool": "transaction_context", "label": f"Looking up your €{transaction['amount_eur']:.2f} {transaction['category'].lower()} purchase"}
        yield {"type": "tool", "tool": "transaction_compare", "label": f"Comparing with {context['similar_prior_60_days']['count']} similar purchases"}
        args = {"transaction_id": transaction_id}
        msgs.append({"role": "assistant", "content": None, "tool_calls": [{
            "id": "transaction_context", "type": "function",
            "function": {"name": "transaction_context", "arguments": json.dumps(args)}}]})
        msgs.append({"role": "tool", "tool_call_id": "transaction_context", "content": json.dumps(context, ensure_ascii=False)})
        trace.append({"tool": "transaction_context", "args": args, "result": context})
    if receipt_id:
        receipt_card = receipt_insight.receipt_insight(receipt_id, customer_id)
    if receipt_card:
        # Ground the conversation in the receipt before the model runs, so the card shows instantly.
        msgs[0]["content"] += RECEIPT_BRIEF
        yield {"type": "tool", "tool": "receipt_insights", "label": f"Reading your {receipt_card['merchant']} receipt · {receipt_card['item_count']} items"}
        yield {"type": "tool", "tool": "receipt_classify", "label": f"Grouping items into {len(receipt_card['groups'])} shopping categories"}
        yield {"type": "tool", "tool": "receipt_month", "label": f"Comparing each with your usual {receipt_card['month_label'].split()[0]}"}
        yield {"type": "receipt", "receipt": receipt_card}
        args = {"receipt_id": receipt_id}
        msgs.append({"role": "assistant", "content": None, "tool_calls": [{
            "id": "receipt_context", "type": "function",
            "function": {"name": "receipt_insights", "arguments": json.dumps(args)}}]})
        msgs.append({"role": "tool", "tool_call_id": "receipt_context", "content": json.dumps(receipt_card, ensure_ascii=False)})
        trace.append({"tool": "receipt_insights", "args": args, "result": receipt_card})
    for _ in range(6):
        stream = client.chat.completions.create(
            model=config.CHAT_MODEL, messages=msgs, tools=TOOL_SPECS, tool_choice="auto", stream=True,
        )
        text = ""
        calls: dict[int, dict] = {}
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                text += delta.content
                yield {"type": "text", "delta": delta.content}
            for tc in delta.tool_calls or []:
                slot = calls.setdefault(tc.index or 0, {"id": "", "name": "", "arguments": ""})
                if tc.id:
                    slot["id"] = tc.id
                if tc.function and tc.function.name:
                    slot["name"] += tc.function.name
                if tc.function and tc.function.arguments:
                    slot["arguments"] += tc.function.arguments
        if not calls:
            break

        if text:
            # Narration before tool calls ("Let me check…") is not part of the final answer.
            yield {"type": "reset"}
        ordered = [calls[i] for i in sorted(calls)]
        msgs.append({
            "role": "assistant", "content": text or None,
            "tool_calls": [{"id": c["id"], "type": "function",
                            "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}} for c in ordered],
        })
        for call in ordered:
            name = call["name"]
            try:
                args = json.loads(call["arguments"] or "{}")
            except json.JSONDecodeError:
                args = {}
            yield {"type": "tool", "tool": name, "label": _tool_label(name, args)}
            try:
                if name == "show_chart":
                    built = charts_mod.build_chart(customer_id, args)
                    result = jsonable_encoder(built["summary"])
                    if built["chart"] and len(charts) < (1 if receipt_card else 2):
                        charts.append(built["chart"])
                        yield {"type": "chart", "chart": built["chart"]}
                else:
                    result = jsonable_encoder(TOOL_IMPL[name](customer_id, args))
                    if name == "receipt_insights" and "groups" in result and receipt_card is None:
                        receipt_card = result
                        yield {"type": "receipt", "receipt": result}
                    elif auto_chart is None:
                        auto_chart = _make_chart(name, result)
            except Exception as exc:  # A bad tool argument should not end the conversation.
                result = {"error": f"{type(exc).__name__}: {exc}"}
            trace.append({"tool": name, "args": args, "result": result})
            msgs.append({"role": "tool", "tool_call_id": call["id"], "content": json.dumps(result, ensure_ascii=False)})
    else:
        text = text or "Sorry, I could not compute that."

    answer, followups = _split_followups(text)
    if not charts and auto_chart and not receipt_card:
        charts.append(auto_chart)
        yield {"type": "chart", "chart": auto_chart}
    result = {
        "answer": answer, "trace": [{"tool": t["tool"], "args": t["args"]} for t in trace],
        "charts": charts, "chart": charts[0] if charts else None, "followups": followups,
        "receipt": receipt_card,
        **_answer_metadata(trace),
    }
    _log_chat(customer_id, messages, {**result, "trace": trace})
    yield {"type": "done", **result}


def chat(messages: list[dict], customer_id: str) -> dict:
    result: dict = {"answer": "Sorry, I could not compute that.", "trace": []}
    for event in chat_events(messages, customer_id):
        if event["type"] == "done":
            result = {k: v for k, v in event.items() if k != "type"}
    return result
