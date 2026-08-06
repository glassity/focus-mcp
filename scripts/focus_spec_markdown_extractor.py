#!/usr/bin/env python3
"""
FOCUS Specification Markdown Extractor - Extracts FOCUS specs from markdown files.

This module clones the FOCUS repository and extracts column and attribute
definitions directly from the markdown source files. Much cleaner than HTML parsing!
"""

import re
import yaml
import subprocess
from pathlib import Path
from typing import Dict, List

from packaging.version import parse


class FocusMarkdownExtractor:
    """Extract column and attribute definitions from FOCUS markdown files."""

    REPO_URL = "https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec.git"

    def __init__(self, repo_dir: str = "/tmp/focus_repo",
                 cache_dir: str = "src/focus_mcp/resources/specifications"):
        """Initialize the extractor.

        Args:
            repo_dir: Directory to clone the repo to
            cache_dir: Directory to cache extracted data
        """
        self.repo_dir = Path(repo_dir)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def update_repo(self) -> None:
        """Clone or update the FOCUS repository."""
        if self.repo_dir.exists():
            print("Updating FOCUS repository...")
            subprocess.run(["git", "pull"], cwd=self.repo_dir, check=True)
        else:
            print("Cloning FOCUS repository...")
            subprocess.run(["git", "clone", "--depth", "1", self.REPO_URL, str(self.repo_dir)], check=True)

    def parse_markdown_column(self, md_path: Path) -> Dict:
        """Parse a column markdown file.

        Args:
            md_path: Path to the markdown file

        Returns:
            Dictionary with column details
        """
        with open(md_path, 'r') as f:
            content = f.read()

        column = {}

        # Extract title (first # heading)
        title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
        if title_match:
            column['display_name'] = title_match.group(1)

        # Extract Column ID
        id_match = re.search(r'^## Column ID\s*\n\s*(.+)$', content, re.MULTILINE)
        if id_match:
            column['column_id'] = id_match.group(1).strip()

        # Extract Description
        desc_match = re.search(r'^## Description\s*\n\s*(.+?)(?=\n##|\n\||$)', content, re.MULTILINE | re.DOTALL)
        if desc_match:
            column['description'] = ' '.join(desc_match.group(1).strip().split())

        # Extract content constraints table
        constraints_match = re.search(r'\|.*Column type.*\|(.*?)\n\n', content, re.DOTALL)
        if constraints_match:
            # Parse the table
            for line in constraints_match.group(0).split('\n'):
                if '|' in line and 'Constraint' not in line and '---' not in line:
                    parts = [p.strip() for p in line.split('|') if p.strip()]
                    if len(parts) >= 2:
                        key = parts[0].lower().replace(' ', '_')
                        value = parts[1]

                        if key == 'column_type':
                            column['column_type'] = value
                        elif key == 'feature_level':
                            column['feature_level'] = value
                        elif key == 'allows_nulls':
                            column['allows_nulls'] = value
                        elif key == 'data_type':
                            column['data_type'] = value
                        elif key == 'value_format':
                            # Clean up value format - remove markdown links
                            value = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', value)
                            if value and value != '<not specified>':
                                column['value_format'] = value

        # FOCUS 1.4 renamed this heading and started appending prose to the
        # version ("1.3 Introduced as a replacement for ..."), so match both
        # spellings and take only the version itself.
        version_match = re.search(
            r'^## (?:Introduced \(version\)|Version Introduced)\s*\n'
            r'\s*(\d+(?:\.\d+)*(?:-preview)?)',
            content,
            re.MULTILINE,
        )
        if version_match:
            column['introduced_version'] = version_match.group(1).strip()

        return column

    def parse_markdown_attribute(self, md_path: Path) -> Dict:
        """Parse an attribute markdown file.

        Args:
            md_path: Path to the markdown file

        Returns:
            Dictionary with attribute details
        """
        with open(md_path, 'r') as f:
            content = f.read()

        attribute = {}

        # Extract title (first # heading)
        title_match = re.search(r'^# (.+)$', content, re.MULTILINE)
        if title_match:
            attribute['name'] = title_match.group(1)
            attribute['attribute_id'] = title_match.group(1).lower().replace(' ', '_').replace('/', '_')

        # Extract Description section
        desc_match = re.search(r'^## Description\s*\n\s*(.+?)(?=\n##|$)', content, re.MULTILINE | re.DOTALL)
        if desc_match:
            attribute['description'] = ' '.join(desc_match.group(1).strip().split())

        # Extract Requirements section
        req_match = re.search(r'^## Requirements\s*\n\s*(.+?)(?=\n##|$)', content, re.MULTILINE | re.DOTALL)
        if req_match:
            req_text = req_match.group(1).strip()
            # Just add the entire requirements section as a single item
            # This preserves the full structure including nested bullets
            if req_text:
                attribute['requirements'] = [req_text]

        # FOCUS 1.4 renamed this heading and started appending prose to the
        # version ("1.3 Introduced as a replacement for ..."), so match both
        # spellings and take only the version itself.
        version_match = re.search(
            r'^## (?:Introduced \(version\)|Version Introduced)\s*\n'
            r'\s*(\d+(?:\.\d+)*(?:-preview)?)',
            content,
            re.MULTILINE,
        )
        if version_match:
            attribute['introduced_version'] = version_match.group(1).strip()

        return attribute

    def extract_all_columns(self) -> List[Dict]:
        """Extract all column definitions from markdown files.

        Returns:
            List of column dictionaries
        """
        columns_dir = self.repo_dir / "specification" / "datasets" / "cost_and_usage" / "columns"
        if not columns_dir.exists():
            raise FileNotFoundError(f"Columns directory not found: {columns_dir}")

        columns = []
        for md_file in sorted(columns_dir.glob("*.md")):
            if md_file.name != "columns.mdpp":  # Skip the template file
                print(f"  Processing column: {md_file.name}")
                column = self.parse_markdown_column(md_file)
                if column:
                    columns.append(column)

        return columns

    def extract_all_attributes(self) -> List[Dict]:
        """Extract all attribute definitions from markdown files.

        Returns:
            List of attribute dictionaries
        """
        attrs_dir = self.repo_dir / "specification" / "attributes"
        if not attrs_dir.exists():
            raise FileNotFoundError(f"Attributes directory not found: {attrs_dir}")

        attributes = []
        for md_file in sorted(attrs_dir.glob("*.md")):
            if md_file.name != "attributes.mdpp":  # Skip the template file
                print(f"  Processing attribute: {md_file.name}")
                attribute = self.parse_markdown_attribute(md_file)
                if attribute:
                    attributes.append(attribute)

        return attributes

    @staticmethod
    def _version_key(version: str):
        return parse(version.replace('-preview', 'a0'))

    def organize_by_version(self, items: List[Dict]) -> Dict[str, List[Dict]]:
        """Group items by the spec version they are first available in.

        Versions are taken from the data, so a new spec release needs no
        edit here.

        Args:
            items: List of columns or attributes with 'introduced_version'

        Returns:
            Dictionary mapping version to the items available by then
        """
        versions = sorted(
            {i.get('introduced_version', '') for i in items} - {''},
            key=self._version_key,
        )
        return {
            target: [
                i for i in items
                if i.get('introduced_version')
                and self._version_key(i['introduced_version'])
                <= self._version_key(target)
            ]
            for target in versions
        }

    def extract_and_cache(self) -> None:
        """Extract all specifications and cache them by version."""
        # Update repo first
        self.update_repo()

        print("\nExtracting columns from markdown files...")
        all_columns = self.extract_all_columns()
        print(f"Found {len(all_columns)} total columns")

        print("\nExtracting attributes from markdown files...")
        all_attributes = self.extract_all_attributes()
        print(f"Found {len(all_attributes)} total attributes")

        # Save ALL columns and attributes to single files
        # No need for version-specific files since we have introduced_version
        columns_file = self.cache_dir / "columns.yaml"
        with open(columns_file, 'w') as f:
            yaml.dump(all_columns, f, default_flow_style=False, sort_keys=False,
                     allow_unicode=True, width=1000)

        attributes_file = self.cache_dir / "attributes.yaml"
        with open(attributes_file, 'w') as f:
            yaml.dump(all_attributes, f, default_flow_style=False, sort_keys=False,
                     allow_unicode=True, width=1000)

        print("\nCached FOCUS specifications:")
        print(f"  - Total columns: {len(all_columns)}")
        print(f"  - Total attributes: {len(all_attributes)}")

        # Show version breakdown for info
        columns_by_version = self.organize_by_version(all_columns)
        for version, cols in columns_by_version.items():
            print(f"  - v{version}: {len(cols)} columns")


def main():
    """Main function to extract all FOCUS specifications from markdown."""
    extractor = FocusMarkdownExtractor()
    extractor.extract_and_cache()
    print("\n✅ FOCUS specifications extracted successfully from markdown sources!")


if __name__ == "__main__":
    main()