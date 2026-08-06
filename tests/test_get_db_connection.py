"""Tests for get_db_connection with local data.

IMPORTANT patching note: FOCUS_DATA_LOCATION is read from the environment
at import time (focus_config.py) and copied into
focus_mcp_server.DATA_LOCATION at import time. monkeypatch.setenv would
therefore silently test nothing — tests must setattr the module global
and reset the connection singleton.
"""

import json
from pathlib import Path

import duckdb
import pytest

import focus_mcp_server

BUNDLED_SAMPLE = Path(__file__).resolve().parent.parent / "data/aws-focus-export"


@pytest.fixture(autouse=True)
def fresh_connection_singleton():
    focus_mcp_server.db_connection = None
    yield
    if focus_mcp_server.db_connection is not None:
        focus_mcp_server.db_connection.close()
    focus_mcp_server.db_connection = None


def write_parquet(directory):
    """Write a tiny FOCUS-ish parquet file under a hive-style subdir."""
    sub = directory / "billing_period=2026-01"
    sub.mkdir()
    c = duckdb.connect()
    c.execute(f"""
        COPY (
            SELECT 'AWS' AS ProviderName, 1.5 AS BilledCost
            UNION ALL
            SELECT 'GCP' AS ProviderName, 2.5 AS BilledCost
        ) TO '{sub}/part.parquet' (FORMAT parquet)
    """)
    c.close()


def test_local_happy_path(tmp_path, monkeypatch):
    write_parquet(tmp_path)
    monkeypatch.setattr(focus_mcp_server, "DATA_LOCATION", str(tmp_path))
    conn = focus_mcp_server.get_db_connection()
    count = conn.execute("SELECT count(*) FROM focus_data_table").fetchone()[0]
    assert count == 2
    # hive partitioning surfaced the directory as a column
    cols = {
        r[0]
        for r in conn.execute("DESCRIBE focus_data_table").fetchall()
    }
    assert "billing_period" in cols


def test_bundled_sample_data_loads(monkeypatch):
    # No metadata/ prefix ships with the sample, so this is the glob path
    monkeypatch.setattr(
        focus_mcp_server, "DATA_LOCATION", str(BUNDLED_SAMPLE)
    )
    conn = focus_mcp_server.get_db_connection()
    count = conn.execute("SELECT count(*) FROM focus_data_table").fetchone()[0]
    assert count > 0
    periods = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT billing_period FROM focus_data_table"
        ).fetchall()
    }
    assert periods == {f"2025-0{m}" for m in range(5, 10)}


def test_aws_export_loads_through_its_manifests(tmp_path, monkeypatch):
    # Two deliveries of the same period: only the manifest's file counts
    data_dir = tmp_path / "data" / "billing_period=2026-01"
    data_dir.mkdir(parents=True)
    c = duckdb.connect()
    for name, cost in [("current.parquet", 1.5), ("stale.parquet", 99.0)]:
        c.execute(f"""
            COPY (SELECT 'AWS' AS ProviderName, {cost} AS BilledCost)
            TO '{data_dir / name}' (FORMAT parquet)
        """)
    c.close()
    manifest = tmp_path / "metadata" / "billing_period=2026-01"
    manifest.mkdir(parents=True)
    (manifest / "focus-export-Manifest.json").write_text(json.dumps({
        "executionId": "exec-1",
        "dataFiles": [str(data_dir / "current.parquet")],
    }))

    monkeypatch.setattr(focus_mcp_server, "DATA_LOCATION", str(tmp_path))
    conn = focus_mcp_server.get_db_connection()
    assert conn.execute(
        "SELECT ProviderName, BilledCost, billing_period FROM focus_data_table"
    ).fetchall() == [("AWS", 1.5, "2026-01")]


def test_missing_local_path_returns_connection_without_view(monkeypatch):
    monkeypatch.setattr(
        focus_mcp_server, "DATA_LOCATION", "/nonexistent/focus-data"
    )
    conn = focus_mcp_server.get_db_connection()
    with pytest.raises(duckdb.CatalogException):
        conn.execute("SELECT * FROM focus_data_table")


def test_local_view_failure_propagates_original_exception(
    tmp_path, monkeypatch
):
    # Directory exists but contains no parquet files: view creation fails.
    # The original DuckDB exception must propagate unwrapped (the
    # RuntimeError wrapping is reserved for backends that returned a hint).
    monkeypatch.setattr(focus_mcp_server, "DATA_LOCATION", str(tmp_path))
    with pytest.raises(duckdb.Error) as excinfo:
        focus_mcp_server.get_db_connection()
    assert not isinstance(excinfo.value, RuntimeError)
