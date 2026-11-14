"""Charts the AI can request on demand.

The model chooses *what* to visualise; every number is computed here from the
user's own transactions, so a chart can never contain invented values.
"""

import datetime

from . import tools

BASKET_LABELS = {
    "mandatory_regular": "Must-pays",
    "mandatory_irregular": "Unexpected",
    "everyday_discretionary": "Everyday",
    "savings_investing": "Saving",
}

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

CHART_TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "show_chart",
        "description": (
            "Render a chart in the chat, computed from the user's own transactions. Use it whenever a visual "
            "makes the answer clearer, or when the user asks to see/show/plot/compare something. "
            "view: 'category_trend' = monthly spending for one category (or all categories) over N months; "
            "'category_split' = share of spending per category over N months; "
            "'baskets' = the three spending baskets (must-pays, unexpected, everyday); default 12 months so rare unexpected costs show up, use the same months as any basket figures you quote; "
            "'peers' = user vs demo peers of the same age per category; "
            "'what_if' = monthly spending in a category vs the same with pct% less; "
            "'budget' = monthly budget split into bills, buffer, everyday, savings and safe-to-spend; "
            "'merchants' = top merchants, optionally for one category; "
            "'grocery_groups' = what the user's itemised supermarket receipts were spent on this month "
            "(fruit & veg, dairy, snacks & sweets, household…) vs their usual for the same days. "
            "Call at most two charts per answer. Do not repeat the chart's numbers line by line in text."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "view": {"type": "string", "enum": ["category_trend", "category_split", "baskets", "peers",
                                                     "what_if", "budget", "merchants", "grocery_groups"]},
                "category": {"type": "string", "description": "Optional category, e.g. Restaurants, Groceries, or 'taxis'"},
                "months": {"type": "integer", "minimum": 1, "maximum": 12, "description": "Look-back in full months, default 6 for trends, 3 otherwise"},
                "pct": {"type": "number", "description": "For what_if: percent reduction, e.g. 20"},
            },
            "required": ["view"],
        },
    },
}


def _month_label(ym: str) -> str:
    try:
        return _MONTHS[int(ym[5:7]) - 1]
    except (ValueError, IndexError):
        return ym


def _monthly(customer_id: str, months: int, category: str | None) -> tuple[list[str], dict[str, dict[str, float]], str, str]:
    start = datetime.date.fromisoformat(tools.months_ago(months, customer_id)).replace(day=1).isoformat()
    end = tools.ref_date(customer_id).isoformat()
    result = tools.spend_by_category(customer_id, months, category, start, end)
    month_keys = []
    first = datetime.date.fromisoformat(start)
    last = datetime.date.fromisoformat(end)
    cursor = first.replace(day=1)
    while cursor <= last:
        month_keys.append(cursor.strftime("%Y-%m"))
        cursor = (cursor.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    table: dict[str, dict[str, float]] = {}
    for row in result["rows"]:
        table.setdefault(row["category"], {})[row["month"]] = row["spent_eur"]
    return month_keys, table, start, end


def build_chart(customer_id: str, args: dict) -> dict:
    view = args.get("view", "category_split")
    category = args.get("category") or None
    default_months = 6 if view in {"category_trend", "what_if"} else 12 if view == "baskets" else 3
    months = max(1, min(12, int(args.get("months") or default_months)))
    label = tools.resolve_category(category)[0] if category else None
    if category and category.strip().lower() in {"taxi", "taxis"}:
        label = "Taxis"

    if view in {"category_trend", "what_if"}:
        ref = tools.ref_date(customer_id)
        partial = ref.day < 28
        # Show full calendar months only; a half-finished month would look like a sudden drop.
        month_keys, table, start, end = _monthly(customer_id, months + (1 if partial else 0), category)
        if partial and len(month_keys) > 1:
            month_keys = month_keys[:-1]
        labels = [_month_label(m) for m in month_keys]
        if category:
            values = [round(sum(t.get(m, 0) for t in table.values()), 2) for m in month_keys]
            if view == "what_if":
                pct = abs(float(args.get("pct") or 20))
                reduced = [round(v * (100 - pct) / 100, 2) for v in values]
                # Same basis as the what_if tool, so the chart and the answer agree.
                plan = tools.what_if(customer_id, category, -pct)
                return {
                    "chart": {
                        "kind": "bar", "title": f"{label or category}: actual vs {pct:g}% less (EUR/month)",
                        "labels": labels, "values": values, "values2": reduced,
                        "series_names": ["Actual", f"With {pct:g}% less"], "unit": "eur",
                        "highlight": {"label": "Could free up",
                                      "value": f"€{plan['saved_monthly_eur']:.0f}/mo · €{plan['saved_yearly_eur']:,.0f}/yr"},
                        "note": "Saving based on your last 3 months of spending",
                    },
                    "summary": {"months": month_keys, "actual_eur": values, "reduced_eur": reduced, **plan,
                                "start": start, "end": end},
                }
            return {
                "chart": {"kind": "bar", "title": f"{label or category} per month (EUR)", "labels": labels,
                          "values": values, "unit": "eur",
                          "note": f"Full months only · {ref:%B} so far not shown" if partial else None},
                "summary": {"months": month_keys, "spent_eur": values, "start": start, "end": end},
            }
        totals = {c: sum(v.values()) for c, v in table.items()}
        top = sorted(totals, key=lambda c: -totals[c])[:5]
        series = [{"name": c, "data": [round(table[c].get(m, 0), 2) for m in month_keys]} for c in top]
        return {
            "chart": {"kind": "line", "title": "Spending by category per month (EUR)", "labels": labels,
                      "series": series, "unit": "eur"},
            "summary": {"months": month_keys, "series": series, "start": start, "end": end},
        }

    if view == "category_split":
        start = tools.months_ago(months, customer_id)
        result = tools.spend_by_category(customer_id, months, None)
        totals: dict[str, float] = {}
        for row in result["rows"]:
            totals[row["category"]] = totals.get(row["category"], 0) + row["spent_eur"]
        top = sorted(totals, key=lambda c: -totals[c])[:6]
        values = [round(totals[c], 2) for c in top]
        return {
            "chart": {"kind": "donut", "title": f"Where your money went · last {months} mo", "labels": top,
                      "values": values, "unit": "eur"},
            "summary": {"start": start, "end": result["end"], "totals_eur": dict(zip(top, values))},
        }

    if view == "baskets":
        result = tools.basket_breakdown(customer_id, months)
        found = {r["basket"]: r["total_eur"] for r in result["totals"]}
        # Always show all three pedagogical baskets, even when one is empty in this window.
        keys = ["mandatory_regular", "mandatory_irregular", "everyday_discretionary"]
        if found.get("savings_investing"):
            keys.append("savings_investing")
        names = {"mandatory_regular": "Must-pays", "mandatory_irregular": "Unexpected",
                 "everyday_discretionary": "Everyday", "savings_investing": "Saving"}
        return {
            "chart": {"kind": "donut", "title": f"Your three money baskets · last {months} months",
                      "labels": [names[k] for k in keys],
                      "values": [round(found.get(k, 0), 2) for k in keys], "unit": "eur",
                      "note": "Must-pays: rent, bills · Unexpected: repairs, health · Everyday: food out, fun"},
            "summary": {"start": result["start"], "end": result["end"],
                        "totals_eur": {BASKET_LABELS[k]: round(found.get(k, 0), 2) for k in keys}},
        }

    if view == "peers":
        result = tools.benchmark(customer_id)
        rows = result.get("rows", [])[:6]
        return {
            "chart": {"kind": "bar", "title": "You vs peers your age (EUR/month)",
                      "labels": [r["category"] for r in rows],
                      "values": [r["user_monthly_eur"] for r in rows],
                      "values2": [r["finn_monthly_eur"] for r in rows],
                      "series_names": ["You", "Peers"], "unit": "eur", "note": "Peers = demo customers of the same age group"},
            "summary": {"rows": rows},
        }

    if view == "budget":
        result = tools.safe_to_spend(customer_id)
        avg = result.get("avg_monthly", {})
        items = [("Must-pays", avg.get("mandatory_regular", 0)),
                 ("Unexpected", avg.get("mandatory_irregular", 0)),
                 ("Everyday", avg.get("everyday_discretionary", 0)),
                 ("Savings", result.get("savings_goal_10pct", 0)),
                 ("Safe to spend", result.get("safe_to_spend_monthly", 0))]
        return {
            "chart": {"kind": "bar", "title": "Your monthly budget (EUR)", "labels": [i[0] for i in items],
                      "values": [round(i[1], 2) for i in items], "unit": "eur"},
            "summary": result,
        }

    if view == "merchants":
        cat = tools.resolve_category(category)[0] if category else None
        rows = tools.top_merchants(customer_id, cat, months)[:6]
        return {
            "chart": {"kind": "bar", "title": f"Top places{f' · {cat}' if cat else ''} (EUR, {months} mo)",
                      "labels": [r["merchant_id"][:12] for r in rows],
                      "values": [r["total_eur"] for r in rows], "unit": "eur"},
            "summary": {"rows": rows},
        }

    if view == "grocery_groups":
        from .receipt_insight import month_groups
        result = month_groups(customer_id)
        if not result:
            return {"chart": None, "summary": {"error": "No itemised receipts for this user"}}
        rows = result["groups"][:7]
        return {
            "chart": {"kind": "bar", "title": f"Groceries by category · {result['month_label']} (EUR)",
                      "labels": [r["group"] for r in rows], "values": [r["month_eur"] for r in rows],
                      "values2": [r["usual_eur"] for r in rows], "series_names": ["This month", "Usual"],
                      "unit": "eur", "note": result["note"] + " · from itemised receipts"},
            "summary": result,
        }

    return {"chart": None, "summary": {"error": f"Unknown view {view}"}}
