"""Tests for the connection pool with local data.

Each dataset location gets its own prepared DuckDB connection with a
focus_data_table view; the pool hands the same connection back for the same
location and evicts the least recently used one when full.
"""

import json
from pathlib import Path

import duckdb
import pytest

from focus_mcp import datasets

BUNDLED_SAMPLE = Path(__file__).resolve().parent.parent / "data/aws-focus-export"


@pytest.fixture
def pool():
    p = datasets.ConnectionPool(max_size=2)
    yield p
    p.close_all()


def write_parquet(directory, providers=("AWS", "GCP")):
    """Write a tiny FOCUS-ish parquet file under a hive-style subdir."""
    sub = directory / "billing_period=2026-01"
    sub.mkdir(parents=True)
    c = duckdb.connect()
    rows = " UNION ALL ".join(
        f"SELECT '{p}' AS ProviderName, {i + 1.5} AS BilledCost" for i, p in enumerate(providers)
    )
    c.execute(f"COPY ({rows}) TO '{sub}/part.parquet' (FORMAT parquet)")
    c.close()


def test_local_happy_path(tmp_path, pool):
    write_parquet(tmp_path)
    entry = pool.get(str(tmp_path))
    count = entry.conn.execute("SELECT count(*) FROM focus_data_table").fetchone()[0]
    assert count == 2
    # hive partitioning surfaced the directory as a column
    cols = {r[0] for r in entry.conn.execute("DESCRIBE focus_data_table").fetchall()}
    assert "billing_period" in cols
    assert entry.strategy is not None


def test_same_location_reuses_the_connection(tmp_path, pool):
    write_parquet(tmp_path)
    first = pool.get(str(tmp_path))
    second = pool.get(str(tmp_path) + "/")
    assert first is second
    assert len(pool) == 1


def test_locations_are_isolated_and_the_oldest_is_evicted(tmp_path, pool):
    a, b, c = (tmp_path / n for n in ("a", "b", "c"))
    write_parquet(a, providers=("AWS",))
    write_parquet(b, providers=("GCP", "Azure"))
    write_parquet(c, providers=("Oracle", "IBM", "Alibaba"))

    assert pool.get(str(a)).conn.execute("SELECT count(*) FROM focus_data_table").fetchone()[0] == 1
    assert pool.get(str(b)).conn.execute("SELECT count(*) FROM focus_data_table").fetchone()[0] == 2
    assert pool.get(str(c)).conn.execute("SELECT count(*) FROM focus_data_table").fetchone()[0] == 3
    assert len(pool) == 2
    # a was the least recently used; asking for it again opens a fresh one
    reopened = pool.get(str(a))
    assert reopened.conn.execute("SELECT count(*) FROM focus_data_table").fetchone()[0] == 1


def test_missing_location_yields_a_connection_without_a_view(tmp_path, pool):
    entry = pool.get(str(tmp_path / "nowhere"))
    assert entry.strategy is None
    tables = entry.conn.execute(
        "SELECT * FROM information_schema.tables WHERE table_name = 'focus_data_table'"
    ).fetchall()
    assert tables == []


@pytest.mark.skipif(
    not BUNDLED_SAMPLE.exists(),
    reason="sample export is untracked; present only in local checkouts",
)
def test_bundled_sample_data_loads(pool):
    # No metadata/ prefix ships with the sample, so this is the glob path
    conn = pool.get(str(BUNDLED_SAMPLE)).conn
    count = conn.execute("SELECT count(*) FROM focus_data_table").fetchone()[0]
    assert count > 0
    periods = {r[0] for r in conn.execute("SELECT DISTINCT billing_period FROM focus_data_table").fetchall()}
    assert periods == {f"2025-0{m}" for m in range(5, 10)}


def write_export_period(root, period, files):
    """Write one delivered billing period of an AWS export.

    files maps a file name to its cost; only the first is manifested, so
    the rest stand in for chunks left behind on the prefix.
    """
    data_dir = root / "data" / f"billing_period={period}"
    data_dir.mkdir(parents=True, exist_ok=True)
    c = duckdb.connect()
    for name, cost in files.items():
        c.execute(f"""
            COPY (SELECT 'AWS' AS ProviderName, {cost} AS BilledCost)
            TO '{data_dir / name}' (FORMAT parquet)
        """)
    c.close()
    manifest = root / "metadata" / f"billing_period={period}"
    manifest.mkdir(parents=True, exist_ok=True)
    (manifest / "focus-export-Manifest.json").write_text(json.dumps({
        "executionId": "exec-1",
        "dataFiles": [str(data_dir / next(iter(files)))],
    }))


def test_aws_export_loads_through_its_manifests(tmp_path, pool):
    # Two deliveries of the same period: only the manifest's file counts
    write_export_period(tmp_path, "2026-01", {"current.parquet": 1.5, "stale.parquet": 99.0})
    entry = pool.get(str(tmp_path))
    assert entry.conn.execute(
        "SELECT ProviderName, BilledCost, billing_period FROM focus_data_table"
    ).fetchall() == [("AWS", 1.5, "2026-01")]
    assert entry.strategy == "manifest"


def test_stale_view_is_rebuilt_for_the_next_delivery(tmp_path, pool, monkeypatch):
    # The manifest strategy pins one delivery's files, so a server left
    # running has to rebuild the view to see the deliveries after it
    write_export_period(tmp_path, "2026-01", {"part.parquet": 1.5})
    monkeypatch.setattr(datasets, "VIEW_MAX_AGE_SECONDS", -1)
    pool.get(str(tmp_path))

    write_export_period(tmp_path, "2026-02", {"part.parquet": 2.5})
    conn = pool.get(str(tmp_path)).conn
    assert conn.execute("SELECT billing_period FROM focus_data_table ORDER BY 1").fetchall() == [
        ("2026-01",),
        ("2026-02",),
    ]


def test_failed_rebuild_keeps_the_loaded_data(tmp_path, pool, monkeypatch):
    write_export_period(tmp_path, "2026-01", {"part.parquet": 1.5})
    monkeypatch.setattr(datasets, "VIEW_MAX_AGE_SECONDS", -1)
    pool.get(str(tmp_path))

    (tmp_path / "metadata" / "billing_period=2026-01" / "focus-export-Manifest.json").write_text("{ not json")
    conn = pool.get(str(tmp_path)).conn
    assert conn.execute("SELECT count(*) FROM focus_data_table").fetchone() == (1,)


def test_local_view_failure_propagates_original_exception(tmp_path, pool):
    # Directory exists but contains no parquet files: view creation fails.
    # The original DuckDB exception must propagate unwrapped (the
    # RuntimeError wrapping is reserved for backends that returned a hint).
    with pytest.raises(duckdb.Error) as excinfo:
        pool.get(str(tmp_path))
    assert not isinstance(excinfo.value, RuntimeError)


def test_view_failure_is_not_cached(tmp_path, pool):
    # Caching a viewless connection would replace this error with a
    # catalog error on every later call, and never retry the load
    with pytest.raises(duckdb.Error):
        pool.get(str(tmp_path))
    assert len(pool) == 0

    write_parquet(tmp_path)
    conn = pool.get(str(tmp_path)).conn
    assert conn.execute("SELECT count(*) FROM focus_data_table").fetchone() == (2,)
