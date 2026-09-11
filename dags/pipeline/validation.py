"""Data quality validation.

`validate_input` runs against the raw downloaded CSV, before cleaning.
`validate_loaded_records` runs against PostgreSQL, after loading, and is
implemented alongside the loader in load.py-adjacent work (see that
module for the database-facing half of validation).
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

EXPECTED_COLUMNS = {
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
}


class DataValidationError(Exception):
    """Raised when raw input or loaded data fails a quality check."""


def validate_input(local_path: str) -> None:
    """Sanity-check the raw CSV before spending effort cleaning it.
    Raises DataValidationError on failure so the Airflow task fails fast
    with a clear message rather than propagating a confusing downstream error.
    """
    df = pd.read_csv(local_path)

    if len(df) == 0:
        raise DataValidationError(f"{local_path} contains zero rows")

    missing_columns = EXPECTED_COLUMNS - set(df.columns)
    if missing_columns:
        raise DataValidationError(f"{local_path} is missing expected columns: {sorted(missing_columns)}")

    logger.info("Input validation passed for %s (%d rows)", local_path, len(df))


def validate_loaded_records(expected_min_rows: int, conn=None) -> None:
    """Post-load validation against PostgreSQL: row count sanity, and the
    same value constraints the schema already enforces (belt-and-braces —
    catching a violation here with a clear message beats a raw IntegrityError).
    """
    from pipeline.load import TABLE, get_connection

    owns_conn = conn is None
    conn = conn or get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*) FROM {TABLE}")
            total_rows = cur.fetchone()[0]

            cur.execute(f"SELECT COUNT(*) FROM {TABLE} WHERE quantity < 0 OR unit_price < 0 OR revenue < 0")
            negative_rows = cur.fetchone()[0]

            cur.execute(
                f"SELECT COUNT(*) FROM {TABLE} WHERE transaction_id IS NULL OR transaction_date IS NULL"
            )
            null_required_rows = cur.fetchone()[0]

            cur.execute(
                f"SELECT COUNT(*) FROM (SELECT transaction_id FROM {TABLE} GROUP BY transaction_id HAVING COUNT(*) > 1) d"
            )
            duplicate_ids = cur.fetchone()[0]
    finally:
        if owns_conn:
            conn.close()

    if total_rows < expected_min_rows:
        raise DataValidationError(
            f"{TABLE} has {total_rows} rows, expected at least {expected_min_rows}"
        )
    if negative_rows:
        raise DataValidationError(f"{TABLE} has {negative_rows} row(s) with a negative quantity/price/revenue")
    if null_required_rows:
        raise DataValidationError(f"{TABLE} has {null_required_rows} row(s) with a null required field")
    if duplicate_ids:
        raise DataValidationError(f"{TABLE} has {duplicate_ids} duplicate transaction_id value(s)")

    logger.info("Post-load validation passed: %d rows in %s", total_rows, TABLE)
