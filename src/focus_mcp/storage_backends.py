#!/usr/bin/env python3
"""
Storage Backends Module - One class per data-source backend.

Each backend recognizes its locations, normalizes them, and prepares a
DuckDB connection for reading them. Preparation loads only what that
backend needs (extensions, credentials), so a local-only server touches
no extensions at startup; ad-hoc SQL against remote URLs still works via
DuckDB's default autoinstall/autoload of known extensions.

Resolution walks BACKENDS in order; LocalBackend is the catch-all.
"""

import os
from abc import ABC, abstractmethod
from typing import Optional

import duckdb

from . import config


class StorageBackend(ABC):
    """Base class for data-source backends."""

    name: str

    @abstractmethod
    def matches(self, location: str) -> bool:
        """Return True if this backend handles the given location."""

    def normalize(self, location: str) -> str:
        """Rewrite the location to its canonical form."""
        return location

    @abstractmethod
    def prepare(
        self, conn: duckdb.DuckDBPyConnection, location: str
    ) -> Optional[str]:
        """
        Load extensions and configure credentials on the connection.

        Returns an error hint to surface if reads later fail, or None
        when there is nothing useful to add.
        """

    def exists(self, location: str) -> bool:
        """Whether data can be expected at the location.

        Remote backends return True: a bucket prefix can't be cheaply
        checked, so view creation is the real check.
        """
        return True


class S3Backend(StorageBackend):
    """s3:// locations, authenticated via the AWS credential chain.

    The credential chain automatically discovers credentials from
    environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY,
    AWS_SESSION_TOKEN), AWS profiles (AWS_PROFILE), IAM roles, and the
    instance metadata service.
    """

    name = "s3"

    def matches(self, location: str) -> bool:
        return location.startswith("s3://")

    def prepare(
        self, conn: duckdb.DuckDBPyConnection, location: str
    ) -> Optional[str]:
        conn.execute("INSTALL httpfs; LOAD httpfs;")
        # Values are passed as bound parameters so no SQL escaping is needed
        conn.execute("""
            CREATE OR REPLACE SECRET aws_s3_secret (
                TYPE s3,
                PROVIDER credential_chain,
                REGION ?
            )
        """, [config.AWS_REGION])
        return None


class GCSBackend(StorageBackend):
    """gs:// locations, with tiered authentication.

    1. HMAC keys: GCS_HMAC_KEY_ID + GCS_HMAC_SECRET env vars are set.
       Creates a DuckDB native gcs secret (S3-interoperability API,
       served by the httpfs extension). Keys are minted with:
       gcloud storage hmac create <service-account-email>
    2. Application Default Credentials: gcsfs is installed (gcs extra).
       Registers a gcsfs filesystem on the connection, which walks ADC
       (gcloud auth application-default login,
       GOOGLE_APPLICATION_CREDENTIALS, or GCE/GKE workload identity).
       httpfs must NOT be loaded on this tier: both claim the gs://
       prefix and httpfs would intercept the reads.
    3. Keyless: neither available. Reads proceed over httpfs, which only
       works for public buckets; prepare() returns a hint explaining how
       to configure credentials in case reads fail.

    Explicit configuration (HMAC) intentionally beats ambient
    credentials (ADC). Accepts the 'gcs://' alias some tools emit and
    normalizes it to the canonical 'gs://'.
    """

    name = "gcs"

    def matches(self, location: str) -> bool:
        return location.startswith("gs://") or location.startswith("gcs://")

    def normalize(self, location: str) -> str:
        if location.startswith("gcs://"):
            return "gs://" + location[len("gcs://"):]
        return location

    def prepare(
        self, conn: duckdb.DuckDBPyConnection, location: str
    ) -> Optional[str]:
        key_id = os.getenv("GCS_HMAC_KEY_ID")
        secret = os.getenv("GCS_HMAC_SECRET")

        if key_id and secret:
            conn.execute("INSTALL httpfs; LOAD httpfs;")
            # Values are passed as bound parameters so no SQL escaping is needed
            conn.execute("""
                CREATE OR REPLACE SECRET gcs_hmac_secret (
                    TYPE gcs,
                    KEY_ID ?,
                    SECRET ?
                )
            """, [key_id, secret])
            return None

        try:
            import gcsfs
        except ImportError:
            conn.execute("INSTALL httpfs; LOAD httpfs;")
            return (
                f"Failed to read {location} without GCS credentials. "
                "Set GCS_HMAC_KEY_ID and GCS_HMAC_SECRET, or install "
                "the gcs extra (pip install 'focus-mcp[gcs]') to use "
                "Application Default Credentials."
            )

        # No project/token arguments: GCSFileSystem discovers ADC on its own
        conn.register_filesystem(gcsfs.GCSFileSystem())
        return None


class LocalBackend(StorageBackend):
    """Local filesystem paths. Catch-all: matches everything."""

    name = "local"

    def matches(self, location: str) -> bool:
        return True

    def prepare(
        self, conn: duckdb.DuckDBPyConnection, location: str
    ) -> Optional[str]:
        return None

    def exists(self, location: str) -> bool:
        return os.path.exists(location)


# Resolution order matters: LocalBackend matches everything, so it goes last
BACKENDS = [S3Backend, GCSBackend, LocalBackend]


def resolve_backend(location: str) -> StorageBackend:
    """Return a fresh backend instance for the given data location."""
    for backend_cls in BACKENDS:
        backend = backend_cls()
        if backend.matches(location):
            return backend
    raise ValueError(f"No storage backend matches location: {location}")
