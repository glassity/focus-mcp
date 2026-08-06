"""Tests for which queries load at a given FOCUS_VERSION.

The library is tagged up to the newest spec release it has been reviewed
against, so a configured version newer than every tag must still get the
queries that do work rather than an empty library.
"""

import pytest

from focus_mcp.queries import version_satisfies


@pytest.mark.parametrize("configured, supported, expected", [
    # a version the query lists
    ("v1.2", ["v1.0", "v1.1", "v1.2"], True),
    ("v1.0", ["v1.0", "v1.1", "v1.2"], True),
    ("v1.2", ["v1.2"], True),
    # newer than everything the query lists
    ("v1.3", ["v1.0", "v1.1", "v1.2"], True),
    ("v1.4", ["v1.2"], True),
    ("v1.10", ["v1.2"], True),
    # older than the query supports: it uses columns that did not exist yet
    ("v1.0", ["v1.2"], False),
    ("v1.1", ["v1.2"], False),
    ("v1.0", ["v1.1", "v1.2"], False),
    # untagged queries are not served
    ("v1.2", [], False),
])
def test_version_satisfies(configured, supported, expected):
    assert version_satisfies(configured, supported) is expected


def test_1_10_sorts_after_1_9_not_before():
    # string comparison would put "v1.10" below "v1.9"
    assert version_satisfies("v1.10", ["v1.9"]) is True
    assert version_satisfies("v1.9", ["v1.10"]) is False


def test_newer_version_loads_the_existing_library(monkeypatch):
    from focus_mcp import config, queries

    monkeypatch.setattr(config, "FOCUS_VERSION", "1.2")
    at_1_2 = len(queries.QueryLoader().queries)
    monkeypatch.setattr(config, "FOCUS_VERSION", "1.4")
    at_1_4 = len(queries.QueryLoader().queries)

    assert at_1_2 > 0
    # Exact-string matching made this zero, silently.
    assert at_1_4 == at_1_2
