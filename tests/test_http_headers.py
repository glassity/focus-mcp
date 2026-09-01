"""Over HTTP a request declares its datasets in headers and reads only those.

The shared server holds no tenant configuration: what the request may read
arrives with it (X-Focus-Datasets), and the keys to read it with (X-Aws-*)
are used for that request's connection only.
"""

import importlib
import json
import socket
import threading

import pytest
import uvicorn
from mcp.client import Client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from focus_mcp import config

import duckdb

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def sample(tmp_path):
    """A one-row FOCUS export with the columns get_data_info summarises."""
    directory = tmp_path / "sample" / "billing_period=2026-07"
    directory.mkdir(parents=True)
    conn = duckdb.connect()
    conn.execute(f"""
        COPY (SELECT 'AWS' AS ProviderName, 'Amazon EC2' AS ServiceName,
                     TIMESTAMP '2026-07-01' AS BillingPeriodStart, TIMESTAMP '2026-08-01' AS BillingPeriodEnd,
                     12.5 AS BilledCost, 12.5 AS EffectiveCost)
        TO '{directory}/part.parquet' (FORMAT parquet)
    """)
    conn.close()
    return tmp_path / "sample"


def connect(url, **headers):
    return Client(streamable_http_client(url, http_client=create_mcp_http_client(headers=headers or None)))


@pytest.fixture
def http_server(monkeypatch):
    monkeypatch.setenv("FOCUS_TRANSPORT", "streamable-http")
    monkeypatch.setenv("FOCUS_DATA_LOCATION", "/nowhere/on/the/host")
    importlib.reload(config)
    from focus_mcp import server

    server = importlib.reload(server)

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = server.mcp.streamable_http_app(stateless_http=True, json_response=True)
    uv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    while not uv.started:
        pass
    yield f"http://127.0.0.1:{port}/mcp", server
    uv.should_exit = True
    thread.join(timeout=5)
    server.pool.close_all()

    monkeypatch.delenv("FOCUS_TRANSPORT")
    monkeypatch.delenv("FOCUS_DATA_LOCATION")
    importlib.reload(config)
    importlib.reload(server)


async def test_the_request_names_what_it_reads(http_server, sample):
    url, _ = http_server
    datasets = f"sample={sample}, other=/nowhere/else"
    async with connect(url, **{"X-Focus-Datasets": datasets, "X-Focus-Version": "1.2"}) as client:
        # The client mirrors x-mcp-header arguments into headers only once
        # it has seen the tool's schema, so list first.
        await client.list_tools()
        info = json.loads((await client.call_tool("get_data_info", {})).content[0].text)["result"]
        assert info["dataset"] == "sample"
        assert info["available_datasets"] == ["sample", "other"]
        assert info["focus_version"] == "1.2"
        assert info["row_count"] > 0

        unknown = json.loads((await client.call_tool("get_data_info", {"dataset": "host"})).content[0].text)
        assert unknown == {"error": "Unknown dataset 'host'. This request may read: sample, other."}


async def test_a_request_without_datasets_sees_the_host_default(http_server):
    url, _ = http_server
    async with connect(url) as client:
        await client.list_tools()
        info = json.loads((await client.call_tool("get_data_info", {})).content[0].text)["result"]
        assert info["status"] == "no_data"
        assert info["data_location"] == "/nowhere/on/the/host"


async def test_keys_are_pooled_per_request_not_shared(http_server, sample):
    url, server = http_server
    headers = {"X-Focus-Datasets": f"sample={sample}"}
    async with connect(url, **headers) as client:
        await client.list_tools()
        await client.call_tool("get_data_info", {})
    async with connect(url, **headers, **{"X-Aws-Access-Key-Id": "AKIA1", "X-Aws-Secret-Access-Key": "s"}) as client:
        await client.list_tools()
        await client.call_tool("get_data_info", {})
    assert sorted(key_id for _, key_id in server.pool._entries) == ["", "AKIA1"]
