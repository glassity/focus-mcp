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

import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional
import focus_config


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
    """
    name: str
    description: str
    query: str
    focus_versions: List[str] = field(default_factory=list)
    citation: str = ""
    slug: str = ""


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
        self.adjustments: Dict[str, dict] = {}  # Store raw adjustments with comments
        self._load_queries()

    def _load_queries(self):
        """
        Load all queries from the YAML file and filter by FOCUS version.

        The loading process:
        1. Loads the comprehensive YAML file with all use cases
        2. Loads adjustments from focus_query_adjustments.yaml
        3. Applies adjustments by overriding fields
        4. Filters queries based on configured FOCUS_VERSION
        5. Converts YAML data to Query objects with full metadata
        6. Indexes queries by slug for flexible access

        This approach provides version-specific query sets while maintaining
        all metadata from the focus.finops.org website.
        """
        # Find the YAML files in resources/queries
        package_dir = Path(__file__).parent
        yaml_file = package_dir / "resources" / "queries" / "focus_use_cases.yaml"
        adjustments_file = package_dir / "resources" / "queries" / "focus_use_cases_adjustments.yaml"

        if not yaml_file.exists():
            print(f"Warning: Query file {yaml_file} does not exist")
            print("Run 'python scrape_to_yaml.py' to generate it")
            return

        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                all_queries = yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading queries from {yaml_file}: {e}")
            return

        # Load adjustments if file exists
        if adjustments_file.exists():
            try:
                with open(adjustments_file, 'r', encoding='utf-8') as f:
                    self.adjustments = yaml.safe_load(f) or {}
                print(f"Loaded {len(self.adjustments)} query adjustments")
            except Exception as e:
                print(f"Error loading adjustments from {adjustments_file}: {e}")
                self.adjustments = {}

        # Normalize the configured version (e.g., "1.0" -> "v1.0")
        configured_version = f"v{focus_config.FOCUS_VERSION}"

        # Process each query
        for key, query_data in all_queries.items():
            # Apply adjustments if they exist for this query
            if key in self.adjustments:
                adjustment = self.adjustments[key]
                # Override fields from adjustment (except fix_comment)
                for field, value in adjustment.items():
                    if field != 'fix_comment':
                        query_data[field] = value

            # Filter by FOCUS version
            focus_versions = query_data.get('focus_versions', [])
            if configured_version not in focus_versions:
                continue  # Skip queries not compatible with configured version

            # Create Query object with all metadata
            query = Query(
                name=query_data.get('title', ''),
                description=query_data.get('description', ''),
                query=query_data.get('sql', ''),
                focus_versions=focus_versions,
                citation=query_data.get('source_url', ''),
                slug=query_data.get('slug', key)
            )

            # Index by slug (key)
            self.queries[key] = query

        print(f"Loaded {len(self.queries)} queries for FOCUS {focus_config.FOCUS_VERSION}")

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
        info.append(f"\nSQL Preview:")
        info.append(sql_preview)

        # Add source
        if query.citation:
            info.append(f"\nSource: {query.citation}")

        return "\n".join(info)


# Global query loader instance
# Initialized at module import to pre-load all available queries
# This singleton pattern ensures queries are loaded once and cached
focus_queries = QueryLoader()
