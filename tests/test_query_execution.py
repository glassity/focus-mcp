"""Execute every shipped query against synthetic data for its FOCUS version.

The upstream library is written in MySQL dialect and is not tested against
DuckDB, which is why a third of the queries here carry corrections. Binding
alone does not catch a broken JSON extraction or a bad cast, so these tests
run the queries rather than merely preparing them.
"""

from pathlib import Path

import duckdb
import pytest
import yaml

from focus_mcp import config, queries

from .focus_fixtures import build_table

VERSIONS = ["1.0", "1.1", "1.2"]
# The specification describes Tags and SkuPriceDetails as JSON; AWS Data
# Exports deliver them as MAP. Queries must work against both.
SHAPES = ["json", "map"]

with open(Path(__file__).parent / "query_params.yaml", encoding="utf-8") as f:
    PARAMS = yaml.safe_load(f)


def load_for(version, monkeypatch):
    monkeypatch.setattr(config, "FOCUS_VERSION", version)
    return queries.QueryLoader().queries


@pytest.fixture
def conn():
    c = duckdb.connect()
    yield c
    c.close()


@pytest.mark.parametrize("version", VERSIONS)
@pytest.mark.parametrize("shape", SHAPES)
def test_every_query_executes(version, shape, conn, monkeypatch):
    build_table(conn, version, json_shape=shape)
    loaded = load_for(version, monkeypatch)
    assert loaded, f"FOCUS {version} loaded no queries"

    failures = []
    for key, query in loaded.items():
        params = PARAMS.get(key, [])
        try:
            conn.execute(query.query, params).fetchall()
        except Exception as e:
            failures.append(f"{key}: {type(e).__name__}: {str(e).splitlines()[0]}")

    assert not failures, (
        f"FOCUS {version} ({shape} columns) query failures:\n  "
        + "\n  ".join(failures)
    )


@pytest.mark.parametrize("version", VERSIONS)
def test_every_query_has_matching_parameters(version, monkeypatch):
    loaded = load_for(version, monkeypatch)
    wrong = [
        f"{key}: sql takes {query.query.count('?')}, "
        f"fixture supplies {len(PARAMS.get(key, []))}"
        for key, query in loaded.items()
        if len(PARAMS.get(key, [])) != query.query.count("?")
    ]
    assert not wrong, (
        "tests/query_params.yaml is out of step with the queries:\n  "
        + "\n  ".join(wrong)
    )


@pytest.mark.parametrize("version", VERSIONS)
def test_queries_only_use_columns_that_exist_at_their_version(
    version, conn, monkeypatch
):
    # A query reaching for a later version's column is the failure mode the
    # per-version schema exists to catch; execution above would surface it,
    # but this names the column rather than reporting a binder error.
    build_table(conn, version)
    present = {
        row[0].lower()
        for row in conn.execute("DESCRIBE focus_data_table").fetchall()
    }
    loaded = load_for(version, monkeypatch)

    missing = []
    for key, query in loaded.items():
        try:
            conn.execute(f"PREPARE _c AS {query.query}")
            conn.execute("DEALLOCATE _c")
        except duckdb.Error as e:
            message = str(e).splitlines()[0]
            if "not found" in message or "does not exist" in message:
                missing.append(f"{key}: {message}")
    assert not missing, (
        f"queries referencing columns absent from FOCUS {version}:\n  "
        + "\n  ".join(missing)
    )
    assert "billedcost" in present


def test_the_fixture_grows_with_the_specification():
    from .focus_fixtures import columns_for

    counts = {v: len(columns_for(v)) for v in VERSIONS}
    assert counts["1.0"] < counts["1.1"] < counts["1.2"], counts
