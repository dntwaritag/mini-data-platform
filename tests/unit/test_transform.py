import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dags"))

from pipeline.transform import transform  # noqa: E402


def make_clean_df(rows):
    columns = [
        "transaction_id",
        "transaction_date",
        "customer_id",
        "product_id",
        "product_category",
        "quantity",
        "unit_price",
        "region",
        "payment_method",
    ]
    return pd.DataFrame(rows, columns=columns)


def test_revenue_is_recomputed_from_quantity_and_unit_price():
    df = make_clean_df([
        ["T1", "2024-03-15", "C1", "P1", "Electronics", 3, 10.5, "North", "Cash"],
    ])
    result = transform(df)
    assert result.loc[0, "revenue"] == pytest.approx(31.5)


def test_sales_year_and_month_derived_from_date():
    df = make_clean_df([
        ["T1", "2024-11-07", "C1", "P1", "Electronics", 1, 5.0, "North", "Cash"],
    ])
    result = transform(df)
    assert result.loc[0, "sales_year"] == 2024
    assert result.loc[0, "sales_month"] == 11


def test_revenue_never_negative():
    df = make_clean_df([
        ["T1", "2024-01-01", "C1", "P1", "Electronics", 0, 0.0, "North", "Cash"],
    ])
    result = transform(df)
    assert (result["revenue"] >= 0).all()
