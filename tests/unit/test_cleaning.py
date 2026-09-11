import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dags"))

from pipeline.cleaning import clean  # noqa: E402


def make_df(rows):
    columns = [
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
    ]
    return pd.DataFrame(rows, columns=columns)


def test_trims_whitespace():
    df = make_df([
        ["T1", "2024-01-01", "  C1  ", "P1", "Electronics", 2, 10.0, 20.0, "North", "Cash"],
    ])
    result = clean(df)
    assert result.loc[0, "customer_id"] == "C1"


def test_normalizes_capitalization():
    df = make_df([
        ["T1", "2024-01-01", "C1", "P1", "ELECTRONICS", 2, 10.0, 20.0, "north", "cash"],
    ])
    result = clean(df)
    assert result.loc[0, "product_category"] == "Electronics"
    assert result.loc[0, "region"] == "North"
    assert result.loc[0, "payment_method"] == "Cash"


def test_missing_categorical_becomes_unknown():
    df = make_df([
        ["T1", "2024-01-01", "C1", "P1", "", 2, 10.0, 20.0, "North", "Cash"],
    ])
    result = clean(df)
    assert result.loc[0, "product_category"] == "Unknown"


def test_drops_row_missing_required_field():
    df = make_df([
        ["T1", "2024-01-01", "", "P1", "Electronics", 2, 10.0, 20.0, "North", "Cash"],  # missing customer_id
        ["T2", "2024-01-01", "C2", "P2", "Electronics", 2, 10.0, 20.0, "North", "Cash"],
    ])
    result = clean(df)
    assert len(result) == 1
    assert result.loc[0, "transaction_id"] == "T2"


def test_drops_row_with_invalid_numeric():
    df = make_df([
        ["T1", "2024-01-01", "C1", "P1", "Electronics", "N/A", 10.0, 20.0, "North", "Cash"],
        ["T2", "2024-01-01", "C2", "P2", "Electronics", 2, 10.0, 20.0, "North", "Cash"],
    ])
    result = clean(df)
    assert len(result) == 1
    assert result.loc[0, "transaction_id"] == "T2"


def test_drops_negative_quantity():
    df = make_df([
        ["T1", "2024-01-01", "C1", "P1", "Electronics", -3, 10.0, 20.0, "North", "Cash"],
        ["T2", "2024-01-01", "C2", "P2", "Electronics", 2, 10.0, 20.0, "North", "Cash"],
    ])
    result = clean(df)
    assert len(result) == 1
    assert result.loc[0, "transaction_id"] == "T2"


def test_deduplicates_transaction_id_keeping_first():
    df = make_df([
        ["T1", "2024-01-01", "C1", "P1", "Electronics", 2, 10.0, 20.0, "North", "Cash"],
        ["T1", "2024-02-01", "C2", "P2", "Books", 5, 3.0, 15.0, "South", "Cash"],
    ])
    result = clean(df)
    assert len(result) == 1
    assert result.loc[0, "customer_id"] == "C1"


def test_drops_row_with_invalid_date():
    df = make_df([
        ["T1", "not-a-date", "C1", "P1", "Electronics", 2, 10.0, 20.0, "North", "Cash"],
        ["T2", "2024-01-01", "C2", "P2", "Electronics", 2, 10.0, 20.0, "North", "Cash"],
    ])
    result = clean(df)
    assert len(result) == 1
    assert result.loc[0, "transaction_id"] == "T2"
