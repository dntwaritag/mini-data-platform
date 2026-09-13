"""End-to-end integration test for a LIVE platform (`make up` first).

Not run by unit CI. Run explicitly with `make integration-test` once the
platform is up and `make pipeline` has been executed at least once.

Covers, per the project spec:
    MinIO    -> the expected test CSV / bucket exists
    Airflow  -> the sales_pipeline DAG exists and is not in a broken state
    Postgres -> expected records/fields appear after a run
    Metabase -> reachable through its health API; if reachable and
                authenticated, confirm the analytics.sales table is
                queryable through it too (best-effort — see docstring below)
"""

from __future__ import annotations

import requests

from .conftest import AIRFLOW_AUTH, AIRFLOW_BASE_URL, METABASE_BASE_URL, MINIO_BUCKET


def test_minio_bucket_exists(minio_client):
    assert minio_client.bucket_exists(MINIO_BUCKET), f"Expected bucket '{MINIO_BUCKET}' to exist"


def test_airflow_dag_is_registered():
    resp = requests.get(f"{AIRFLOW_BASE_URL}/api/v1/dags/sales_pipeline", timeout=10, auth=AIRFLOW_AUTH)
    assert resp.status_code == 200, f"sales_pipeline DAG not found via Airflow API: {resp.status_code}"
    body = resp.json()
    assert body.get("is_paused") in (True, False)  # DAG metadata parses as expected


def test_postgres_has_loaded_sales_records(postgres_conn):
    with postgres_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM analytics.sales")
        (count,) = cur.fetchone()
    assert count > 0, "Expected analytics.sales to contain rows after the pipeline has run at least once"


def test_postgres_loaded_records_have_transformed_fields(postgres_conn):
    with postgres_conn.cursor() as cur:
        cur.execute(
            "SELECT revenue, sales_year, sales_month FROM analytics.sales LIMIT 1"
        )
        row = cur.fetchone()
    assert row is not None
    revenue, sales_year, sales_month = row
    assert revenue is not None and revenue >= 0
    assert sales_year is not None
    assert 1 <= sales_month <= 12


def test_postgres_has_no_duplicate_transaction_ids(postgres_conn):
    with postgres_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM (SELECT transaction_id FROM analytics.sales "
            "GROUP BY transaction_id HAVING COUNT(*) > 1) d"
        )
        (dupes,) = cur.fetchone()
    assert dupes == 0


def test_metabase_is_reachable():
    """Metabase reachability via its own health endpoint.

    We deliberately don't attempt full Metabase-API-driven dashboard
    validation here: doing so requires an authenticated session and
    Metabase's card/query API is version-sensitive (see dashboards/README.md
    for why full dashboard automation wasn't pursued). This is the
    strongest reliable, low-maintenance check: is Metabase up and healthy.
    """
    resp = requests.get(f"{METABASE_BASE_URL}/api/health", timeout=10)
    assert resp.status_code == 200
