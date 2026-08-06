"""Locate data files that ship inside the focus_mcp package.

Resources are addressed through importlib.resources rather than __file__ or a
relative path, so they resolve identically whether the server was started from
a checkout, a wheel installed by uvx, or the Docker image.
"""

from importlib.resources import files
from pathlib import Path


def resource_path(*parts: str) -> Path:
    """Return the absolute path to a file under focus_mcp/resources/.

    Args:
        parts: Path components below the resources directory, for example
            ("specifications", "columns.yaml").

    The package is always installed unzipped, so this yields a real filesystem
    path that DuckDB and PyYAML can open directly.
    """
    return Path(str(files("focus_mcp").joinpath("resources", *parts)))
