#!/usr/bin/env python3
"""
FOCUS Specification Loader - Loads FOCUS specification data from YAML files.

Provides access to FOCUS column and attribute definitions with version filtering.
"""

import sys
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any
from packaging.version import parse
from .paths import resource_path


def _version_key(value):
    return parse(str(value).replace('-preview', 'a0'))


def _available_at(item, version) -> bool:
    """Whether a column or attribute exists in the given FOCUS version.

    The specification deletes a retired item's file rather than marking it,
    so the cached metadata records removed_version and both ends of the
    range are checked. Without the upper bound, 1.4 would still be told it
    has ProviderName.
    """
    introduced = item.get('introduced_version')
    if not introduced or _version_key(introduced) > _version_key(version):
        return False
    removed = item.get('removed_version')
    return not removed or _version_key(removed) > _version_key(version)


class FocusSpecLoader:
    """Loader for FOCUS specification data from YAML files."""

    def __init__(self, spec_dir: str | None = None):
        """Initialize loader and load specification data.

        Args:
            spec_dir: Directory containing columns.yaml and attributes.yaml.
                Defaults to the specifications that ship inside the package.
                Tests and the scripts/ extractors pass a checkout directory.
        """
        spec_path = Path(spec_dir) if spec_dir is not None else resource_path("specifications")

        # Load data files with graceful degradation
        columns_file = spec_path / "columns.yaml"
        attributes_file = spec_path / "attributes.yaml"

        # Initialize with empty data by default
        self.columns = []
        self.attributes = []

        # Try to load columns
        if columns_file.exists():
            try:
                with open(columns_file, 'r') as f:
                    self.columns = yaml.safe_load(f) or []
                print(f"Loaded {len(self.columns)} column definitions from {columns_file}", file=sys.stderr)
            except Exception as e:
                print(f"Warning: Failed to load columns from {columns_file}: {e}", file=sys.stderr)
                self.columns = []
        else:
            print(f"Warning: Column definitions not found at {columns_file}", file=sys.stderr)
            print("FOCUS column metadata will not be available.", file=sys.stderr)
            print("To generate specification files, run: python scripts/focus_spec_markdown_extractor.py", file=sys.stderr)

        # Try to load attributes
        if attributes_file.exists():
            try:
                with open(attributes_file, 'r') as f:
                    self.attributes = yaml.safe_load(f) or []
                print(f"Loaded {len(self.attributes)} attribute definitions from {attributes_file}", file=sys.stderr)
            except Exception as e:
                print(f"Warning: Failed to load attributes from {attributes_file}: {e}", file=sys.stderr)
                self.attributes = []
        else:
            print(f"Warning: Attribute definitions not found at {attributes_file}", file=sys.stderr)
            print("FOCUS attribute metadata will not be available.", file=sys.stderr)

    def get_columns(self,
                   version: Optional[str] = None,
                   feature_level: Optional[str] = None,
                   column_type: Optional[str] = None,
                   search: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get columns with optional filters.

        Args:
            version: FOCUS version (e.g., "1.2") - returns columns up to this version
            feature_level: Filter by feature level (Mandatory, Conditional, Optional, Recommended)
            column_type: Filter by type (Dimension, Metric)
            search: Search term for column ID, name, or description

        Returns:
            List of matching column definitions
        """
        result = self.columns

        # Filter by version (include all columns introduced up to this version)
        if version:
            result = [
                col for col in result
                if _available_at(col, version)
            ]

        # Filter by feature level
        if feature_level:
            result = [
                col for col in result
                if col.get('feature_level') == feature_level
            ]

        # Filter by column type
        if column_type:
            result = [
                col for col in result
                if col.get('column_type') == column_type
            ]

        # Search filter
        if search:
            search_lower = search.lower()
            result = [
                col for col in result
                if (search_lower in col.get('column_id', '').lower() or
                    search_lower in col.get('display_name', '').lower() or
                    search_lower in col.get('description', '').lower())
            ]

        return result

    def get_attributes(self,
                      version: Optional[str] = None,
                      search: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get attributes with optional filters.

        Args:
            version: FOCUS version - returns attributes up to this version
            search: Search term for attribute ID, name, or description

        Returns:
            List of matching attribute definitions
        """
        result = self.attributes

        # Filter by version
        if version:
            result = [
                attr for attr in result
                if _available_at(attr, version)
            ]

        # Search filter
        if search:
            search_lower = search.lower()
            result = [
                attr for attr in result
                if (search_lower in attr.get('attribute_id', '').lower() or
                    search_lower in attr.get('name', '').lower() or
                    search_lower in attr.get('description', '').lower())
            ]

        return result

    def find_column(self, identifier: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Find a specific column by ID or display name.

        Args:
            identifier: Column ID or display name (case-insensitive)
            version: Optional version filter

        Returns:
            Column definition or None if not found
        """
        identifier_lower = identifier.lower()

        columns = self.get_columns(version=version)

        # Try exact match on column_id first
        for col in columns:
            if col.get('column_id', '').lower() == identifier_lower:
                return col

        # Then try display_name
        for col in columns:
            if col.get('display_name', '').lower() == identifier_lower:
                return col

        return None

    def find_attribute(self, identifier: str, version: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Find a specific attribute by ID or name.

        Args:
            identifier: Attribute ID or name (case-insensitive)
            version: Optional version filter

        Returns:
            Attribute definition or None if not found
        """
        identifier_lower = identifier.lower()

        attributes = self.get_attributes(version=version)

        # Try exact match on attribute_id first
        for attr in attributes:
            if attr.get('attribute_id', '').lower() == identifier_lower:
                return attr

        # Then try name
        for attr in attributes:
            if attr.get('name', '').lower() == identifier_lower:
                return attr

        return None

    def get_versions(self) -> List[str]:
        """Get all unique versions from the specifications.

        Returns:
            Sorted list of version strings
        """
        versions = set()

        for col in self.columns:
            if 'introduced_version' in col:
                versions.add(col['introduced_version'])

        for attr in self.attributes:
            if 'introduced_version' in attr:
                versions.add(attr['introduced_version'])

        # Sort versions properly using packaging.version
        return sorted(versions, key=lambda v: parse(v.replace('-preview', 'a0')))


def main():
    """Test the FOCUS specification loader."""
    loader = FocusSpecLoader()

    # Show available versions
    versions = loader.get_versions()
    print(f"Available versions: {versions}")

    # Test column queries
    print("\n=== Column Queries ===")

    # All columns in v1.2
    cols_1_2 = loader.get_columns(version="1.2")
    print(f"Total columns in v1.2: {len(cols_1_2)}")

    # Mandatory columns only
    mandatory = loader.get_columns(version="1.2", feature_level="Mandatory")
    print(f"Mandatory columns in v1.2: {len(mandatory)}")

    # Search for cost-related columns
    cost_cols = loader.get_columns(search="cost")
    print(f"Columns containing 'cost': {len(cost_cols)}")
    for col in cost_cols[:3]:
        print(f"  - {col['display_name']} ({col['column_id']})")

    # Find specific column
    billed_cost = loader.find_column("BilledCost")
    if billed_cost:
        print("\nBilledCost details:")
        print(f"  Type: {billed_cost.get('column_type')}")
        print(f"  Feature: {billed_cost.get('feature_level')}")
        print(f"  Introduced: {billed_cost.get('introduced_version')}")

    # Test attribute queries
    print("\n=== Attribute Queries ===")

    attrs = loader.get_attributes(version="1.2")
    print(f"Total attributes in v1.2: {len(attrs)}")

    # Find specific attribute
    unit_format = loader.find_attribute("unit_format")
    if unit_format:
        print("\nUnit Format attribute:")
        print(f"  Name: {unit_format.get('name')}")
        print(f"  Introduced: {unit_format.get('introduced_version')}")


if __name__ == "__main__":
    main()