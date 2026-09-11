"""Synthetic sales data generator for the Mini Data Platform.

Generates a CSV of synthetic sales transactions. Supports a deterministic
seed for reproducibility, and can optionally inject a configurable
proportion of "dirty" records (missing values, inconsistent capitalization,
whitespace, duplicate transaction IDs, invalid numeric values) so the
downstream Airflow cleaning stage has something real to demonstrate.

Usage:
    python generate_sales.py --rows 1000 --output data/sales.csv
    python generate_sales.py --rows 5000 --seed 42 --dirty-fraction 0.05
"""

from __future__ import annotations

import argparse
import csv
import logging
import random
import uuid
from dataclasses import asdict, dataclass
from datetime import date, timedelta

logger = logging.getLogger(__name__)

PRODUCT_CATEGORIES = [
    "Electronics",
    "Home & Kitchen",
    "Clothing",
    "Sports & Outdoors",
    "Books",
    "Toys & Games",
    "Beauty",
    "Groceries",
]

REGIONS = ["North", "South", "East", "West", "Central"]

PAYMENT_METHODS = ["Credit Card", "Debit Card", "Cash", "Mobile Wallet", "Bank Transfer"]

FIELDNAMES = [
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


@dataclass
class SalesRecord:
    transaction_id: str
    transaction_date: str
    customer_id: str
    product_id: str
    product_category: str
    quantity: int
    unit_price: float
    revenue: float
    region: str
    payment_method: str


def _random_date(rng: random.Random, start: date, end: date) -> date:
    delta_days = (end - start).days
    return start + timedelta(days=rng.randint(0, delta_days))


def _rng_uuid(rng: random.Random) -> str:
    """Generate a UUID4-shaped string from the seeded RNG so output is fully
    reproducible for a given seed (uuid.uuid4() itself is not seedable)."""
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


def generate_clean_record(rng: random.Random, index: int, start_date: date, end_date: date) -> SalesRecord:
    quantity = rng.randint(1, 10)
    unit_price = round(rng.uniform(3.0, 500.0), 2)
    revenue = round(quantity * unit_price, 2)
    return SalesRecord(
        transaction_id=_rng_uuid(rng),
        transaction_date=_random_date(rng, start_date, end_date).isoformat(),
        customer_id=f"CUST-{rng.randint(1, 3000):05d}",
        product_id=f"PROD-{rng.randint(1, 500):04d}",
        product_category=rng.choice(PRODUCT_CATEGORIES),
        quantity=quantity,
        unit_price=unit_price,
        revenue=revenue,
        region=rng.choice(REGIONS),
        payment_method=rng.choice(PAYMENT_METHODS),
    )


def dirty_variant(rng: random.Random, record: SalesRecord, previous_id: str | None) -> dict:
    """Return a dict representation of `record` with one random data-quality
    defect injected, so the Airflow cleaning stage has real work to do."""
    row = asdict(record)
    defect = rng.choice(
        ["missing_value", "bad_capitalization", "whitespace", "duplicate_id", "invalid_numeric"]
    )

    if defect == "missing_value":
        field = rng.choice(["customer_id", "product_category", "region", "payment_method"])
        row[field] = ""
    elif defect == "bad_capitalization":
        field = rng.choice(["product_category", "region", "payment_method"])
        row[field] = row[field].upper() if rng.random() < 0.5 else row[field].lower()
    elif defect == "whitespace":
        field = rng.choice(["product_category", "region", "payment_method", "customer_id"])
        row[field] = f"  {row[field]}  "
    elif defect == "duplicate_id" and previous_id:
        row["transaction_id"] = previous_id
    elif defect == "invalid_numeric":
        field = rng.choice(["quantity", "unit_price"])
        row[field] = rng.choice([-1, "N/A", ""])

    return row


def generate_dataset(
    rows: int,
    seed: int | None,
    dirty_fraction: float,
    start_date: date,
    end_date: date,
) -> list[dict]:
    if rows <= 0:
        raise ValueError("rows must be a positive integer")
    if not (0.0 <= dirty_fraction <= 1.0):
        raise ValueError("dirty_fraction must be between 0.0 and 1.0")

    rng = random.Random(seed)
    records: list[dict] = []
    previous_id: str | None = None

    for i in range(rows):
        record = generate_clean_record(rng, i, start_date, end_date)
        if rng.random() < dirty_fraction:
            row = dirty_variant(rng, record, previous_id)
        else:
            row = asdict(record)
        records.append(row)
        previous_id = row["transaction_id"]

    return records


def write_csv(records: list[dict], output_path: str) -> None:
    import os

    directory = os.path.dirname(output_path)
    if directory:
        os.makedirs(directory, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(records)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate synthetic sales data for the Mini Data Platform.")
    parser.add_argument("--rows", type=int, default=1000, help="Number of rows to generate (default: 1000)")
    parser.add_argument("--output", type=str, default="data/sales.csv", help="Output CSV path")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible output")
    parser.add_argument(
        "--dirty-fraction",
        type=float,
        default=0.03,
        help="Fraction of rows (0.0-1.0) to intentionally corrupt for cleaning demos (default: 0.03)",
    )
    parser.add_argument("--start-date", type=str, default="2024-01-01", help="Earliest transaction date (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, default="2024-12-31", help="Latest transaction date (YYYY-MM-DD)")
    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    start_date = date.fromisoformat(args.start_date)
    end_date = date.fromisoformat(args.end_date)

    records = generate_dataset(
        rows=args.rows,
        seed=args.seed,
        dirty_fraction=args.dirty_fraction,
        start_date=start_date,
        end_date=end_date,
    )
    write_csv(records, args.output)
    logger.info("Wrote %d records to %s (seed=%s, dirty_fraction=%s)", len(records), args.output, args.seed, args.dirty_fraction)


if __name__ == "__main__":
    main()
