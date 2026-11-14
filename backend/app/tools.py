import datetime

from .db import connect
from .receipts import CUSTOMER_ID as RECEIPT_CUSTOMER_ID

_ref_date: datetime.date | None = None


def ref_date(customer_id: str | None = None) -> datetime.date:
    if customer_id == RECEIPT_CUSTOMER_ID:
        with connect() as con:
            latest = con.execute("SELECT max(tx_date) FROM tx WHERE customer_id = ?", [customer_id]).fetchone()[0]
        if latest is not None:
            return latest
    global _ref_date
    if _ref_date is None:
        con = connect()
        _ref_date = con.execute("SELECT max(tx_date) FROM tx WHERE customer_id != ?", [RECEIPT_CUSTOMER_ID]).fetchone()[0]
        con.close()
    return _ref_date


def build_enriched() -> None:
    con = connect()
    con.execute("""
        CREATE OR REPLACE TABLE tx_stats AS
        SELECT
            customer_id,
            merchant_id,
            median(abs(tx_amount_eur)) AS median_abs,
            count(*) FILTER (WHERE tx_date >= (SELECT max(tx_date) FROM tx WHERE customer_id != ?) - INTERVAL 6 MONTH) AS cnt_6m,
            count(*) AS cnt_total,
            round(avg(abs(tx_amount_eur)), 2) AS avg_abs,
            round(stddev_samp(abs(tx_amount_eur)), 2) AS std_abs,
            CASE WHEN cnt_6m >= 3 AND avg_abs > 0 AND std_abs <= 0.35 * avg_abs
                 THEN 1 ELSE 0 END AS regular_pattern
        FROM tx
        WHERE customer_id != ? AND merchant_id IS NOT NULL AND merchant_id != ''
        GROUP BY customer_id, merchant_id
    """, [RECEIPT_CUSTOMER_ID, RECEIPT_CUSTOMER_ID])
    con.execute(f"CREATE OR REPLACE TABLE tx_enriched AS {ENRICHED_SELECT}")
    con.close()


def enrich_receipt_customer(con):
    con.execute(f"INSERT INTO tx_enriched BY NAME {ENRICHED_SELECT} WHERE t.customer_id = ?", [RECEIPT_CUSTOMER_ID])


ENRICHED_SELECT = """
        SELECT
            t.*,
            COALESCE(mc.basket, '') AS jev_basket,
            COALESCE(mc.is_subscription, 0) AS is_subscription,
            COALESCE(mc.irregular_risk, 0) AS irregular_risk,
            COALESCE(mc.confidence, 0) AS jev_confidence,
            COALESCE(s.regular_pattern, 0) AS regular_pattern,
            CASE
                WHEN t.flow = 'income' THEN 'income'
                WHEN t.transaction_type IN ('housing_payment', 'utilities_payment') THEN 'mandatory_regular'
                WHEN t.transaction_type IN ('investment_deposit', 'investment_withdrawal', 'salary_sweep') THEN 'savings_investing'
                WHEN s.regular_pattern = 1 AND (mc.is_subscription >= 0.5
                     OR t.category IN ('Health', 'Transportation', 'Home & Tech', 'Utilities')) THEN 'mandatory_regular'
                WHEN mc.irregular_risk >= 0.5 AND s.median_abs > 0
                     AND abs(t.tx_amount_eur) > 2.5 * s.median_abs THEN 'mandatory_irregular'
                WHEN mc.basket IS NOT NULL AND mc.confidence >= 0.7 THEN mc.basket
                WHEN t.category IN ('Health', 'Transportation', 'Home & Tech') THEN 'mandatory_regular'
                ELSE 'everyday_discretionary'
            END AS basket,
            0 AS simulated
        FROM tx t
        LEFT JOIN merchant_classification mc ON t.merchant_id = mc.merchant_id AND t.merchant_id != ''
        LEFT JOIN tx_stats s ON t.customer_id = s.customer_id AND t.merchant_id = s.merchant_id AND t.merchant_id != ''
"""


def months_ago(n: int, customer_id: str | None = None) -> str:
    start = ref_date(customer_id).replace(day=1)
    for _ in range(n - 1):
        start = (start - datetime.timedelta(days=1)).replace(day=1)
    return start.isoformat()


CATEGORIES = [
    "Entertainment", "Food", "Non-food", "Groceries", "Health", "Home & Tech", "Housing",
    "Invest Deposit", "Invest Withdraw", "Lifestyle", "Other Income",
    "Restaurants", "Salary", "Salary Sweep", "Transportation", "Travel", "Utilities",
]

ALIASES = {
    "taxis": "taxi",
    "taxi": "taxi",
    "dining": "Restaurants",
    "dining out": "Restaurants",
    "eating out": "Restaurants",
    "coffee": "Restaurants",
    "cafes": "Restaurants",
    "rent": "Housing",
    "groceries": "Groceries",
    "entertainment": "Entertainment",
    "transport": "Transportation",
    "travelling": "Travel",
}

TAXI_MCCS = ("4121", "4122")


def resolve_category(raw: str | None) -> tuple[str | None, str | None]:
    """Returns (category, mcc) — mcc set when the query is taxi-specific."""
    if not raw:
        return None, None
    key = raw.strip().lower()
    if key in ("taxis", "taxi"):
        return "Transportation", TAXI_MCCS[0]
    for k in sorted(ALIASES, key=len, reverse=True):
        if k in key:
            return ALIASES[k], None
    for c in sorted(CATEGORIES, key=len, reverse=True):
        if c.lower() in key:
            return c, None
    return None, None


def spending_filters(customer_id, start, end, category=None, basket=None, attention=None):
    conditions = ["customer_id = ?", "flow = 'expense'", "simulated = 0", "tx_date BETWEEN ? AND ?"]
    args = [customer_id, start, end]
    if category:
        cat, mcc = resolve_category(category)
        conditions.append("category = ?")
        args.append(cat or category)
        if mcc:
            conditions.append("mcc_code IN (?, ?)")
            args.extend(TAXI_MCCS)
    if basket:
        conditions.append("basket = ?")
        args.append(basket)
    if attention:
        conditions.append("basket IN ('mandatory_irregular', 'everyday_discretionary')")
    return " AND ".join(conditions), args


TRANSACTION_FIELDS = ("id", "date", "category", "merchant", "amount_eur", "basket", "transaction_type", "receipt_id")


def spending_transaction(customer_id: str, transaction_id: int) -> dict | None:
    with connect() as con:
        receipt_column = ", receipt_id" if customer_id == RECEIPT_CUSTOMER_ID else ""
        row = con.execute(f"""
            SELECT rowid, cast(tx_date AS VARCHAR), category, merchant_id, -tx_amount_eur,
                   basket, transaction_type{receipt_column}
            FROM tx_enriched
            WHERE rowid = ? AND customer_id = ? AND flow = 'expense' AND simulated = 0
        """, [transaction_id, customer_id]).fetchone()
    return dict(zip(TRANSACTION_FIELDS, row)) if row else None


def transaction_list(customer_id, start=None, end=None, category=None, basket=None, attention=False, offset=0):
    end = end or ref_date(customer_id).isoformat()
    with connect() as con:
        show_receipts = customer_id == RECEIPT_CUSTOMER_ID
        if start is None and show_receipts:
            start = con.execute("SELECT cast(min(tx_date) AS VARCHAR) FROM tx WHERE customer_id = ?",
                                [customer_id]).fetchone()[0]
        start = start or months_ago(3, customer_id)
        where, args = spending_filters(customer_id, start, end, category, basket, attention)
        count, total = con.execute(
            f"SELECT count(*), coalesce(round(sum(-tx_amount_eur), 2), 0) FROM tx_enriched WHERE {where}", args
        ).fetchone()
        receipt_column = ", receipt_id" if show_receipts else ""
        rows = con.execute(f"""
            SELECT rowid, cast(tx_date AS VARCHAR), category, merchant_id, -tx_amount_eur, basket, transaction_type{receipt_column}
            FROM tx_enriched WHERE {where}
            ORDER BY tx_date DESC, tx_timestamp DESC, category, merchant_id, tx_amount_eur, basket, transaction_type{receipt_column}, rowid
            LIMIT 25 OFFSET ?
        """, [*args, offset]).fetchall()
    return {
        "start": start, "end": end, "category": category, "basket": basket,
        "count": count, "total_eur": float(total),
        "rows": [dict(zip(TRANSACTION_FIELDS, row)) for row in rows],
    }


def spend_by_category(customer_id: str, months: int = 3, category: str | None = None,
                      start: str | None = None, end: str | None = None):
    start, end = start or months_ago(months, customer_id), end or ref_date(customer_id).isoformat()
    # Parse explicit dates before running the query so malformed model arguments fail predictably.
    start, end = datetime.date.fromisoformat(start).isoformat(), datetime.date.fromisoformat(end).isoformat()
    where, args = spending_filters(customer_id, start, end, category)
    with connect() as con:
        rows = con.execute(f"""
            SELECT category, strftime(tx_date, '%Y-%m'), round(sum(-tx_amount_eur), 2), count(*)
            FROM tx_enriched WHERE {where}
            GROUP BY 1, 2 ORDER BY 2, 1
        """, args).fetchall()
    return {
        "months": months, "start": start, "end": end, "category": category,
        "count": sum(row[3] for row in rows),
        "rows": [dict(zip(("category", "month", "spent_eur"), row[:3])) for row in rows],
    }


def basket_breakdown(customer_id: str, months: int = 3):
    start = months_ago(months, customer_id)
    end = ref_date(customer_id).isoformat()
    con = connect()
    totals = con.execute("""
        SELECT basket, round(sum(-tx_amount_eur), 2) AS total
        FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND simulated = 0 AND tx_date BETWEEN ? AND ?
        GROUP BY basket ORDER BY total DESC
    """, [customer_id, start, end]).fetchall()
    top = con.execute("""
        SELECT basket, merchant_id, count(*) AS n, round(sum(-tx_amount_eur), 2) AS total
        FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND simulated = 0 AND tx_date BETWEEN ? AND ? AND merchant_id != ''
        GROUP BY basket, merchant_id ORDER BY basket, total DESC
    """, [customer_id, start, end]).fetchall()
    con.close()
    return {
        "months": months, "start": start, "end": end,
        "totals": [dict(zip(("basket", "total_eur"), r)) for r in totals],
        "top_merchants": [dict(zip(("basket", "merchant_id", "tx_count", "total_eur"), r)) for r in top],
    }


def monthly_income(customer_id: str, months: int = 6):
    start = months_ago(months, customer_id)
    con = connect()
    rows = con.execute("""
        SELECT strftime(tx_date, '%Y-%m') AS month, round(sum(tx_amount_eur), 2) AS income
        FROM tx_enriched
        WHERE customer_id = ? AND transaction_type = 'salary' AND tx_date >= ?
        GROUP BY month ORDER BY month
    """, [customer_id, start]).fetchall()
    con.close()
    vals = [r[1] for r in rows]
    median = sorted(vals)[len(vals) // 2] if vals else 0
    return {"median_monthly_income": median, "by_month": [dict(zip(("month", "income_eur"), r)) for r in rows]}


def current_balance(customer_id: str):
    con = connect()
    row = con.execute("""
        SELECT balance_after_eur + (
            SELECT coalesce(sum(tx_amount_eur), 0) FROM tx_enriched
            WHERE customer_id = ? AND simulated = 1
        ) AS balance
        FROM tx_enriched WHERE customer_id = ? AND simulated = 0
        ORDER BY tx_date DESC, tx_timestamp DESC LIMIT 1
    """, [customer_id, customer_id]).fetchone()
    con.close()
    return {"balance_eur": round(row[0], 2) if row and row[0] is not None else None}


def subscriptions(customer_id: str):
    start = months_ago(6, customer_id)
    con = connect()
    rows = con.execute("""
        SELECT merchant_id, category, count(*) AS n,
               round(sum(-tx_amount_eur), 2) AS total_eur,
               count(DISTINCT strftime(tx_date, '%Y-%m')) AS months_active
        FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense'
          AND (is_subscription >= 0.5 OR regular_pattern = 1)
          AND tx_date >= ? AND merchant_id != ''
        GROUP BY merchant_id, category
        HAVING n >= 3
        ORDER BY total_eur DESC
    """, [customer_id, start]).fetchall()
    con.close()
    items = []
    for merchant, cat, n, total, active in rows:
        months = max(active, 1)
        items.append({
            "merchant_id": merchant,
            "category": cat,
            "tx_count": n,
            "total_6m_eur": total,
            "monthly_cost_eur": round(total / months, 2),
        })
    total = round(sum(i["monthly_cost_eur"] for i in items), 2)
    return {"total_monthly_eur": total, "items": items}


def safe_to_spend(customer_id: str):
    start = months_ago(3, customer_id)
    con = connect()
    income = monthly_income(customer_id)["median_monthly_income"]
    mandatory = con.execute("""
        SELECT round(sum(-tx_amount_eur), 2) FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND basket = 'mandatory_regular'
          AND simulated = 0 AND tx_date >= ? AND transaction_type NOT IN ('investment_deposit', 'investment_withdrawal')
    """, [customer_id, start]).fetchone()[0] or 0
    irregular = con.execute("""
        SELECT round(sum(-tx_amount_eur), 2) FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND basket = 'mandatory_irregular' AND simulated = 0 AND tx_date >= ?
    """, [customer_id, start]).fetchone()[0] or 0
    everyday = con.execute("""
        SELECT round(sum(-tx_amount_eur), 2) FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND basket = 'everyday_discretionary' AND simulated = 0 AND tx_date >= ?
    """, [customer_id, start]).fetchone()[0] or 0
    simulated = con.execute("""
        SELECT coalesce(round(sum(-tx_amount_eur), 2), 0) FROM tx_enriched
        WHERE customer_id = ? AND simulated = 1 AND tx_date >= ?
    """, [customer_id, ref_date(customer_id).replace(day=1).isoformat()]).fetchone()[0] or 0
    con.close()

    mandatory_monthly = mandatory / 3
    irregular_monthly = irregular / 3
    everyday_monthly = everyday / 3
    savings_goal = 0.10 * income
    buffer = 0.5 * irregular_monthly
    safe_monthly = income - mandatory_monthly - buffer - savings_goal - simulated
    return {
        "median_monthly_income": income,
        "avg_monthly": {
            "mandatory_regular": round(mandatory_monthly, 2),
            "mandatory_irregular": round(irregular_monthly, 2),
            "everyday_discretionary": round(everyday_monthly, 2),
        },
        "savings_goal_10pct": round(savings_goal, 2),
        "irregular_buffer": round(buffer, 2),
        "simulated_spend_this_month": simulated,
        "safe_to_spend_monthly": round(safe_monthly, 2),
        "safe_to_spend_weekly": round(safe_monthly / 4.33, 2),
    }


def what_if(customer_id: str, category: str, change_pct: float):
    cat, _ = resolve_category(category)
    where, args = spending_filters(customer_id, months_ago(3, customer_id), ref_date(customer_id), category)
    with connect() as con:
        total = con.execute(
            f"SELECT coalesce(round(sum(-tx_amount_eur), 2), 0) FROM tx_enriched WHERE {where}", args
        ).fetchone()[0]
    monthly = total / 3
    saved_monthly = -monthly * (change_pct / 100)
    return {
        "category": category,
        "resolved_category": cat,
        "change_pct": change_pct,
        "current_monthly_eur": round(monthly, 2),
        "saved_monthly_eur": round(saved_monthly, 2),
        "saved_yearly_eur": round(saved_monthly * 12, 2),
    }


def spender_profile(customer_id: str):
    start = months_ago(3, customer_id)
    con = connect()
    baskets = con.execute("""
        SELECT basket, round(sum(-tx_amount_eur), 2) FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND simulated = 0 AND tx_date BETWEEN ? AND ?
        GROUP BY basket
    """, [customer_id, start, ref_date(customer_id)]).fetchall()
    small_or_weekend = con.execute("""
        SELECT count(*) FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND basket = 'everyday_discretionary'
          AND (tx_amount_eur > -10 OR dayofweek(tx_date) IN (0, 6))
          AND simulated = 0 AND tx_date BETWEEN ? AND ?
    """, [customer_id, start, ref_date(customer_id)]).fetchone()[0]
    everyday_count = con.execute("""
        SELECT count(*) FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND basket = 'everyday_discretionary' AND simulated = 0 AND tx_date BETWEEN ? AND ?
    """, [customer_id, start, ref_date(customer_id)]).fetchone()[0]
    con.close()
    total = sum(r[1] for r in baskets) or 1
    shares = {r[0]: round(r[1] / total * 100, 1) for r in baskets}
    impulse = round(small_or_weekend / everyday_count * 100, 1) if everyday_count else 0
    return {
        "months": 3,
        "basket_shares_pct": shares,
        "impulse_score_0_100": impulse,
        "impulse_explanation": "share of everyday purchases that are under 10 EUR or made on weekends",
    }


def recent_transactions(customer_id: str, limit: int = 10):
    con = connect()
    rows = con.execute("""
        SELECT tx_date, category, merchant_id, tx_amount_eur, basket
        FROM tx_enriched WHERE customer_id = ?
        ORDER BY tx_date DESC LIMIT ?
    """, [customer_id, limit]).fetchall()
    con.close()
    return [dict(zip(("date", "category", "merchant_id", "amount_eur", "basket"), r)) for r in rows]


def top_merchants(customer_id: str, category: str | None = None, months: int = 3):
    start = months_ago(months, customer_id)
    con = connect()
    q = """
        SELECT merchant_id, count(*) AS n, round(sum(-tx_amount_eur), 2) AS total
        FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND merchant_id != '' AND tx_date >= ?
    """
    args: list = [customer_id, start]
    if category:
        q += " AND category = ?"
        args.append(category)
    q += " GROUP BY merchant_id ORDER BY total DESC LIMIT 10"
    rows = con.execute(q, args).fetchall()
    con.close()
    return [dict(zip(("merchant_id", "tx_count", "total_eur"), r)) for r in rows]


def upcoming_events(customer_id: str) -> dict:
    import calendar

    start = months_ago(6, customer_id)
    con = connect()
    ref = ref_date(customer_id)

    salary = con.execute("""
        SELECT round(median(tx_amount_eur), 2), cast(round(median(dayofmonth(tx_date))) AS INTEGER),
               max(tx_date)
        FROM tx_enriched
        WHERE customer_id = ? AND transaction_type = 'salary' AND tx_date >= ?
    """, [customer_id, start]).fetchone()

    bills = con.execute("""
        SELECT COALESCE(merchant_id, transaction_type) AS label, transaction_type AS kind,
               cast(round(median(dayofmonth(tx_date))) AS INTEGER) AS dom,
               round(median(abs(tx_amount_eur)), 2) AS amt, count(*) AS n
        FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND tx_date >= ?
          AND (transaction_type IN ('housing_payment', 'utilities_payment')
               OR (is_subscription >= 0.5 AND regular_pattern = 1))
        GROUP BY 1, 2
        HAVING n >= 2
    """, [customer_id, start]).fetchall()
    con.close()

    today = ref
    kind_labels = {"housing_payment": "Rent/mortgage", "utilities_payment": "Utilities"}
    events = []
    for label, kind, dom, amt, n in bills:
        target = today.replace(day=min(dom, calendar.monthrange(today.year, today.month)[1]))
        if target < today:
            next_month = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
            target = next_month.replace(day=min(dom, calendar.monthrange(next_month.year, next_month.month)[1]))
        events.append({
            "name": kind_labels.get(kind, str(label)),
            "kind": kind,
            "amount_eur": amt,
            "predicted_date": target.isoformat(),
            "days_until": (target - today).days,
        })

    salary_info = None
    if salary and salary[0] is not None:
        amt, dom, last = salary
        target = today.replace(day=min(dom, calendar.monthrange(today.year, today.month)[1]))
        if target <= today:
            y, m = (today.year, today.month + 1)
            if m > 12:
                y, m = y + 1, 1
            target = datetime.date(y, m, min(dom, calendar.monthrange(y, m)[1]))
        salary_info = {
            "amount_eur": amt,
            "predicted_date": target.isoformat(),
            "days_until": (target - today).days,
        }

    events.sort(key=lambda e: e["days_until"])

    balance = current_balance(customer_id)["balance_eur"] or 0
    sim = balance
    low = None
    if salary_info:
        for e in events:
            if e["days_until"] < salary_info["days_until"]:
                sim = round(sim - e["amount_eur"], 2)
        if sim < 0:
            low = {"projected_balance_eur": sim, "gap_eur": round(-sim, 2)}
        elif sim < 300:
            low = {"projected_balance_eur": sim, "gap_eur": 0}

    return {
        "today": ref.isoformat(),
        "next_salary": salary_info,
        "upcoming_bills": events,
        "balance_now_eur": balance,
        "low_balance_risk": low,
    }


def payday_check(customer_id: str, purchase_eur: float = 0, buffer_eur: float = 100) -> dict:
    forecast = upcoming_events(customer_id)
    salary = forecast["next_salary"]
    balance = forecast["balance_now_eur"]
    if not salary:
        return {"estimated_payday": None, "as_of": forecast["today"]}
    # Reserve same-day bills too because their order relative to income is unknown.
    bills = [bill for bill in forecast["upcoming_bills"] if bill["days_until"] <= salary["days_until"]]
    bill_total = round(sum(bill["amount_eur"] for bill in bills), 2)
    projected = round(balance - bill_total, 2)
    return {
        "as_of": forecast["today"], "estimated_payday": salary["predicted_date"],
        "balance_eur": balance, "bills": bills, "bill_total_eur": bill_total, "buffer_eur": buffer_eur,
        "purchase_eur": purchase_eur, "projected_before_eur": projected,
        "projected_after_eur": round(projected - purchase_eur, 2),
        "room_eur": max(0, round(projected - buffer_eur, 2)),
    }


def welcome_message(customer_id: str) -> str:
    u = upcoming_events(customer_id)
    parts = []
    if u["next_salary"]:
        s = u["next_salary"]
        parts.append(f"salary {s['amount_eur']:.2f} EUR in {s['days_until']} days")
    if u["low_balance_risk"] is not None:
        r = u["low_balance_risk"]
        if r["gap_eur"] > 0:
            parts.append(
                f"watch out: before salary your balance dips to {r['projected_balance_eur']:.2f} EUR"
            )
        else:
            parts.append(
                f"before salary your balance dips to {r['projected_balance_eur']:.2f} EUR"
            )
    bills = [e for e in u["upcoming_bills"] if e["days_until"] <= 14][:3]
    if bills:
        names = ", ".join(f"{e['name']} in {e['days_until']}d" for e in bills)
        parts.append(f"bills due soon: {names}")
    if parts:
        return "In this demo, " + ", ".join(parts) + "."
    return "Start with a question about your weekly budget or recent spending."


def monthly_overview(customer_id: str):
    reference = ref_date(customer_id)
    first_of_month = reference.replace(day=1)
    # The receipt profile opens on a complete month of the combined history.
    end = first_of_month - datetime.timedelta(days=1) if customer_id == RECEIPT_CUSTOMER_ID else datetime.date.max
    start = (end if customer_id == RECEIPT_CUSTOMER_ID else reference).replace(day=1).isoformat()
    con = connect()
    income = con.execute("""
        SELECT round(sum(tx_amount_eur), 2) FROM tx_enriched
        WHERE customer_id = ? AND flow = 'income' AND tx_date BETWEEN ? AND ?
    """, [customer_id, start, end]).fetchone()[0] or 0
    expense = con.execute("""
        SELECT round(sum(-tx_amount_eur), 2) FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND tx_date BETWEEN ? AND ?
    """, [customer_id, start, end]).fetchone()[0] or 0
    per_category = con.execute("""
        SELECT category, round(sum(-tx_amount_eur), 2) FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND tx_date BETWEEN ? AND ?
        GROUP BY category ORDER BY 2 DESC
    """, [customer_id, start, end]).fetchall()
    per_basket = con.execute("""
        SELECT basket, round(sum(-tx_amount_eur), 2) FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND tx_date BETWEEN ? AND ?
        GROUP BY basket ORDER BY 2 DESC
    """, [customer_id, start, end]).fetchall()
    balance_trend = con.execute("""
        SELECT tx_date, last_value(balance_after_eur) OVER (
            PARTITION BY tx_date ORDER BY tx_timestamp, balance_after_eur ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
        ) AS bal
        FROM tx_enriched
        WHERE customer_id = ? AND tx_date BETWEEN ? AND ?
        ORDER BY tx_date
    """, [customer_id, start, end]).fetchall()
    daily = list(dict.fromkeys((str(d), b) for d, b in balance_trend))
    con.close()
    return {
        "month": start[:7],
        "income": income,
        "expense": expense,
        "net": round(income - expense, 2),
        "balance": current_balance(customer_id)["balance_eur"],
        "per_category": [dict(zip(("category", "spent_eur"), r)) for r in per_category],
        "per_basket": [dict(zip(("basket", "spent_eur"), r)) for r in per_basket],
        "balance_trend": [{"day": d, "balance_eur": b} for d, b in daily],
        "safe_to_spend": safe_to_spend(customer_id),
    }


def apartment_plan(customer_id: str) -> dict | None:
    if customer_id != RECEIPT_CUSTOMER_ID:
        return None
    end = ref_date(customer_id).replace(day=1) - datetime.timedelta(days=1)
    start = end.replace(day=1)
    with connect() as con:
        income, expense, dining = con.execute("""
            SELECT coalesce(round(sum(tx_amount_eur) FILTER (WHERE flow = 'income'), 2), 0),
                   coalesce(round(sum(-tx_amount_eur) FILTER (WHERE flow = 'expense'), 2), 0),
                   coalesce(round(sum(-tx_amount_eur) FILTER (
                       WHERE flow = 'expense' AND category = 'Restaurants'), 2), 0)
            FROM tx_enriched
            WHERE customer_id = ? AND simulated = 0 AND tx_date BETWEEN ? AND ?
        """, [customer_id, start, end]).fetchone()
    if not income:
        return None
    goal = get_goal(customer_id)
    if goal is None:
        return None
    target, months, saved = goal["target_eur"], goal["months"], goal["saved_so_far_eur"]
    remaining = max(0, round(target - saved, 2))
    net = round(income - expense, 2)
    reduction = round(dining * 0.2, 2)
    return {
        "goal": goal["name"],
        "target_eur": target,
        "saved_eur": saved,
        "months": months,
        "needed_monthly_eur": round(remaining / months, 2) if months else None,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "income_eur": income,
        "expense_eur": expense,
        "net_eur": net,
        "dining_eur": dining,
        "dining_cap_eur": round(dining - reduction, 2),
        "reduction_eur": reduction,
        "projected_net_eur": round(net + reduction, 2),
        "dining_change_pct": 20,
    }


def simulate_transaction(customer_id: str, amount: float, description: str, category: str | None = None,
                         merchant_id: str | None = None, mcc: str | int | None = None, prior: list[dict] | None = None):
    from . import config, jev

    amount = abs(float(amount))
    cls = None
    if config.TYPESAFE_API_KEY:
        try:
            cls = {**jev.classify_transaction(description, amount, category), "source": "jev"}
        except Exception:
            pass
    if cls is None:
        cls = {
            "basket": "mandatory_regular" if category in {"Housing", "Health", "Transportation", "Home & Tech", "Utilities"}
                      else "everyday_discretionary",
            "confidence": 0.0,
            "is_subscription": 0.0,
            "probabilities": {},
            "source": "rules",
        }

    cat = category or "Uncategorised"
    con = connect()
    start = ref_date(customer_id).replace(day=1).isoformat()
    cat_total = con.execute("""
        SELECT round(sum(-tx_amount_eur), 2) FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND category = ? AND tx_date >= ?
    """, [customer_id, cat, start]).fetchone()[0] or 0
    balance = current_balance(customer_id)["balance_eur"] or 0
    account = con.execute("""
        SELECT bank_account_id FROM tx WHERE customer_id = ? LIMIT 1
    """, [customer_id]).fetchone()[0]

    safe_before = safe_to_spend(customer_id)
    weekly_before = safe_before["safe_to_spend_weekly"]
    con.close()

    ts = ref_date(customer_id).strftime("%d%b%y").upper() + ":23:59:59"
    balance_after = round(balance - amount, 2)

    con = connect()
    con.execute("""
        INSERT INTO tx_enriched
        (customer_id, bank_account_id, tx_date, tx_timestamp, category, tx_amount_eur,
         balance_after_eur, transaction_type, merchant_id, mcc_code, flow,
         jev_basket, is_subscription, irregular_risk, jev_confidence, regular_pattern, basket, simulated)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'purchase', ?, ?, 'expense',
                ?, ?, 0, ?, 0, ?, 1)
    """, [
        customer_id, account, ref_date(customer_id), ts, cat, round(-amount, 2), balance_after,
        merchant_id or "", str(mcc) if mcc else None, cls["basket"], cls.get("is_subscription", 0),
        cls.get("confidence", 0), cls["basket"],
    ])
    con.close()

    safe_after = safe_to_spend(customer_id)
    weekly_after = safe_after["safe_to_spend_weekly"]

    if balance_after < 0 or weekly_after < 0:
        verdict, tone = "This purchase exceeds your demo budget", "bad"
    elif amount > weekly_before:
        verdict, tone = "This purchase costs more than your weekly estimate", "warn"
    else:
        verdict, tone = "Fits your budget", "good"

    salary = upcoming_events(customer_id).get("next_salary")
    remaining = round(weekly_after, 2)
    alternatives = []
    if salary:
        alternatives.append({
            "kind": "wait",
            "text": f"Buy after salary day in {salary['days_until']} days — your buffer stays intact.",
            "days_until": salary["days_until"],
        })
    if remaining < 0:
        alternatives.append({
            "kind": "cut",
            "text": f"To make it fit, trim {abs(remaining):.2f} EUR from your everyday spending this week.",
            "cut_needed_eur": abs(remaining),
        })
    alternatives.append({
        "kind": "goal",
        "text": "Or turn this into a savings goal and buy it when it's planned.",
    })

    return {
        "classification": cls,
        "amount": round(amount, 2),
        "description": description,
        "category": cat,
        "category_month_spent_eur": cat_total,
        "category_month_after_eur": round(cat_total + amount, 2),
        "balance_now_eur": balance,
        "balance_after_eur": balance_after,
        "safe_to_spend_weekly_eur": weekly_before,
        "safe_to_spend_weekly_after_eur": weekly_after,
        "remaining_after_eur": remaining,
        "verdict": verdict,
        "tone": tone,
        "alternatives": alternatives,
        "persisted": True,
    }


def clear_simulated(customer_id: str | None = None) -> int:
    con = connect()
    if customer_id:
        n = con.execute("SELECT count(*) FROM tx_enriched WHERE simulated = 1 AND customer_id = ?", [customer_id]).fetchone()[0]
        con.execute("DELETE FROM tx_enriched WHERE simulated = 1 AND customer_id = ?", [customer_id])
    else:
        n = con.execute("SELECT count(*) FROM tx_enriched WHERE simulated = 1").fetchone()[0]
        con.execute("DELETE FROM tx_enriched WHERE simulated = 1")
    con.close()
    return n


MCC_LABELS = {    "4111": "local transport ticket",
    "4121": "taxi ride",
    "4511": "flight",
    "4722": "travel package",
    "5200": "home improvement store",
    "5251": "hardware store",
    "5411": "grocery shopping",
    "5422": "butcher shop",
    "5451": "dairy shop",
    "5499": "corner store",
    "5541": "gas station",
    "5542": "fuel pump",
    "5651": "clothing store",
    "5691": "menswear shop",
    "5712": "furniture store",
    "5732": "electronics store",
    "5734": "software store",
    "5812": "restaurant",
    "5813": "bar",
    "5814": "fast food",
    "5912": "pharmacy",
    "5941": "sports shop",
    "5942": "bookstore",
    "5945": "toy store",
    "5999": "specialty shop",
    "7011": "hotel",
    "7512": "car rental",
    "7523": "parking garage",
    "7832": "cinema",
}


def random_transaction(customer_id: str | None = None) -> dict:
    con = connect()
    if customer_id:
        row = con.execute("""
            SELECT category, mcc_code, tx_amount_eur, merchant_id FROM tx
            WHERE customer_id = ? AND flow = 'expense' AND tx_amount_eur BETWEEN -250 AND -5
            ORDER BY random() LIMIT 1
        """, [customer_id]).fetchone()
    else:
        row = con.execute("""
            SELECT category, mcc_code, tx_amount_eur, merchant_id FROM tx
            WHERE flow = 'expense' AND tx_amount_eur BETWEEN -250 AND -5
            ORDER BY random() LIMIT 1
        """).fetchone()
    con.close()
    category, mcc, amount, merchant = row
    label = MCC_LABELS.get(mcc, category.lower())
    desc = f"{label} ({merchant})" if merchant else label
    return {
        "description": desc,
        "category": category,
        "mcc": mcc,
        "amount": round(-amount, 2),
        "merchant_id": merchant,
    }


BENCHMARKS = {
    "18-24": {"Groceries": 220, "Restaurants": 95, "Transportation": 90, "Entertainment": 70},
    "25-44": {"Groceries": 280, "Restaurants": 130, "Transportation": 160, "Entertainment": 85},
    "45-64": {"Groceries": 310, "Restaurants": 110, "Transportation": 150, "Entertainment": 75},
    "65+": {"Groceries": 260, "Restaurants": 80, "Transportation": 70, "Entertainment": 55},
}

_CATS = ("Groceries", "Restaurants", "Transportation", "Entertainment")


def _age_group(age: int) -> str:
    if age <= 24:
        return "18-24"
    if age <= 44:
        return "25-44"
    if age <= 64:
        return "45-64"
    return "65+"


def _data_benchmarks() -> dict:
    con = connect()
    rows = con.execute("""
        WITH grp AS (
            SELECT customer_id,
                CASE WHEN customer_age <= 24 THEN '18-24'
                     WHEN customer_age <= 44 THEN '25-44'
                     WHEN customer_age <= 64 THEN '45-64'
                     ELSE '65+' END AS g
            FROM customers WHERE customer_id != ?
        ),
        monthly AS (
            SELECT customer_id, category,
                   round(sum(-tx_amount_eur) / 3, 2) AS m
            FROM tx_enriched
            WHERE flow = 'expense'
              AND category IN ('Groceries', 'Restaurants', 'Transportation', 'Entertainment')
              AND tx_date >= (SELECT max(tx_date) FROM tx WHERE customer_id != ?) - INTERVAL 3 MONTH
            GROUP BY customer_id, category
        )
        SELECT g.g, m.category, round(avg(m.m), 2)
        FROM grp g JOIN monthly m USING (customer_id)
        GROUP BY 1, 2
    """, [RECEIPT_CUSTOMER_ID, RECEIPT_CUSTOMER_ID]).fetchall()
    con.close()
    out: dict[str, dict[str, float]] = {k: {} for k in BENCHMARKS}
    for g, cat, avg in rows:
        out[g][cat] = avg
    for g in out:
        for cat in _CATS:
            out[g].setdefault(cat, BENCHMARKS[g][cat])
    return out


def benchmark(customer_id: str) -> dict:
    con = connect()
    age = con.execute("SELECT customer_age FROM customers WHERE customer_id = ?", [customer_id]).fetchone()[0]
    start = months_ago(3, customer_id)
    rows = []
    user_total = 0.0
    finn_total = 0.0
    bench = _data_benchmarks()[_age_group(age)]
    for cat, finn in bench.items():
        total = con.execute("""
            SELECT coalesce(sum(-tx_amount_eur), 0) FROM tx_enriched
            WHERE customer_id = ? AND flow = 'expense' AND category = ? AND tx_date >= ?
        """, [customer_id, cat, start]).fetchone()[0]
        user = round(total / 3, 2)
        user_total += user
        finn_total += finn
        delta = round((user - finn) / finn * 100, 1) if finn else 0.0
        rows.append({
            "category": cat,
            "user_monthly_eur": user,
            "finn_monthly_eur": finn,
            "delta_pct": delta,
        })
    rows.sort(key=lambda r: -r["delta_pct"])
    over = [r for r in rows if r["delta_pct"] > 15]
    under = [r for r in rows if r["delta_pct"] < -10]
    for r in rows:
        r["delta_eur"] = round(r["user_monthly_eur"] - r["finn_monthly_eur"], 2)
    con.close()
    return {
        "age_group": _age_group(age),
        "age": age,
        "rows": rows,
        "user_total_monthly": round(user_total, 2),
        "finn_total_monthly": round(finn_total, 2),
        "total_delta_eur": round(user_total - finn_total, 2),
        "story": {
            "top_over": over[0] if over else None,
            "over": over[1:],
            "under": under,
        },
        "note": "Benchmarks inspired by Statistics Finland open data, calibrated to this demo dataset.",
    }


def coaching_plan(customer_id: str) -> dict:
    start = months_ago(3, customer_id)
    con = connect()
    cats = con.execute("""
        SELECT category, round(sum(-tx_amount_eur)/3, 2) AS monthly FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND category IN
            ('Restaurants', 'Entertainment', 'Lifestyle', 'Travel') AND tx_date >= ?
        GROUP BY category ORDER BY monthly DESC LIMIT 1
    """, [customer_id, start]).fetchone()
    con.close()

    safe = safe_to_spend(customer_id)
    everyday = safe["avg_monthly"]["everyday_discretionary"]
    safe_to_save = max(round(safe["safe_to_spend_monthly"] - everyday, 2), 0)

    subs = subscriptions(customer_id)
    sub_total = subs["total_monthly_eur"]

    impulse = spender_profile(customer_id)["impulse_score_0_100"]

    actions = []
    if cats:
        cat, monthly = cats
        yearly = round(monthly * 0.20 * 12, 2)
        actions.append({
            "kind": "cut",
            "title": f"Trim {cat.lower()} by 20%",
            "detail": f"You spend {monthly} EUR/month on {cat.lower()}. Cutting a fifth would free up {round(monthly * 0.2, 2)} EUR/month.",
            "impact_eur": yearly,
            "impact_monthly": round(monthly * 0.2, 2),
            "impact_label": f"{round(monthly * 0.2, 2)} EUR/month",
        })
    if sub_total > 10:
        actions.append({
            "kind": "subs",
            "title": "Audit your subscriptions",
            "detail": f"Your recurring payments add up to {sub_total} EUR/month. Cutting even one frees money with zero lifestyle change.",
            "impact_eur": round(sub_total * 12, 2),
            "impact_monthly": sub_total,
            "impact_label": f"{sub_total} EUR/month",
        })
    else:
        actions.append({
            "kind": "impulse",
            "title": "Slow down small purchases",
            "detail": f"Your impulse score is {impulse}/100 — about {impulse}% of your everyday buys are small or weekend splurges. A 2-day rule before buying helps.",
            "impact_eur": round(everyday * 0.15 * 12, 2),
            "impact_monthly": round(everyday * 0.15, 2),
            "impact_label": f"~{round(everyday * 0.15, 2)} EUR/month",
        })
    actions.append({
        "kind": "save",
        "title": "Automate a monthly transfer",
        "detail": f"Your safe-to-save is {safe_to_save} EUR/month. Move it to savings on salary day before it slips into everyday spending.",
        "impact_eur": round(safe_to_save * 12, 2),
        "impact_monthly": safe_to_save,
        "impact_label": f"{safe_to_save} EUR/month",
    })
    return {"safe_to_save_monthly": safe_to_save, "actions": actions[:3]}


def scenario(customer_id: str, description: str, monthly_eur: float) -> dict:
    monthly = round(abs(float(monthly_eur)), 2)
    safe = safe_to_spend(customer_id)
    before_monthly = safe["safe_to_spend_monthly"]
    before_weekly = safe["safe_to_spend_weekly"]
    after_monthly = round(before_monthly - monthly, 2)

    plan = coaching_plan(customer_id)

    if after_monthly >= 0:
        return {
            "description": description,
            "monthly_eur": monthly,
            "status": "fits",
            "safe_monthly_before_eur": before_monthly,
            "safe_monthly_after_eur": after_monthly,
            "safe_weekly_before_eur": before_weekly,
            "safe_weekly_after_eur": round(after_monthly / 4.33, 2),
            "suggestion": f"With {after_monthly} EUR/month left, you can still save "
                          f"{round(after_monthly * 0.5, 2)} EUR/month towards a goal.",
        }

    gap = -after_monthly
    cover = []
    remaining = gap
    for a in plan["actions"]:
        impact = a.get("impact_monthly", 0)
        if impact <= 0:
            continue
        cover.append({"action": a["title"], "monthly_eur": impact})
        remaining = round(remaining - impact, 2)
        if remaining <= 0:
            break

    return {
        "description": description,
        "monthly_eur": monthly,
        "status": "over",
        "safe_monthly_before_eur": before_monthly,
        "safe_monthly_after_eur": after_monthly,
        "safe_weekly_before_eur": before_weekly,
        "safe_weekly_after_eur": round(after_monthly / 4.33, 2),
        "gap_monthly_eur": gap,
        "cover_options": cover,
        "remaining_gap_eur": max(remaining, 0),
    }


def set_goal(customer_id: str, name: str, target_eur: float, months: int | None = None) -> dict:
    import math

    from .db import ensure_app_tables

    safe = safe_to_spend(customer_id)
    everyday = safe["avg_monthly"]["everyday_discretionary"]
    safe_to_save = max(round(safe["safe_to_spend_monthly"] - everyday, 2), 0)
    plan = coaching_plan(customer_id)

    if months is None:
        months = math.ceil(target_eur / safe_to_save) if safe_to_save > 0 else None

    con = connect()
    ensure_app_tables(con)
    con.execute("""
        INSERT INTO goals (customer_id, name, target_eur, months, weekly_eur, safe_to_save_monthly, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (customer_id) DO UPDATE SET
            name = excluded.name, target_eur = excluded.target_eur, months = excluded.months,
            weekly_eur = excluded.weekly_eur, safe_to_save_monthly = excluded.safe_to_save_monthly,
            created_at = excluded.created_at
    """, [
        customer_id, name, round(float(target_eur), 2), months,
        round(target_eur / (months * 4.33), 2) if months else None,
        safe_to_save, ref_date(customer_id),
    ])
    con.close()

    goal = get_goal(customer_id)
    assert goal is not None
    goal["note"] = (
        "Plan your own pace — a shorter timeline means trimming more everyday spending."
        if months
        else "Your current safe-to-save is 0 EUR/month. Trim an action below to start saving."
    )
    goal["suggestion"] = plan["actions"][0]["title"] if plan["actions"] else None
    return goal


def get_goal(customer_id: str) -> dict | None:
    from .db import ensure_app_tables

    con = connect()
    ensure_app_tables(con)
    row = con.execute("""
        SELECT name, target_eur, months, weekly_eur, safe_to_save_monthly, created_at
        FROM goals WHERE customer_id = ?
    """, [customer_id]).fetchone()
    if not row:
        exists = customer_id == RECEIPT_CUSTOMER_ID and con.execute(
            "SELECT 1 FROM customers WHERE customer_id = ?", [customer_id]
        ).fetchone()
        con.close()
        if exists:
            return {
                "name": "Apartment deposit", "target_eur": 15000, "months": 36,
                "weekly_eur": round(15000 / (36 * 4.33), 2),
                "safe_to_save_monthly": 0, "saved_so_far_eur": 0,
            }
        return None
    saved = con.execute("""
        SELECT coalesce(round(sum(-tx_amount_eur), 2), 0) FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense'
          AND transaction_type IN ('investment_deposit')
          AND tx_date >= ?
    """, [customer_id, row[5]]).fetchone()[0]
    con.close()
    return {
        "name": row[0],
        "target_eur": row[1],
        "months": row[2],
        "weekly_eur": row[3],
        "safe_to_save_monthly": row[4],
        "saved_so_far_eur": saved,
        "created_at": str(row[5]),
    }


def challenge_quote(customer_id: str, category: str, pct: float, days: int) -> dict:
    cat, _ = resolve_category(category)
    category = cat or category
    start = months_ago(3, customer_id)
    where, args = spending_filters(customer_id, start, ref_date(customer_id), category)
    with connect() as con:
        total = con.execute(
            f"SELECT coalesce(sum(-tx_amount_eur), 0) FROM tx_enriched WHERE {where}", args
        ).fetchone()[0]
    baseline_daily = round(float(total) / 90, 2)
    target_daily = round(baseline_daily * (1 - pct / 100), 2)
    return {
        "kind": "spend_cap", "category": category, "pct": pct, "days": days,
        "baseline_daily_eur": baseline_daily, "target_daily_eur": target_daily,
        "budget_eur": round(target_daily * days, 2),
    }


def create_challenge(customer_id: str, category: str, pct: float, days: int = 14) -> dict:
    from .db import ensure_app_tables

    quote = challenge_quote(customer_id, category, pct, days)
    start_date = ref_date(customer_id) + datetime.timedelta(days=1)
    end_date = start_date + datetime.timedelta(days=days - 1)
    with connect() as con:
        ensure_app_tables(con)
        con.execute("BEGIN TRANSACTION")
        con.execute("""
            DELETE FROM tx_enriched
            WHERE customer_id = ? AND simulated = 1 AND tx_date >= ?
        """, [customer_id, start_date])
        con.execute("UPDATE challenges SET status = 'completed' WHERE customer_id = ? AND status = 'active'", [customer_id])
        cid = con.execute("SELECT nextval('challenge_seq')").fetchone()[0]
        con.execute("""
            INSERT INTO challenges VALUES (?, ?, 'spend_cap', ?, ?, ?, ?, ?, ?, 'active', ?)
        """, [cid, customer_id, quote["category"], float(pct), quote["baseline_daily_eur"],
              quote["target_daily_eur"], start_date, end_date, ref_date(customer_id)])
        con.commit()
    return {**quote, "id": cid, "start_date": start_date.isoformat(), "end_date": end_date.isoformat(), "status": "active"}


def _fast_forward_sample(customer_id: str, first_day: datetime.date, days: int, category: str, target_daily: float):
    con = connect()
    day_span = max(days, 3)
    rows = con.execute("""
        SELECT category, merchant_id, mcc_code, tx_amount_eur FROM tx
        WHERE customer_id = ? AND flow = 'expense' AND tx_amount_eur BETWEEN -250 AND -5
        ORDER BY random() LIMIT ?
    """, [customer_id, day_span * 4]).fetchall()
    con.close()
    if not rows:
        return
    out = []
    last_bal = current_balance(customer_id)["balance_eur"] or 0
    for i in range(days):
        spent = 0.0
        for cat_r, merch, mcc, amt in rows[i::days]:
            a = abs(amt)
            if cat_r == category:
                room = target_daily - spent
                if room <= 0:
                    continue
                a = min(a, room)
                spent += a
            last_bal = round(last_bal - a, 2)
            out.append((first_day + datetime.timedelta(days=i), cat_r, merch or "", str(mcc) if mcc else None, a, last_bal))
    if not out:
        return
    with connect() as con:
        con.execute("BEGIN TRANSACTION")
        con.executemany("""
            INSERT INTO tx_enriched
            (customer_id, bank_account_id, tx_date, tx_timestamp, category, tx_amount_eur,
             balance_after_eur, transaction_type, merchant_id, mcc_code, flow,
             jev_basket, is_subscription, irregular_risk, jev_confidence, regular_pattern, basket, simulated)
            VALUES (?, (SELECT bank_account_id FROM tx WHERE customer_id = ? LIMIT 1), ?, ?, ?, ?, ?, 'purchase', ?, ?, 'expense',
                    'everyday_discretionary', 0, 0, 0, 0, 'everyday_discretionary', 1)
        """, [
            [customer_id, customer_id, day, day.strftime("%d%b%y").upper() + ":12:00:00",
             cat, round(-amount, 2), balance, merchant, mcc]
            for day, cat, merchant, mcc, amount, balance in out
        ])
        con.commit()


def fast_forward(customer_id: str, days: int = 7) -> dict:
    progress = challenge_progress(customer_id)
    active = progress["active"]
    if not active:
        return progress
    remaining = active["total_days"] - active["days_elapsed"]
    if remaining <= 0:
        return progress
    first_day = datetime.date.fromisoformat(active["start_date"]) + datetime.timedelta(days=active["days_elapsed"])
    _fast_forward_sample(customer_id, first_day, min(days, remaining), active["category"], active["target_daily_eur"])
    return challenge_progress(customer_id, fast_forwarded=True)


def challenge_progress(customer_id: str, fast_forwarded: bool = False, simulated_spent: float = 0.0) -> dict:
    from .db import ensure_app_tables

    con = connect()
    ensure_app_tables(con)
    row = con.execute("""
        SELECT id, kind, category, pct, baseline_daily, target_daily, start_date, end_date, created_at, status
        FROM challenges WHERE customer_id = ? AND status = 'active' ORDER BY id DESC LIMIT 1
    """, [customer_id]).fetchone()
    if not row:
        con.close()
        return {"active": None}
    cid, kind, cat, pct, baseline, target, start_date, end_date, created, status = row
    eff_today = con.execute("""
        SELECT coalesce(max(tx_date), ?) FROM tx_enriched WHERE simulated = 1 AND customer_id = ?
    """, [ref_date(customer_id), customer_id]).fetchone()[0]
    con.close()

    total_days = (end_date - start_date).days + 1
    elapsed = min((eff_today - start_date).days + 1, total_days)
    if elapsed < 0:
        elapsed = 0
    budget_so_far = round(target * elapsed, 2)
    pace_so_far = round(baseline * elapsed, 2)
    start = start_date.isoformat()
    con = connect()
    actual = con.execute("""
        SELECT coalesce(round(sum(-tx_amount_eur), 2), 0) FROM tx_enriched
        WHERE customer_id = ? AND flow = 'expense' AND category = ? AND tx_date >= ? AND tx_date <= ?
    """, [customer_id, cat, start, end_date.isoformat()]).fetchone()[0] or 0
    con.close()
    under = actual <= budget_so_far
    saved = round(pace_so_far - actual, 2)
    return {
        "active": {
            "id": cid,
            "kind": kind,
            "category": cat,
            "pct": pct,
            "baseline_daily_eur": baseline,
            "target_daily_eur": target,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "effective_today": eff_today.isoformat(),
            "total_days": total_days,
            "days_elapsed": max(elapsed, 0),
            "budget_so_far_eur": budget_so_far,
            "actual_so_far_eur": actual,
            "on_track": under,
            "saved_vs_pace_eur": saved,
            "overspent_eur": round(actual - budget_so_far, 2) if not under else 0,
            "fast_forwarded": fast_forwarded,
        }
    }
