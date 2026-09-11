"""Data cleaning for raw sales CSVs.

Business rules (also documented in the README "Data quality rules" section):

Required fields — a row is DROPPED if any of these are missing or invalid
after coercion, since the record cannot be trusted or reliably loaded:
    transaction_id, transaction_date, customer_id, product_id,
    quantity (must coerce to an int >= 1), unit_price (must coerce to a
    float >= 0)

Optional categorical fields — a row is KEPT and the value is replaced with
"Unknown" if missing, since these don't invalidate the transaction itself:
    product_category, region, payment_method

Other rules:
    * String fields are trimmed of leading/trailing whitespace.
    * Categorical string fields are normalized to Title Case so
      "ELECTRONICS", "electronics", " Electronics " all collapse to the
      same value.
    * Duplicate transaction_id values are de-duplicated, keeping the first
      occurrence, since a transaction_id should be unique by definition.
    * Dates that don't parse are treated as invalid and the row is dropped.
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = ["transaction_id", "transaction_date", "customer_id", "product_id"]
CATEGORICAL_FIELDS = ["product_category", "region", "payment_method"]
STRING_FIELDS = ["transaction_id", "customer_id", "product_id", *CATEGORICAL_FIELDS]


def _strip_strings(df: pd.DataFrame) -> pd.DataFrame:
    for col in STRING_FIELDS:
        if col in df.columns:
            df[col] = df[col].astype("string").str.strip()
    return df


def _normalize_categoricals(df: pd.DataFrame) -> pd.DataFrame:
    for col in CATEGORICAL_FIELDS:
        if col in df.columns:
            df[col] = df[col].str.title()
            df[col] = df[col].replace({"": pd.NA, "Nan": pd.NA}).fillna("Unknown")
    return df


def _coerce_numeric(df: pd.DataFrame) -> pd.DataFrame:
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["unit_price"] = pd.to_numeric(df["unit_price"], errors="coerce")
    return df


def _parse_dates(df: pd.DataFrame) -> pd.DataFrame:
    df["transaction_date"] = pd.to_datetime(df["transaction_date"], errors="coerce", format="mixed")
    return df


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Pure cleaning function: DataFrame in, cleaned DataFrame out."""
    df = df.copy()

    df = _strip_strings(df)
    df = _normalize_categoricals(df)
    df = _coerce_numeric(df)
    df = _parse_dates(df)

    # Replace empty-string required fields with NA so dropna catches them.
    for col in REQUIRED_FIELDS:
        if col in df.columns and df[col].dtype == "string":
            df[col] = df[col].replace("", pd.NA)

    before = len(df)
    df = df.dropna(subset=[*REQUIRED_FIELDS, "quantity", "unit_price"])
    df = df[(df["quantity"] >= 1) & (df["unit_price"] >= 0)]
    dropped_invalid = before - len(df)
    if dropped_invalid:
        logger.info("Dropped %d row(s) with missing/invalid required fields", dropped_invalid)

    before_dedupe = len(df)
    df = df.drop_duplicates(subset=["transaction_id"], keep="first")
    dropped_dupes = before_dedupe - len(df)
    if dropped_dupes:
        logger.info("Dropped %d duplicate transaction_id row(s)", dropped_dupes)

    df["quantity"] = df["quantity"].astype(int)
    df["unit_price"] = df["unit_price"].astype(float).round(2)

    return df.reset_index(drop=True)


def clean_dataframe(local_path: str, output_path: str | None = None) -> str:
    """I/O wrapper used by the Airflow task: read `local_path`, clean it,
    write the result, and return the output path."""
    df = pd.read_csv(local_path)
    cleaned = clean(df)

    output_path = output_path or local_path.replace(".csv", "_cleaned.csv")
    cleaned.to_csv(output_path, index=False)
    logger.info("Wrote %d cleaned rows to %s", len(cleaned), output_path)
    return output_path
