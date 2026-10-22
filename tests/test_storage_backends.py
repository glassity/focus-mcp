"""Tests for storage_backends: dispatch, normalization, and connection prep.

Notes:
- Tests that exercise `INSTALL httpfs` need network access the first time
  they run on a machine (the extension is cached afterwards).
- Every test uses a fresh in-memory DuckDB connection so secrets and
  extensions don't bleed between tests.
"""

import sys
import types

import duckdb
import pytest

from focus_mcp import config
from focus_mcp.datasets import Credentials
from focus_mcp.storage_backends import (
    GCSBackend,
    LocalBackend,
    S3Backend,
    resolve_backend,
    secret_name,
)


@pytest.fixture
def conn():
    c = duckdb.connect()
    yield c
    c.close()


def loaded_extensions(c):
    rows = c.execute(
        "SELECT extension_name FROM duckdb_extensions() WHERE loaded"
    ).fetchall()
    return {r[0] for r in rows}


def secret_names(c):
    rows = c.execute("SELECT name FROM duckdb_secrets()").fetchall()
    return {r[0] for r in rows}


def secret_scopes(c):
    rows = c.execute("SELECT scope FROM duckdb_secrets()").fetchall()
    return {tuple(r[0]) for r in rows}


def secret_fields(c, location):
    """The settings of the secret prepared for one location."""
    row = c.execute(
        "SELECT secret_string FROM duckdb_secrets() WHERE name = ?",
        [secret_name(location)],
    ).fetchone()
    return dict(part.split("=", 1) for part in row[0].split(";"))


class FakeConn:
    """Stands in for a DuckDB connection where real SQL isn't needed."""

    def __init__(self):
        self.registered = []
        self.executed = []

    def register_filesystem(self, fs):
        self.registered.append(fs)

    def execute(self, sql, params=None):
        self.executed.append(sql)


# --- dispatch ---

@pytest.mark.parametrize(
    "location,expected_cls",
    [
        ("s3://bucket/path", S3Backend),
        ("gs://bucket/path", GCSBackend),
        ("gcs://bucket/path", GCSBackend),
        ("/absolute/path", LocalBackend),
        ("relative/path", LocalBackend),
    ],
)
def test_resolve_backend_dispatch(location, expected_cls):
    assert isinstance(resolve_backend(location), expected_cls)


def test_resolve_backend_returns_fresh_instances():
    assert resolve_backend("s3://b/p") is not resolve_backend("s3://b/p")


# --- normalize ---

def test_gcs_normalize_rewrites_alias():
    assert GCSBackend().normalize("gcs://bucket/path") == "gs://bucket/path"


def test_gcs_normalize_keeps_canonical():
    assert GCSBackend().normalize("gs://bucket/path") == "gs://bucket/path"


def test_local_normalize_is_identity():
    assert LocalBackend().normalize("data/focus-export") == "data/focus-export"


# --- exists ---

def test_local_exists_checks_filesystem(tmp_path):
    backend = LocalBackend()
    assert backend.exists(str(tmp_path))
    assert not backend.exists(str(tmp_path / "missing"))


def test_remote_exists_always_true():
    assert S3Backend().exists("s3://no-such-bucket/x")
    assert GCSBackend().exists("gs://no-such-bucket/x")


# --- prepare: local ---

def test_local_prepare_loads_no_extensions(conn):
    hint = LocalBackend().prepare(conn, "data/focus-export")
    assert hint is None
    assert "httpfs" not in loaded_extensions(conn)


# --- prepare: s3 ---

def test_s3_prepare_creates_secret_and_loads_httpfs(conn):
    hint = S3Backend().prepare(conn, "s3://bucket/path")
    assert hint is None
    assert "aws_s3_secret" in secret_names(conn)
    assert "httpfs" in loaded_extensions(conn)


# --- prepare: gcs tiers ---

def _clear_hmac_env(monkeypatch):
    monkeypatch.delenv("GCS_HMAC_KEY_ID", raising=False)
    monkeypatch.delenv("GCS_HMAC_SECRET", raising=False)


def test_gcs_hmac_tier(conn, monkeypatch):
    monkeypatch.setenv("GCS_HMAC_KEY_ID", "dummy-key")
    monkeypatch.setenv("GCS_HMAC_SECRET", "dummy-secret")
    hint = GCSBackend().prepare(conn, "gs://bucket/path")
    assert hint is None
    assert "gcs_hmac_secret" in secret_names(conn)
    assert "httpfs" in loaded_extensions(conn)


def test_gcs_adc_tier_registers_filesystem_without_httpfs(monkeypatch):
    _clear_hmac_env(monkeypatch)
    fake_gcsfs = types.ModuleType("gcsfs")

    class FakeFS:
        pass

    fake_gcsfs.GCSFileSystem = FakeFS
    monkeypatch.setitem(sys.modules, "gcsfs", fake_gcsfs)

    fake_conn = FakeConn()
    hint = GCSBackend().prepare(fake_conn, "gs://bucket/path")
    assert hint is None
    assert len(fake_conn.registered) == 1
    assert isinstance(fake_conn.registered[0], FakeFS)
    # httpfs must NOT be loaded on the adc tier: no SQL was executed at all
    assert fake_conn.executed == []


def test_gcs_keyless_tier_returns_hint(conn, monkeypatch):
    _clear_hmac_env(monkeypatch)
    # A None entry in sys.modules makes `import gcsfs` raise ImportError
    monkeypatch.setitem(sys.modules, "gcsfs", None)
    hint = GCSBackend().prepare(conn, "gs://bucket/path")
    assert hint is not None
    assert hint == (
        "Failed to read gs://bucket/path without GCS credentials. "
        "Set GCS_HMAC_KEY_ID and GCS_HMAC_SECRET, or install "
        "the gcs extra (pip install 'focus-mcp[gcs]') to use "
        "Application Default Credentials."
    )
    assert "httpfs" in loaded_extensions(conn)


def test_request_keys_get_one_secret_per_location_and_never_an_open_one(conn):
    # A dataset spans several locations, so their secrets cannot share a
    # name; and a stray path outside them must not pick the keys up
    keys = Credentials("AKIA", "secret", "", "us-east-1")
    S3Backend().prepare(conn, "s3://one/prefix", keys)
    S3Backend().prepare(conn, "s3://two/prefix", keys)
    assert secret_scopes(conn) == {("s3://one/prefix/",), ("s3://two/prefix/",)}


def test_a_location_region_beats_the_session_region(conn):
    keys = Credentials("AKIA", "secret", "", "us-east-1")
    S3Backend().prepare(conn, "s3://one/prefix", keys, region="eu-west-1")
    S3Backend().prepare(conn, "s3://two/prefix", keys)
    assert secret_fields(conn, "s3://one/prefix")["region"] == "eu-west-1"
    # No region for this one: the session default it was sent with applies
    assert secret_fields(conn, "s3://two/prefix")["region"] == "us-east-1"


def test_without_any_request_region_the_configured_one_applies(conn):
    S3Backend().prepare(conn, "s3://one/prefix")
    assert secret_fields(conn, "s3://one/prefix")["region"] == config.AWS_REGION
