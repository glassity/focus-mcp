#!/usr/bin/env python3
"""
FOCUS Specification Markdown Extractor - Extracts FOCUS specs from markdown files.

This module clones the FOCUS repository and extracts column and attribute
definitions directly from the markdown source files. Much cleaner than HTML parsing!
"""

import re
import sys
import yaml
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
# The predicate and the ordering the server uses at runtime, not copies of
# them: a version boundary fixed in one place but not the other would let
# the cached YAML be computed under different semantics than it is served.
from focus_mcp.spec_loader import _available_at, _version_key  # noqa: E402

MARKDOWN_LINK = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

INTRODUCED_HEADING = re.compile(
    # FOCUS 1.4 renamed this heading and started appending prose to the
    # version ("1.3 Introduced as a replacement for ..."), so match both
    # spellings and take only the version itself.
    r'^## (?:Introduced \(version\)|Version Introduced)\s*\n'
    r'\s*(\d+(?:\.\d+)*(?:-preview)?)',
    re.MULTILINE,
)


def introduced_version(content: str) -> Optional[str]:
    match = INTRODUCED_HEADING.search(content)
    return match.group(1).strip() if match else None


def clean_links(text: str) -> str:
    """Replace markdown links with text an MCP client can actually use.

    Internal anchors (#glossary:..., #attributes...) only resolve inside
    the rendered specification, so just the text is kept; external URLs
    are real references and stay, in parentheses.
    """
    def repl(match):
        label, target = match.group(1), match.group(2)
        if target.startswith("http"):
            return f"{label} ({target})"
        return label

    return MARKDOWN_LINK.sub(repl, text)


def section(content: str, *titles: str) -> str:
    """The body of the first '## <title>' section that exists.

    Sections run to the next '## ' heading or end of file. This exists
    because a lazy regex with MULTILINE lets '$' match every line end,
    which silently truncates a section to its first line - how attribute
    requirements shipped as just their intro sentence.
    """
    for title in titles:
        match = re.search(
            rf'^## {re.escape(title)}\s*\n(.*?)(?=^## |\Z)',
            content,
            re.MULTILINE | re.DOTALL,
        )
        if match:
            return match.group(1).strip()
    return ""


def requirement_items(body: str) -> List[str]:
    """Requirement bullets as a list, nesting preserved inside each item.

    Shapes across tags: v1.0 states requirements as prose paragraphs;
    later versions use a boilerplate intro ("X MUST adhere to the
    following requirements:") followed by bullets, sometimes nested two
    levels deep. Top-level bullets and prose paragraphs each become one
    item; nested bullets stay inside their parent, since a sub-requirement
    is meaningless without it. The colon-terminated intro right before a
    bullet list carries no information and is dropped.
    """
    items: List[str] = []
    # A finished paragraph is held back rather than emitted, because
    # whether it matters depends on what follows: a colon-terminated
    # paragraph directly before a bullet is the list's intro and is
    # dropped; before anything else it is a requirement in its own right.
    pending: List[str] = []
    paragraph: List[str] = []
    # Top-level is relative to the list, not to column zero: a list may
    # sit indented under a prose intro, and its first bullet sets the
    # baseline the rest of that list is measured against.
    base: List[int] = []

    def close_paragraph():
        if paragraph:
            items.extend(pending)
            pending[:] = [clean_links(" ".join(paragraph))]
            paragraph.clear()
            base.clear()

    for raw in body.splitlines():
        stripped = raw.strip()
        if not stripped:
            close_paragraph()
            continue
        marker = re.match(r'([*-])\s+', stripped)
        if marker:
            close_paragraph()
            indent = len(raw) - len(raw.lstrip())
            text = clean_links(stripped[marker.end():].strip())
            if not base:
                base.append(indent)
            if indent <= base[0]:
                if not (pending and pending[-1].endswith(":")):
                    items.extend(pending)
                pending.clear()
                items.append(text)
            else:
                depth = max((indent - base[0]) // 2, 1)
                items[-1] += "\n" + "  " * (depth - 1) + "- " + text
            continue
        paragraph.append(stripped)
    close_paragraph()
    items.extend(pending)
    return items


def allowed_values(content: str) -> List[Dict[str, str]]:
    """The column's allowed-values table, if it declares one.

    Newer tags put the table under an '## Allowed Values' heading; through
    1.2 it sat inside Content Constraints behind an 'Allowed values:'
    paragraph. Both shapes are read so retired columns keep theirs.
    """
    body = section(content, "Allowed Values")
    if not body:
        match = re.search(
            r'^Allowed values:\s*\n(.*?)(?=^## |\Z)',
            content,
            re.MULTILINE | re.DOTALL,
        )
        body = match.group(1).strip() if match else ""

    values = []
    for line in body.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower() == "value" or set(cells[0]) <= set(":- "):
            continue
        values.append({
            "value": clean_links(cells[0]),
            "description": clean_links(cells[1]),
        })
    return values


class FocusMarkdownExtractor:
    """Extract column and attribute definitions from FOCUS markdown files."""

    REPO_URL = "https://github.com/FinOps-Open-Cost-and-Usage-Spec/FOCUS_Spec.git"

    # The specification deletes a column's file once it is retired rather
    # than keeping it marked, so reading only the newest tag loses every
    # column earlier versions still have - ProviderName and PublisherName,
    # for instance, vanish at 1.4. Each tag is read in turn and the results
    # unioned, which is also what tells us when a column disappeared.
    TAGS = ["v1.0", "v1.1", "v1.2", "v1.3", "v1.4"]

    # Anchored to this file, not the working directory: run from anywhere
    # else, a relative default would silently write the refreshed YAML to
    # a stray tree while the shipped resources stayed stale and green.
    DEFAULT_CACHE_DIR = (
        Path(__file__).resolve().parents[1]
        / "src" / "focus_mcp" / "resources" / "specifications"
    )

    def __init__(self, repo_dir: str = "/tmp/focus_repo",
                 cache_dir: "str | Path" = DEFAULT_CACHE_DIR):
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
        self._refuse_stale_tags()

    def _refuse_stale_tags(self) -> None:
        """Abort if the spec has released a version TAGS does not cover.

        Running against stale TAGS exits green while columns.yaml never
        learns the new version - and the fixtures would then build that
        version's table from the previous release's column list.
        """
        listed = subprocess.run(
            ["git", "tag", "-l", "v*"],
            cwd=self.repo_dir, check=True, capture_output=True, text=True,
        ).stdout.split()
        releases = [t for t in listed if re.fullmatch(r"v\d+\.\d+", t)]
        missing = sorted(
            (t for t in releases
             if t not in self.TAGS
             and _version_key(t.lstrip("v")) > _version_key(self.TAGS[-1].lstrip("v"))),
            key=lambda t: _version_key(t.lstrip("v")),
        )
        if missing:
            raise SystemExit(
                f"The FOCUS spec has released {', '.join(missing)} but TAGS "
                f"stops at {self.TAGS[-1]}. Add the new tag(s) to TAGS, "
                "re-run, and review what the new version changes."
            )

    def checkout(self, tag: str) -> None:
        subprocess.run(["git", "checkout", "--quiet", tag],
                       cwd=self.repo_dir, check=True)

    def merge_versions(self, per_tag: Dict[str, List[Dict]], id_field: str) -> List[Dict]:
        """Union definitions seen across tags, oldest tag first.

        The newest tag's file replaces the item wholesale, since later
        tags correct earlier wording and may deliberately drop a field -
        carrying old keys forward would serve retracted metadata as
        current. The one field kept across tags is introduced_version,
        because a later tag may stop declaring it. An item present in one
        tag and absent from the next was retired, and gets a
        removed_version so consumers can tell which versions still have
        it.
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
                if "removed_version" in existing:
                    # One [introduced, removed) interval cannot represent
                    # an availability gap, so this ships wrong metadata
                    # for the gap versions either way. Say so instead of
                    # silently pretending it was always present.
                    print(
                        f"  WARNING: {key} reappears in {tag} after being "
                        f"removed in {existing['removed_version']}; the gap "
                        "is not representable and is dropped"
                    )
                merged[key] = dict(item)
                introduced = (item.get("introduced_version")
                              or existing.get("introduced_version"))
                if introduced:
                    merged[key]["introduced_version"] = introduced
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
                    and _version_key(declared) < _version_key(appeared)):
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
        description = section(content, 'Description')
        if description:
            column['description'] = clean_links(' '.join(description.split()))

        values = allowed_values(content)
        if values:
            column['allowed_values'] = values

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
                            value = clean_links(value)
                            if value and value != '<not specified>':
                                column['value_format'] = value

        introduced = introduced_version(content)
        if introduced:
            column['introduced_version'] = introduced

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
        description = section(content, 'Description')
        if description:
            attribute['description'] = clean_links(' '.join(description.split()))

        # Extract Requirements section
        requirements = requirement_items(section(content, 'Requirements'))
        if requirements:
            attribute['requirements'] = requirements

        introduced = introduced_version(content)
        if introduced:
            attribute['introduced_version'] = introduced

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

    def organize_by_version(self, items: List[Dict]) -> Dict[str, List[Dict]]:
        """Group items by the spec version they are first available in.

        Versions are taken from the data, so a new spec release needs no
        edit here; availability comes from the same predicate the server
        uses at runtime.

        Args:
            items: List of columns or attributes with 'introduced_version'

        Returns:
            Dictionary mapping version to the items available by then
        """
        versions = sorted(
            {i.get('introduced_version', '') for i in items} - {''},
            key=_version_key,
        )
        return {
            target: [i for i in items if _available_at(i, target)]
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