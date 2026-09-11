import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dags"))

from pipeline.ingestion import (  # noqa: E402
    NoNewFileFound,
    detect_new_files,
    download_file,
    ensure_bucket,
    mark_processed,
)


def _obj(name, minutes_ago):
    return SimpleNamespace(object_name=name, last_modified=datetime.utcnow() - timedelta(minutes=minutes_ago))


def test_detect_new_files_picks_oldest_csv():
    client = MagicMock()
    client.list_objects.return_value = [
        _obj("incoming/sales_b.csv", minutes_ago=5),
        _obj("incoming/sales_a.csv", minutes_ago=30),  # oldest -> should win
        _obj("incoming/README.txt", minutes_ago=100),  # not a csv -> ignored
    ]

    result = detect_new_files(client=client, bucket="raw-data")

    assert result == "incoming/sales_a.csv"
    client.list_objects.assert_called_once_with("raw-data", prefix="incoming/", recursive=True)


def test_detect_new_files_raises_when_empty():
    client = MagicMock()
    client.list_objects.return_value = []

    with pytest.raises(NoNewFileFound):
        detect_new_files(client=client, bucket="raw-data")


def test_ensure_bucket_creates_when_missing():
    client = MagicMock()
    client.bucket_exists.return_value = False

    ensure_bucket(client, "raw-data")

    client.make_bucket.assert_called_once_with("raw-data")


def test_ensure_bucket_skips_when_present():
    client = MagicMock()
    client.bucket_exists.return_value = True

    ensure_bucket(client, "raw-data")

    client.make_bucket.assert_not_called()


def test_download_file_calls_fget_object():
    client = MagicMock()

    local_path = download_file("incoming/sales.csv", client=client, bucket="raw-data")

    assert local_path.endswith("sales.csv")
    client.fget_object.assert_called_once()
    args = client.fget_object.call_args[0]
    assert args[0] == "raw-data"
    assert args[1] == "incoming/sales.csv"


def test_mark_processed_copies_then_removes():
    client = MagicMock()

    mark_processed("incoming/sales.csv", client=client, bucket="raw-data")

    client.copy_object.assert_called_once()
    client.remove_object.assert_called_once_with("raw-data", "incoming/sales.csv")
