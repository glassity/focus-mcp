#!/usr/bin/env python3
"""
Data Source Module - Parse data locations for FOCUS data.

Supports local paths, S3 URIs, and Google Cloud Storage URIs.
"""

from typing import Tuple


def is_s3_location(location: str) -> bool:
    """
    Check if location is an S3 path.

    Args:
        location: Data location string

    Returns:
        True if location is an S3 URI, False otherwise
    """
    return location.startswith("s3://")


def is_gcs_location(location: str) -> bool:
    """
    Check if location is a Google Cloud Storage path.

    Accepts both the canonical 'gs://' scheme and the 'gcs://' alias
    some tools emit.

    Args:
        location: Data location string

    Returns:
        True if location is a GCS URI, False otherwise
    """
    return location.startswith("gs://") or location.startswith("gcs://")


def parse_data_location(location: str) -> Tuple[str, str]:
    """
    Parse data location to determine source type.

    Args:
        location: Data location string (local path, S3 URI, or GCS URI)

    Returns:
        Tuple of (source_type, location) where source_type is "s3",
        "gcs", or "local". GCS locations are normalized to the
        canonical 'gs://' scheme.
    """
    if is_s3_location(location):
        return "s3", location
    if is_gcs_location(location):
        # Normalize the 'gcs://' alias to canonical 'gs://'
        if location.startswith("gcs://"):
            location = "gs://" + location[len("gcs://"):]
        return "gcs", location
    return "local", location
