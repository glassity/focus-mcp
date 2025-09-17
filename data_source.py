#!/usr/bin/env python3
"""
Data Source Module - Parse data locations for FOCUS data.

Supports local paths and S3 URIs.
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


def parse_data_location(location: str) -> Tuple[str, str]:
    """
    Parse data location to determine source type.

    Args:
        location: Data location string (local path or S3 URI)

    Returns:
        Tuple of (source_type, location) where source_type is "s3" or "local"
    """
    if is_s3_location(location):
        return "s3", location
    return "local", location