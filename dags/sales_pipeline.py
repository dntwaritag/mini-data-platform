"""Mini Data Platform — sales pipeline DAG.

    Check for new MinIO file -> Download raw CSV -> Validate input
        -> Clean data -> Transform data -> Load PostgreSQL
        -> Validate loaded records

Implemented with the TaskFlow API. The actual stage logic lives in
`dags/pipeline/` so it can be unit tested without a running Airflow
instance; this module only wires the tasks together and owns retries,
scheduling, and dependencies.
"""

from __future__ import annotations

import logging
from datetime import timedelta

import pendulum
from airflow.decorators import dag, task
from airflow.exceptions import AirflowSkipException

logger = logging.getLogger(__name__)

DEFAULT_ARGS = {
    "owner": "data-platform",
    "retries": 3,
    "retry_delay": timedelta(minutes=2),
}


@dag(
    dag_id="sales_pipeline",
    description="Ingest raw sales CSVs from MinIO, clean/transform them, and load into PostgreSQL.",
    schedule="@daily",
    start_date=pendulum.datetime(2024, 1, 1, tz="UTC"),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["sales", "mini-data-platform"],
)
def sales_pipeline():
    from pipeline.cleaning import clean_dataframe
    from pipeline.ingestion import NoNewFileFound, detect_new_files, download_file, mark_processed
    from pipeline.load import load_dataframe
    from pipeline.transform import transform_dataframe
    from pipeline.validation import validate_input, validate_loaded_records

    @task
    def check_for_new_file() -> str:
        """Return the object key of the next unprocessed CSV in MinIO, or
        skip the rest of the DAG run if there is nothing new to process."""
        try:
            return detect_new_files()
        except NoNewFileFound as exc:
            logger.info(str(exc))
            raise AirflowSkipException(str(exc)) from exc

    @task
    def download_raw_csv(object_key: str) -> str:
        return download_file(object_key)

    @task
    def validate_raw_input(local_path: str) -> str:
        validate_input(local_path)
        return local_path

    @task
    def clean(local_path: str) -> str:
        return clean_dataframe(local_path)

    @task
    def transform(cleaned_path: str) -> str:
        return transform_dataframe(cleaned_path)

    @task
    def load(transformed_path: str) -> int:
        return load_dataframe(transformed_path)

    @task
    def validate_load(row_count: int) -> None:
        validate_loaded_records(expected_min_rows=row_count)

    @task
    def finalize(object_key: str, _validated: None) -> None:
        # Move the object to processed/ only after the load has been
        # validated, so a failed run leaves the file in incoming/ for retry.
        mark_processed(object_key)

    object_key = check_for_new_file()
    raw_path = download_raw_csv(object_key)
    validated_raw_path = validate_raw_input(raw_path)
    cleaned_path = clean(validated_raw_path)
    transformed_path = transform(cleaned_path)
    row_count = load(transformed_path)
    validated = validate_load(row_count)
    finalize(object_key, validated)


sales_pipeline()
