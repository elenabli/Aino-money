import json
import time

from typesafe_sdk import Choice, Noul, TypeSafeClient

from . import config
from .db import connect

BASKETS = {
    "mandatory_regular": "Must-pay bills that recur predictably: rent, mortgage, utilities, insurance, phone, loan payments, regular subscriptions",
    "mandatory_irregular": "Necessary expenses that are unexpected or one-off: repairs, broken appliance, health emergency, moving",
    "everyday_discretionary": "Day-to-day spending that can slip through your fingers: coffee, eating out, entertainment, shopping, hobbies",
    "savings_investing": "Money set aside for the future: investments, savings transfers",
}

RULES = {
    "salary": "mandatory_regular",
    "salary_sweep": "mandatory_regular",
    "housing_payment": "mandatory_regular",
    "utilities_payment": "mandatory_regular",
    "investment_deposit": "savings_investing",
    "investment_withdrawal": "savings_investing",
    "other_income": "mandatory_regular",
}


def merchant_state(m: dict) -> str:
    return (
        f"Merchant: {m['merchant_id']}\n"
        f"Category: {m['category']}\n"
        f"MCC code: {m['mcc_code']}\n"
        f"Transactions seen: {m['tx_count']}\n"
        f"Average amount: {m['avg_amount']} EUR, median: {m['median_amount']} EUR\n"
        f"Amount range: {m['min_amount']} to {m['max_amount']} EUR"
    )


def jev_questions() -> dict:
    return {
        "basket": Choice(
            instructions="Which of the three spending baskets (plus savings) best describes "
            "typical spending at this merchant?",
            criteria=BASKETS,
        ),
        "is_subscription": Noul(
            instructions="This merchant charges recurring, roughly fixed-amount payments "
            "typical of a subscription or regular bill (streaming, phone, gym, membership, insurance)"
        ),
        "irregular_risk": Noul(
            instructions="A purchase at this merchant could plausibly be an unexpected, "
            "necessary one-off expense (appliance repair, car trouble, medical emergency)"
        ),
    }


def classify_transaction(description: str, amount: float, category: str | None = None) -> dict:
    state = (
        f"Transaction description: {description}\n"
        f"Category: {category or 'unknown'}\n"
        f"Amount: {amount:.2f} EUR"
    )
    with TypeSafeClient(model=config.TYPESAFE_MODEL, timeout=8.0) as client:
        resp = client.system_one(
            state=state,
            questions={
                "basket": Choice(
                    instructions="Which basket does this single transaction belong to?",
                    criteria=BASKETS,
                ),
                "is_subscription": Noul(
                    instructions="This transaction is a recurring fixed-amount payment "
                    "typical of a subscription or regular bill"
                ),
            },
        )
    ans = resp.choices["basket"]
    return {
        "basket": ans.choice,
        "probabilities": ans.probabilities,
        "confidence": ans.confidence,
        "is_subscription": resp.nouls["is_subscription"].noul,
    }


def classify_merchants(limit: int | None = None, delay: float = 0.0) -> None:
    cache = {}
    if config.JEV_CACHE_PATH.exists():
        cache = json.loads(config.JEV_CACHE_PATH.read_text())

    con = connect()
    rows = con.execute(
        "SELECT merchant_id, category, mcc_code, tx_count, avg_amount, median_amount, "
        "min_amount, max_amount FROM merchants ORDER BY tx_count DESC"
    ).fetchall()
    cols = [d[0] for d in con.description]
    con.close()

    todo = [dict(zip(cols, r)) for r in rows]
    if limit:
        todo = todo[:limit]
    todo = [m for m in todo if m["merchant_id"] not in cache]

    if not todo:
        print("all merchants already classified")
        return

    with TypeSafeClient(model=config.TYPESAFE_MODEL) as client:
        for i, m in enumerate(todo):
            resp = client.system_one(state=merchant_state(m), questions=jev_questions())
            choice_ans = resp.choices["basket"]
            cache[m["merchant_id"]] = {
                "basket": choice_ans.choice,
                "probabilities": choice_ans.probabilities,
                "confidence": choice_ans.confidence,
                "is_subscription": resp.nouls["is_subscription"].noul,
                "irregular_risk": resp.nouls["irregular_risk"].noul,
                "category": m["category"],
            }
            if i % 25 == 0 or i == len(todo) - 1:
                config.JEV_CACHE_PATH.write_text(json.dumps(cache, indent=2))
                print(f"classified {i + 1}/{len(todo)} ({m['merchant_id']})")
            if delay:
                time.sleep(delay)

    config.JEV_CACHE_PATH.write_text(json.dumps(cache, indent=2))
    write_labels_to_db(cache)
    print(f"done: {len(cache)} merchants classified")


def write_labels_to_db(cache: dict) -> None:
    con = connect()
    con.execute("DELETE FROM merchant_classification")
    rows = [
        (
            mid,
            v["basket"],
            v.get("is_subscription"),
            v.get("irregular_risk"),
            v.get("confidence"),
            "jev",
        )
        for mid, v in cache.items()
    ]
    con.executemany(
        "INSERT INTO merchant_classification VALUES (?, ?, ?, ?, ?, ?)", rows
    )
    con.close()
    print("labels written to duckdb")
