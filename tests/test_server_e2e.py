"""Tool calls through a real MCP client, end to end.

The in-memory client speaks the same protocol as a network one, so this is
what a chat actually sees: the dataset handle chooses which parquet is read,
an unknown handle is a tool error the model can act on, and the version
chooses the query collection.
"""

import json

import duckdb
import pytest
from mcp.client import Client

from focus_mcp import server
from focus_mcp.datasets import Catalog, ConnectionPool

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def write_export(directory, provider, cost):
    sub = directory / "billing_period=2026-01"
    sub.mkdir(parents=True)
    c = duckdb.connect()
    c.execute(
        f"COPY (SELECT '{provider}' AS ProviderName, 'svc' AS ServiceName, {cost}::DOUBLE AS BilledCost, "
        f"{cost}::DOUBLE AS EffectiveCost, DATE '2026-01-01' AS BillingPeriodStart, "
        f"DATE '2026-02-01' AS BillingPeriodEnd) TO '{sub}/part.parquet' (FORMAT parquet)"
    )
    c.close()


@pytest.fixture
def two_datasets(tmp_path, monkeypatch):
    write_export(tmp_path / "acme", "AWS", 10.0)
    write_export(tmp_path / "globex", "GCP", 20.0)
    monkeypatch.setattr(
        server,
        "catalog",
        Catalog(
            default_location=str(tmp_path / "acme"),
            default_version="1.0",
            datasets={
                "acme": {"location": str(tmp_path / "acme"), "version": "1.2"},
                "globex": {"location": str(tmp_path / "globex"), "version": ""},
            },
            allow_raw_locations=False,
        ),
    )
    pool = ConnectionPool(max_size=4)
    monkeypatch.setattr(server, "pool", pool)
    yield
    pool.close_all()


def payload(result):
    return json.loads(result.content[0].text)


async def test_each_handle_reads_its_own_data(two_datasets):
    async with Client(server.mcp) as client:
        default = payload(await client.call_tool("get_data_info", {}))
        acme = payload(await client.call_tool("get_data_info", {"dataset": "acme"}))
        globex = payload(await client.call_tool("get_data_info", {"dataset": "globex"}))

    assert default["result"]["total_cost"] == 10.0 and default["result"]["dataset"] is None
    assert acme["result"]["total_cost"] == 10.0 and acme["result"]["focus_version"] == "1.2"
    assert globex["result"]["providers"]["samples"] == ["GCP"]
    assert globex["result"]["focus_version"] == "1.0"


async def test_execute_query_binds_to_the_named_dataset(two_datasets):
    async with Client(server.mcp) as client:
        result = payload(
            await client.call_tool(
                "execute_query",
                {"query": "SELECT ProviderName, BilledCost FROM focus_data_table", "dataset": "globex"},
            )
        )
    assert result["result"]["data"] == [{"ProviderName": "GCP", "BilledCost": 20.0}]
    assert result["result"]["dataset"] == "globex"


async def test_unknown_handle_is_an_error_the_model_can_recover_from(two_datasets):
    async with Client(server.mcp) as client:
        result = payload(await client.call_tool("execute_query", {"query": "SELECT 1", "dataset": "initech"}))
    assert result == {"error": "Unknown dataset 'initech'. Known datasets: acme, globex."}


async def test_raw_locations_are_not_accepted_by_name(two_datasets, tmp_path):
    async with Client(server.mcp) as client:
        result = payload(await client.call_tool("get_data_info", {"dataset": str(tmp_path / "globex")}))
    assert "Unknown dataset" in result["error"]


async def test_version_selects_the_query_collection(two_datasets):
    async with Client(server.mcp) as client:
        v10 = payload(await client.call_tool("list_use_cases", {}))
        v14 = payload(await client.call_tool("list_use_cases", {"focus_version": "1.4"}))
    assert v10["result"]["focus_version"] == "1.0"
    assert v14["result"]["focus_version"] == "1.4"
    assert v14["result"]["total"] > v10["result"]["total"]
