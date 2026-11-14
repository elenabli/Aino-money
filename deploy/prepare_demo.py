"""Build a cloud demo database using only synthetic bank and receipt data."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import duckdb

from backend.app import config, db, receipts, tools

OUTPUT = ROOT / "deploy" / "data" / "aino-money.duckdb"
CUSTOMERS = ("CUST00001", "CUST02220", "CUST05013")


def main():
    OUTPUT.parent.mkdir(exist_ok=True)
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.unlink(missing_ok=True)
    try:
        with duckdb.connect(str(temporary)) as con:
            con.execute("PRAGMA threads=4")
            # Read the original synthetic exports, with no dependency on the local database.
            db._ingest(con)
            placeholders = ", ".join("?" for _ in CUSTOMERS)
            for table in ("tx", "customers"):
                con.execute(f"DELETE FROM {table} WHERE customer_id NOT IN ({placeholders})", CUSTOMERS)
            con.execute("""
                CREATE TEMP TABLE demo_baskets AS
                SELECT r.receipt_id, (r.tx_date + INTERVAL 2 MONTH)::TIMESTAMP + INTERVAL 17 HOUR AS purchased_at,
                       r.receipt_total_eur, r.food_spend_eur
                FROM read_csv_auto(?) r
                JOIN tx t ON r.customer_id = t.customer_id AND r.tx_timestamp = t.tx_timestamp
                    AND r.merchant_id = t.merchant_id AND r.tx_date = t.tx_date
                    AND r.receipt_total_eur = round(-t.tx_amount_eur, 2)
                WHERE r.synthetic AND r.customer_id = ?
                  AND r.tx_date >= DATE '2025-09-14'
                QUALIFY row_number() OVER (PARTITION BY r.receipt_id ORDER BY t.tx_date) = 1
            """, [str(ROOT / "receipts/prisma_receipts.csv"), receipts.BANK_TEMPLATE_ID])
            con.execute("""
                INSERT INTO s_etukortti_receipts
                SELECT receipt_id, purchased_at, 'Prisma Demo', receipt_total_eur, food_spend_eur
                FROM demo_baskets
            """)
            con.execute("""
                INSERT INTO s_etukortti_receipt_items
                    (receipt_id, line_number, name, amount_eur, category, product_category)
                SELECT i.receipt_id, i.line_number, i.product_name, i.line_total_eur,
                    CASE WHEN i.nutrition_source IS NULL THEN 'Non-food' ELSE 'Food' END,
                    i.category
                FROM read_csv_auto(?) i JOIN demo_baskets b USING (receipt_id)
            """, [str(ROOT / "receipts/prisma_receipt_items.csv")])
            receipts.restore_transactions(con)
            count = con.execute("SELECT count(*) FROM s_etukortti_receipts").fetchone()[0]
            if not count:
                raise RuntimeError("No synthetic receipts matched the source transactions")
        config.DB_PATH = temporary
        tools.build_enriched()
        if not tools.apartment_plan(receipts.CUSTOMER_ID) or not receipts.grocery_insights(receipts.CUSTOMER_ID):
            raise RuntimeError("The synthetic Sofia profile is missing its budget or receipt insights")
        temporary.replace(OUTPUT)
        print(f"Prepared {count} synthetic receipts and four demo profiles")
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
