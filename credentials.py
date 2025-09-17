#!/usr/bin/env python3
"""
Credentials Module - Handle cloud storage authentication for DuckDB.

Uses DuckDB's credential_chain provider for automatic credential discovery.
"""

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
    conn.execute(f"""
        CREATE OR REPLACE SECRET aws_s3_secret (
            TYPE s3,
            PROVIDER credential_chain,
            REGION '{region}'
        )
    """)
