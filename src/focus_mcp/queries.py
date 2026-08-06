#!/usr/bin/env python3
"""
FOCUS Query Library - Dynamic query loader for FOCUS billing analytics.

This module provides a structured way to load and manage predefined analytical
queries for FOCUS (FinOps Open Cost and Usage Specification) billing data.
Queries are loaded from a comprehensive JSON file containing all use cases
from focus.finops.org, with automatic filtering based on the configured
FOCUS version.

The query library provides:
- Version-specific query filtering (v1.0, v1.1, v1.2)
- Comprehensive metadata including columns and parameters
- Parameter descriptions with types and examples
- Column identification for query validation
- Source attribution for all queries
"""

import sys
import yaml
from dataclasses import dataclass, field
from typing import List, Dict, Optional
from packaging.version import parse
from . import config
from .paths import resource_path


def version_satisfies(configured: str, supported: List[str]) -> bool:
    """Whether a query tagged `supported` should load at `configured`.

    A query loads for a version it lists, and for anything newer, since
    the library is only tagged up to the release it was reviewed against.
    Older versions are excluded: a query tagged only v1.2 uses columns
    v1.0 does not have.
    """
    if not supported:
        return False
    if configured in supported:
        return True
    newest = max(parse(v.lstrip('v')) for v in supported)
    return parse(configured.lstrip('v')) > newest


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
        Load all queries from the YAML file and filter by FOCUS version.

        The loading process:
        1. Loads focus_use_cases.yaml, which holds the queries as they run
        2. Filters queries based on configured FOCUS_VERSION
        3. Converts YAML data to Query objects with full metadata
        4. Indexes queries by slug for flexible access

        Corrections to upstream's SQL live in that same file rather than in
        an overlay applied here, so the text on disk is the text that runs.
        Each corrected query carries a fix_comment, and CI checks those
        against upstream/focus_use_cases.yaml.
        """
        # Find the YAML file that ships inside the package
        yaml_file = resource_path("queries", "focus_use_cases.yaml")

        if not yaml_file.exists():
            print(f"Warning: Query file {yaml_file} does not exist", file=sys.stderr)
            print("Run 'python scripts/sync_use_cases.py' to generate it", file=sys.stderr)
            return

        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                all_queries = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading queries from {yaml_file}: {e}", file=sys.stderr)
            return

        # Normalize the configured version (e.g., "1.0" -> "v1.0")
        configured_version = f"v{config.FOCUS_VERSION}"

        # Process each query
        for key, query_data in all_queries.items():
            # Filter by FOCUS version
            focus_versions = query_data.get('focus_versions', [])
            if not version_satisfies(configured_version, focus_versions):
                continue  # Skip queries not compatible with configured version

            # Create Query object with all metadata
            query = Query(
                name=query_data.get('title', ''),
                description=query_data.get('description', ''),
                query=query_data.get('sql', ''),
                focus_versions=focus_versions,
                citation=query_data.get('source_url', ''),
                slug=query_data.get('slug', key),
                adapted=bool(query_data.get('fix_comment'))
            )

            # Index by slug (key)
            self.queries[key] = query

        print(f"Loaded {len(self.queries)} queries for FOCUS {config.FOCUS_VERSION}", file=sys.stderr)

    def get_query(self, query_identifier: str) -> Optional[Query]:
        """
        Retrieve a specific query by its slug identifier.

        Args:
            query_identifier: The query slug (underscore-separated key)

        Returns:
            Query object if found, None otherwise
        """
        return self.queries.get(query_identifier)

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
