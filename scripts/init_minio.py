"""Create the raw-data MinIO bucket (if needed) and upload a CSV file into
its `incoming/` prefix, where the Airflow DAG will pick it up.

Usage:
    python scripts/init_minio.py --file data/sales.csv
    python scripts/init_minio.py --file data/sales.csv --endpoint localhost:9000
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "dags"))

from minio import Minio  # noqa: E402
from pipeline.ingestion import INCOMING_PREFIX, ensure_bucket  # noqa: E402

logger = logging.getLogger(__name__)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Upload a CSV into the MinIO raw-data bucket.")
    parser.add_argument("--file", required=True, help="Path to the local CSV file to upload")
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        help="MinIO endpoint host:port (default: env MINIO_ENDPOINT or localhost:9000, "
        "for use from the host machine rather than inside the Docker network)",
    )
    parser.add_argument("--access-key", default=os.environ.get("MINIO_ROOT_USER", "minio_admin"))
    parser.add_argument("--secret-key", default=os.environ.get("MINIO_ROOT_PASSWORD", "minio_password"))
    parser.add_argument("--bucket", default=os.environ.get("MINIO_BUCKET", "raw-data"))
    parser.add_argument("--secure", action="store_true", help="Use HTTPS instead of HTTP")
    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    file_path = Path(args.file)
    if not file_path.exists():
        raise FileNotFoundError(f"No such file: {file_path}")

    client = Minio(args.endpoint, access_key=args.access_key, secret_key=args.secret_key, secure=args.secure)
    ensure_bucket(client, args.bucket)

    object_key = f"{INCOMING_PREFIX}{file_path.name}"
    client.fput_object(args.bucket, object_key, str(file_path))
    logger.info("Uploaded %s to %s/%s", file_path, args.bucket, object_key)


if __name__ == "__main__":
    main()
