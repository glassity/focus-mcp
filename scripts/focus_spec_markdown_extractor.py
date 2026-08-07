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

    # The specification deletes a column's file once it is retired rather
    # than keeping it marked, so reading only the newest tag loses every
    # column earlier versions still have - ProviderName and PublisherName,
    # for instance, vanish at 1.4. Each tag is read in turn and the results
    # unioned, which is also what tells us when a column disappeared.
    TAGS = ["v1.0", "v1.1", "v1.2", "v1.3", "v1.4"]

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
        """Clone or fetch the FOCUS repository, tags included."""
        if self.repo_dir.exists():
            print("Fetching FOCUS repository...")
            subprocess.run(["git", "fetch", "--tags", "--force"],
                           cwd=self.repo_dir, check=True)
        else:
            print("Cloning FOCUS repository...")
            subprocess.run(["git", "clone", self.REPO_URL, str(self.repo_dir)],
                           check=True)

    def checkout(self, tag: str) -> None:
        subprocess.run(["git", "checkout", "--quiet", tag],
                       cwd=self.repo_dir, check=True)

    def merge_versions(self, per_tag: Dict[str, List[Dict]], id_field: str) -> List[Dict]:
        """Union definitions seen across tags, oldest tag first.

        The newest definition of an item wins, since later tags correct
        earlier wording. An item present in one tag and absent from the
        next was retired, and gets a removed_version so consumers can tell
        which versions still have it.
        """
        merged: Dict[str, Dict] = {}
        first_seen: Dict[str, str] = {}
        earliest = self.TAGS[0].lstrip("v")
        for tag, items in per_tag.items():
            version = tag.lstrip("v")
            seen = set()
            for item in items:
                key = item.get(id_field)
                if not key:
                    continue
                seen.add(key)
                first_seen.setdefault(key, version)
                existing = merged.get(key, {})
                # A later tag may drop the introduced version from the file;
                # keep the earliest one we ever saw.
                introduced = existing.get("introduced_version") or item.get("introduced_version")
                merged[key] = {**existing, **item}
                if introduced:
                    merged[key]["introduced_version"] = introduced
                merged[key].pop("removed_version", None)
            for key, item in merged.items():
                if key not in seen and "removed_version" not in item:
                    item["removed_version"] = version

        # A renamed item keeps the original's introduced_version in its
        # markdown, which would claim it existed under a name no release
        # ever used. Where the ID only turns up in a later tag, that tag is
        # the real lower bound.
        for key, item in merged.items():
            appeared = first_seen[key]
            declared = item.get("introduced_version")
            if (appeared != earliest and declared
                    and self._version_key(declared) < self._version_key(appeared)):
                item["introduced_version"] = appeared
        return list(merged.values())

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
        # 1.3 split the specification into datasets; before that every
        # column lived in one directory. Only Cost and Usage is read either
        # way, since that is the single table focus_data_table exposes.
        candidates = [
            self.repo_dir / "specification" / "datasets" / "cost_and_usage" / "columns",
            self.repo_dir / "specification" / "columns",
        ]
        columns_dir = next((c for c in candidates if c.exists()), None)
        if columns_dir is None:
            raise FileNotFoundError(f"No columns directory among: {candidates}")

        columns = []
        for md_file in sorted(columns_dir.glob("*.md")):
            if not md_file.name.endswith(("_overview.md", ".mdpp")):
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
            # *_overview.md is the section index, not an attribute
            if not md_file.name.endswith(("_overview.md", ".mdpp")):
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
        def available_at(item, target):
            if not item.get('introduced_version'):
                return False
            if self._version_key(item['introduced_version']) > self._version_key(target):
                return False
            removed = item.get('removed_version')
            return not removed or self._version_key(removed) > self._version_key(target)

        return {
            target: [i for i in items if available_at(i, target)]
            for target in versions
        }

    def extract_and_cache(self) -> None:
        """Extract all specifications across tags and cache the union."""
        self.update_repo()

        columns_per_tag: Dict[str, List[Dict]] = {}
        attributes_per_tag: Dict[str, List[Dict]] = {}
        for tag in self.TAGS:
            print(f"\nReading {tag}...")
            self.checkout(tag)
            columns_per_tag[tag] = self.extract_all_columns()
            attributes_per_tag[tag] = self.extract_all_attributes()
            print(f"  {len(columns_per_tag[tag])} columns, "
                  f"{len(attributes_per_tag[tag])} attributes")

        all_columns = self.merge_versions(columns_per_tag, "column_id")
        all_attributes = self.merge_versions(attributes_per_tag, "attribute_id")
        print(f"\nUnion across {len(self.TAGS)} tags: {len(all_columns)} columns, "
              f"{len(all_attributes)} attributes")

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

        retired = [c["column_id"] for c in all_columns if c.get("removed_version")]
        if retired:
            print(f"  - retired along the way: {', '.join(sorted(retired))}")
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