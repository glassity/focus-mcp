#!/usr/bin/env python3
"""
FOCUS MCP Server - A Model Context Protocol server for analyzing cloud billing data.

This server provides tools to query and analyze FOCUS (FinOps Open Cost and Usage Specification)
compliant billing data using DuckDB. It serves as a bridge between MCP clients (like Claude)
and cloud cost data stored in Parquet format.

Key Features:
- Automatic Parquet file discovery and loading
- Predefined analytical queries for common FinOps use cases
- Dynamic SQL execution with parameter binding
- FOCUS schema exploration and data profiling

Architecture:
- Uses DuckDB for high-performance analytical queries on Parquet files
- Implements MCP (Model Context Protocol) for AI assistant integration
- Supports both predefined queries and ad-hoc SQL execution
- Handles FOCUS billing data standards and conventions
"""

import os
from typing import Any, Optional
from pydantic import Field
import duckdb
from mcp.server.fastmcp import FastMCP

import focus_config
from focus_queries import focus_queries
from focus_spec_loader import FocusSpecLoader

# Initialize MCP server with FOCUS-specific instructions
# FastMCP provides a simplified interface for creating MCP servers
mcp = FastMCP(
    "focus-mcp-server",
    instructions="""
    # FOCUS Billing Analytics Server

    ## Database Engine

    This server uses DuckDB as its SQL engine. Custom queries must follow DuckDB SQL syntax.
    The main table is named 'focus_data_table' and contains all FOCUS billing data loaded from Parquet files.

    ## Best Practices

    - Start with get_data_info to understand the loaded data
    - Use list_use_cases to explore predefined queries
    - Use get_use_case to see details before executing a predefined query, including parameters needed
    - Use execute_query to run SQL or predefined queries
    - Use list_columns and get_column_details to understand the FOCUS schema
    - Query distinct values to discover valid parameters (e.g., SELECT DISTINCT ServiceName)

    ## Tool Usage Guide

    1. **Data Discovery**
       - get_data_info: Overview of loaded data (row count, date range, providers)
       - list_columns: Browse all FOCUS columns with metadata
       - get_column_details: Detailed info for specific columns including data types

    2. **Query Execution**
       - list_use_cases: Browse 36+ predefined FinOps queries
       - get_use_case: View SQL and parameters for a specific query
       - execute_query: Run custom SQL or predefined queries with parameters

    3. **Schema & Standards**
       - list_attributes: View FOCUS formatting standards
       - get_attribute_details: Detailed requirements for data formatting

    ## Documentation Deep Dive

    The server provides comprehensive documentation through column and attribute details:

    **Cost Metrics Explained** (use get_column_details):
    - BilledCost: Basis for invoicing, includes discounts but excludes amortization
    - EffectiveCost: Amortized cost after all discounts and prepaid purchases
    - ContractedCost: Cost based on negotiated pricing (contracted unit price × quantity)
    - ListCost: Cost at list prices without any discounts

    **Date/Time Handling** (use get_attribute_details for 'date_time_format'):
    - All dates in UTC format
    - ISO 8601 format with timezone (e.g., 2025-05-01T02:00:00+02:00)
    - Start dates are inclusive, end dates are exclusive
    - BillingPeriod: When charges appear on invoice
    - ChargePeriod: When usage actually occurred

    **Charge Categories** (use get_column_details for 'ChargeCategory'):
    - Usage: Charges for actual resource consumption
    - Purchase: Upfront commitment purchases
    - Tax: Tax charges
    - Adjustment: Corrections and credits

    ## Parameter Format Examples

    - Dates: '2025-01-01' or '2025-01-01T00:00:00Z'
    - Service names: Exact match required, query distinct values first
    - SubAccountId: String format, even if numeric
    - Multiple parameters: Pass as list ['param1', 'param2', 'param3']

    ## Parameter Discovery Tips

    - For enum columns (e.g., ChargeCategory), run: SELECT DISTINCT column_name FROM focus_data_table
    - For date ranges, check get_data_info for available period
    - For service names, query: SELECT DISTINCT ServiceName FROM focus_data_table
    - For valid SubAccounts: SELECT DISTINCT SubAccountId, SubAccountName FROM focus_data_table
    """,
)

# Configuration - Load from environment variables via focus_config
DATA_PATH = focus_config.DATA_PATH

# Global database connection - Singleton pattern for performance
# DuckDB connections are thread-safe and expensive to create, so we reuse one instance
db_connection: Optional[duckdb.DuckDBPyConnection] = None

# Global specification loader - Singleton for cached spec data
spec_loader: Optional[FocusSpecLoader] = None


def get_db_connection() -> duckdb.DuckDBPyConnection:
    """
    Get or create a DuckDB database connection with FOCUS data loaded.

    This function implements a singleton pattern to ensure we only create one
    database connection per server instance. The connection is configured with:

    1. httpfs extension for reading remote files (future use)
    2. A 'focus_data_table' view that automatically discovers all Parquet files
       in the configured data directory using Hive partitioning

    The Hive partitioning feature allows DuckDB to automatically understand
    directory structures like 'year=2024/month=01/' commonly used in cloud
    data exports, making queries more efficient by enabling partition pruning.

    Returns:
        DuckDB connection with FOCUS data view ready for querying

    Raises:
        Exception: If DuckDB fails to initialize or load the data
    """
    global db_connection

    if db_connection is None:
        # Create new DuckDB connection (in-memory database)
        db_connection = duckdb.connect()

        # Install and load httpfs extension for potential remote file access
        # This enables reading from S3, GCS, or Azure blob storage in the future
        db_connection.execute("INSTALL httpfs; LOAD httpfs;")

        # Create a view that aggregates all FOCUS Parquet files
        # The '**/*.parquet' pattern recursively finds all parquet files
        # hive_partitioning=true enables automatic partition column inference
        if os.path.exists(DATA_PATH):
            view_query = f"""
                CREATE OR REPLACE VIEW focus_data_table AS
                SELECT * FROM read_parquet('{DATA_PATH}/**/*.parquet', hive_partitioning=true)
            """
            db_connection.execute(view_query)

    return db_connection


def get_spec_loader() -> FocusSpecLoader:
    """
    Get or create the FOCUS specification loader.

    Returns:
        FocusSpecLoader instance for accessing column and attribute definitions
    """
    global spec_loader

    if spec_loader is None:
        spec_loader = FocusSpecLoader()

    return spec_loader


def format_query_results(rows, columns, limit):
    """
    Format query results into a list of dictionaries for JSON serialization.

    Converts DuckDB query results (list of tuples) into a more usable format
    for MCP clients. Each row becomes a dictionary with column names as keys.

    Args:
        rows: Raw query results from DuckDB (list of tuples)
        columns: Column names from the query
        limit: Maximum number of rows to return (for truncation)

    Returns:
        List of dictionaries where each dict represents one row
    """
    return [dict(zip(columns, row)) for row in rows[:limit]]


@mcp.tool()
async def get_data_info() -> dict[str, Any]:
    """
    Get comprehensive information about the loaded FOCUS billing data.

    This tool provides essential metadata about the billing dataset including:
    - Data volume and date coverage
    - Cloud provider breakdown
    - Service diversity
    - Total cost aggregation
    - Schema information

    This is typically the first tool called to understand the scope and
    structure of the available billing data before running analytical queries.

    Returns:
        Dictionary containing data summary or error information
    """
    try:
        conn = get_db_connection()

        # Check if the focus_data_table view was successfully created
        # This indicates whether data files were found and loaded
        view_check = conn.execute(
            "SELECT * FROM information_schema.tables WHERE table_name = 'focus_data_table'"
        ).fetchone()

        if not view_check:
            return {
                "result": {
                    "status": "no_data",
                    "message": "No FOCUS data loaded. Set FOCUS_DATA_PATH environment variable.",
                    "data_path": DATA_PATH,
                }
            }

        # Generate comprehensive data summary using FOCUS standard columns
        # These fields are part of the FOCUS specification for cloud billing
        summary_query = """
            SELECT
                COUNT(*) as row_count,
                MIN(BillingPeriodStart) as earliest_date,
                MAX(BillingPeriodEnd) as latest_date,
                COUNT(DISTINCT ProviderName) as provider_count,
                COUNT(DISTINCT ServiceName) as service_count,
                ROUND(SUM(EffectiveCost), 2) as total_cost
            FROM focus_data_table
        """
        summary = conn.execute(summary_query).fetchone()

        # Get complete column list to understand data schema
        # Useful for users to know what fields are available for analysis
        columns_query = "SELECT column_name FROM information_schema.columns WHERE table_name = 'focus_data_table'"
        columns = [row[0] for row in conn.execute(columns_query).fetchall()]

        # Sample cloud providers to give users context about data sources
        # Limited to 10 to avoid overwhelming output while providing useful examples
        providers_query = "SELECT DISTINCT ProviderName FROM focus_data_table LIMIT 10"
        providers = [row[0] for row in conn.execute(providers_query).fetchall()]

        return {
            "result": {
                "data_path": DATA_PATH,
                "row_count": summary[0],
                "date_range": {
                    "start": str(summary[1]) if summary[1] else None,
                    "end": str(summary[2]) if summary[2] else None,
                },
                "providers": {
                    "count": summary[3],
                    "samples": providers,
                },
                "services": {
                    "count": summary[4],
                },
                "total_cost": summary[5],
                "column_count": len(columns),
                "columns_sample": columns[:10],
            }
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def list_use_cases() -> dict[str, Any]:
    """
    List all available predefined FOCUS analytical queries.

    Returns a lightweight overview of available queries without the full SQL text.
    This helps users discover relevant analyses for their billing data.

    The queries are sourced from focus.finops.org and cover common FinOps
    use cases like cost trends, service analysis, and optimization opportunities.

    Use get_use_case(id) to see the full SQL and parameter requirements
    before executing a specific query.

    Returns:
        Dictionary containing the list of available queries with metadata
    """
    try:
        all_queries = list(focus_queries.queries.values())

        # Format use cases with lightweight metadata only
        # Excludes SQL text to keep response size manageable for browsing
        use_cases = []
        for query in all_queries:
            use_case = {
                "id": query.slug,
                "name": query.name,
                "description": query.description or "No description available",
                "parameter_count": query.query.count('?'),
            }
            use_cases.append(use_case)

        return {
            "result": {
                "total": len(use_cases),
                "use_cases": use_cases,
            }
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_use_case(
    use_case_id: str = Field(..., description="Use case ID to get details for"),
) -> dict[str, Any]:
    """
    Get detailed information about a specific predefined FOCUS query.

    This tool shows the complete SQL query, parameter requirements, and metadata
    for a specific analytical query. Use this before executing a query to understand:
    - What parameters are needed (indicated by ? placeholders)
    - What the query actually does
    - The source/citation of the query

    Parameters are bound using positional placeholders (?), so when executing
    the query, provide parameters as a list in the order they appear.

    Args:
        use_case_id: The identifier for the query (from list_use_cases)

    Returns:
        Dictionary with complete query details or error information
    """
    try:
        # Retrieve the query template from the loaded queries
        # Try both formats: with underscores (key) and with hyphens (slug)
        query_template = focus_queries.get_query(use_case_id)
        if not query_template:
            # Try converting hyphens to underscores
            alt_id = use_case_id.replace("-", "_")
            query_template = focus_queries.get_query(alt_id)

        if not query_template:
            return {"error": f"Use case not found: {use_case_id}"}

        # Build comprehensive query information
        result = {
            "id": use_case_id,
            "name": query_template.name,
            "description": query_template.description or "No description available",
            "sql": query_template.query,
            "focus_versions": query_template.focus_versions,
            "citation": query_template.citation,
        }

        # Show parameter count from SQL
        result["parameter_count"] = query_template.query.count("?")

        return {"result": result}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def execute_query(
    query: Optional[str] = Field(None, description="SQL query to execute"),
    use_case: Optional[str] = Field(
        None,
        description="Predefined use case ID to run (call get_use_case first to see parameters)",
    ),
    parameters: Optional[list[Any] | dict[str, Any]] = Field(
        None,
        description="Parameters for the query (prefer list format: ['2025-01-01', '2025-02-01'])",
    ),
    limit: Optional[int] = Field(100, description="Max rows to return"),
) -> dict[str, Any]:
    """
    Execute SQL queries or predefined use cases against FOCUS billing data.

    This is the primary execution tool that supports two modes:
    1. Ad-hoc SQL queries: Pass raw SQL in the 'query' parameter
    2. Predefined queries: Pass a use case ID from list_use_cases

    Parameter binding uses positional placeholders (?) for security and performance.
    Parameters are bound in order, so ['2024-01-01', '2024-12-31'] maps to the first
    and second ? placeholders respectively.

    The tool includes automatic result limiting and formatting for MCP clients,
    converting raw DuckDB results into JSON-serializable dictionaries.

    Args:
        query: Raw SQL to execute (mutually exclusive with use_case)
        use_case: ID of predefined query to run (mutually exclusive with query)
        parameters: Values for ? placeholders (list preferred, dict for compatibility)
        limit: Maximum rows to return (default 100, prevents overwhelming responses)

    Returns:
        Dictionary containing query results, metadata, or error information
    """
    try:
        # Input validation - enforce mutually exclusive parameters
        if not query and not use_case:
            return {
                "error": "Must provide either 'query' (SQL) or 'use_case' (predefined query ID)"
            }

        if query and use_case:
            return {"error": "Provide either 'query' or 'use_case', not both"}

        conn = get_db_connection()

        # Determine SQL to execute and gather metadata
        if use_case:
            # Load predefined query from the query library
            # Try both formats: with hyphens (slug) and with underscores (key)
            query_template = focus_queries.get_query(use_case)
            if not query_template:
                # Try converting hyphens to underscores
                alt_id = use_case.replace("-", "_")
                query_template = focus_queries.get_query(alt_id)

            if not query_template:
                return {
                    "error": f"Use case not found: {use_case}. Use 'list_use_cases' to see available queries."
                }

            sql = query_template.query
            query_name = query_template.name
            query_description = query_template.description

            # Handle parameter binding for parameterized queries
            # Count ? placeholders to validate parameter count
            param_count = sql.count("?")
            if param_count > 0:
                if not parameters:
                    error_msg = f"Query '{query_name}' requires {param_count} parameters but none provided.\n"
                    error_msg += f"Use 'get_use_case' with id '{use_case}' to see the SQL query and identify parameter requirements."
                    return {"error": error_msg}

                # Normalize parameters to list format for consistent binding
                # List format is preferred for positional parameter binding
                if isinstance(parameters, list):
                    if len(parameters) != param_count:
                        return {
                            "error": f"Query requires {param_count} parameters but {len(parameters)} provided. Use 'get_use_case' with id '{use_case}' to see parameter requirements."
                        }
                elif isinstance(parameters, dict):
                    # Support legacy dict format with numbered keys for backward compatibility
                    # Convert {"1": "value1", "2": "value2"} to ["value1", "value2"]
                    param_list = []
                    for i in range(1, param_count + 1):
                        key = str(i)
                        if key in parameters:
                            param_list.append(parameters[key])
                        else:
                            return {
                                "error": f"Missing parameter {i} in parameters dict. Use 'get_use_case' with id '{use_case}' to see parameter requirements."
                            }
                    parameters = param_list
                else:
                    return {
                        "error": "Parameters must be a list (preferred) or numbered dict. Use 'get_use_case' to see parameter requirements."
                    }
        else:
            # Handle ad-hoc SQL queries
            sql = query
            query_name = "Custom Query"
            query_description = None

        # Apply result limiting if not already present in the query
        # This prevents accidentally returning millions of rows
        if limit and "LIMIT" not in sql.upper():
            sql = f"{sql} LIMIT {limit}"

        # Execute query with proper parameter binding
        # DuckDB handles parameter binding securely to prevent SQL injection
        if use_case and parameters and sql.count("?") > 0:
            result = conn.execute(sql, parameters).fetchall()
        else:
            result = conn.execute(sql).fetchall()
        columns = [desc[0] for desc in conn.description]

        # Format results for JSON serialization
        formatted_data = format_query_results(result, columns, limit or 100)

        # Build response with metadata and results
        response = {
            "query_name": query_name,
            "row_count": len(result),
            "columns": columns,
            "data": formatted_data,
        }

        if query_description:
            response["description"] = query_description

        # Indicate if results were truncated due to limit
        if len(result) == limit:
            response["truncated"] = True

        return {"result": response}
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def list_columns(
    version: Optional[str] = Field(None, description="FOCUS version (e.g., '1.0', '1.1', '1.2'). Uses configured version if not specified."),
    feature_level: Optional[str] = Field(None, description="Filter by feature level: Mandatory, Conditional, or Optional"),
    column_type: Optional[str] = Field(None, description="Filter by column type: Dimension or Metric"),
) -> dict[str, Any]:
    """
    List all FOCUS columns with their basic metadata.

    This tool provides a comprehensive list of all columns defined in the FOCUS
    specification for a given version. You can filter the results by feature level
    (Mandatory/Conditional/Optional) or column type (Dimension/Metric).

    Use this to discover available columns before querying billing data or to
    understand the schema structure of FOCUS datasets.

    Args:
        version: FOCUS version to query (defaults to configured version)
        feature_level: Optional filter for column requirement level
        column_type: Optional filter for column type

    Returns:
        Dictionary containing list of columns with metadata
    """
    try:
        loader = get_spec_loader()

        # Use configured version if not specified
        if not version:
            version = focus_config.FOCUS_VERSION

        # Ensure version is a string without 'v' prefix
        version = str(version).lstrip('v')

        # Get columns - ensure None values are passed correctly
        columns = loader.get_columns(
            version=version,
            feature_level=feature_level if isinstance(feature_level, str) else None,
            column_type=column_type if isinstance(column_type, str) else None
        )

        # Handle case where no spec data is available
        if not columns:
            return {
                "result": {
                    "version": version,
                    "total_columns": 0,
                    "filters_applied": {
                        "feature_level": feature_level,
                        "column_type": column_type
                    },
                    "columns": [],
                    "warning": "No FOCUS specification data available. Column definitions may need to be generated."
                }
            }

        # Convert to response format
        columns_list = [
            {
                'column_id': col.get('column_id', ''),
                'display_name': col.get('display_name', ''),
                'data_type': col.get('data_type', ''),
                'feature_level': col.get('feature_level', ''),
                'column_type': col.get('column_type', ''),
                'introduced_version': col.get('introduced_version', '')
            }
            for col in columns
        ]

        return {
            "result": {
                "version": version,
                "total_columns": len(columns),
                "filters_applied": {
                    "feature_level": feature_level,
                    "column_type": column_type
                },
                "columns": columns_list
            }
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_column_details(
    column_ids: list[str] = Field(..., description="List of column IDs or names to get details for"),
    version: Optional[str] = Field(None, description="FOCUS version (uses configured version if not specified)"),
) -> dict[str, Any]:
    """
    Get detailed information for specific FOCUS columns.

    This tool provides comprehensive metadata for one or more columns including:
    - Column ID and display name
    - Description and purpose
    - Data type and format
    - Feature level (Mandatory/Conditional/Optional)
    - Column type (Dimension/Metric)
    - Null handling
    - Version introduced
    - Any special requirements or constraints

    Use this when you need detailed information about specific columns before
    writing queries or understanding data semantics.

    Args:
        column_ids: List of column IDs (e.g., 'BillingAccountId') or names (e.g., 'Billing Account ID')
        version: FOCUS version to query

    Returns:
        Dictionary containing detailed column definitions
    """
    try:
        loader = get_spec_loader()

        # Use configured version if not specified
        if not version:
            version = focus_config.FOCUS_VERSION

        version = str(version).lstrip('v')

        # Get detailed information using new API
        details = []
        for col_id in column_ids:
            col = loader.find_column(col_id, version=version)
            if col:
                details.append(col)
            else:
                details.append({
                    'column_id': col_id,
                    'error': f'Column not found: {col_id}'
                })

        return {
            "result": {
                "version": version,
                "requested_columns": column_ids,
                "found": len([d for d in details if 'error' not in d]),
                "not_found": len([d for d in details if 'error' in d]),
                "details": details
            }
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def list_attributes(
    version: Optional[str] = Field(None, description="FOCUS version (uses configured version if not specified)"),
) -> dict[str, Any]:
    """
    List all FOCUS attributes that apply across the specification.

    Attributes are cross-cutting requirements that apply to multiple columns or
    the entire dataset. They define formatting standards, data handling rules,
    and other conventions that ensure consistency across FOCUS implementations.

    Common attributes include:
    - Currency Format: How monetary values should be formatted
    - Date/Time Format: ISO 8601 standards for temporal data
    - Null Handling: How missing values should be represented
    - String Handling: Character encoding and length constraints
    - Numeric Format: Precision and scale requirements

    Returns:
        Dictionary containing list of all FOCUS attributes
    """
    try:
        loader = get_spec_loader()

        # Use configured version if not specified
        if not version:
            version = focus_config.FOCUS_VERSION

        version = str(version).lstrip('v')

        # Get attributes using new API
        attributes = loader.get_attributes(version=version)

        # Handle case where no spec data is available
        if not attributes:
            return {
                "result": {
                    "version": version,
                    "total_attributes": 0,
                    "attributes": [],
                    "warning": "No FOCUS specification data available. Attribute definitions may need to be generated."
                }
            }

        # Convert to response format
        attributes_list = [
            {
                'attribute_id': attr.get('attribute_id', ''),
                'name': attr.get('name', ''),
                'description': attr.get('description', '')[:200] + '...'
                    if len(attr.get('description', '')) > 200
                    else attr.get('description', '')
            }
            for attr in attributes
        ]

        return {
            "result": {
                "version": version,
                "total_attributes": len(attributes),
                "attributes": attributes_list
            }
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def get_attribute_details(
    attribute_ids: list[str] = Field(..., description="List of attribute IDs or names to get details for"),
    version: Optional[str] = Field(None, description="FOCUS version (uses configured version if not specified)"),
) -> dict[str, Any]:
    """
    Get detailed information for specific FOCUS attributes.

    This tool provides comprehensive information about FOCUS attributes including:
    - Full description and purpose
    - Specific requirements and constraints
    - Affected columns or data types
    - Examples and edge cases
    - Implementation guidance

    Use this when you need to understand how to properly format or handle
    data according to FOCUS specifications.

    Args:
        attribute_ids: List of attribute IDs or names (e.g., 'currency_format', 'Currency Format')
        version: FOCUS version to query

    Returns:
        Dictionary containing detailed attribute specifications
    """
    try:
        loader = get_spec_loader()

        # Use configured version if not specified
        if not version:
            version = focus_config.FOCUS_VERSION

        version = str(version).lstrip('v')

        # Get detailed information using new API
        details = []
        for attr_id in attribute_ids:
            attr = loader.find_attribute(attr_id, version=version)
            if attr:
                details.append(attr)
            else:
                details.append({
                    'attribute_id': attr_id,
                    'error': f'Attribute not found: {attr_id}'
                })

        return {
            "result": {
                "version": version,
                "requested_attributes": attribute_ids,
                "found": len([d for d in details if 'error' not in d]),
                "not_found": len([d for d in details if 'error' in d]),
                "details": details
            }
        }
    except Exception as e:
        return {"error": str(e)}


def main():
    """
    Run the FOCUS MCP server.

    Starts the FastMCP server which handles MCP protocol communication
    and exposes the FOCUS billing analysis tools to MCP clients.

    The server runs indefinitely until interrupted, maintaining the
    database connection and serving requests.
    """
    mcp.run()


if __name__ == "__main__":
    main()
