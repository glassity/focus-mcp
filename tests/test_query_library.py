"""The library must stay honest about where it departs from upstream.

Every difference between focus_use_cases.yaml and the snapshot in
upstream/ is a deliberate correction, so each must carry a fix_comment -
and a fix_comment describing no difference means upstream has since made
that fix itself.
"""

import importlib.util
from pathlib import Path

import pytest
import yaml

QUERIES = Path(__file__).resolve().parent.parent / "src" / "focus_mcp" / "resources" / "queries"

# Fields we own rather than mirror from upstream. slug is among them: it
# is the identifier the MCP tools expose, so it stays stable even when
# upstream republishes a use case under a new one.
LOCAL_ONLY = {"fix_comment", "upstream", "slug"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def library():
    return load(QUERIES / "focus_use_cases.yaml")


@pytest.fixture(scope="module")
def snapshot():
    return load(QUERIES / "upstream" / "focus_use_cases.yaml")


def upstream_body(entry):
    return {k: v for k, v in entry.items() if k not in LOCAL_ONLY}


def test_every_divergence_from_upstream_is_explained(library, snapshot):
    unexplained = [
        key for key, entry in library.items()
        if key in snapshot
        and upstream_body(entry) != upstream_body(snapshot[key])
        and not entry.get("fix_comment")
    ]
    assert unexplained == [], (
        "these queries differ from the upstream snapshot with no "
        "fix_comment saying why: " + ", ".join(unexplained)
    )


def test_every_explanation_still_describes_a_difference(library, snapshot):
    stale = [
        key for key, entry in library.items()
        if entry.get("fix_comment")
        and key in snapshot
        and upstream_body(entry) == upstream_body(snapshot[key])
    ]
    assert stale == [], (
        "these queries carry a fix_comment but no longer differ from "
        "upstream, so the fix has been made upstream and ours should be "
        "dropped: " + ", ".join(stale)
    )


def test_library_and_snapshot_cover_the_same_queries(library, snapshot):
    assert set(library) == set(snapshot)


def test_every_query_keeps_its_attribution(library):
    missing = [k for k, e in library.items()
               if not (e.get("source_url") or "").startswith("https://focus.finops.org/")]
    assert missing == [], (
        "the library is CC BY 4.0 and every query must keep its source "
        "link: " + ", ".join(missing)
    )


# --- sync script behaviour that does not need the network ---

@pytest.fixture(scope="module")
def sync():
    path = Path(__file__).resolve().parent.parent / "scripts" / "sync_use_cases.py"
    spec = importlib.util.spec_from_file_location("sync_use_cases", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("slug, expected", [
    ("analyze-credit-memos", "analyze_credit_memos"),
    # a version bump republishes as a new post with a -N suffix
    ("analyze-credit-memos-2", "analyze_credit_memos"),
    ("report-costs-by-service-category-and-subcategory-2",
     "report_costs_by_service_category_and_subcategory"),
])
def test_key_ignores_the_wordpress_suffix(sync, slug, expected):
    assert sync.key_for(slug) == expected


def test_title_matching_survives_reslugging(sync):
    library = {"analyze_credit_memos": {"title": "Analyze credit memos"}}
    entry = {"slug": "analyze-credit-memos-2", "title": "Analyze credit memos"}
    assert sync.match_existing(entry, library) == "analyze_credit_memos"


def test_stored_upstream_slug_wins_over_title(sync):
    library = {
        "renamed": {"title": "Something else entirely",
                    "upstream": {"slug": "verify-accuracy-of-service-provider-invoices"}},
        "decoy": {"title": "Verify accuracy of service provider invoices"},
    }
    entry = {"slug": "verify-accuracy-of-service-provider-invoices",
             "title": "Verify accuracy of service provider invoices"}
    assert sync.match_existing(entry, library) == "renamed"


def test_ambiguous_titles_do_not_match(sync):
    library = {"a": {"title": "Same name"}, "b": {"title": "Same name"}}
    assert sync.match_existing({"slug": "x", "title": "Same name"}, library) is None


def test_newest_sql_variant_wins(sync):
    detail = {"related_queries": [
        {"sql_query": "SELECT 1", "focus_versions": ["v1-3"]},
        {"sql_query": "SELECT 2", "focus_versions": ["v1-4"]},
    ]}
    variant, count = sync.pick_query(detail)
    assert (variant["sql_query"], count) == ("SELECT 2", 2)


def test_use_case_without_sql_is_skipped(sync):
    assert sync.to_entry({"title": "x", "related_queries": []}) is None
