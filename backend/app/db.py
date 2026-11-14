import duckdb

from . import config


def connect() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(config.DB_PATH))
    con.execute("PRAGMA threads=4")
    return con


def ensure_app_tables(con: duckdb.DuckDBPyConnection | None = None) -> None:
    own = con is None
    if own:
        con = connect()
    con.execute("""
        CREATE TABLE IF NOT EXISTS goals (
            customer_id VARCHAR PRIMARY KEY,
            name VARCHAR,
            target_eur DOUBLE,
            months INTEGER,
            weekly_eur DOUBLE,
            safe_to_save_monthly DOUBLE,
            created_at DATE
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS challenges (
            id INTEGER PRIMARY KEY,
            customer_id VARCHAR,
            kind VARCHAR,
            category VARCHAR,
            pct DOUBLE,
            baseline_daily DOUBLE,
            target_daily DOUBLE,
            start_date DATE,
            end_date DATE,
            status VARCHAR,
            created_at DATE
        )
    """)
    con.execute("CREATE SEQUENCE IF NOT EXISTS challenge_seq START 1")
    if own:
        con.close()


def ingest() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = connect()
    con.execute(f"""
        CREATE OR REPLACE TABLE tx AS
        SELECT
            customer_id,
            bank_account_id,
            CAST(tx_date AS DATE) AS tx_date,
            tx_timestamp,
            category,
            tx_amount_eur,
            balance_after_eur,
            transaction_type,
            merchant_id,
            mcc_code,
            CASE WHEN tx_amount_eur > 0 THEN 'income' ELSE 'expense' END AS flow
        FROM read_csv_auto('{config.TX_PATH}', header=true)
    """)
    con.execute(f"""
        CREATE OR REPLACE TABLE customers AS
        SELECT customer_id, customer_postal_code, customer_age
        FROM read_csv_auto('{config.CUSTOMERS_PATH}', header=true)
    """)
    con.execute("""
        CREATE OR REPLACE TABLE merchants AS
        SELECT
            merchant_id,
            any_value(category) AS category,
            any_value(mcc_code) AS mcc_code,
            count(*) AS tx_count,
            round(avg(tx_amount_eur), 2) AS avg_amount,
            round(median(tx_amount_eur), 2) AS median_amount,
            min(tx_amount_eur) AS min_amount,
            max(tx_amount_eur) AS max_amount
        FROM tx
        WHERE merchant_id IS NOT NULL AND merchant_id != ''
        GROUP BY merchant_id
    """)
    con.execute("""
        CREATE OR REPLACE TABLE merchant_classification (
            merchant_id VARCHAR PRIMARY KEY,
            basket VARCHAR,
            is_subscription FLOAT,
            irregular_risk FLOAT,
            confidence FLOAT,
            source VARCHAR
        )
    """)
    ensure_app_tables(con)
    n = con.execute("SELECT count(*) FROM tx").fetchone()[0]
    m = con.execute("SELECT count(*) FROM merchants").fetchone()[0]
    c = con.execute("SELECT count(*) FROM customers").fetchone()[0]
    con.close()
    print(f"ingested: {n:,} tx rows, {m} merchants, {c} customers -> {config.DB_PATH}")
