import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dags"))

from pipeline.validation import DataValidationError, validate_input  # noqa: E402

COLUMNS = [
    "transaction_id", "transaction_date", "customer_id", "product_id",
    "product_category", "quantity", "unit_price", "revenue", "region", "payment_method",
]


def test_validate_input_passes_for_well_formed_csv(tmp_path):
    df = pd.DataFrame([["T1", "2024-01-01", "C1", "P1", "Electronics", 1, 1.0, 1.0, "North", "Cash"]], columns=COLUMNS)
    path = tmp_path / "ok.csv"
    df.to_csv(path, index=False)

    validate_input(str(path))  # should not raise


def test_validate_input_rejects_empty_file(tmp_path):
    df = pd.DataFrame([], columns=COLUMNS)
    path = tmp_path / "empty.csv"
    df.to_csv(path, index=False)

    with pytest.raises(DataValidationError):
        validate_input(str(path))


def test_validate_input_rejects_missing_columns(tmp_path):
    df = pd.DataFrame([["T1", "2024-01-01"]], columns=["transaction_id", "transaction_date"])
    path = tmp_path / "incomplete.csv"
    df.to_csv(path, index=False)

    with pytest.raises(DataValidationError):
        validate_input(str(path))
