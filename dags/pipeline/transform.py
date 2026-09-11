"""Derived-field transformation for cleaned sales data.

Adds:
    revenue      = quantity * unit_price (recomputed here rather than
                   trusted from the source, so it can never drift from the
                   other two fields)
    sales_year   = calendar year of transaction_date
    sales_month  = calendar month (1-12) of transaction_date
"""

from __future__ import annotations

import logging

import pandas as pd

logger = logging.getLogger(__name__)


def transform(df: pd.DataFrame) -> pd.DataFrame:
    """Pure transform function: cleaned DataFrame in, transformed DataFrame out."""
    df = df.copy()

    df["transaction_date"] = pd.to_datetime(df["transaction_date"])
    df["revenue"] = (df["quantity"] * df["unit_price"]).round(2)
    df["sales_year"] = df["transaction_date"].dt.year
    df["sales_month"] = df["transaction_date"].dt.month

    assert (df["revenue"] >= 0).all(), "revenue must be non-negative after transformation"

    return df


def transform_dataframe(cleaned_path: str, output_path: str | None = None) -> str:
    """I/O wrapper used by the Airflow task."""
    df = pd.read_csv(cleaned_path)
    transformed = transform(df)

    output_path = output_path or cleaned_path.replace("_cleaned.csv", "_transformed.csv")
    transformed.to_csv(output_path, index=False)
    logger.info("Wrote %d transformed rows to %s", len(transformed), output_path)
    return output_path
