#!/usr/bin/env python3
"""
FOCUS Query Library - Dynamic SQL query loader for FOCUS billing analytics.

This module provides a structured way to load and manage predefined analytical
queries for FOCUS (FinOps Open Cost and Usage Specification) billing data.
Queries are stored as SQL files with embedded metadata and loaded dynamically
based on the configured FOCUS version.

The query library supports:
- Version-specific query collections
- Metadata extraction from SQL comment headers
- Parameter binding with ? placeholders
- Citation tracking for query sources

Query files are expected to follow this format:
-- Query Name Here
-- Description of what the query does
-- Source: https://focus.finops.org/...
SELECT ...
"""

from pathlib import Path
from dataclasses import dataclass
import focus_config


@dataclass
class Query:
    """
    Represents a single analytical query with metadata.

    This class encapsulates all information needed to execute and understand
    a FOCUS billing query, including the SQL text, human-readable description,
    and source attribution.

    Attributes:
        name: Human-readable name of the query
        description: Brief description of what the query analyzes
        query: The SQL text with ? placeholders for parameters
        citation: Source URL or reference (typically from focus.finops.org)
        filename: Original SQL file name for tracking
    """
    name: str
    description: str
    query: str
    citation: str = ""
    filename: str = ""


class QueryLoader:
    """
    Manages loading and accessing FOCUS analytical queries.

    This class handles the discovery and parsing of SQL query files from
    version-specific directories. It extracts metadata from comment headers
    and provides a simple interface for query retrieval.

    The loader automatically discovers queries at initialization and provides
    methods to access them by name or iterate through all available queries.
    """

    def __init__(self):
        """Initialize the query loader and discover all available queries."""
        self.queries: dict[str, Query] = {}
        self._load_queries()

    def _load_queries(self):
        """
        Discover and load all SQL queries from the version-specific directory.

        The query loading process:
        1. Constructs the path based on FOCUS version (e.g., queries_v1_0)
        2. Scans for all .sql files in that directory
        3. Parses each file to extract metadata and SQL
        4. Stores queries indexed by filename (without .sql extension)

        This approach allows for different query sets per FOCUS version,
        accommodating schema changes and new analytical capabilities.
        """
        base_dir = Path("resources/queries")
        # Convert version like "1.0" to directory name like "queries_v1_0"
        version_dir = f"queries_v{focus_config.FOCUS_VERSION.replace('.', '_')}"
        queries_dir = base_dir / version_dir

        if not queries_dir.exists():
            print(f"Warning: Queries directory {queries_dir} does not exist")
            return

        # Process all SQL files in the version directory
        for sql_file in queries_dir.glob("*.sql"):
            if query := self._parse_file(sql_file):
                # Use filename without extension as the query identifier
                self.queries[sql_file.stem] = query

    def _parse_file(self, filepath: Path) -> Query | None:
        """
        Parse a single SQL file to extract query metadata and SQL content.

        Expected file format:
        -- Query Name (first line)
        -- Optional description lines
        -- Source: https://focus.finops.org/... (optional)
        -- Other comment lines
        SELECT ... (actual SQL starts here)

        The parser separates comment lines (starting with --) from SQL content,
        extracting key metadata while preserving the executable SQL.

        Args:
            filepath: Path to the SQL file to parse

        Returns:
            Query object with parsed metadata and SQL, or None if parsing fails
        """
        try:
            content = filepath.read_text()
            lines = content.split("\n")

            # Extract query name from first comment line
            # Fall back to filename if no comment header
            name = lines[0].replace("-- ", "") if lines else filepath.stem

            # Look for source citation in comment lines
            source = ""
            for line in lines:
                if "Source:" in line:
                    # Clean up the source line to extract just the URL/reference
                    source = line.replace("-- Source: ", "").strip()
                    break

            # Extract SQL content by filtering out comment lines
            # This preserves the executable SQL while removing metadata
            sql_lines = [line for line in lines if not line.startswith("--")]
            sql = "\n".join(sql_lines).strip()

            # Skip empty files or files with only comments
            if not sql:
                return None

            return Query(
                name=name,
                description="Query from focus.finops.org",  # Generic description for now
                query=sql,
                citation=source,
                filename=filepath.name,
            )

        except Exception as e:
            print(f"Error parsing {filepath}: {e}")
            return None

    def get_query(self, query_name: str) -> Query | None:
        """
        Retrieve a specific query by its identifier.

        Args:
            query_name: The query identifier (filename without .sql extension)

        Returns:
            Query object if found, None otherwise
        """
        return self.queries.get(query_name)


# Global query loader instance
# Initialized at module import to pre-load all available queries
# This singleton pattern ensures queries are loaded once and cached
focus_queries = QueryLoader()
