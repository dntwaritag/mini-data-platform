import csv
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "data_generator"))

from generate_sales import FIELDNAMES, generate_dataset, write_csv  # noqa: E402


def test_generate_dataset_row_count():
    records = generate_dataset(rows=200, seed=1, dirty_fraction=0.0, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    assert len(records) == 200


def test_generate_dataset_is_deterministic_with_seed():
    a = generate_dataset(rows=50, seed=42, dirty_fraction=0.1, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    b = generate_dataset(rows=50, seed=42, dirty_fraction=0.1, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    assert a == b


def test_generate_dataset_varies_without_fixed_seed_context():
    # Different seeds should (overwhelmingly likely) produce different data.
    a = generate_dataset(rows=50, seed=1, dirty_fraction=0.0, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    b = generate_dataset(rows=50, seed=2, dirty_fraction=0.0, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    assert a != b


def test_clean_dataset_has_valid_types_and_values():
    records = generate_dataset(rows=300, seed=7, dirty_fraction=0.0, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    for row in records:
        assert row["quantity"] >= 1
        assert row["unit_price"] > 0
        assert abs(row["revenue"] - round(row["quantity"] * row["unit_price"], 2)) < 0.01
        assert row["region"] in {"North", "South", "East", "West", "Central"}


def test_dirty_fraction_zero_produces_no_known_defects():
    records = generate_dataset(rows=500, seed=3, dirty_fraction=0.0, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    ids = [r["transaction_id"] for r in records]
    assert len(ids) == len(set(ids))  # no duplicates
    for row in records:
        assert row["customer_id"] != ""
        assert isinstance(row["quantity"], int)


def test_dirty_fraction_introduces_defects():
    records = generate_dataset(rows=2000, seed=11, dirty_fraction=0.5, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    has_blank = any(v == "" for r in records for v in r.values())
    has_duplicate = len({r["transaction_id"] for r in records}) < len(records)
    has_whitespace = any(isinstance(v, str) and v != v.strip() and v.strip() != "" for r in records for v in r.values())
    # With a 50% dirty fraction over 2000 rows, at least one of these defect
    # categories must appear (randomized defect choice per dirty row).
    assert has_blank or has_duplicate or has_whitespace


def test_invalid_rows_raise():
    import pytest

    with pytest.raises(ValueError):
        generate_dataset(rows=0, seed=1, dirty_fraction=0.0, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    with pytest.raises(ValueError):
        generate_dataset(rows=10, seed=1, dirty_fraction=1.5, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))


def test_write_csv_round_trip(tmp_path):
    records = generate_dataset(rows=25, seed=5, dirty_fraction=0.0, start_date=date(2024, 1, 1), end_date=date(2024, 12, 31))
    out_file = tmp_path / "out" / "sales.csv"
    write_csv(records, str(out_file))

    assert out_file.exists()
    with open(out_file, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == FIELDNAMES
        rows = list(reader)
    assert len(rows) == 25
