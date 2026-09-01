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

# Derived, not listed: a new curated/<version>/ directory must arrive with
# execution coverage rather than being shippable by mkdir alone.
VERSIONS = queries.available_versions()
# The specification describes Tags and SkuPriceDetails as JSON; AWS Data
# Exports deliver them as MAP. Queries must work against both.
SHAPES = ["json", "map"]

# Queries the fixture cannot yet satisfy: they filter on data shapes the
# synthetic rows do not produce (multi-provider commitment programmes,
# unit-economics denominators, accrual-vs-cash splits). They are executed,
# but their results are not verified, so keep this list shrinking rather
# than growing. Anything not listed here must return rows - a query that
# silently matches nothing is how a broken JSON extraction ships.
UNVERIFIED_RESULTS = {
    "calculate_unit_economics",
    "cash_vs_accrual_comparison_by_billing_period",
    "compare_commitment_opportunities_across_providers_cross_provider_with_saas",
    "discount_effectiveness_by_service",
    "identify_eligible_capacity_reservation_spend",
    "identify_eligible_uncovered_spend_by_program_type",
    "recurring_commitment_charges",
    "service_costs_subaccount",
}

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
    # A YAML error is reported and skipped, so count the files too: the
    # collection must not shrink quietly.
    on_disk = len(list(
        (Path(queries.resource_path("queries", "curated", version))).glob("*.yaml")
    ))
    assert len(loaded) == on_disk, (
        f"FOCUS {version}: {on_disk} query files but {len(loaded)} loaded"
    )

    failures, empty, unexpected_rows = [], [], []
    for key, query in loaded.items():
        params = PARAMS.get(key, [])
        try:
            rows = conn.execute(query.query, params).fetchall()
        except Exception as e:
            failures.append(f"{key}: {type(e).__name__}: {str(e).splitlines()[0]}")
            continue
        if not rows and key not in UNVERIFIED_RESULTS:
            empty.append(key)
        if rows and key in UNVERIFIED_RESULTS:
            unexpected_rows.append(key)

    assert not failures, (
        f"FOCUS {version} ({shape} columns) query failures:\n  "
        + "\n  ".join(failures)
    )
    # Executing is not the same as working: a query whose filters match
    # nothing never evaluates the expressions the corrections fixed.
    assert not empty, (
        f"FOCUS {version} ({shape} columns) returned no rows, so nothing "
        "about their results is verified. Seed the fixture to cover them, "
        "or add them to UNVERIFIED_RESULTS with a reason:\n  "
        + "\n  ".join(empty)
    )
    assert not unexpected_rows, (
        f"FOCUS {version} ({shape} columns): listed in UNVERIFIED_RESULTS "
        "but now returning rows - remove them from the list:\n  "
        + "\n  ".join(unexpected_rows)
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

    counts = [len(columns_for(v)) for v in VERSIONS]
    assert counts == sorted(counts), dict(zip(VERSIONS, counts))
    assert len(set(counts)) > 1, "every version has the same column count"


@pytest.mark.parametrize("version", VERSIONS)
def test_every_advertised_id_resolves_back_to_its_query(version, monkeypatch):
    # list_use_cases hands out ids the client passes back to get_use_case
    # and execute_query. A query has two names - the file key and
    # upstream's URL slug, which can differ beyond hyphenation (upstream
    # appends -2 to disambiguate titles; keys are reused across versions
    # when a title changes) - and both must round-trip.
    monkeypatch.setattr(config, "FOCUS_VERSION", version)
    loader = queries.QueryLoader()
    assert loader.queries
    unresolved = [
        name
        for key, query in loader.queries.items()
        for name in (key, query.slug)
        if loader.get_query(name) is not query
    ]
    assert unresolved == [], (
        f"FOCUS {version}: ids that do not resolve to their own query: "
        + ", ".join(unresolved)
    )


@pytest.mark.parametrize("version", VERSIONS)
def test_get_data_info_survives_the_provider_rename(version, conn, monkeypatch):
    # get_data_info aggregates by provider; FOCUS 1.3 renamed ProviderName
    # to ServiceProviderName, so the column has to come from the dataset's
    # schema rather than being hardcoded to either name. The tool itself is
    # called, not a re-implementation of its SQL, so hardcoding either name
    # anywhere in its path fails here.
    import asyncio

    from focus_mcp import server

    from focus_mcp.datasets import Connection

    build_table(conn, version)
    monkeypatch.setattr(server.pool, "get", lambda location, credentials=None: Connection(conn, location, "glob", 0.0))
    result = asyncio.run(server.get_data_info())
    assert "error" not in result, f"FOCUS {version}: {result['error']}"
    summary = result["result"]
    assert summary["row_count"] == 13
    assert summary["providers"]["count"] > 0
    assert "AWS" in summary["providers"]["samples"], (version, summary)


def test_provider_expression_prefers_the_newer_name():
    from focus_mcp.server import provider_expression

    # A union_by_name dataset spanning the rename carries both, half-null.
    both = provider_expression(["ProviderName", "ServiceProviderName"])
    assert both == "COALESCE(ServiceProviderName, ProviderName)"
    assert provider_expression(["BilledCost"]) == "NULL"
