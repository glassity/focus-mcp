#!/usr/bin/env python3
"""
FOCUS MCP Server Configuration - Environment-based settings.

This module centralizes all configuration for the FOCUS MCP server,
providing a single point of control for data paths, FOCUS version,
transport, datasets, and authentication.

Configuration is environment-driven to support different deployment
scenarios (development, staging, production) without code changes.
All settings have sensible defaults for quick local development.

Environment Variables:
    FOCUS_DATA_LOCATION: Path to the default FOCUS data (local path, s3:// or gs:// URI)
                         Default: "data/focus-export"
                         Relative local paths are resolved against the working
                         directory at startup and reported as absolute.

    FOCUS_VERSION: FOCUS specification version of the default dataset
                   Default: "1.0"

    FOCUS_DATASETS: JSON map of named datasets a client may select per call,
                    e.g. {"prod": {"location": "s3://b/focus", "version": "1.2"}}.
                    Names are opaque handles; "version" is optional and
                    falls back to FOCUS_VERSION.

    FOCUS_CATALOG_URL: HTTP catalog that resolves a dataset handle to
                       {"location": ..., "version": ...}. The server GETs
                       <url>/<handle>, forwarding the caller's bearer token,
                       so the catalog decides what each caller may read.

    FOCUS_ALLOW_RAW_LOCATIONS: "true" to let clients pass a location
                               (s3://..., /path) as the dataset over HTTP.
                               Always allowed over stdio, where the client
                               is the same user as the server.

    FOCUS_MAX_DATASETS: Open DuckDB connections kept at once (default 8);
                        the least recently used one is closed beyond that.

    FOCUS_TRANSPORT: "stdio" (default) or "streamable-http".
    FOCUS_HTTP_HOST / FOCUS_HTTP_PORT: bind address for streamable-http
                                       (default 127.0.0.1:8000).

    FOCUS_JWKS_URL: JWKS endpoint used to verify bearer tokens (RS256/ES256).
                    Unset means no authentication.
    FOCUS_OIDC_ISSUER: expected "iss" claim; also published as the
                       authorization server in protected-resource metadata.
    FOCUS_RESOURCE_URL: this server's public URL (the OAuth resource
                        indicator clients must request tokens for).
    FOCUS_REQUIRED_SCOPES: space-separated scopes a token must carry.

    AWS_REGION: AWS region for S3 access
                Default: "us-east-1"

    AWS_PROFILE: Optional AWS profile for authentication
                 Uses credential chain if not specified

    GCS_HMAC_KEY_ID / GCS_HMAC_SECRET: GCS HMAC credentials for gs://
                     locations. If unset, Application Default Credentials
                     are used when gcsfs is installed (gcs extra).
"""

import json
import os
from pathlib import Path


def _resolve_location(location: str) -> str:
    """Make local paths absolute; leave remote URIs exactly as given.

    A relative path resolved against an MCP client's working directory is not
    something a user can debug from an error message. Remote URIs must survive
    verbatim: Path() would collapse the double slash in "s3://bucket".
    """
    if "://" in location:
        return location
    return str(Path(location).expanduser().resolve())


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def _parse_datasets(raw: str) -> dict[str, dict[str, str]]:
    """Parse FOCUS_DATASETS, rejecting shapes the server could not serve.

    Fails at startup rather than on the first tool call: a typo here would
    otherwise surface as "unknown dataset" to every client.
    """
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"FOCUS_DATASETS is not valid JSON: {e}") from e
    if not isinstance(parsed, dict):
        raise ValueError("FOCUS_DATASETS must be a JSON object of name -> {location, version}")
    datasets = {}
    for name, entry in parsed.items():
        if isinstance(entry, str):
            entry = {"location": entry}
        if not isinstance(entry, dict) or not entry.get("location"):
            raise ValueError(f"FOCUS_DATASETS entry {name!r} needs a location")
        datasets[name] = {
            "location": _resolve_location(str(entry["location"])),
            "version": str(entry["version"]).lstrip("v") if entry.get("version") else "",
        }
    return datasets


DATA_LOCATION = _resolve_location(os.getenv("FOCUS_DATA_LOCATION", "data/focus-export"))

# FOCUS specification version of the default dataset. Each version has its
# own curated query collection; a client can pick another per call.
FOCUS_VERSION = os.getenv("FOCUS_VERSION", "1.0")

DATASETS = _parse_datasets(os.getenv("FOCUS_DATASETS", ""))
CATALOG_URL = os.getenv("FOCUS_CATALOG_URL", "").rstrip("/")
ALLOW_RAW_LOCATIONS = _env_flag("FOCUS_ALLOW_RAW_LOCATIONS")
MAX_DATASETS = int(os.getenv("FOCUS_MAX_DATASETS", "8"))

TRANSPORT = os.getenv("FOCUS_TRANSPORT", "stdio")
HTTP_HOST = os.getenv("FOCUS_HTTP_HOST", "127.0.0.1")
HTTP_PORT = int(os.getenv("FOCUS_HTTP_PORT", "8000"))

JWKS_URL = os.getenv("FOCUS_JWKS_URL", "")
OIDC_ISSUER = os.getenv("FOCUS_OIDC_ISSUER", "")
RESOURCE_URL = os.getenv("FOCUS_RESOURCE_URL", "")
REQUIRED_SCOPES = os.getenv("FOCUS_REQUIRED_SCOPES", "").split()

# AWS Configuration (optional)
# Region for S3 access - defaults to us-east-1 if not specified
AWS_REGION = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))
