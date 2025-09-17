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
    FOCUS_DATA_LOCATION: Path to FOCUS data (local or S3 URI)
                         Default: "data/focus-export"
                         Examples: "/path/to/data" or "s3://bucket/path"

    AWS_REGION: AWS region for S3 access
                Default: "us-east-1"

    AWS_PROFILE: Optional AWS profile for authentication
                 Uses credential chain if not specified

    FOCUS_VERSION: FOCUS specification version
                   Default: "1.0"

The configuration supports both absolute and relative paths for data,
with relative paths resolved from the server's working directory.
"""

import os

# Data source configuration
# Supports both local paths and S3 locations
# Examples:
#   Local: "/path/to/focus/data" or "data/focus-export"
#   S3: "s3://bucket-name/path/to/focus/data"
#
# For S3, authentication is handled automatically via AWS credential chain:
# - IAM roles (EC2, ECS, Lambda)
# - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
# - AWS CLI profiles (AWS_PROFILE)
# - Instance metadata service
DATA_LOCATION = os.getenv("FOCUS_DATA_LOCATION", "data/focus-export")

# AWS Configuration (optional)
# Region for S3 access - defaults to us-east-1 if not specified
AWS_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))

# FOCUS specification version
# Determines which queries are available based on their focus_versions field
# Queries are filtered from the unified YAML file at runtime
# This allows supporting multiple FOCUS versions with version-specific query sets
FOCUS_VERSION = os.getenv("FOCUS_VERSION", "1.0")
