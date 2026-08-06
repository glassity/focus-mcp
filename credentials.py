#!/usr/bin/env python3
"""
Credentials Module - Handle cloud storage authentication for DuckDB.

S3 uses DuckDB's credential_chain provider for automatic discovery.
GCS is tiered: explicit HMAC keys, then Application Default Credentials
via gcsfs, then keyless (public buckets).
"""

import os

import duckdb


def setup_s3_credentials(
    conn: duckdb.DuckDBPyConnection,
    region: str = "us-east-1"
) -> None:
    """
    Configure S3 credentials for DuckDB using AWS credential chain.

    The credential chain automatically discovers credentials from:
    - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_SESSION_TOKEN)
    - AWS profiles (~/.aws/credentials, use AWS_PROFILE env var to specify)
    - IAM roles (EC2, ECS, Lambda)
    - Instance metadata service

    Args:
        conn: Active DuckDB connection
        region: AWS region (defaults to us-east-1)
    """
    # Create S3 secret using credential chain for automatic discovery
    # Values are passed as bound parameters so no SQL escaping is needed
    conn.execute("""
        CREATE OR REPLACE SECRET aws_s3_secret (
            TYPE s3,
            PROVIDER credential_chain,
            REGION ?
        )
    """, [region])


def setup_gcs_credentials(conn: duckdb.DuckDBPyConnection) -> str:
    """
    Configure GCS access for DuckDB, trying methods in priority order.

    1. "hmac": GCS_HMAC_KEY_ID + GCS_HMAC_SECRET env vars are set.
       Creates a DuckDB native gcs secret (S3-interoperability API,
       served by the httpfs extension). Keys are minted with:
       gcloud storage hmac create <service-account-email>
    2. "adc": gcsfs is installed. Registers a gcsfs filesystem on the
       connection, which walks Google Application Default Credentials
       (gcloud auth application-default login, GOOGLE_APPLICATION_CREDENTIALS,
       or GCE/GKE workload identity).
    3. "none": neither available. Reads proceed keyless over httpfs,
       which only works for public buckets.

    Explicit configuration (HMAC) intentionally beats ambient
    credentials (ADC).

    Args:
        conn: Active DuckDB connection

    Returns:
        The tier used: "hmac", "adc", or "none"
    """
    key_id = os.getenv("GCS_HMAC_KEY_ID")
    secret = os.getenv("GCS_HMAC_SECRET")

    if key_id and secret:
        # Values are passed as bound parameters so no SQL escaping is needed
        conn.execute("""
            CREATE OR REPLACE SECRET gcs_hmac_secret (
                TYPE gcs,
                KEY_ID ?,
                SECRET ?
            )
        """, [key_id, secret])
        return "hmac"

    try:
        import gcsfs
    except ImportError:
        return "none"

    # No project/token arguments: GCSFileSystem discovers ADC on its own
    conn.register_filesystem(gcsfs.GCSFileSystem())
    return "adc"
