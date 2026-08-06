"""FOCUS MCP server: query FOCUS billing data over the Model Context Protocol."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("focus-mcp")
except PackageNotFoundError:  # running from a source tree with no install
    __version__ = "0.0.0.dev0"

__all__ = ["__version__"]
