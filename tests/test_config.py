"""FOCUS_DATA_LOCATION handling.

Local relative paths are resolved at import time so error messages can name a
path the user can act on. Remote URIs are passed through untouched, because
rewriting them would corrupt the bucket address.
"""

import importlib
from pathlib import Path

import pytest

import focus_mcp.config as config


def test_relative_local_path_becomes_absolute(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FOCUS_DATA_LOCATION", "data/focus-export")
    importlib.reload(config)
    assert config.DATA_LOCATION == str(Path(tmp_path).resolve() / "data" / "focus-export")


def test_absolute_local_path_is_preserved(monkeypatch, tmp_path):
    monkeypatch.setenv("FOCUS_DATA_LOCATION", str(tmp_path))
    importlib.reload(config)
    assert config.DATA_LOCATION == str(Path(tmp_path).resolve())


@pytest.mark.parametrize("uri", ["s3://bucket/prefix", "gs://bucket/prefix", "gcs://bucket/prefix"])
def test_remote_uris_are_untouched(monkeypatch, uri):
    monkeypatch.setenv("FOCUS_DATA_LOCATION", uri)
    importlib.reload(config)
    assert config.DATA_LOCATION == uri


def test_nonexistent_relative_path_still_resolves(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FOCUS_DATA_LOCATION", "nowhere/at/all")
    importlib.reload(config)
    assert config.DATA_LOCATION == str(Path(tmp_path).resolve() / "nowhere" / "at" / "all")


@pytest.fixture(autouse=True)
def _restore_config():
    yield
    importlib.reload(config)
