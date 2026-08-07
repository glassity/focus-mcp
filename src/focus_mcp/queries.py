#!/usr/bin/env python3
"""
FOCUS Query Library - Dynamic query loader for FOCUS billing analytics.

This module provides a structured way to load and manage predefined analytical
queries for FOCUS (FinOps Open Cost and Usage Specification) billing data.
Each FOCUS version has its own directory of query files under
resources/queries/curated/, so the directory listing is the collection for
that version and the SQL on disk is the SQL that runs.

The query library provides:
- One curated collection per FOCUS version
- Comprehensive metadata including columns and parameters
- Parameter descriptions with types and examples
- Column identification for query validation
- Source attribution for all queries
"""

import sys
import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Optional

from packaging.version import InvalidVersion, parse

from . import config
from .paths import resource_path


def available_versions() -> List[str]:
    """FOCUS versions that have a curated collection, oldest first.

    Names that are not versions are ignored rather than raising: this runs
    at import time, so a stray directory would take the server down.
    """
    root = resource_path("queries", "curated")
    if not root.is_dir():
        return []
    found = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        try:
            found.append((parse(entry.name), entry.name))
        except InvalidVersion:
            continue
    return [name for _, name in sorted(found)]


@dataclass
class Query:
    """
    Represents a single FOCUS analytical query with comprehensive metadata.

    This class encapsulates all information needed to execute, understand,
    and validate a FOCUS billing query, including the SQL text and metadata.

    Attributes:
        name: Human-readable name of the query
        description: Description of what the query analyzes
        query: The SQL text with ? placeholders for parameters
        focus_versions: FOCUS specification versions this query supports
        citation: Source URL from focus.finops.org
        slug: URL-friendly identifier
        adapted: Whether the SQL departs from upstream's, which CC BY
            requires be stated alongside the attribution
    """
    name: str
    description: str
    query: str
    focus_versions: List[str] = field(default_factory=list)
    citation: str = ""
    slug: str = ""
    adapted: bool = False


class QueryLoader:
    """
    Manages loading and accessing FOCUS analytical queries from JSON.

    This class loads all FOCUS use cases from a comprehensive JSON file
    and filters them based on the configured FOCUS version. It provides
    rich metadata for each query including columns, parameters, and descriptions.

    The loader automatically filters queries at initialization based on
    the FOCUS_VERSION environment variable and provides methods to access
    queries by ID, slug, or iterate through all available queries.
    """

    def __init__(self):
        """Initialize the query loader and load version-specific queries."""
        self.queries: Dict[str, Query] = {}
        self._load_queries()

    def _load_queries(self):
        """
        Load the curated collection for the configured FOCUS version.

        Each version has its own directory of query files, so the listing
        is the collection: no tags to filter and no overlay applied here,
        which means the SQL on disk is the SQL that runs. Corrections to
        upstream's text live in the file itself, marked by fix_comment and
        checked against resources/queries/upstream/ in CI.
        """
        version = config.FOCUS_VERSION
        available = available_versions()
        # Checked against the listing rather than trusted as a path
        # component: "../upstream/1.4" is a real directory, and loading it
        # would serve upstream's untested SQL as though it were ours.
        folder = (
            resource_path("queries", "curated", version)
            if version in available
            else None
        )

        if folder is None or not folder.is_dir():
            print(
                f"No query collection for FOCUS {version}; "
                f"available: {', '.join(available) or 'none'}",
                file=sys.stderr,
            )
            return

        for path in sorted(folder.glob("*.yaml")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict):
                    raise ValueError("expected a mapping")
                self.queries[path.stem] = Query(
                    name=data.get("title", ""),
                    description=data.get("description", ""),
                    query=data.get("sql", ""),
                    focus_versions=[f"v{version}"],
                    citation=data.get("source_url", ""),
                    slug=data.get("slug", path.stem),
                    adapted=bool(data.get("fix_comment")),
                )
            except Exception as e:
                # The loader runs at import, so one bad file must cost one
                # query rather than the whole server. CI counts files
                # against queries loaded, so it cannot pass unnoticed.
                print(f"Error loading query {path}: {e}", file=sys.stderr)

        print(
            f"Loaded {len(self.queries)} queries for FOCUS {version}",
            file=sys.stderr,
        )

    def get_query(self, query_identifier: str) -> Optional[Query]:
        """
        Retrieve a specific query by key or upstream slug.

        A query has two names: the file key (underscored) and upstream's
        URL slug, which appears in source_url and is not always the key
        with hyphens - upstream disambiguates duplicate titles with -2
        suffixes and keys are reused across versions when a title changes.
        Both must resolve, or an id shown to the client comes back
        "not found" when passed back in.

        Args:
            query_identifier: The query key or its focus.finops.org slug

        Returns:
            Query object if found, None otherwise
        """
        query = self.queries.get(query_identifier)
        if query is None:
            # Exact slug before the lossy hyphen transform, so a slug
            # whose underscored form collides with another query's key
            # still resolves to its own query.
            query = next(
                (q for q in self.queries.values()
                 if q.slug == query_identifier),
                None,
            )
        if query is None:
            query = self.queries.get(query_identifier.replace("-", "_"))
        return query

    def list_queries(self) -> List[Dict[str, str]]:
        """
        List all available queries with basic metadata.

        Returns:
            List of dictionaries with query metadata for display
        """
        return [
            {
                'slug': query.slug,
                'name': query.name,
                'description': query.description or 'No description available',
                'parameter_count': query.query.count('?'),
                'versions': ', '.join(query.focus_versions)
            }
            for query in self.queries.values()
        ]

    def get_query_info(self, query: Query) -> str:
        """
        Generate comprehensive information about a query for the LLM.

        This method creates a detailed description of the query that helps
        the LLM understand what parameters are needed and how to use the query.

        Args:
            query: The Query object to describe

        Returns:
            Formatted string with complete query information
        """
        info = []
        info.append(f"Query: {query.name}")

        if query.description:
            info.append(f"Description: {query.description}")

        info.append(f"\nFOCUS Versions: {', '.join(query.focus_versions)}")

        # Just show parameter count from SQL
        param_count = query.query.count('?')
        if param_count > 0:
            info.append(f"\nParameters Required: {param_count}")

        # Add SQL preview
        sql_preview = query.query[:200] + "..." if len(query.query) > 200 else query.query
        info.append("\nSQL Preview:")
        info.append(sql_preview)

        # Add source. The library is CC BY 4.0, which requires both the
        # attribution and a statement of whether the work was modified.
        if query.citation:
            adapted = " - adapted for DuckDB" if query.adapted else ""
            info.append(f"\nSource: {query.citation}")
            info.append(f"(FOCUS use case library, CC BY 4.0{adapted})")

        return "\n".join(info)


# Global query loader instance
# Initialized at module import to pre-load all available queries
# This singleton pattern ensures queries are loaded once and cached
focus_queries = QueryLoader()
