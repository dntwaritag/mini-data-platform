import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dags"))

from pipeline.load import COLUMNS, load_records  # noqa: E402
from pipeline.validation import DataValidationError, validate_loaded_records  # noqa: E402


def _mock_conn():
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    return conn, cur


def test_load_records_commits_and_returns_row_count():
    conn, cur = _mock_conn()
    records = [tuple(range(len(COLUMNS))), tuple(range(len(COLUMNS)))]

    with patch("pipeline.load.psycopg2.extras.execute_values") as mock_execute_values:
        count = load_records(records, conn=conn)

    mock_execute_values.assert_called_once()
    assert count == 2
    conn.commit.assert_called_once()


def test_validate_loaded_records_passes_when_clean():
    conn, cur = _mock_conn()
    # total_rows, negative_rows, null_required_rows, duplicate_ids
    cur.fetchone.side_effect = [(10,), (0,), (0,), (0,)]

    validate_loaded_records(expected_min_rows=5, conn=conn)  # should not raise


def test_validate_loaded_records_fails_on_too_few_rows():
    conn, cur = _mock_conn()
    cur.fetchone.side_effect = [(2,), (0,), (0,), (0,)]

    with pytest.raises(DataValidationError):
        validate_loaded_records(expected_min_rows=5, conn=conn)


def test_validate_loaded_records_fails_on_negative_values():
    conn, cur = _mock_conn()
    cur.fetchone.side_effect = [(10,), (3,), (0,), (0,)]

    with pytest.raises(DataValidationError):
        validate_loaded_records(expected_min_rows=5, conn=conn)


def test_validate_loaded_records_fails_on_duplicates():
    conn, cur = _mock_conn()
    cur.fetchone.side_effect = [(10,), (0,), (0,), (2,)]

    with pytest.raises(DataValidationError):
        validate_loaded_records(expected_min_rows=5, conn=conn)
