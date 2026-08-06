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

    print(f"{kind} verification passed")


if __name__ == "__main__":
    main()
