"""The collections must stay honest about where they depart from upstream,
and consistent with each other where they should not differ.

Each FOCUS version is a directory of query files. Duplication across those
directories is deliberate, and it is only safe if a fix applied to one
version cannot silently miss another - which is what the drift check is
for. Execution tests cannot catch that: a semantic fix missing from one
folder still runs there, it just answers wrong.
"""

import re
from pathlib import Path

import pytest
import yaml

QUERIES = Path(__file__).resolve().parent.parent / "src" / "focus_mcp" / "resources" / "queries"
CURATED = QUERIES / "curated"
UPSTREAM = QUERIES / "upstream"

# Derived from the same tree the collections are read from. Taking it from
# the installed package instead would let these checks iterate empty
# directories and report green - the baselines are repo-only.
VERSIONS = sorted(p.name for p in CURATED.iterdir() if p.is_dir()) if CURATED.is_dir() else []

# Fields we own rather than mirror from upstream.
LOCAL_ONLY = {"fix_comment", "divergence_note"}

# Renames the specification declares, newest name first. Comparing across
# versions normalises these away: a column renamed by the spec is not a
# missed fix, and flagging it would bury the differences that are.
RENAMES = {"ServiceProviderName": "ProviderName"}


def read(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def collection(root: Path, version: str) -> dict[str, dict]:
    return {p.stem: read(p) for p in sorted((root / version).glob("*.yaml"))}


def mirrored(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if k not in LOCAL_ONLY}


def test_there_is_at_least_one_collection():
    assert VERSIONS, f"no curated collections under {CURATED}"


def test_every_collection_has_a_baseline_to_compare_against():
    missing = [v for v in VERSIONS if not (UPSTREAM / v).is_dir()]
    assert missing == [], (
        f"no upstream baseline under {UPSTREAM} for: {', '.join(missing)}"
    )


@pytest.mark.parametrize("version", VERSIONS)
def test_every_divergence_from_upstream_is_explained(version):
    curated, upstream = collection(CURATED, version), collection(UPSTREAM, version)
    unexplained = [
        key for key, entry in curated.items()
        if key in upstream
        and mirrored(entry) != mirrored(upstream[key])
        and not entry.get("fix_comment")
    ]
    assert unexplained == [], (
        f"FOCUS {version}: these queries differ from upstream with no "
        "fix_comment saying why: " + ", ".join(unexplained)
    )


@pytest.mark.parametrize("version", VERSIONS)
def test_every_explanation_still_describes_a_difference(version):
    curated, upstream = collection(CURATED, version), collection(UPSTREAM, version)
    stale = [
        key for key, entry in curated.items()
        if entry.get("fix_comment")
        and key in upstream
        and mirrored(entry) == mirrored(upstream[key])
    ]
    assert stale == [], (
        f"FOCUS {version}: these carry a fix_comment but no longer differ "
        "from upstream, so the fix has been made upstream and ours should "
        "be dropped: " + ", ".join(stale)
    )


@pytest.mark.parametrize("version", VERSIONS)
def test_every_curated_query_has_an_upstream_counterpart(version):
    curated, upstream = collection(CURATED, version), collection(UPSTREAM, version)
    orphans = sorted(set(curated) - set(upstream))
    assert orphans == [], (
        f"FOCUS {version}: no upstream baseline for {', '.join(orphans)}, so "
        "nothing checks whether our version still needs to differ"
    )


def normalised(sql: str) -> str:
    """SQL reduced to what a difference would have to change to matter.

    Declared renames and layout are normalised away: upstream reformats
    freely between versions, and drowning the real differences in those
    is how a check stops being read. Case is deliberately left alone,
    since it is significant inside string literals.
    """
    for current, former in RENAMES.items():
        sql = re.sub(rf"\b{current}\b", former, sql or "")
    return re.sub(r"\s+", " ", sql).strip()


def test_no_unacknowledged_drift_between_versions():
    """A query shared by two versions must not differ without saying so.

    Key sets legitimately differ between versions - a query arrives with
    the columns it needs, or retires when a column is removed - so only
    keys present in both are compared.
    """
    collections = {v: collection(CURATED, v) for v in VERSIONS}
    drift = []
    for older, newer in zip(VERSIONS, VERSIONS[1:]):
        shared = set(collections[older]) & set(collections[newer])
        for key in sorted(shared):
            a, b = collections[older][key], collections[newer][key]
            if normalised(a.get("sql")) == normalised(b.get("sql")):
                continue
            if a.get("divergence_note") or b.get("divergence_note"):
                continue
            drift.append(f"{key}: differs between {older} and {newer}")

    assert drift == [], (
        "unacknowledged differences between version collections - backport "
        "the fix, or add divergence_note to say the difference is "
        "deliberate:\n  " + "\n  ".join(drift)
    )


def test_every_divergence_note_still_describes_a_difference():
    """A note that no longer explains anything is an expired exemption.

    Without this, a note added for one version bump keeps that query out of
    the drift check forever, including for differences introduced later.
    """
    collections = {v: collection(CURATED, v) for v in VERSIONS}
    stale = []
    for version, entries in collections.items():
        for key, entry in entries.items():
            if not entry.get("divergence_note"):
                continue
            neighbours = [o for o in VERSIONS
                          if o != version and key in collections[o]]
            if neighbours and all(
                normalised(collections[o][key].get("sql"))
                == normalised(entry.get("sql")) for o in neighbours
            ):
                stale.append(f"{version}/{key}")
    assert stale == [], (
        "these carry a divergence_note but no longer differ from the other "
        "collections, so the exemption should be dropped: " + ", ".join(stale)
    )


@pytest.mark.parametrize("version", VERSIONS)
def test_every_query_keeps_its_attribution(version):
    curated = collection(CURATED, version)
    missing = [
        key for key, entry in curated.items()
        if not (entry.get("source_url") or "").startswith("https://focus.finops.org/")
    ]
    assert missing == [], (
        f"FOCUS {version}: the library is CC BY 4.0 and every query must "
        "keep its source link: " + ", ".join(missing)
    )


@pytest.mark.parametrize("version", VERSIONS)
def test_query_files_carry_no_version_field(version):
    # The directory is the version; a field would be a second source of
    # truth able to disagree with it.
    strays = [
        key for key, entry in collection(CURATED, version).items()
        if "focus_versions" in entry
    ]
    assert strays == [], f"FOCUS {version}: stray focus_versions in " + ", ".join(strays)
