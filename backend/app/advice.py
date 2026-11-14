"""Ground Aino's check-in and purchase findings in the demo ledger."""

from datetime import date, timedelta

from . import tools
from .receipts import CUSTOMER_ID

PROFILES = {
    "CUST02220": (
        "Keep next week manageable",
        "Emma is balancing study and a first job. Be informal and concise. Focus on making the next week affordable, small recurring purchases and one realistic weekly adjustment. Explain concepts simply without lecturing; preserve room for social life and avoid proposing a strict overhaul.",
    ),
    "CUST05013": (
        "Make room for your next goal",
        "Mikko values direct numbers and trade-offs. Lead with cash flow and quantified trade-offs, then connect a realistic option to his saved goal when one exists. Compare current pace with alternatives for planning questions; avoid generic coffee-cutting advice or assuming a home-buying goal.",
    ),
    "CUST00001": (
        "Plan for the days ahead",
        "Riitta values predictable spending on a fixed income. Use plain language, explain dates and amounts, and prioritise bills and a cash buffer before discretionary cuts or savings targets. Use a calm, respectful tone without slang, pressure or assumptions about technical ability.",
    ),
    "CUST00541": (
        "Bring spending back under income",
        "Laura's spending has run above income for several months. Be warm and practical. Lead with the gap and the one or two flexible categories driving it, and suggest one realistic weekly cap. Never shame or imply irresponsibility; acknowledge what is already working.",
    ),
    "CUST04216": (
        "Recover from an unexpected cost",
        "Antti's account went into the red after a large one-off cost. Be calm and reassuring. Prioritise getting back above zero before payday and covering bills, then suggest building a small buffer for the next surprise. Explain the 'unexpected' basket simply; don't lecture about the past purchase.",
    ),
    "CUST05012": (
        "Plan around irregular income",
        "Pekka's freelance income varies month to month. Use direct, numbers-first language. Frame budgets around a low-income month, the savings cushion, and smoothing spending across months. Avoid assuming a fixed salary or a payday.",
    ),
    CUSTOMER_ID: (
        "See what changed in your spending",
        "Sofia wants to understand her purchases while saving for an apartment. Lead with receipt and spending patterns. Use measured, nonjudgmental language. Identify receipt-backed treat spending and offer a modest grocery experiment when relevant to her apartment goal; never imply that sweets are bad or every small shopping trip is wasteful.",
    ),
}


def profile(customer_id: str) -> tuple[str, str]:
    return PROFILES.get(customer_id, ("Your spending check-in", "Use plain language and follow the user's priorities."))


def flexible_window(customer_id: str, start: date, end: date) -> list[dict]:
    where, args = tools.spending_filters(customer_id, start, end, basket="everyday_discretionary")
    with tools.connect() as con:
        rows = con.execute(f"""
            SELECT category, round(sum(-tx_amount_eur), 2), count(*)
            FROM tx_enriched WHERE {where}
            GROUP BY category ORDER BY 2 DESC, category
        """, args).fetchall()
    return [{"category": category, "amount_eur": float(amount), "count": count} for category, amount, count in rows]


def check_in(customer_id: str) -> dict:
    end = tools.ref_date(customer_id)
    start = end - timedelta(days=13)
    recent = flexible_window(customer_id, start, end)
    prior = flexible_window(customer_id, start - timedelta(days=14), start - timedelta(days=1))
    spend = round(sum(row["amount_eur"] for row in recent), 2)
    previous = round(sum(row["amount_eur"] for row in prior), 2)
    forecast = tools.payday_check(customer_id)
    limit = forecast.get("estimated_payday")
    days = max(0, (date.fromisoformat(limit) - end).days) if limit else 7
    projected_spend = round(spend * days / 14, 2)
    scenarios = [
        {"reduction_pct": pct, "spend_eur": round(projected_spend * (100 - pct) / 100, 2)}
        for pct in (0, 10, 20)
    ]
    bills_only = forecast.get("projected_before_eur")
    if bills_only is not None:
        for scenario in scenarios:
            scenario["balance_eur"] = round(bills_only - scenario["spend_eur"], 2)
    goal = tools.get_goal(customer_id)
    if goal:
        goal = {key: goal[key] for key in ("name", "target_eur", "saved_so_far_eur", "weekly_eur")}
    return {
        "title": profile(customer_id)[0], "start": start.isoformat(), "end": end.isoformat(),
        "spend_eur": spend, "previous_eur": previous, "top_category": recent[0] if recent else None,
        "previous_start": (start - timedelta(days=14)).isoformat(),
        "previous_end": (start - timedelta(days=1)).isoformat(),
        "recent_categories": recent, "previous_categories": prior,
        "days": days, "estimated_payday": limit, "bills_eur": forecast.get("bill_total_eur"),
        "scenarios": scenarios, "goal": goal,
    }


SWEET_CATEGORIES = {"Chocolate", "Candy and liquorice", "Cakes and sweet pastries", "Ice cream and ice pops"}


def receipt_finding(categories: list[dict]) -> str | None:
    if not categories:
        return None
    top = categories[0]
    sweets = sum(group["amount_eur"] for group in categories if group["name"] in SWEET_CATEGORIES)
    if sweets > 0:
        return f"Sweets came to **€{sweets:.2f}** on this receipt."
    return f"The largest group was **{top['name'].lower()} (€{top['amount_eur']:.2f})**."
