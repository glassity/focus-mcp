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
    FOCUS_DATA_LOCATION: Path to FOCUS data (local path, s3:// or gs:// URI)
                         Default: "data/focus-export"
                         Relative local paths are resolved against the working
                         directory at startup and reported as absolute.

    AWS_REGION: AWS region for S3 access
                Default: "us-east-1"

    AWS_PROFILE: Optional AWS profile for authentication
                 Uses credential chain if not specified

    GCS_HMAC_KEY_ID: GCS HMAC access key for gs:// locations
                     (create with: gcloud storage hmac create <service-account>)

    GCS_HMAC_SECRET: GCS HMAC secret paired with GCS_HMAC_KEY_ID.
                     If unset, Application Default Credentials are used
                     when gcsfs is installed (gcs extra).

    FOCUS_VERSION: FOCUS specification version
                   Default: "1.0"

The configuration supports both absolute and relative paths for data,
with relative paths resolved from the server's working directory.
"""

import os
from pathlib import Path

# Data source configuration
# Supports local paths, S3 locations, and GCS locations
# Examples:
#   Local: "/path/to/focus/data" or "data/focus-export"
#   S3: "s3://bucket-name/path/to/focus/data"
#   GCS: "gs://bucket-name/path/to/focus/data"
#
# For S3, authentication is handled automatically via AWS credential chain:
# - IAM roles (EC2, ECS, Lambda)
# - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
# - AWS CLI profiles (AWS_PROFILE)
# - Instance metadata service
#
# For GCS, authentication is tiered (see storage_backends.py):
# - HMAC env vars (GCS_HMAC_KEY_ID, GCS_HMAC_SECRET) if set
# - Application Default Credentials via gcsfs (gcs extra) otherwise
# - Keyless access as last resort (public buckets only)
def _resolve_location(location: str) -> str:
    """Make local paths absolute; leave remote URIs exactly as given.

    A relative path resolved against an MCP client's working directory is not
    something a user can debug from an error message. Remote URIs must survive
    verbatim: Path() would collapse the double slash in "s3://bucket".
    """
    if "://" in location:
        return location
    return str(Path(location).expanduser().resolve())


DATA_LOCATION = _resolve_location(os.getenv("FOCUS_DATA_LOCATION", "data/focus-export"))

# AWS Configuration (optional)
# Region for S3 access - defaults to us-east-1 if not specified
AWS_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))

# FOCUS specification version
# Determines which queries are available based on their focus_versions field
# Queries load from the collection directory for this version
# This allows supporting multiple FOCUS versions with version-specific query sets
FOCUS_VERSION = os.getenv("FOCUS_VERSION", "1.0")
