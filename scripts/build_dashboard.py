"""Best-effort automated Metabase dashboard build.

Creates the 8 cards (4 KPIs + 4 charts) documented in dashboards/README.md
and assembles them into a "Sales Overview" dashboard, via the Metabase
REST API.

This is intentionally more fragile than scripts/init_metabase.py: Metabase's
card/dashboard-layout API has changed shape across versions, and this script
is written against the API surface of the pinned image
(metabase/metabase:v0.50.8 in docker-compose.yml). If it fails partway
through, the cards it already created are still usable — finish the
dashboard manually in the UI (see dashboards/README.md), or fix and re-run
this script; card creation is idempotent-ish (it does not de-duplicate by
name, so re-running will create duplicate cards — delete the old ones first
if you re-run after a partial failure).

Usage:
    python scripts/build_dashboard.py --metabase-url http://localhost:3000
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

import requests

logger = logging.getLogger(__name__)

DATABASE_NAME = "Sales Analytics (PostgreSQL)"
DASHBOARD_NAME = "Sales Overview"

# (name, sql, display type, visualization_settings)
CARDS = [
    ("Total Revenue", "SELECT SUM(revenue) AS total_revenue FROM analytics.sales", "scalar", {}),
    ("Total Transactions", "SELECT COUNT(*) AS total_transactions FROM analytics.sales", "scalar", {}),
    ("Total Quantity Sold", "SELECT SUM(quantity) AS total_quantity FROM analytics.sales", "scalar", {}),
    (
        "Average Transaction Value",
        "SELECT ROUND(AVG(revenue), 2) AS avg_transaction_value FROM analytics.sales",
        "scalar",
        {},
    ),
    (
        "Revenue Over Time",
        "SELECT transaction_date, SUM(revenue) AS revenue FROM analytics.sales "
        "GROUP BY transaction_date ORDER BY transaction_date",
        "line",
        {"graph.dimensions": ["transaction_date"], "graph.metrics": ["revenue"]},
    ),
    (
        "Revenue by Product Category",
        "SELECT product_category, SUM(revenue) AS revenue FROM analytics.sales "
        "GROUP BY product_category ORDER BY revenue DESC",
        "bar",
        {"graph.dimensions": ["product_category"], "graph.metrics": ["revenue"]},
    ),
    (
        "Revenue by Region",
        "SELECT region, SUM(revenue) AS revenue FROM analytics.sales "
        "GROUP BY region ORDER BY revenue DESC",
        "bar",
        {"graph.dimensions": ["region"], "graph.metrics": ["revenue"]},
    ),
    (
        "Top Products",
        "SELECT product_id, SUM(revenue) AS revenue, SUM(quantity) AS units_sold FROM analytics.sales "
        "GROUP BY product_id ORDER BY revenue DESC LIMIT 10",
        "table",
        {},
    ),
]

# 2-column KPI row, then one chart per row.
LAYOUT = [
    {"row": 0, "col": 0, "size_x": 4, "size_y": 3},
    {"row": 0, "col": 4, "size_x": 4, "size_y": 3},
    {"row": 0, "col": 8, "size_x": 4, "size_y": 3},
    {"row": 0, "col": 12, "size_x": 4, "size_y": 3},
    {"row": 3, "col": 0, "size_x": 16, "size_y": 6},
    {"row": 9, "col": 0, "size_x": 8, "size_y": 6},
    {"row": 9, "col": 8, "size_x": 8, "size_y": 6},
    {"row": 15, "col": 0, "size_x": 16, "size_y": 6},
]


def login(metabase_url: str, email: str, password: str) -> str:
    resp = requests.post(f"{metabase_url}/api/session", json={"username": email, "password": password}, timeout=15)
    resp.raise_for_status()
    return resp.json()["id"]


def get_database_id(metabase_url: str, headers: dict, name: str) -> int:
    resp = requests.get(f"{metabase_url}/api/database", headers=headers, timeout=15)
    resp.raise_for_status()
    databases = resp.json().get("data", resp.json())  # some versions wrap in {"data": [...]}
    for db in databases:
        if db["name"] == name:
            return db["id"]
    raise RuntimeError(f"Database '{name}' not found in Metabase. Run `make init-metabase` first.")


def create_card(metabase_url: str, headers: dict, database_id: int, name: str, sql: str, display: str, viz: dict) -> int:
    payload = {
        "name": name,
        "dataset_query": {
            "type": "native",
            "native": {"query": sql},
            "database": database_id,
        },
        "display": display,
        "visualization_settings": viz,
    }
    resp = requests.post(f"{metabase_url}/api/card", headers=headers, json=payload, timeout=30)
    resp.raise_for_status()
    card_id = resp.json()["id"]
    logger.info("Created card '%s' (id=%s)", name, card_id)
    return card_id


def create_dashboard(metabase_url: str, headers: dict, name: str) -> int:
    resp = requests.post(f"{metabase_url}/api/dashboard", headers=headers, json={"name": name}, timeout=15)
    resp.raise_for_status()
    dashboard_id = resp.json()["id"]
    logger.info("Created dashboard '%s' (id=%s)", name, dashboard_id)
    return dashboard_id


def add_card_to_dashboard(metabase_url: str, headers: dict, dashboard_id: int, card_id: int, layout: dict) -> None:
    payload = {"cardId": card_id, **layout}
    resp = requests.post(f"{metabase_url}/api/dashboard/{dashboard_id}/cards", headers=headers, json=payload, timeout=15)
    resp.raise_for_status()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Best-effort automated Metabase dashboard build.")
    parser.add_argument("--metabase-url", default=os.environ.get("METABASE_URL", "http://localhost:3000"))
    parser.add_argument("--admin-email", default=os.environ.get("METABASE_ADMIN_EMAIL", "admin@example.com"))
    parser.add_argument("--admin-password", default=os.environ.get("METABASE_ADMIN_PASSWORD", "ChangeMe123!"))
    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        session_id = login(args.metabase_url, args.admin_email, args.admin_password)
    except requests.RequestException as exc:
        print(f"Login failed: {exc}\nCheck METABASE_ADMIN_EMAIL/PASSWORD in .env.", file=sys.stderr)
        sys.exit(1)

    headers = {"X-Metabase-Session": session_id}

    try:
        database_id = get_database_id(args.metabase_url, headers, DATABASE_NAME)

        card_ids = []
        for name, sql, display, viz in CARDS:
            card_id = create_card(args.metabase_url, headers, database_id, name, sql, display, viz)
            card_ids.append(card_id)

        dashboard_id = create_dashboard(args.metabase_url, headers, DASHBOARD_NAME)

        for card_id, layout in zip(card_ids, LAYOUT):
            add_card_to_dashboard(args.metabase_url, headers, dashboard_id, card_id, layout)

    except requests.RequestException as exc:
        body = getattr(exc.response, "text", "")[:500] if getattr(exc, "response", None) is not None else ""
        print(
            f"Dashboard build failed partway through: {exc}\n{body}\n"
            "Any cards already created are still usable — finish manually in the UI "
            "(see dashboards/README.md), or fix and re-run (this will create duplicate "
            "cards if some already succeeded — delete those first).",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"Dashboard ready: {args.metabase_url}/dashboard/{dashboard_id}")


if __name__ == "__main__":
    main()
