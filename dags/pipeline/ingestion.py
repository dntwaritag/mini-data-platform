"""MinIO ingestion logic for the sales pipeline.

Convention used in the `raw-data` bucket:

    incoming/<file>.csv    -- uploaded by the data generator / upload script,
                               waiting to be picked up by the DAG
    processed/<file>.csv   -- moved here once successfully loaded, so the
                               same file is never processed twice

This keeps "what's new" derivable purely from bucket state (no external
tracking table needed), and makes the pipeline idempotent: re-running it
with no new files in `incoming/` is a safe no-op.
"""

from __future__ import annotations

import logging
import os
import tempfile

from minio import Minio

logger = logging.getLogger(__name__)

INCOMING_PREFIX = "incoming/"
PROCESSED_PREFIX = "processed/"


class NoNewFileFound(Exception):
    """Raised when there is nothing new to process in the incoming/ prefix."""


def get_minio_client() -> Minio:
    endpoint = os.environ.get("MINIO_ENDPOINT", "minio:9000")
    access_key = os.environ.get("MINIO_ROOT_USER", "minio_admin")
    secret_key = os.environ.get("MINIO_ROOT_PASSWORD", "minio_password")
    secure = os.environ.get("MINIO_SECURE", "false").lower() == "true"
    return Minio(endpoint, access_key=access_key, secret_key=secret_key, secure=secure)


def get_bucket_name() -> str:
    return os.environ.get("MINIO_BUCKET", "raw-data")


def ensure_bucket(client: Minio, bucket: str) -> None:
    if not client.bucket_exists(bucket):
        client.make_bucket(bucket)
        logger.info("Created MinIO bucket '%s'", bucket)


def detect_new_files(client: Minio | None = None, bucket: str | None = None) -> str:
    """Return the object key of the oldest unprocessed CSV under
    `incoming/`. Raises NoNewFileFound if the prefix is empty."""
    client = client or get_minio_client()
    bucket = bucket or get_bucket_name()

    objects = list(client.list_objects(bucket, prefix=INCOMING_PREFIX, recursive=True))
    csv_objects = [obj for obj in objects if obj.object_name.endswith(".csv")]

    if not csv_objects:
        raise NoNewFileFound(f"No new CSV files found under '{INCOMING_PREFIX}' in bucket '{bucket}'")

    oldest = min(csv_objects, key=lambda obj: obj.last_modified)
    logger.info("Detected new file: %s", oldest.object_name)
    return oldest.object_name


def download_file(object_key: str, client: Minio | None = None, bucket: str | None = None) -> str:
    """Download `object_key` to a local temp path and return that path."""
    client = client or get_minio_client()
    bucket = bucket or get_bucket_name()

    local_dir = tempfile.mkdtemp(prefix="sales_pipeline_")
    filename = os.path.basename(object_key)
    local_path = os.path.join(local_dir, filename)

    client.fget_object(bucket, object_key, local_path)
    logger.info("Downloaded %s/%s to %s", bucket, object_key, local_path)
    return local_path


def mark_processed(object_key: str, client: Minio | None = None, bucket: str | None = None) -> None:
    """Move an object from `incoming/` to `processed/` so it is not
    re-ingested on the next DAG run."""
    from minio.commonconfig import CopySource

    client = client or get_minio_client()
    bucket = bucket or get_bucket_name()

    filename = os.path.basename(object_key)
    dest_key = f"{PROCESSED_PREFIX}{filename}"

    client.copy_object(bucket, dest_key, CopySource(bucket, object_key))
    client.remove_object(bucket, object_key)
    logger.info("Moved %s -> %s", object_key, dest_key)
