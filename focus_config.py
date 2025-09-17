#!/usr/bin/env python3
"""
FOCUS MCP Server Configuration - Environment-based settings.

This module centralizes all configuration for the FOCUS MCP server,
providing a single point of control for data paths, FOCUS version,
and other runtime settings.

Configuration is environment-driven to support different deployment
scenarios (development, staging, production) without code changes.
All settings have sensible defaults for quick local development.

Environment Variables:
    FOCUS_DATA_PATH: Path to directory containing FOCUS Parquet files
                     Default: "data/focus-export"

    FOCUS_VERSION: FOCUS specification version for query compatibility
                   Default: "1.0"
                   Affects which query directory is loaded

The configuration supports both absolute and relative paths for data,
with relative paths resolved from the server's working directory.
"""

import os

# Data source configuration
# Path to directory containing FOCUS-compliant Parquet files
# Should contain either:
# - Flat structure: *.parquet files directly in directory
# - Hive partitioned: subdirectories like year=2024/month=01/
DATA_PATH = os.getenv("FOCUS_DATA_PATH", "data/focus-export")

# FOCUS specification version
# Determines which queries are available based on their focus_versions field
# Queries are filtered from the unified YAML file at runtime
# This allows supporting multiple FOCUS versions with version-specific query sets
FOCUS_VERSION = os.getenv("FOCUS_VERSION", "1.0")
