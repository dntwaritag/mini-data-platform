"""Drive one full pipeline run against a LIVE platform and validate it.

Intended for `make pipeline` follow-up validation and for the CI
integration-test job (which brings the stack up in a runner first). Not
runnable in an environment without a live Docker Compose stack — see
README "Limitations" for where this was and wasn't exercised.

Steps:
    1. Wait for Postgres, MinIO, Airflow, and Metabase health endpoints.
    2. Generate a small synthetic dataset and upload it to MinIO.
    3. Unpause and trigger the sales_pipeline DAG via the Airflow REST API.
    4. Poll until the DAG run finishes (success or failure).
    5. Run tests/integration/test_end_to_end.py via pytest.
"""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path

import psycopg2
import requests
from minio import Minio

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data_generator"))

logger = logging.getLogger(__name__)

AIRFLOW_URL = "http://localhost:8080"
METABASE_URL = "http://localhost:3000"
MINIO_ENDPOINT = "localhost:9000"
POSTGRES_DSN = dict(host="localhost", port=5432, dbname="mini_data_platform", user="platform_user", password="platform_pass")

POLL_INTERVAL_SECONDS = 5
TIMEOUT_SECONDS = 300


def wait_for(name: str, check_fn, timeout: int = TIMEOUT_SECONDS) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if check_fn():
                logger.info("%s is ready", name)
                return
        except Exception as exc:  # noqa: BLE001 - broad on purpose while polling
            logger.debug("%s not ready yet: %s", name, exc)
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError(f"{name} did not become ready within {timeout}s")


def wait_for_services() -> None:
    wait_for("PostgreSQL", lambda: psycopg2.connect(**POSTGRES_DSN, connect_timeout=3).close() or True)
    wait_for("MinIO", lambda: Minio(MINIO_ENDPOINT, access_key="minio_admin", secret_key="minio_password", secure=False).list_buckets() is not None)
    wait_for("Airflow", lambda: requests.get(f"{AIRFLOW_URL}/health", timeout=5).status_code == 200)
    wait_for("Metabase", lambda: requests.get(f"{METABASE_URL}/api/health", timeout=5).status_code == 200)


def generate_and_upload() -> None:
    subprocess.run(
        [sys.executable, "data_generator/generate_sales.py", "--rows", "200", "--seed", "99", "--output", "data/pipeline_test_sales.csv"],
        check=True,
    )
    subprocess.run(
        [sys.executable, "scripts/init_minio.py", "--file", "data/pipeline_test_sales.csv", "--endpoint", MINIO_ENDPOINT],
        check=True,
    )


def trigger_dag(auth=("admin", "admin")) -> str:
    requests.patch(f"{AIRFLOW_URL}/api/v1/dags/sales_pipeline", json={"is_paused": False}, auth=auth, timeout=10)
    resp = requests.post(f"{AIRFLOW_URL}/api/v1/dags/sales_pipeline/dagRuns", json={}, auth=auth, timeout=10)
    resp.raise_for_status()
    return resp.json()["dag_run_id"]


def wait_for_dag_run(dag_run_id: str, auth=("admin", "admin")) -> str:
    deadline = time.time() + TIMEOUT_SECONDS
    while time.time() < deadline:
        resp = requests.get(
            f"{AIRFLOW_URL}/api/v1/dags/sales_pipeline/dagRuns/{dag_run_id}", auth=auth, timeout=10
        )
        resp.raise_for_status()
        state = resp.json()["state"]
        if state in ("success", "failed"):
            return state
        time.sleep(POLL_INTERVAL_SECONDS)
    raise TimeoutError("DAG run did not finish in time")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    logger.info("Waiting for services to be healthy...")
    wait_for_services()

    logger.info("Generating and uploading test data...")
    generate_and_upload()

    logger.info("Triggering sales_pipeline DAG...")
    dag_run_id = trigger_dag()

    logger.info("Waiting for DAG run %s to finish...", dag_run_id)
    state = wait_for_dag_run(dag_run_id)
    if state != "success":
        logger.error("DAG run finished with state=%s", state)
        sys.exit(1)

    logger.info("Pipeline run succeeded — running integration test suite...")
    result = subprocess.run([sys.executable, "-m", "pytest", "tests/integration", "-v"])
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
