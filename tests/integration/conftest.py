"""Shared fixtures for integration tests.

These tests exercise a REAL running platform (`make up`) — they are not
run as part of `make test` / unit CI. They connect to the same ports the
host machine would use (localhost:<port>), not the internal Docker service
names, since the test runner is expected to run on the host or in a CI job
that has published those ports.
"""

from __future__ import annotations

import os

import psycopg2
import pytest
from minio import Minio

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_DB = os.environ.get("POSTGRES_DB", "mini_data_platform")
POSTGRES_USER = os.environ.get("POSTGRES_USER", "platform_user")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "platform_pass")

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
MINIO_ROOT_USER = os.environ.get("MINIO_ROOT_USER", "minio_admin")
MINIO_ROOT_PASSWORD = os.environ.get("MINIO_ROOT_PASSWORD", "minio_password")
MINIO_BUCKET = os.environ.get("MINIO_BUCKET", "raw-data")

AIRFLOW_BASE_URL = os.environ.get("AIRFLOW_BASE_URL", "http://localhost:8080")
METABASE_BASE_URL = os.environ.get("METABASE_BASE_URL", "http://localhost:3000")


@pytest.fixture(scope="session")
def postgres_conn():
    conn = psycopg2.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        dbname=POSTGRES_DB,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        connect_timeout=5,
    )
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def minio_client():
    return Minio(MINIO_ENDPOINT, access_key=MINIO_ROOT_USER, secret_key=MINIO_ROOT_PASSWORD, secure=False)
