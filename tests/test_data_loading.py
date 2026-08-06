"""Tests for data_loading: manifest discovery and view construction.

Fixtures mimic an AWS BCM Data Export on the local filesystem:
{root}/data/<PARTITION>/*.parquet next to
{root}/metadata/<PARTITION>/<export>-Manifest.json.

Note: mixed-casing cases use two different billing periods, one per
casing. macOS filesystems are case-insensitive, so a single period cannot
have both billing_period= and BILLING_PERIOD= directories there.
"""

import json

import duckdb
import pytest

from focus_mcp.data_loading import (
    collect_data_files,
    create_focus_view,
    discover_manifests,
)


@pytest.fixture
def conn():
    c = duckdb.connect()
    yield c
    c.close()


class DeniedMetadataPrefix:
    """Connection whose metadata/ listing fails, as a denied prefix does."""

    def __init__(self, conn):
        self.conn = conn

    def execute(self, sql, params=None):
        if params and any("/metadata/" in str(p) for p in params):
            raise duckdb.IOException("HTTP 403")
        return self.conn.execute(sql, params or [])


def write_parquet(path, rows):
    """Write rows of (ProviderName, BilledCost) to a Parquet file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    values = ", ".join(f"('{p}', {cost})" for p, cost in rows)
    c = duckdb.connect()
    c.execute(f"""
        COPY (SELECT * FROM (VALUES {values}) AS t(ProviderName, BilledCost))
        TO '{path}' (FORMAT parquet)
    """)
    c.close()


def write_manifest(path, data_files):
    """Write an export manifest listing the given data files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "executionId": "exec-1",
        "exportArn": "arn:aws:bcm-data-exports:us-east-1:1234:export/focus",
        "columns": [{"name": "ProviderName"}, {"name": "BilledCost"}],
        "dataFiles": [str(f) for f in data_files],
        "additionalOutputFiles": [],
    }))


def write_period(root, partition, rows, manifest=True):
    """Write one billing period's data file, with its manifest by default."""
    data_file = root / "data" / partition / "part-00001.parquet"
    write_parquet(data_file, rows)
    if manifest:
        write_manifest(
            root / "metadata" / partition / "focus-export-Manifest.json",
            [data_file],
        )
    return data_file


def write_one_column(root, select_sql, partition="billing_period=2026-04"):
    """Write a single-file period from an arbitrary SELECT."""
    data_file = root / "data" / partition / "part.parquet"
    data_file.parent.mkdir(parents=True)
    duckdb.connect().execute(f"COPY ({select_sql}) TO '{data_file}' (FORMAT parquet)")
    write_manifest(
        root / "metadata" / partition / "focus-export-Manifest.json", [data_file]
    )
    return data_file


def view_rows(conn):
    return conn.execute(
        "SELECT ProviderName, BilledCost, billing_period FROM focus_data_table"
        " ORDER BY billing_period, BilledCost"
    ).fetchall()


# --- manifest discovery ---

def test_discovers_partition_manifests_in_both_casings(conn, tmp_path):
    write_period(tmp_path, "billing_period=2026-04", [("AWS", 1.0)])
    write_period(tmp_path, "BILLING_PERIOD=2026-05", [("AWS", 2.0)])
    found = discover_manifests(conn, str(tmp_path))
    assert [p.split("/")[-2] for p in found] == [
        "BILLING_PERIOD=2026-05",
        "billing_period=2026-04",
    ]


def test_ignores_execution_level_manifests(conn, tmp_path):
    write_period(tmp_path, "billing_period=2026-04", [("AWS", 1.0)])
    # CREATE_NEW_REPORT writes a manifest per execution one level deeper
    write_manifest(
        tmp_path / "metadata" / "billing_period=2026-04" / "exec-abc"
        / "focus-export-Manifest.json",
        [tmp_path / "data" / "billing_period=2026-04" / "old.parquet"],
    )
    found = discover_manifests(conn, str(tmp_path))
    assert len(found) == 1
    assert found[0].endswith(
        "metadata/billing_period=2026-04/focus-export-Manifest.json"
    )


def test_ignores_manifest_focus_sibling(conn, tmp_path):
    write_period(tmp_path, "billing_period=2026-04", [("AWS", 1.0)])
    write_manifest(
        tmp_path / "metadata" / "billing_period=2026-04"
        / "focus-export-Manifest-FOCUS.json",
        [tmp_path / "data" / "billing_period=2026-04" / "other.parquet"],
    )
    found = discover_manifests(conn, str(tmp_path))
    assert len(found) == 1
    assert found[0].endswith("focus-export-Manifest.json")


def test_ignores_non_partition_metadata_dirs(conn, tmp_path):
    write_manifest(
        tmp_path / "metadata" / "schema" / "focus-export-Manifest.json",
        [tmp_path / "data" / "part.parquet"],
    )
    assert discover_manifests(conn, str(tmp_path)) == []


def test_discovery_on_missing_location_returns_nothing(conn, tmp_path):
    assert discover_manifests(conn, str(tmp_path / "missing")) == []


def test_unlistable_metadata_prefix_is_not_treated_as_no_manifests(
    conn, tmp_path
):
    # Downgrading to the glob here would silently double-count the export
    write_period(tmp_path, "billing_period=2026-04", [("AWS", 1.0)])
    with pytest.raises(duckdb.Error):
        create_focus_view(DeniedMetadataPrefix(conn), str(tmp_path))


# --- data file collection ---

def test_data_files_combined_and_deduped(conn, tmp_path):
    april = write_period(tmp_path, "billing_period=2026-04", [("AWS", 1.0)])
    may = write_period(tmp_path, "BILLING_PERIOD=2026-05", [("AWS", 2.0)])
    # A file listed twice (e.g. a period re-delivered) is loaded once
    write_manifest(
        tmp_path / "metadata" / "billing_period=2026-06"
        / "focus-export-Manifest.json",
        [may],
    )
    files = collect_data_files(
        conn, discover_manifests(conn, str(tmp_path)), str(tmp_path)
    )
    assert sorted(files) == sorted([str(april), str(may)])


def test_data_files_are_rebased_onto_the_location(conn, tmp_path):
    # A copy of an export (aws s3 sync, a mirror bucket) keeps AWS's
    # layout but not the bucket URIs its manifests were written with
    write_parquet(
        tmp_path / "data" / "billing_period=2026-04" / "part-00001.parquet",
        [("AWS", 1.0)],
    )
    write_parquet(
        tmp_path / "data" / "BILLING_PERIOD=2026-05" / "exec-1" / "part.parquet",
        [("AWS", 2.0)],
    )
    write_manifest(
        tmp_path / "metadata" / "billing_period=2026-04"
        / "focus-export-Manifest.json",
        ["s3://delivery-bucket/focus/data/billing_period=2026-04/"
         "part-00001.parquet"],
    )
    write_manifest(
        tmp_path / "metadata" / "BILLING_PERIOD=2026-05"
        / "focus-export-Manifest.json",
        ["s3://delivery-bucket/focus/data/BILLING_PERIOD=2026-05/exec-1/"
         "part.parquet"],
    )
    assert create_focus_view(conn, str(tmp_path)) == "manifest"
    assert view_rows(conn) == [
        ("AWS", 1.0, "2026-04"),
        ("AWS", 2.0, "2026-05"),
    ]


def test_unparseable_manifest_is_skipped(conn, tmp_path):
    april = write_period(tmp_path, "billing_period=2026-04", [("AWS", 1.0)])
    broken = (
        tmp_path / "metadata" / "billing_period=2026-05"
        / "focus-export-Manifest.json"
    )
    broken.parent.mkdir(parents=True)
    broken.write_text("{ this is not json")
    assert collect_data_files(
        conn, discover_manifests(conn, str(tmp_path)), str(tmp_path)
    ) == [str(april)]


def test_manifest_without_data_files_key_is_skipped(conn, tmp_path):
    april = write_period(tmp_path, "billing_period=2026-04", [("AWS", 1.0)])
    incomplete = (
        tmp_path / "metadata" / "billing_period=2026-05"
        / "focus-export-Manifest.json"
    )
    incomplete.parent.mkdir(parents=True)
    incomplete.write_text(json.dumps({"executionId": "exec-2"}))
    assert collect_data_files(
        conn, discover_manifests(conn, str(tmp_path)), str(tmp_path)
    ) == [str(april)]


# --- view creation: manifest-driven ---

def test_manifest_view_excludes_orphan_files(conn, tmp_path):
    write_period(tmp_path, "billing_period=2026-04", [("AWS", 1.0)])
    # A superseded chunk, still on the prefix but out of the manifest
    write_parquet(
        tmp_path / "data" / "billing_period=2026-04" / "stale.parquet",
        [("AWS", 99.0)],
    )
    # A partition orphaned by an AWS-side casing switch: it never got a
    # metadata/ entry, so no manifest points at it
    write_parquet(
        tmp_path / "data" / "BILLING_PERIOD=2026-05" / "part.parquet",
        [("AWS", 50.0)],
    )
    assert create_focus_view(conn, str(tmp_path)) == "manifest"
    assert view_rows(conn) == [("AWS", 1.0, "2026-04")]


def test_manifest_view_derives_billing_period_for_both_casings(
    conn, tmp_path
):
    write_period(tmp_path, "billing_period=2026-04", [("AWS", 1.0)])
    write_period(tmp_path, "BILLING_PERIOD=2026-05", [("AWS", 2.0)])
    create_focus_view(conn, str(tmp_path))
    assert view_rows(conn) == [
        ("AWS", 1.0, "2026-04"),
        ("AWS", 2.0, "2026-05"),
    ]


def test_manifest_view_hides_the_filename_column(conn, tmp_path):
    write_period(tmp_path, "billing_period=2026-04", [("AWS", 1.0)])
    create_focus_view(conn, str(tmp_path))
    cols = [r[0] for r in conn.execute("DESCRIBE focus_data_table").fetchall()]
    assert "filename" not in cols
    assert cols[:3] == ["ProviderName", "BilledCost", "billing_period"]


def test_manifest_view_unions_differing_schemas(conn, tmp_path):
    older = tmp_path / "data" / "billing_period=2026-04" / "part.parquet"
    older.parent.mkdir(parents=True)
    duckdb.connect().execute(
        f"COPY (SELECT 'AWS' AS ProviderName) TO '{older}' (FORMAT parquet)"
    )
    write_manifest(
        tmp_path / "metadata" / "billing_period=2026-04"
        / "focus-export-Manifest.json",
        [older],
    )
    write_period(tmp_path, "billing_period=2026-05", [("AWS", 2.0)])
    create_focus_view(conn, str(tmp_path))
    assert conn.execute(
        "SELECT BilledCost FROM focus_data_table"
        " WHERE billing_period = '2026-04'"
    ).fetchone() == (None,)


def test_empty_data_files_is_an_error_not_a_glob(conn, tmp_path):
    # Manifests prove this is an export, and globbing an export is what
    # this module exists to avoid, so there is nothing to fall back to
    write_parquet(
        tmp_path / "data" / "billing_period=2026-04" / "part.parquet",
        [("AWS", 1.0)],
    )
    write_manifest(
        tmp_path / "metadata" / "billing_period=2026-04"
        / "focus-export-Manifest.json",
        [],
    )
    with pytest.raises(RuntimeError, match="no data file"):
        create_focus_view(conn, str(tmp_path))


def test_manifested_file_that_vanished_is_skipped(conn, tmp_path):
    write_period(tmp_path, "billing_period=2026-04", [("AWS", 1.0)])
    # A period's data expired or cleaned up without its metadata
    expired = write_period(tmp_path, "billing_period=2026-05", [("AWS", 2.0)])
    expired.unlink()
    assert create_focus_view(conn, str(tmp_path)) == "manifest-partial"
    assert view_rows(conn) == [("AWS", 1.0, "2026-04")]


def test_manifest_view_fails_when_no_file_is_readable(conn, tmp_path):
    expired = write_period(tmp_path, "billing_period=2026-04", [("AWS", 1.0)])
    expired.unlink()
    with pytest.raises(duckdb.Error):
        create_focus_view(conn, str(tmp_path))


# --- view creation: glob fallback ---

def test_glob_fallback_without_metadata(conn, tmp_path):
    write_parquet(
        tmp_path / "billing_period=2026-04" / "part.parquet", [("AWS", 1.0)]
    )
    write_parquet(
        tmp_path / "billing_period=2026-05" / "part.parquet", [("GCP", 2.0)]
    )
    assert create_focus_view(conn, str(tmp_path)) == "glob"
    assert view_rows(conn) == [
        ("AWS", 1.0, "2026-04"),
        ("GCP", 2.0, "2026-05"),
    ]


def test_glob_fallback_on_flat_directory(conn, tmp_path):
    write_parquet(tmp_path / "part.parquet", [("GCP", 1.0)])
    assert create_focus_view(conn, str(tmp_path)) == "glob"
    assert conn.execute("SELECT count(*) FROM focus_data_table").fetchone() == (
        1,
    )


def test_hive_mismatch_retries_without_partitioning(conn, tmp_path):
    write_parquet(
        tmp_path / "billing_period=2026-04" / "part.parquet", [("AWS", 1.0)]
    )
    write_parquet(
        tmp_path / "BILLING_PERIOD=2026-05" / "part.parquet", [("AWS", 2.0)]
    )
    assert create_focus_view(conn, str(tmp_path)) == "glob-no-hive"
    # Both casings load, and billing_period survives the retry
    assert view_rows(conn) == [
        ("AWS", 1.0, "2026-04"),
        ("AWS", 2.0, "2026-05"),
    ]


def test_hive_mismatch_retry_unions_differing_schemas(conn, tmp_path):
    older = tmp_path / "billing_period=2026-04" / "part.parquet"
    older.parent.mkdir(parents=True)
    duckdb.connect().execute(
        f"COPY (SELECT 'AWS' AS ProviderName) TO '{older}' (FORMAT parquet)"
    )
    write_parquet(
        tmp_path / "BILLING_PERIOD=2026-05" / "part.parquet", [("AWS", 2.0)]
    )
    assert create_focus_view(conn, str(tmp_path)) == "glob-no-hive"
    assert view_rows(conn) == [
        ("AWS", None, "2026-04"),
        ("AWS", 2.0, "2026-05"),
    ]


def test_glob_failure_propagates(conn, tmp_path):
    with pytest.raises(duckdb.Error):
        create_focus_view(conn, str(tmp_path))


# --- renamed columns ---

def test_exposes_the_new_name_for_pre_1_3_data(conn, tmp_path):
    write_period(tmp_path, "billing_period=2026-04", [("AWS", 1.0)])
    create_focus_view(conn, str(tmp_path))
    assert conn.execute(
        "SELECT ServiceProviderName FROM focus_data_table"
    ).fetchall() == [("AWS",)]


def test_exposes_the_former_name_for_1_3_data(conn, tmp_path):
    write_one_column(tmp_path, "SELECT 'AWS' AS ServiceProviderName")
    create_focus_view(conn, str(tmp_path))
    # A query written against 1.2 must still bind on an export speaking 1.3.
    assert conn.execute(
        "SELECT ProviderName FROM focus_data_table"
    ).fetchall() == [("AWS",)]


def test_merges_both_names_when_the_data_spans_the_rename(conn, tmp_path):
    # A provider that upgrades mid-stream leaves each name populated only
    # for its own periods; union_by_name then yields both, each half null.
    # Grouping on either name must still see every row.
    before = tmp_path / "data" / "billing_period=2026-04" / "part.parquet"
    after = tmp_path / "data" / "billing_period=2026-05" / "part.parquet"
    for path, sql in (
        (before, "SELECT 'AWS' AS ProviderName, 1.0 AS BilledCost"),
        (after, "SELECT 'AWS' AS ServiceProviderName, 2.0 AS BilledCost"),
    ):
        path.parent.mkdir(parents=True)
        duckdb.connect().execute(f"COPY ({sql}) TO '{path}' (FORMAT parquet)")
        write_manifest(
            tmp_path / "metadata" / path.parent.name
            / "focus-export-Manifest.json",
            [path],
        )
    create_focus_view(conn, str(tmp_path))

    for column in ("ProviderName", "ServiceProviderName"):
        assert conn.execute(
            f"SELECT {column}, SUM(BilledCost) FROM focus_data_table"
            f" GROUP BY 1"
        ).fetchall() == [("AWS", 3.0)], f"{column} lost a period"


def test_no_column_is_invented_when_neither_name_is_present(conn, tmp_path):
    write_one_column(tmp_path, "SELECT 1.0 AS BilledCost")
    create_focus_view(conn, str(tmp_path))
    cols = [r[0] for r in conn.execute("DESCRIBE focus_data_table").fetchall()]
    assert "ServiceProviderName" not in cols
    assert "ProviderName" not in cols
