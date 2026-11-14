"""Import S-Etukortti receipts into the local demo database."""
import argparse
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from hashlib import sha256
from html.parser import HTMLParser
from pathlib import Path

from .receipt_categories import product_category

CUSTOMER_ID = "DEMO-SETUKORTTI"
AGE = 35
BANK_TEMPLATE_ID = "CUST02220"
OPENING_BALANCE_EUR = 6000

MONEY = r"-?\d+,\d{2}"
TOTAL = re.compile(rf"^ *\*?YHTEENSÄ(?:: EUR)? +({MONEY})(?: +\*| *)$", re.M | re.I)
ITEM = re.compile(rf"^\*(.+?) +({MONEY}) +\* *$", re.M)
BUNDLE_ITEM = re.compile(rf"^ +\*(.+?)(?: +{MONEY})? +\* *$", re.M)
VAT = re.compile(rf"^ *\d+ +(\d+,\d+)% +{MONEY} +{MONEY} +({MONEY}) *$", re.M)
PURCHASE_TIME = re.compile(r"\b(\d{1,2}\.\d{1,2}\.\d{4}) +(\d{2}[:.]\d{2}(?:\.\d{2})?)\b")

# When several item combinations match the same VAT subtotal, prefer the one
# whose labels describe household goods, personal care, alcohol or deposits.
NON_FOOD_LABEL = re.compile(
    r"PANTTI|NEIPA|\bOLUT\b|\bALE\b|\bIPA\b(?! ALKOHOLITON)|"
    r"KASSI|PUSSI|TALOUSPAPERI|WC-|PESUNESTE|TAHRANPOISTO|KONETISKI|"
    r"WETTEX|LIINA|SUIHKE|SUIHKUGEELI|KONDOMI|VOIDE|KYLPY|SHAMPOO|"
    r"HAMMASTAHNA|HAMMASHARJA|HIUS|HAMMASLANKA|LANKA|PUHDISTUS|"
    r"AKU ANKAN|^AURINGONKUKKA$|HARSOKUKKA|CALLUNA|SUKKAHOUSU|JALKINE|"
    r"LEGO|TÄHTILAIVA|MUOTOILTAVA|PARISTO|\bFOLIO\b|LEIVINPAPERI|"
    r"LAUTANEN|KYNTTILÄ|KISSAN|KOIRAN|VITAMIINI|TUOREKELMU|PYYKINPESUN|"
    r"TALOUSKÄSINE|PYYHEKUMI|TEROITIN|SEOSKAASU|SAIPPUA|HTAHNA|SINITARRA|"
    r"ILMAPALLO|KORISTEHÖYHEN|ASKARTELU|LYIJYKYNÄ|HUOPALAJITELMA|"
    r"STARTTIPAKKAUS|ASTIANPESUAINE|LAASTARI|TERVEYSSIDE",
    re.I,
)


def cents(amount: str) -> int:
    return int(amount.replace(",", ""))


class ReceiptHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks: list[str] = []
        self.lines: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "pre":
            self.lines = []

    def handle_data(self, data):
        if self.lines is not None:
            self.lines.append(data)

    def handle_endtag(self, tag):
        if tag == "pre" and self.lines is not None:
            self.blocks.append("".join(self.lines))
            self.lines = None


@dataclass
class Receipt:
    id: str
    timestamp: datetime
    merchant: str
    total: int
    items: list[tuple[str, int, str]]

    @property
    def food(self) -> int:
        return sum(amount for _, amount, category in self.items if category == "Food")


def classify_items(items: list[tuple[str, int]], non_food: int) -> list[tuple[str, int, str]]:
    # Find the closest label-based classification that reconciles to the cent.
    # Every value stores its score and the indices assigned to Non-food.
    choices: dict[int, tuple[int, tuple[int, ...]]] = {0: (0, ())}
    for index, (name, amount) in enumerate(items):
        score = 1 if NON_FOOD_LABEL.search(name) else -1
        for subtotal, (previous_score, indices) in list(choices.items()):
            new_total = subtotal + amount
            if new_total not in choices or previous_score + score > choices[new_total][0]:
                choices[new_total] = (previous_score + score, (*indices, index))
    if non_food not in choices:
        raise ValueError("Item prices cannot be reconciled to the VAT breakdown")
    selected = set(choices[non_food][1])
    return [(name, amount, "Non-food" if i in selected else "Food")
            for i, (name, amount) in enumerate(items)]


def purchase_lines(text: str) -> list[tuple[str, int]]:
    matches = list(ITEM.finditer(text))
    purchases = []
    for index, match in enumerate(matches):
        name = match[1].strip()
        if name.startswith("TASAERÄ"):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            components = BUNDLE_ITEM.findall(text[match.end():end])
            if components:
                name += " · " + " / ".join(component.strip() for component in components)
        purchases.append((name, cents(match[2])))
    return purchases


def item_category(name: str, group: str) -> str:
    if name.startswith("TASAERÄ"):
        _, _, components = name.partition(" · ")
        categories = {product_category(part, group) for part in components.split(" / ") if part}
        return next(iter(categories)) if len(categories) == 1 else "Mixed promotional bundle"
    return product_category(name, group)


def parse_receipt(block: str) -> Receipt:
    body = block.strip()
    merchant = body.splitlines()[0].strip().strip("*").strip()
    total_match = TOTAL.search(body)
    stamp = PURCHASE_TIME.search(body)
    if total_match is None or stamp is None:
        raise ValueError("Missing receipt date or total")
    time = stamp[2].replace(".", ":")
    timestamp = datetime.strptime(f"{stamp[1]} {time}", "%d.%m.%Y %H:%M" if len(time) == 5 else "%d.%m.%Y %H:%M:%S")
    total = cents(total_match[1])
    if merchant.startswith("ABC "):
        fuel = body[stamp.end():total_match.start()].strip().splitlines()[0]
        items = [(fuel, total, "Non-food")]
    else:
        # Indented lines describe quantities, discounts and components of a
        # bundle. The top-level bundle line already contains the net price.
        purchases = purchase_lines(body[:total_match.start()])
        vat = [(rate, cents(amount)) for rate, amount in VAT.findall(body[total_match.end():])]
        if not purchases or sum(amount for _, amount in purchases) != total or sum(amount for _, amount in vat) != total:
            raise ValueError("Receipt total does not match item prices and VAT breakdown")
        food = sum(amount for rate, amount in vat if rate in {"13,50", "14,00"})
        items = classify_items(purchases, total - food)
    receipt_id = "SE-" + sha256(body.encode()).hexdigest()[:24]
    return Receipt(receipt_id, timestamp, merchant, total, items)


def ensure_tables(con):
    con.execute("""
        CREATE TABLE IF NOT EXISTS s_etukortti_receipts (
            receipt_id VARCHAR PRIMARY KEY, purchased_at TIMESTAMP NOT NULL,
            merchant VARCHAR NOT NULL, total_eur DECIMAL(12, 2) NOT NULL,
            food_eur DECIMAL(12, 2) NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS s_etukortti_receipt_items (
            receipt_id VARCHAR REFERENCES s_etukortti_receipts(receipt_id), line_number INTEGER,
            name VARCHAR NOT NULL, amount_eur DECIMAL(12, 2) NOT NULL,
            category VARCHAR CHECK (category IN ('Food', 'Non-food')),
            PRIMARY KEY (receipt_id, line_number)
        )
    """)
    con.execute("ALTER TABLE s_etukortti_receipt_items ADD COLUMN IF NOT EXISTS product_category VARCHAR")


def restore_transactions(con):
    con.execute("ALTER TABLE tx ADD COLUMN IF NOT EXISTS receipt_id VARCHAR")
    if not con.execute("SELECT count(*) FROM s_etukortti_receipts").fetchone()[0]:
        return
    con.execute("INSERT INTO customers VALUES (?, NULL, ?)", [CUSTOMER_ID, AGE])
    # Align the synthetic bank history with the receipt period. Replace the
    # template's grocery and fuel purchases with the observed receipt charges.
    con.execute("""
        INSERT INTO tx (customer_id, bank_account_id, tx_date, tx_timestamp, category,
            tx_amount_eur, balance_after_eur, transaction_type, merchant_id, mcc_code, flow, receipt_id)
        WITH receipt_period AS (
            SELECT min(purchased_at)::DATE AS first_day, max(purchased_at)::DATE AS last_day
            FROM s_etukortti_receipts
        ), bank AS (
            SELECT (tx_date + INTERVAL 2 MONTH)::DATE AS day, tx_timestamp,
                category, tx_amount_eur::DECIMAL(12, 2) AS amount, transaction_type,
                merchant_id, mcc_code, flow
            FROM tx
            WHERE customer_id = ? AND category IS DISTINCT FROM 'Groceries'
                AND (mcc_code IS NULL OR mcc_code NOT IN (5541, 5542))
        ), combined AS (
            SELECT day, strftime(day, '%Y-%m-%d') || 'T' || right(tx_timestamp, 8) AS stamp,
                category, amount, transaction_type, merchant_id, mcc_code, flow, NULL::VARCHAR AS receipt_id
            FROM bank, receipt_period WHERE day BETWEEN first_day AND last_day
            UNION ALL
            SELECT purchased_at::DATE, strftime(purchased_at, '%Y-%m-%dT%H:%M:%S'),
                CASE WHEN upper(merchant) LIKE 'ABC %' THEN 'Transportation'
                     WHEN upper(merchant) LIKE 'SOKOS %' THEN 'Lifestyle'
                     ELSE 'Groceries' END,
                -total_eur, 'purchase', merchant, NULL, 'expense', receipt_id
            FROM s_etukortti_receipts
        )
        SELECT ?, 'DEMO-SETUKORTTI-ACCOUNT', day, stamp, category, amount,
            ? + sum(amount) OVER (
                ORDER BY day, stamp, receipt_id, category, amount, merchant_id ROWS UNBOUNDED PRECEDING
            ), transaction_type, merchant_id, mcc_code, flow, receipt_id
        FROM combined
    """, [BANK_TEMPLATE_ID, CUSTOMER_ID, OPENING_BALANCE_EUR])


def import_html(path: Path):
    from . import db, tools

    parser = ReceiptHTML()
    parser.feed(path.read_text(encoding="utf-8-sig"))
    parser.close()
    if not parser.blocks:
        raise ValueError("No receipt blocks found")
    receipts = {}
    for index, block in enumerate(parser.blocks, 1):
        try:
            receipt = parse_receipt(block)
        except ValueError as exc:
            raise ValueError(f"Receipt {index}: {exc}") from exc
        receipts[receipt.id] = receipt

    with db.connect() as con:
        con.begin()
        ensure_tables(con)
        # Keep earlier receipts when importing another export with overlap.
        known = {row[0] for row in con.execute("SELECT receipt_id FROM s_etukortti_receipts").fetchall()}
        for receipt in receipts.values():
            if receipt.id not in known:
                con.execute("INSERT INTO s_etukortti_receipts VALUES (?, ?, ?, ?, ?)", [
                    receipt.id, receipt.timestamp, receipt.merchant, receipt.total / 100, receipt.food / 100,
                ])
            con.executemany("""
                INSERT INTO s_etukortti_receipt_items
                    (receipt_id, line_number, name, amount_eur, category, product_category)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT (receipt_id, line_number) DO UPDATE SET
                    name = excluded.name, amount_eur = excluded.amount_eur, category = excluded.category,
                    product_category = excluded.product_category
            """, [
                (receipt.id, index, name, amount / 100, category, item_category(name, category))
                for index, (name, amount, category) in enumerate(receipt.items, 1)
            ])
        con.execute("DELETE FROM customers WHERE customer_id = ?", [CUSTOMER_ID])
        con.execute("DELETE FROM tx WHERE customer_id = ?", [CUSTOMER_ID])
        restore_transactions(con)
        con.execute("ALTER TABLE tx_enriched ADD COLUMN IF NOT EXISTS receipt_id VARCHAR")
        con.execute("DELETE FROM tx_enriched WHERE customer_id = ? AND simulated = 0", [CUSTOMER_ID])
        tools.enrich_receipt_customer(con)
        con.commit()
    print(f"Imported {len(receipts) - len(receipts.keys() & known)} new receipts ({len(receipts)} in export)")


def grocery_insights(customer_id: str, start: str | None = None, end: str | None = None) -> dict | None:
    from . import db

    if customer_id != CUSTOMER_ID:
        return None
    with db.connect() as con:
        bounds = con.execute("""
            SELECT min(tx_date), max(tx_date) FROM tx
            WHERE customer_id = ? AND category = 'Groceries'
        """, [customer_id]).fetchone()
        if bounds[1] is None:
            return None
        last_day = date.fromisoformat(end) if end else bounds[1]
        first_day = date.fromisoformat(start) if start else max(bounds[0], last_day - timedelta(days=83))
        if first_day > last_day:
            return None

        where = "t.customer_id = ? AND t.category = 'Groceries' AND t.tx_date BETWEEN ? AND ?"
        args = [customer_id, first_day, last_day]
        visits, days, total, small_visits, small_total = con.execute(f"""
            SELECT count(*), count(DISTINCT t.tx_date), coalesce(sum(r.total_eur), 0),
                count(*) FILTER (WHERE r.total_eur <= 20),
                coalesce(sum(r.total_eur) FILTER (WHERE r.total_eur <= 20), 0)
            FROM tx t JOIN s_etukortti_receipts r USING (receipt_id)
            WHERE {where}
        """, args).fetchone()
        if not visits:
            return None

        rows = con.execute(f"""
            SELECT i.product_category, sum(i.amount_eur), count(DISTINCT t.receipt_id),
                coalesce(sum(i.amount_eur) FILTER (WHERE r.total_eur <= 20), 0)
            FROM tx t JOIN s_etukortti_receipts r USING (receipt_id)
            JOIN s_etukortti_receipt_items i USING (receipt_id)
            WHERE {where}
            GROUP BY 1 ORDER BY 2 DESC, 1
        """, args).fetchall()

    categories = [
        {"name": name, "spent_eur": float(spent), "visits": count, "on_small_trips_eur": float(small_spent)}
        for name, spent, count, small_spent in rows
    ]
    treat_names = {
        "Snacks & sweets",
        "Chocolate", "Candy and liquorice", "Ice cream and ice pops", "Biscuits and wafers",
        "Crisps and popcorn", "Cakes and sweet pastries", "Soft drinks", "Energy and sports drinks",
    }
    treat = next((category for category in categories if category["name"] in treat_names), None)
    return {
        "start": first_day.isoformat(),
        "end": last_day.isoformat(),
        "visits": visits,
        "shopping_days": days,
        "trips_per_week": round(visits * 7 / ((last_day - first_day).days + 1), 1),
        "total_eur": float(total),
        "small_trips": small_visits,
        "small_trip_total_eur": float(small_total),
        "categories": categories,
        "experiment": {
            "category": treat["name"],
            "baseline_eur": treat["spent_eur"],
            "target_eur": round(treat["spent_eur"] * 0.8, 2),
            "savings_eur": round(treat["spent_eur"] * 0.2, 2),
        } if treat else None,
    }


def details(receipt_id: str, customer_id: str):
    from . import db

    if customer_id != CUSTOMER_ID:
        return None
    with db.connect() as con:
        if not con.execute("SELECT 1 FROM customers WHERE customer_id = ?", [customer_id]).fetchone():
            return None
        receipt = con.execute("""
            SELECT r.total_eur, r.food_eur, r.total_eur - r.food_eur
            FROM s_etukortti_receipts r JOIN tx t USING (receipt_id)
            WHERE t.customer_id = ? AND r.receipt_id = ?
        """, [customer_id, receipt_id]).fetchone()
        if receipt is None:
            return None
        items = con.execute("""
            SELECT * EXCLUDE (receipt_id, line_number)
            FROM s_etukortti_receipt_items WHERE receipt_id = ? ORDER BY line_number
        """, [receipt_id]).fetchall()
    lines = []
    totals = {}
    for name, amount, group, *stored_category in items:
        category = (stored_category and stored_category[0]) or item_category(name, group)
        lines.append({"name": name, "amount_eur": float(amount), "category": category, "group": group})
        totals[category] = totals.get(category, 0) + amount
    return {
        "total_eur": float(receipt[0]),
        "food_eur": float(receipt[1]),
        "non_food_eur": float(receipt[2]),
        "items": lines,
        "categories": [{"name": name, "amount_eur": float(amount)}
                       for name, amount in sorted(totals.items(), key=lambda entry: (-entry[1], entry[0]))],
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("html", type=Path)
    import_html(parser.parse_args().html)
