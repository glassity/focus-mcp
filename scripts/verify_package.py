#!/usr/bin/env python3
"""Prove a built wheel or sdist installs clean and serves MCP from a foreign directory.

Usage:
    uv run python scripts/verify_package.py dist/focus_mcp-0.2.0-py3-none-any.whl
    uv run python scripts/verify_package.py dist/focus_mcp-0.2.0.tar.gz

Accepts either a wheel (.whl) or an sdist (.tar.gz). Checks, in order:
  1. For a wheel only: it contains exactly one top-level package and no repo
     scaffolding, and the packaged resources are present inside it. An sdist
     legitimately contains tests/, pyproject.toml and other files this check
     would reject, so it does not apply and is skipped for sdists.
  2. Installed into a clean venv and launched from an unrelated working
     directory, the console script completes an MCP handshake and list_columns
     returns a non-empty column set.

Check 2 is the one that matters, for both artifact types. It exercises the
console script, the entry point, package imports, FastMCP wiring and resource
loading in a single assertion, which is the whole failure surface between
"the package built" and "uvx focus-mcp works". For the sdist it additionally
exercises the build-from-source path (installing an sdist makes uv/pip invoke
the build backend), which a wheel install never touches.
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

REQUIRED_MEMBERS = [
    "focus_mcp/server.py",
    "focus_mcp/paths.py",
    "focus_mcp/resources/queries/focus_use_cases.yaml",
    "focus_mcp/resources/specifications/columns.yaml",
    "focus_mcp/resources/specifications/attributes.yaml",
]

EXPECTED_TOOLS = {
    "execute_query",
    "get_attribute_details",
    "get_column_details",
    "get_data_info",
    "get_use_case",
    "list_attributes",
    "list_columns",
    "list_use_cases",
}


def artifact_kind(artifact: Path) -> str:
    if artifact.suffix == ".whl":
        return "wheel"
    if artifact.name.endswith(".tar.gz"):
        return "sdist"
    raise SystemExit(f"unsupported artifact type: {artifact.name} (expected .whl or .tar.gz)")


def check_wheel_contents(wheel: Path) -> None:
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()

    top_level = {name.split("/")[0] for name in names}
    packages = {name for name in top_level if not name.endswith(".dist-info")}
    if packages != {"focus_mcp"}:
        raise SystemExit(
            f"wheel must contain exactly one top-level package 'focus_mcp', found: {sorted(packages)}"
        )

    missing = [member for member in REQUIRED_MEMBERS if member not in names]
    if missing:
        raise SystemExit(f"wheel is missing packaged files: {missing}")

    print(f"wheel contents OK ({len(names)} members)")


def install_into_clean_venv(artifact: Path, venv: Path) -> Path:
    subprocess.run(["uv", "venv", "--python", sys.executable, str(venv)], check=True)
    subprocess.run(
        ["uv", "pip", "install", "--python", str(venv / "bin" / "python"), str(artifact)],
        check=True,
    )
    script = venv / "bin" / "focus-mcp"
    if not script.exists():
        raise SystemExit(f"console script not installed at {script}")
    return script


async def handshake(script: Path, cwd: Path) -> None:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = dict(os.environ)
    env["FOCUS_DATA_LOCATION"] = str(cwd / "no-such-data")

    params = StdioServerParameters(command=str(script), args=[], env=env, cwd=str(cwd))
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            listed = await session.list_tools()
            names = {tool.name for tool in listed.tools}
            if not EXPECTED_TOOLS.issubset(names):
                raise SystemExit(f"missing tools: {sorted(EXPECTED_TOOLS - names)}")
            print(f"handshake OK, {len(names)} tools advertised")

            result = await session.call_tool("list_columns", {})
            payload = json.loads(result.content[0].text)
            total = payload.get("result", {}).get("total_columns", 0)
            if total <= 0:
                raise SystemExit(f"list_columns returned no columns: {payload}")
            print(f"list_columns OK, {total} columns from a foreign working directory")


def check_stdout_purity(script: Path, cwd: Path) -> None:
    """Prove the console script never writes anything but JSON-RPC to stdout.

    The handshake() check above goes through the Python `mcp` client, which
    silently skips any line it cannot parse as JSON-RPC. That leniency is a
    property of that one client, not of the protocol, so handshake() would
    stay green even if a print() statement snuck a human-readable line into
    stdout. This check bypasses the client and inspects the raw byte stream
    instead.

    It drives the same minimal exchange by hand - initialize, then the
    notifications/initialized notification, then a tools/call for
    list_columns - and reads stdout in full once the process exits. The
    list_columns call matters here specifically because it is what triggers
    the lazy get_spec_loader() path inside the server: a check that only
    covered startup would miss a print() reintroduced mid-session, which is
    the more dangerous case since it can desynchronise an already-running
    client.

    PYTHONUNBUFFERED=1 is set for the child on purpose: a stray print() left
    on stdout sits in Python's block-buffered stdout until enough output
    accumulates or the interpreter flushes it, and this process does not
    reliably flush its default stdout on exit (it is double-wrapped by the
    stdio transport's own TextIOWrapper around the same fd, and only that
    wrapper gets flushed). Confirmed empirically: without this flag a single
    reverted print() vanished without a trace on both streams, which would
    have made this check pass over the exact regression it exists to catch.
    """
    env = dict(os.environ)
    env["FOCUS_DATA_LOCATION"] = str(cwd / "no-such-data")
    env["PYTHONUNBUFFERED"] = "1"

    request_messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "verify-package-stdout-purity", "version": "0.0.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "list_columns", "arguments": {}},
        },
    ]
    stdin_text = "".join(json.dumps(message) + "\n" for message in request_messages)

    proc = subprocess.Popen(
        [str(script)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(cwd),
        env=env,
    )
    try:
        stdout, stderr = proc.communicate(input=stdin_text, timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        raise SystemExit(
            f"raw MCP exchange timed out waiting for the server to exit; stderr:\n{stderr}"
        )

    lines = [line for line in stdout.splitlines() if line.strip()]

    saw_list_columns_result = False
    for line in lines:
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as e:
            raise SystemExit(
                f"stdout is not pure JSON-RPC, found a non-JSON line: {line!r} ({e})\n"
                f"full stdout was:\n{stdout}\nstderr was:\n{stderr}"
            )
        if parsed.get("id") == 2 and "result" in parsed:
            saw_list_columns_result = True

    if not saw_list_columns_result:
        raise SystemExit(
            "raw MCP exchange never produced a list_columns result, so this check "
            f"did not exercise the mid-session get_spec_loader() path; "
            f"exit code {proc.returncode}, stdout:\n{stdout}\nstderr:\n{stderr}"
        )

    print(f"stdout purity OK, {len(lines)} line(s) all parsed as JSON-RPC")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_package.py <wheel-or-sdist>")

    artifact = Path(sys.argv[1]).resolve()
    if not artifact.is_file():
        raise SystemExit(f"no such artifact: {artifact}")

    kind = artifact_kind(artifact)
    print(f"verifying {kind}: {artifact.name}")

    if kind == "wheel":
        check_wheel_contents(artifact)
    else:
        print("skipping wheel-content check (not applicable to an sdist)")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        script = install_into_clean_venv(artifact, tmpdir / "venv")
        workdir = tmpdir / "workdir"
        workdir.mkdir()
        asyncio.run(handshake(script, workdir))
        check_stdout_purity(script, workdir)

    print(f"{kind} verification passed")


if __name__ == "__main__":
    main()
