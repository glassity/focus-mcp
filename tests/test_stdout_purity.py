"""Diagnostics must not go to stdout.

For a stdio MCP server, stdout carries JSON-RPC protocol traffic. A stray
human-readable line desynchronises any client that frames strictly. The
loaders here print on two paths: queries.py at import time, before the
handshake, and spec_loader.py lazily from get_spec_loader(), which can emit
in the middle of an established session.
"""

import importlib

from focus_mcp.spec_loader import FocusSpecLoader


def test_spec_loader_diagnostics_avoid_stdout(capsys):
    FocusSpecLoader()
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "column definitions" in captured.err


def test_spec_loader_warnings_avoid_stdout(capsys, tmp_path):
    FocusSpecLoader(spec_dir=str(tmp_path))
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not found" in captured.err


def test_query_loading_diagnostics_avoid_stdout(capsys):
    import focus_mcp.queries as queries_module

    importlib.reload(queries_module)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "queries for FOCUS" in captured.err
