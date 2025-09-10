#!/usr/bin/env python3

import os
from typing import Any, Optional
from pydantic import Field
import duckdb
from mcp.server.fastmcp import FastMCP

import focus_config
from focus_queries import focus_queries

# Initialize server
mcp = FastMCP(
    "focus-mcp-server",
    instructions="""
    # FOCUS Billing Analytics Server

    ## Best Practices
    
    - Start with get_data_info to understand the loaded data
    - Use list_use_cases to explore predefined queries
    - Use get_use_case to see details before executing a predefined query, including parameters needed
    - Use execute_query to run SQL or predefined queries

    ## Tool Usage Guide

    Use get_data_info to show what data is loaded
    Use list_use_cases to browse available predefined queries
    Use get_use_case to get detailed info about a specific query
    Use execute_query to run SQL or predefined queries
    """,
)

# Configuration
DATA_PATH = focus_config.DATA_PATH

# Global connection
db_connection: Optional[duckdb.DuckDBPyConnection] = None


def get_db_connection() -> duckdb.DuckDBPyConnection:
    """Get or create database connection."""
    global db_connection

    if db_connection is None:
        db_connection = duckdb.connect()
        db_connection.execute("INSTALL httpfs; LOAD httpfs;")

        # Create FOCUS data view
        if os.path.exists(DATA_PATH):
            view_query = f"""
                CREATE OR REPLACE VIEW focus_data AS
                SELECT * FROM read_parquet('{DATA_PATH}/**/*.parquet', hive_partitioning=true)
            """
            db_connection.execute(view_query)

    return db_connection


def format_query_results(rows, columns, limit):
    """Simple result formatter."""
    return [dict(zip(columns, row)) for row in rows[:limit]]


@mcp.tool()
async def get_data_info() -> dict[str, Any]:
    """Get information about loaded FOCUS data."""
    try:
        conn = get_db_connection()

        # Check if view exists
        view_check = conn.execute(
            "SELECT * FROM information_schema.tables WHERE table_name = 'focus_data'"
        ).fetchone()

        if not view_check:
            return {
                "result": {
                    "status": "no_data",
                    "message": "No FOCUS data loaded. Set FOCUS_DATA_PATH environment variable.",
                    "data_path": DATA_PATH,
                }
            }

        # Get data summary
        summary_query = """
            SELECT
                COUNT(*) as row_count,
                MIN(BillingPeriodStart) as earliest_date,
                MAX(BillingPeriodEnd) as latest_date,
                COUNT(DISTINCT ProviderName) as provider_count,
                COUNT(DISTINCT ServiceName) as service_count,
                ROUND(SUM(EffectiveCost), 2) as total_cost
            FROM focus_data
        """
        summary = conn.execute(summary_query).fetchone()

        # Get actual columns
        columns_query = "SELECT column_name FROM information_schema.columns WHERE table_name = 'focus_data'"
        columns = [row[0] for row in conn.execute(columns_query).fetchall()]

        # Get providers
        providers_query = "SELECT DISTINCT ProviderName FROM focus_data LIMIT 10"
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
    """List available predefined FOCUS queries. Use get_use_case(id) to see details before executing."""
    try:
        all_queries = list(focus_queries.queries.values())

        # Format use cases (lightweight - no SQL)
        use_cases = []
        for query in all_queries:
            use_case = {
                "id": query.filename.replace(".sql", "")
                if query.filename
                else query.name,
                "name": query.name,
                "description": query.description,
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
    """Get detailed information about a specific FOCUS query including SQL and parameter requirements."""
    try:
        # Get the query template
        query_template = focus_queries.get_query(use_case_id)
        if not query_template:
            return {"error": f"Use case not found: {use_case_id}"}

        # Count parameters for user guidance
        param_count = query_template.query.count("?")

        return {
            "result": {
                "id": use_case_id,
                "name": query_template.name,
                "description": query_template.description,
                "sql": query_template.query,
                "parameter_count": param_count,
                "citation": query_template.citation
                if hasattr(query_template, "citation")
                else None,
            }
        }
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
    """Execute SQL query or predefined use case on FOCUS data. For use cases, call get_use_case first to see parameter requirements."""
    try:
        # Validate input - need either query or use_case
        if not query and not use_case:
            return {
                "error": "Must provide either 'query' (SQL) or 'use_case' (predefined query ID)"
            }

        if query and use_case:
            return {"error": "Provide either 'query' or 'use_case', not both"}

        conn = get_db_connection()

        # Get the SQL to execute
        if use_case:
            # Get predefined query
            query_template = focus_queries.get_query(use_case)
            if not query_template:
                return {
                    "error": f"Use case not found: {use_case}. Use 'list_use_cases' to see available queries."
                }

            sql = query_template.query
            query_name = query_template.name
            query_description = query_template.description

            # Handle parameter substitution for ? placeholders
            param_count = sql.count("?")
            if param_count > 0:
                if not parameters:
                    return {
                        "error": f"Query requires {param_count} parameters but none provided. Use 'get_use_case' with id '{use_case}' to see parameter requirements."
                    }

                # Handle parameters - prefer list format
                if isinstance(parameters, list):
                    if len(parameters) != param_count:
                        return {
                            "error": f"Query requires {param_count} parameters but {len(parameters)} provided. Use 'get_use_case' with id '{use_case}' to see parameter requirements."
                        }
                elif isinstance(parameters, dict):
                    # Convert numbered dict to list for backward compatibility
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
            sql = query
            query_name = "Custom Query"
            query_description = None

        # Apply limit
        if limit and "LIMIT" not in sql.upper():
            sql = f"{sql} LIMIT {limit}"

        # Execute with or without parameters
        if use_case and parameters and sql.count("?") > 0:
            result = conn.execute(sql, parameters).fetchall()
        else:
            result = conn.execute(sql).fetchall()
        columns = [desc[0] for desc in conn.description]

        # Format results
        formatted_data = format_query_results(result, columns, limit or 100)

        response = {
            "query_name": query_name,
            "row_count": len(result),
            "columns": columns,
            "data": formatted_data,
        }

        if query_description:
            response["description"] = query_description

        if len(result) == limit:
            response["truncated"] = True

        return {"result": response}
    except Exception as e:
        return {"error": str(e)}


def main():
    """Run the FOCUS MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
