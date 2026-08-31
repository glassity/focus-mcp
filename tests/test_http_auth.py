"""Over HTTP with a catalog, the bearer token is required and reaches the catalog.

The server cannot judge an opaque token itself; what matters is that no
request without one gets to a tool, and that the one presented is what the
catalog is asked with, since the catalog answers per token.
"""

import importlib
import json
import socket
import threading

import httpx
import pytest
import uvicorn
from mcp.client import Client
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from focus_mcp import config

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def connect(url, token=None):
    headers = {"Authorization": f"Bearer {token}"} if token else None
    return Client(streamable_http_client(url, http_client=create_mcp_http_client(headers=headers)))


class RecordingCatalog:
    """Stands in for the HTTP catalog: remembers the bearer it was asked with."""

    def __init__(self):
        self.tokens = []

    def get(self, url, headers=None, timeout=None):
        self.tokens.append(headers.get("Authorization"))

        class Response:
            status_code = 404

            def json(self):
                return {}

        return Response()


@pytest.fixture
def catalog_server(monkeypatch):
    monkeypatch.setenv("FOCUS_CATALOG_URL", "https://app.example/api/focus/datasets")
    monkeypatch.setenv("FOCUS_TRANSPORT", "streamable-http")
    importlib.reload(config)
    from focus_mcp import server

    server = importlib.reload(server)
    recorder = RecordingCatalog()
    server.catalog._http_client = recorder

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    app = server.mcp.streamable_http_app(stateless_http=True, json_response=True)
    uv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=uv.run, daemon=True)
    thread.start()
    while not uv.started:
        pass
    yield f"http://127.0.0.1:{port}/mcp", recorder
    uv.should_exit = True
    thread.join(timeout=5)

    monkeypatch.delenv("FOCUS_CATALOG_URL")
    monkeypatch.delenv("FOCUS_TRANSPORT")
    importlib.reload(config)
    importlib.reload(server)


async def test_a_request_without_a_token_is_rejected_before_any_tool(catalog_server):
    url, recorder = catalog_server
    body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/list",
        "params": {"_meta": {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientInfo": {"name": "t", "version": "1"},
            "io.modelcontextprotocol/clientCapabilities": {},
        }},
    }
    headers = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2026-07-28", "Mcp-Method": "tools/list"}
    async with httpx.AsyncClient() as http:
        response = await http.post(url, json=body, headers=headers)
    assert response.status_code == 401
    assert "resource_metadata" in response.headers.get("www-authenticate", "")
    assert recorder.tokens == []


async def test_the_bearer_is_what_the_catalog_is_asked_with(catalog_server):
    url, recorder = catalog_server
    async with connect(url, "tenant-seven") as client:
        # The client mirrors x-mcp-header arguments into headers only once
        # it has seen the tool's schema; a call before tools/list is
        # rejected by the server as a header/body mismatch.
        await client.list_tools()
        result = await client.call_tool("get_data_info", {"dataset": "aws-1"})
    assert json.loads(result.content[0].text) == {"error": "Unknown dataset 'aws-1'."}
    assert recorder.tokens == ["Bearer tenant-seven"]
