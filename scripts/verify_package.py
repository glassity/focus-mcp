#!/usr/bin/env python3
"""Prove a built wheel or sdist installs clean and serves MCP from a foreign directory.

Usage:
    uv run python scripts/verify_package.py dist/focus_mcp-0.3.0-py3-none-any.whl
    uv run python scripts/verify_package.py dist/focus_mcp-0.3.0.tar.gz

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
import threading
import zipfile
from pathlib import Path

REQUIRED_MEMBERS = [
    "focus_mcp/server.py",
    "focus_mcp/paths.py",
    "focus_mcp/resources/specifications/columns.yaml",
    "focus_mcp/resources/specifications/attributes.yaml",
]

# Query collections are directories of files rather than one named file, so
# the wheel is checked for a populated collection instead of a fixed path.
# Only curated/ ships: upstream/ is the baseline CI compares against and no
# runtime code reads it, so packaging it would double the payload for data
# no user can reach.
REQUIRED_PREFIXES = ["focus_mcp/resources/queries/curated/"]
FORBIDDEN_PREFIXES = ["focus_mcp/resources/queries/upstream/"]

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

    empty = [
        prefix
        for prefix in REQUIRED_PREFIXES
        if not any(name.startswith(prefix) and name.endswith(".yaml") for name in names)
    ]
    if empty:
        raise SystemExit(f"wheel carries no query files under: {empty}")

    shipped = [p for p in FORBIDDEN_PREFIXES
               if any(name.startswith(p) for name in names)]
    if shipped:
        raise SystemExit(f"wheel should not carry: {shipped}")

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
    from mcp.client import Client
    from mcp.client.stdio import StdioServerParameters

    env = dict(os.environ)
    env["FOCUS_DATA_LOCATION"] = str(cwd / "no-such-data")

    params = StdioServerParameters(command=str(script), args=[], env=env, cwd=str(cwd))
    async with Client(params) as client:
        listed = await client.list_tools()
        names = {tool.name for tool in listed.tools}
        if not EXPECTED_TOOLS.issubset(names):
            raise SystemExit(f"missing tools: {sorted(EXPECTED_TOOLS - names)}")
        print(f"handshake OK, {len(names)} tools advertised")

        result = await client.call_tool("list_columns", {})
        payload = json.loads(result.content[0].text)
        total = payload.get("result", {}).get("total_columns", 0)
        if total <= 0:
            raise SystemExit(f"list_columns returned no columns: {payload}")
        print(f"list_columns OK, {total} columns from a foreign working directory")


def check_stdout_purity(script: Path, cwd: Path) -> None:
    """Prove the console script writes nothing but JSON-RPC to stdout.

    The spec is explicit: a stdio server MUST NOT write anything to stdout
    that is not a valid MCP message. handshake() cannot catch a violation
    because the Python `mcp` client silently skips lines it cannot parse, so
    this drives the exchange by hand and reads the raw stream.

    The tools/call for list_columns triggers the server's lazy
    get_spec_loader() path, where a stray print() would land mid-session.
    PYTHONUNBUFFERED=1 is required: without it a stray print() sits in block
    buffering and disappears at exit, hiding the regression this exists to
    catch.
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

    # Closing stdin is how a client signals shutdown, so it has to wait until
    # the tools/call reply arrives; communicate() would send both at once and
    # the server can exit before flushing the reply.
    collected: list[str] = []
    reply_seen = threading.Event()

    def drain_stdout() -> None:
        for line in proc.stdout:
            collected.append(line)
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict) and parsed.get("id") == 2:
                reply_seen.set()

    reader = threading.Thread(target=drain_stdout, daemon=True)
    reader.start()

    proc.stdin.write(stdin_text)
    proc.stdin.flush()
    got_reply = reply_seen.wait(timeout=60)

    try:
        proc.stdin.close()
    except OSError:
        pass
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    reader.join(timeout=10)

    stdout = "".join(collected)
    stderr = proc.stderr.read()

    if not got_reply:
        raise SystemExit(
            "raw MCP exchange never produced a list_columns reply within 60s, so this "
            f"check did not exercise the mid-session get_spec_loader() path; "
            f"exit code {proc.returncode}, stdout:\n{stdout}\nstderr:\n{stderr}"
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
