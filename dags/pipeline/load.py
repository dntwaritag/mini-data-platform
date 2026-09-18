"""Load transformed sales data into PostgreSQL.

Uses an UPSERT (INSERT ... ON CONFLICT (transaction_id) DO UPDATE) so
re-running the DAG for a file that was already (partially) loaded is safe
and idempotent, matching the transaction_id UNIQUE constraint in
config/postgres/init.sql.
"""

from __future__ import annotations

import logging
import os

import pandas as pd
import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

TABLE = "analytics.sales"

COLUMNS = [
    "transaction_id",
    "transaction_date",
    "customer_id",
    "product_id",
    "product_category",
    "quantity",
    "unit_price",
    "revenue",
    "region",
    "payment_method",
    "sales_year",
    "sales_month",
]

UPSERT_SQL = f"""
    INSERT INTO {TABLE} ({", ".join(COLUMNS)})
    VALUES %s
    ON CONFLICT (transaction_id) DO UPDATE SET
        transaction_date = EXCLUDED.transaction_date,
        customer_id = EXCLUDED.customer_id,
        product_id = EXCLUDED.product_id,
        product_category = EXCLUDED.product_category,
        quantity = EXCLUDED.quantity,
        unit_price = EXCLUDED.unit_price,
        revenue = EXCLUDED.revenue,
        region = EXCLUDED.region,
        payment_method = EXCLUDED.payment_method,
        sales_year = EXCLUDED.sales_year,
        sales_month = EXCLUDED.sales_month
"""


def get_connection():
    return psycopg2.connect(
        host=os.environ.get("ANALYTICS_DB_HOST", "postgres"),
        dbname=os.environ.get("ANALYTICS_DB_NAME", "mini_data_platform"),
        user=os.environ.get("ANALYTICS_DB_USER", "platform_user"),
        password=os.environ.get("ANALYTICS_DB_PASSWORD", "platform_pass"),
        port=os.environ.get("ANALYTICS_DB_PORT", "5432"),
    )


def load_records(records: list[tuple], conn=None) -> int:
    """Pure-ish loading function: given a connection and a list of row
    tuples (in COLUMNS order), upsert them and return the row count."""
    owns_conn = conn is None
    conn = conn or get_connection()
    try:
        with conn.cursor() as cur:
            # page_size default is 100, meaning 500k rows would be 5,000
            # separate round-trips to Postgres — bump it so large batches
            # (demo runs with ROWS=500000 etc.) load in a handful of
            # multi-thousand-row statements instead.
            psycopg2.extras.execute_values(cur, UPSERT_SQL, records, page_size=5000)
        conn.commit()
        return len(records)
    finally:
        if owns_conn:
            conn.close()


def load_dataframe(transformed_path: str, conn=None) -> int:
    """I/O wrapper used by the Airflow task: read the transformed CSV and
    load it into PostgreSQL. Returns the number of rows loaded."""
    df = pd.read_csv(transformed_path)
    records = list(df[COLUMNS].itertuples(index=False, name=None))

    row_count = load_records(records, conn=conn)
    logger.info("Loaded %d rows into %s", row_count, TABLE)
    return row_count
