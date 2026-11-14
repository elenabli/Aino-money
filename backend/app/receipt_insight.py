"""Turn one classified Prisma receipt into per-category insight and evaluations.

Each receipt line already carries a detailed product category (see receipt_categories.py).
Here those categories are grouped into everyday shopping groups, and each group in the
receipt is compared with the same group's spend this month and the user's usual month.
"""

import calendar
from datetime import date

from . import db, receipts

# (group, kind) per detailed product category. kind drives the pedagogy:
# staple = everyday essential food, treat/convenience = spending that slips through fingers.
GROUPS: dict[str, tuple[str, str]] = {}
_DEFS = {
    ("Fruit & veg", "staple"): [
        "Tomatoes", "Berries", "Citrus fruit", "Tropical fruit and melons", "Bananas", "Apples", "Mushrooms",
        "Peppers and chillies", "Cabbage, broccoli and cauliflower", "Cucumbers", "Salad greens and herbs",
        "Onions and garlic", "Squash, aubergines, corn and peas", "Carrots", "Stone fruit", "Grapes", "Potatoes",
        "Beetroot, turnips and radishes", "Pears", "Frozen vegetables and chips"],
    ("Dairy & eggs", "staple"): [
        "Cheese", "Eggs", "Quark, puddings and dairy desserts", "Yogurt, kefir and cultured milk",
        "Butter and spreads", "Cream and cooking dairy", "Milk", "Plant-based milk and cream"],
    ("Bread & grains", "staple"): [
        "Bread, rolls and croissants", "Pasta and noodles", "Breakfast cereal and muesli", "Rice and grains",
        "Tortillas and flatbread", "Crackers and rice cakes", "Flour, sugar and baking ingredients", "Pastry dough"],
    ("Protein", "staple"): [
        "Fish fillets and smoked fish", "Plant-based meat alternatives", "Canned and preserved fish",
        "Sausages and deli meats", "Tofu, tempeh and soy products", "Beans, lentils and chickpeas", "Poultry",
        "Beef", "Fish fingers and nuggets"],
    ("Pantry", "staple"): [
        "Sauces, dressings and condiments", "Herbs, spices and seasonings", "Cooking oils and vinegar",
        "Jam and preserves", "Nuts, seeds and dried fruit", "Canned vegetables and tomato products",
        "Pickles, olives and fermented vegetables"],
    ("Ready meals", "convenience"): [
        "Pizza and pizza snacks", "Sushi", "Ready meals and soups", "Deli sandwiches"],
    ("Snacks & sweets", "treat"): [
        "Chocolate", "Cakes and sweet pastries", "Candy and liquorice", "Fruit, cereal and snack bars",
        "Biscuits and wafers", "Crisps and popcorn", "Ice cream and ice pops", "Nut and chocolate spreads",
        "Chewing gum and mints", "Dessert sauces", "Plant-based desserts"],
    ("Drinks", "treat"): [
        "Beer", "Cider", "Soft drinks", "Energy and sports drinks", "Juice and fruit drinks",
        "Smoothies and fruit purées", "Drink concentrates", "Alcohol-free beer and cocktails", "Bottle deposits",
        "Coffee and cocoa drinks", "Tea and herbal infusions", "Mineral water"],
    ("Household & care", "household"): [
        "Bath, soap and shower", "Laundry", "Toilet and kitchen paper", "Cleaning tools and surface cleaners",
        "Hair care", "Face care", "Oral care", "Body moisturisers and cotton pads", "Dishwashing",
        "Waste and compost bags", "Toilet cleaning and fresheners", "Food storage and baking supplies",
        "Shopping and gift bags", "Vitamins and supplements", "First aid", "Menstrual care",
        "Sexual and reproductive health", "Batteries and electrical accessories", "Hair accessories"],
    ("Extras", "fun"): [
        "Toys and building sets", "Books and comics", "Arts and crafts", "Yarn and knitting", "Party decorations",
        "Flowers and garden", "Footwear", "Socks, tights and gloves", "Fragrance", "Exercise accessories",
        "Home fixtures and coverings", "School and office supplies"],
    ("Fuel", "transport"): ["Fuel", "Car care", "Camping fuel"],
}
for (_group, _kind), _names in _DEFS.items():
    for _name in _names:
        GROUPS[_name] = (_group, _kind)

# The generated (synthetic) receipts used in the cloud demo carry group-level names already.
_SYNTHETIC = {
    "Fruit & vegetables": "Fruit & veg", "Dairy & eggs": "Dairy & eggs", "Bakery & grains": "Bread & grains",
    "Meat, fish & plant proteins": "Protein", "Pantry": "Pantry", "Frozen & ready meals": "Ready meals",
    "Snacks & sweets": "Snacks & sweets", "Drinks": "Drinks", "Household & personal care": "Household & care",
}
for _alias, _group in _SYNTHETIC.items():
    GROUPS.setdefault(_alias, next((g, k) for (g, k) in _DEFS if g == _group))

KIND_LABELS = {
    "staple": "Everyday essential", "treat": "Treat", "convenience": "Convenience",
    "household": "Household essential", "fun": "Extra", "transport": "Transport",
}


def group_of(product_category: str | None, coarse: str | None) -> tuple[str, str]:
    if product_category in GROUPS:
        return GROUPS[product_category]
    return ("Household & care", "household") if coarse == "Non-food" else ("Pantry", "staple")


def _month_bounds(day: date) -> tuple[date, date]:
    return day.replace(day=1), day.replace(day=calendar.monthrange(day.year, day.month)[1])


def _shift_month(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)


def _evaluate(kind: str, month_eur: float, usual_eur: float | None) -> dict:
    if not usual_eur or usual_eur < 1:
        return {"label": "New this month", "tone": "neutral",
                "text": "No usual pattern yet in your recent receipts."}
    ratio = month_eur / usual_eur
    pct = round((ratio - 1) * 100)
    if ratio >= 1.3:
        tone = "warn" if kind in {"treat", "convenience", "fun"} else "neutral"
        return {"label": f"{pct}% above usual", "tone": tone, "ratio": round(ratio, 2),
                "text": "Running ahead of your usual month." if tone == "neutral"
                else "This is where spending slips through: ahead of your usual pace."}
    if ratio <= 0.7:
        return {"label": f"{abs(pct)}% below usual", "tone": "good", "ratio": round(ratio, 2),
                "text": "Lower than your usual month so far."}
    return {"label": "On your usual pace", "tone": "good", "ratio": round(ratio, 2),
            "text": "In line with a typical month for you."}


def receipt_insight(receipt_id: str, customer_id: str) -> dict | None:
    receipt = receipts.details(receipt_id, customer_id)
    if receipt is None:
        return None
    with db.connect() as con:
        meta = con.execute("""
            SELECT r.merchant, t.tx_date, r.purchased_at
            FROM s_etukortti_receipts r JOIN tx t USING (receipt_id)
            WHERE t.customer_id = ? AND r.receipt_id = ?
        """, [customer_id, receipt_id]).fetchone()
        last_day = con.execute("SELECT max(tx_date) FROM tx WHERE customer_id = ?", [customer_id]).fetchone()[0]
        merchant, day, purchased_at = meta
        month_start, month_end = _month_bounds(day)
        history_start = _shift_month(month_start, -3)
        rows = con.execute("""
            SELECT t.tx_date, i.product_category, i.category, i.amount_eur
            FROM tx t JOIN s_etukortti_receipt_items i USING (receipt_id)
            WHERE t.customer_id = ? AND t.tx_date BETWEEN ? AND ?
        """, [customer_id, history_start, month_end]).fetchall()

    # Month in progress: compare month-to-date with the same share of a usual month.
    through = min(month_end, last_day)
    share = through.day / month_end.day
    month: dict[str, float] = {}
    history: dict[str, float] = {}
    months_seen = set()
    for tx_date, product, coarse, amount in rows:
        group = group_of(product, coarse)[0]
        if tx_date >= month_start:
            if tx_date <= through:
                month[group] = month.get(group, 0) + float(amount)
        else:
            months_seen.add((tx_date.year, tx_date.month))
            history[group] = history.get(group, 0) + float(amount)
    n_months = max(1, len(months_seen))

    in_receipt: dict[str, dict] = {}
    for item in receipt["items"]:
        product = item["category"]
        group, kind = group_of(product, item.get("group"))
        entry = in_receipt.setdefault(group, {"group": group, "kind": kind, "receipt_eur": 0.0, "items": []})
        entry["receipt_eur"] += item["amount_eur"]
        entry["items"].append({"name": item["name"].title(), "category": product, "amount_eur": item["amount_eur"]})

    groups = []
    for entry in sorted(in_receipt.values(), key=lambda g: -g["receipt_eur"]):
        usual_full = history.get(entry["group"], 0) / n_months
        usual_to_date = round(usual_full * share, 2)
        month_eur = round(month.get(entry["group"], 0), 2)
        groups.append({
            **entry,
            "receipt_eur": round(entry["receipt_eur"], 2),
            "kind_label": KIND_LABELS[entry["kind"]],
            "month_eur": month_eur,
            "usual_eur": usual_to_date,
            "usual_month_eur": round(usual_full, 2),
            "eval": _evaluate(entry["kind"], month_eur, usual_to_date),
        })

    treat_eur = round(sum(g["receipt_eur"] for g in groups if g["kind"] in {"treat", "convenience"}), 2)
    return {
        "receipt_id": receipt_id,
        "merchant": merchant.title(),
        "date": day.isoformat(),
        "time": purchased_at.strftime("%H:%M") if purchased_at else None,
        "total_eur": receipt["total_eur"],
        "item_count": len(receipt["items"]),
        "month_start": month_start.isoformat(), "month_through": through.isoformat(),
        "month_label": f"{month_start:%B} 1–{through.day}" if through < month_end else f"{month_start:%B}",
        "comparison_note": (f"Usual = your average for the same {through.day} days over the previous {n_months} months"
                            if through < month_end else f"Usual = your average month over the previous {n_months} months"),
        "treat_share_pct": round(treat_eur / receipt["total_eur"] * 100) if receipt["total_eur"] else 0,
        "groups": groups,
    }


def month_groups(customer_id: str) -> dict | None:
    """All shopping groups for the latest month so far vs the usual for the same days."""
    with db.connect() as con:
        last_day = con.execute("SELECT max(tx_date) FROM tx WHERE customer_id = ?", [customer_id]).fetchone()[0]
        if last_day is None:
            return None
        month_start, month_end = _month_bounds(last_day)
        rows = con.execute("""
            SELECT t.tx_date, i.product_category, i.category, i.amount_eur
            FROM tx t JOIN s_etukortti_receipt_items i USING (receipt_id)
            WHERE t.customer_id = ? AND t.tx_date BETWEEN ? AND ?
        """, [customer_id, _shift_month(month_start, -3), last_day]).fetchall()
    if not rows:
        return None
    share = last_day.day / month_end.day
    month: dict[str, float] = {}
    history: dict[str, float] = {}
    months_seen = set()
    for tx_date, product, coarse, amount in rows:
        group = group_of(product, coarse)[0]
        if group == "Fuel":
            continue
        if tx_date >= month_start:
            month[group] = month.get(group, 0) + float(amount)
        else:
            months_seen.add((tx_date.year, tx_date.month))
            history[group] = history.get(group, 0) + float(amount)
    n = max(1, len(months_seen))
    names = sorted(set(month) | set(history), key=lambda g: -max(month.get(g, 0), history.get(g, 0) / n * share))
    return {
        "month_label": f"{month_start:%B} 1–{last_day.day}",
        "groups": [{"group": g, "kind": _kind_of_group(g),
                    "month_eur": round(month.get(g, 0), 2), "usual_eur": round(history.get(g, 0) / n * share, 2)}
                   for g in names],
        "note": f"Usual = your average for the same {last_day.day} days over the previous {n} months",
    }


def _kind_of_group(group: str) -> str:
    return next((kind for (name, kind) in _DEFS if name == group), "staple")


RECEIPT_TOOL_SPEC = {
    "type": "function",
    "function": {
        "name": "receipt_insights",
        "description": (
            "Itemised Prisma/S-group receipt for one purchase: every line classified into a product category, "
            "grouped into shopping groups (fruit & veg, dairy, snacks & sweets, household…), with this month's "
            "spend per group, the user's usual amount for the same point in the month, and an evaluation."
        ),
        "parameters": {
            "type": "object",
            "properties": {"receipt_id": {"type": "string"}},
            "required": ["receipt_id"],
        },
    },
}
